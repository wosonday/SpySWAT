# spyswat/calibration/manager.py
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import shutil, tempfile
import logging
from pathlib import Path

from spyswat.swat_calib.core.workingFolder_manager import (
    _copy_over, _stamp_output_rch, _check_fresh_output_rch, _param_exts, _baseline_files,
)

from spyswat.logger import Logger

logger = logging.getLogger(__name__)


def check_observation_step(obs_index: pd.DatetimeIndex, sim_freq: str) -> None:
    """
    Raise ValueError unless the observation step matches the simulation print step.

    Observations count as monthly when every timestamp is the first day of a month at
    midnight and no two timestamps fall in the same month; otherwise they count as
    daily (gaps are fine; pd.infer_freq is deliberately not used). A single observation
    is always accepted. Observations are never resampled: aggregate them to the model's
    print step (IPRINT in file.cio) before calibrating.
    """
    if sim_freq not in ('D', 'MS'):
        raise ValueError(
            f"Unsupported simulation frequency {sim_freq!r}: only daily ('D') and "
            f"monthly ('MS') print steps are supported."
        )
    idx = pd.DatetimeIndex(obs_index)
    if len(idx) <= 1:
        return
    monthly = bool(
        (idx.day == 1).all()
        and (idx == idx.normalize()).all()
        and not idx.to_period('M').duplicated().any()
    )
    if monthly and sim_freq == 'D':
        raise ValueError(
            "Observations are monthly but the simulation prints daily output (IPRINT in "
            "file.cio). Aggregate the observations to the model's print step first, or "
            "change IPRINT."
        )
    if not monthly and sim_freq == 'MS':
        raise ValueError(
            "Observations are daily but the simulation prints monthly output (IPRINT in "
            "file.cio). Aggregate the observations to the model's print step first "
            "(e.g. monthly means for flow), or change IPRINT."
        )


class CalibrationManager:
    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None

    # ── Unified param_ranges parser ──────────────────────────────────

    @staticmethod
    def _parse_spec(param_ranges: dict) -> Tuple[dict, dict, dict]:
        """
        Parse unified param_ranges into (bounds, methods, subbasins).

        Supported formats (can mix freely in same dict):
            "CN2.mgt": (60, 98)                        # old format -- bounds only
            "CN2.mgt": ((60, 98), "r")                 # bounds + method
            "CN2.mgt": ((60, 98), "r", [71, 45, 70])  # bounds + method + subbasins
        """
        bounds, methods, subbasins = {}, {}, {}
        for name, spec in param_ranges.items():
            if isinstance(spec[0], (int, float)):
                # Old format: (min, max)
                if len(spec) > 2:
                    raise ValueError(
                        f"Parameter '{name}': old format (min, max) accepts exactly 2 values, "
                        f"got {len(spec)}. Use new format: ((min, max), method, subbasins)."
                    )
                bounds[name] = (float(spec[0]), float(spec[1]))
            else:
                # New format: ((min, max), method?, subbasins?)
                bounds[name] = (float(spec[0][0]), float(spec[0][1]))
                if len(spec) >= 2 and spec[1] is not None:
                    methods[name] = spec[1]
                if len(spec) >= 3 and spec[2] is not None:
                    subbasins[name] = spec[2]
        return bounds, methods, subbasins

    def _format_params(self, raw: dict,
                       methods: dict = None, subbasins: dict = None) -> dict:
        """Convert {name: float} -> {name: [(val, method, [subs])]}."""
        _m = methods   or {}
        _s = subbasins or {}
        out = {}
        for name, val in raw.items():
            method = _m.get(name, "v")
            subs   = _s.get(name)
            out[name] = [(float(val), method, subs)] if subs is not None else [(float(val), method)]
        return out

    @staticmethod
    def _is_raw(param_dict: dict) -> bool:
        """True if {name: float}, False if already formatted {name: [tuple]}."""
        for v in param_dict.values():
            return isinstance(v, (int, float))
        return True

    # ── Core run methods ─────────────────────────────────────────────

    def run_iteration(self, param_dict, observed, metric=None,
                      reach_id=1, output_variable='FLOW_OUTcms',
                      methods=None, subbasins=None) -> float:
        formatted = self._format_params(param_dict, methods, subbasins) if self._is_raw(param_dict) else param_dict
        self._backup_state()
        try:
            self.project.HRU.update_params(formatted)

            out_dir = self._txinout_dir()
            before = _stamp_output_rch(out_dir) if out_dir is not None else None
            self.project.run()
            if out_dir is not None:
                _check_fresh_output_rch(out_dir, before)

            sim = self.project.Output.read_rch(
                columns=['RCH', 'MON', output_variable],
                reach_id=reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]
        except Exception as e:
            # Always restore baseline inputs so that relative-change methods ('r', 'a')
            # start from the original parameter values on the next iteration.
            try:
                self._restore_state()
            except Exception as restore_err:
                raise RuntimeError(
                    f"Iteration failed: {e}; additionally the input files could not be "
                    f"restored: {restore_err}"
                ) from e
            raise RuntimeError(f"Iteration failed: {e}") from e
        except BaseException:
            try:
                self._restore_state()
            except Exception as restore_err:
                logger.error(f"Restore after interruption failed: {restore_err}")
            raise
        self._restore_state()
        return score

    def _txinout_dir(self) -> Path | None:
        """The project's TxtInOut directory as a Path (None if it cannot be resolved)."""
        try:
            return Path(self.project.txinout.directory)
        except TypeError:
            return None

    def _input_files(self) -> List[Path]:
        """file.cio + every input file of all extensions in the parameter file."""
        tx = self.project.txinout
        directory = Path(tx.directory)
        files: List[Path] = []
        cio = directory / "file.cio"
        if cio.exists():
            files.append(cio)
        param_file = getattr(self.project, "param_file", None)
        if param_file is not None:
            exts = _param_exts(str(param_file.param_path))
            files.extend(_baseline_files(tx, exts))
        seen, out = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def _backup_state(self):
        """Back up only the input files that calibration can modify (never outputs)."""
        if self._backup_dir is not None:
            # A previous restore failed: finish it first, never overwrite that backup.
            try:
                self._restore_state()
            except RuntimeError as exc:
                raise RuntimeError(
                    f"Cannot take a new backup: the original input files are still kept "
                    f"unrestored in {self._backup_dir}. Close whatever locks the TxtInOut "
                    f"files, then retry (or copy that folder's files back by hand). {exc}"
                ) from exc
        backup = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        try:
            for f in self._input_files():
                shutil.copyfile(f, backup / f.name)
        except Exception:
            shutil.rmtree(backup, ignore_errors=True)
            raise
        self._backup_dir = backup

    def _restore_state(self):
        """
        Copy the backed-up input files back; the TxtInOut folder itself is never removed.

        The backup is deleted only after EVERY file was copied back. If any copy fails the
        backup is kept (its path is logged and named in the RuntimeError) so the next
        ``_backup_state`` / ``_restore_state`` can finish the job.
        """
        if self._backup_dir is None:
            return
        backup = self._backup_dir
        dst_dir = Path(self.project.txinout.directory)
        failed = []
        for f in sorted(backup.iterdir()):
            try:
                _copy_over(f, dst_dir / f.name)
            except Exception as exc:
                failed.append((f.name, exc))
        if failed:
            logger.error(
                f"Could not restore {len(failed)} input file(s) ({failed[0][0]}: "
                f"{failed[0][1]}); backup kept in {backup}"
            )
            raise RuntimeError(
                f"Could not restore {len(failed)} input file(s) in {dst_dir} "
                f"(first: {failed[0][0]}: {failed[0][1]}). The backup is kept in {backup}."
            ) from failed[0][1]
        shutil.rmtree(backup, ignore_errors=True)
        self._backup_dir = None

    def setup_parallel(self, overwrite: bool = False) -> None:
        """Create worker directories for parallel execution."""
        self.project.WorkingFolder.setup(overwrite=overwrite)
        logger.info(
            f"Parallel setup: {self.project.WorkingFolder.n_parallel} workers at "
            f"{self.project.WorkingFolder.working_dir}"
        )

    def run_batch(self, param_sets, observed, metrics=None,
                  reach_id=1, output_variable='FLOW_OUTcms',
                  methods=None, subbasins=None) -> pd.DataFrame:
        """
        Return DataFrame. param_sets can be list of {name: float} (raw) or
        {name: [(val, method, ...)]} (pre-formatted) -- both are accepted.

        Logging
        ───────
        Progress is written to both tqdm (visual) and logger.info (file/console)
        at every chunk boundary so runs are inspectable in the log file.

        Worker log records are routed through a multiprocessing.Queue so
        multiple subprocesses never write to the log file simultaneously.
        """
        if metrics is None:
            metrics = ['nse', 'kge', 'r2', 'rmse', 'pbias']
        elif isinstance(metrics, str):
            metrics = [metrics]

        formatted_sets = [
            self._format_params(p, methods, subbasins) if self._is_raw(p) else p
            for p in param_sets
        ]

        total       = len(formatted_sets)
        wf          = self.project.WorkingFolder
        n_workers   = wf.n_parallel
        total_batches = (total + n_workers - 1) // n_workers

        try:
            from tqdm import tqdm
            pbar = tqdm(total=total, desc="SWAT runs", unit="run")
        except ImportError:
            pbar = None

        # ── start queue listener so workers log through the queue ──────
        log_queue = Logger.init_queue_listener()
        logger.info(
            f"[run_batch] Starting — {total} runs, "
            f"{n_workers} workers, {total_batches} batches"
        )

        all_rows = []
        try:
            for chunk_start in range(0, total, n_workers):
                batch_num = chunk_start // n_workers + 1
                chunk     = formatted_sets[chunk_start: chunk_start + n_workers]

                results = wf.run_parallel(
                    self.project.swat_exe.swat_exe_path,
                    param_sets=chunk,
                    log_queue=log_queue,
                )

                # ── read outputs (rows stay in input order) ────────────
                batch_scores = []
                for j, res in enumerate(results):
                    row = {m: np.nan for m in metrics}
                    if not res.ok:
                        logger.error(f"[run_batch] Run {chunk_start + j + 1} failed "
                                     f"(worker {j+1}): {res.error}")
                    else:
                        try:
                            w_proj = self.project.worker(j + 1)
                            sim = w_proj.Output.read_rch(
                                columns=['RCH', 'MON', output_variable],
                                reach_id=reach_id
                            )[output_variable]
                            obs_a, sim_a = self._align_series(observed, sim)
                            scores = w_proj.Statistic.calculate_statistics(
                                obs_a, sim_a, metrics=metrics
                            )
                            for m in metrics:
                                row[m] = scores.get(m, np.nan)
                        except Exception as e:
                            logger.warning(
                                f"[run_batch] Run {chunk_start + j + 1} (worker {j+1}) "
                                f"output unreadable: {e}"
                            )
                    batch_scores.append(row)
                    all_rows.append(row)

                # ── progress: tqdm + logger ────────────────────────────
                done = chunk_start + len(chunk)
                last = batch_scores[-1] if batch_scores else {}
                score_summary = "  ".join(
                    f"{m}={last[m]:.3f}" for m in metrics if m in last
                )
                logger.info(
                    f"[Batch {batch_num}/{total_batches}] "
                    f"{done}/{total} runs ({done/total:.0%})  |  {score_summary}"
                )
                if pbar is not None:
                    pbar.update(len(chunk))

        finally:
            if pbar is not None:
                pbar.close()
            Logger.stop_listener()

        logger.info(f"[run_batch] Done — {total} runs complete")
        return pd.DataFrame(all_rows, columns=metrics)

    _FREQ_LEVEL = {'D': 0, 'MS': 1, 'YS': 2}  # IPRINT values accepted from file.cio

    def _sim_freq(self, obs: pd.Series | None = None) -> str:
        """Simulation output frequency from IPRINT in file.cio (contract C4)."""
        freq = self.project.FileCIO.get_iprint()
        if not isinstance(freq, str):
            # Duck-typed / mocked project without a real FileCIO: infer from the observations.
            inferred = pd.infer_freq(obs.index) if obs is not None and len(obs) >= 3 else None
            return 'MS' if (inferred and inferred.upper().startswith(('M', 'Q', 'A', 'Y'))) else 'D'
        if freq not in self._FREQ_LEVEL:
            raise ValueError(f"Unsupported simulation frequency {freq!r} from file.cio")
        return freq

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        """
        Give ``sim`` the simulation date index and intersect it with ``obs``.

        The simulation frequency comes from IPRINT in file.cio. Raises ValueError
        when the simulated length does not match the simulation period (partial-year
        runs via IDAF/IDAL are not supported), when the observation step differs from
        the simulation step (see ``check_observation_step``), or when there is no
        common date.
        """
        freq = self._sim_freq(obs)
        check_observation_step(obs.index, freq)
        date_range = self.project.get_date_range(freq=freq)
        sim = sim.reset_index(drop=True)
        if len(sim) != len(date_range):
            raise ValueError(
                f"Simulated series has {len(sim)} values but the simulation period "
                f"(file.cio, freq={freq}) has {len(date_range)} expected values. "
                f"Partial-year runs (IDAF/IDAL) are not supported."
            )
        sim.index = date_range

        common = obs.index.intersection(sim.index)
        if len(common) == 0:
            raise ValueError(
                f"No common dates between observations "
                f"({obs.index.min()} .. {obs.index.max()}) and simulation "
                f"({sim.index.min()} .. {sim.index.max()})."
            )
        return obs.loc[common], sim.loc[common]
