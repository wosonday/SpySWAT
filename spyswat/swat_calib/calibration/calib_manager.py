# spyswat/calibration/manager.py
from typing import List
import pandas as pd
import numpy as np
from contextlib import contextmanager
import shutil, tempfile
import logging
from pathlib import Path

from spyswat.swat_calib.core.workingFolder_manager import (
    _copy_over, _stamp_output_rch, _check_fresh_output_rch, _param_exts, _baseline_files,
)

from spyswat.logger import Logger
from .param_spec import parse_spec, format_params, is_raw, param_columns
from .run_log import RunLog

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
    if (not monthly and sim_freq == 'MS' and bool(idx.is_month_end.all())
            and not idx.to_period('M').duplicated().any()):
        raise ValueError(
            "Observations look monthly but are dated at the END of each month (pandas "
            "resample('M') default). Monthly observations must be dated on the 1st of the "
            "month: use obs.index = obs.index.to_period('M').to_timestamp()."
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
        self._log = RunLog(project)

    # Compatibility for callers that set session state to simulate name races.

    @property
    def _session_base(self):
        return self._log._session_base

    @_session_base.setter
    def _session_base(self, value):
        self._log._session_base = value

    @property
    def _session_id(self):
        return self._log._session_id

    @_session_id.setter
    def _session_id(self, value):
        self._log._session_id = value

    @property
    def _session_dir(self):
        return self._log._session_dir

    @_session_dir.setter
    def _session_dir(self, value):
        self._log._session_dir = value

    @property
    def _session_claimed(self):
        return self._log._session_claimed

    @_session_claimed.setter
    def _session_claimed(self, value):
        self._log._session_claimed = value

    @property
    def _session_n(self):
        return self._log._session_n

    @_session_n.setter
    def _session_n(self, value):
        self._log._session_n = value

    # ── Per-run result log delegates ─────────────────────────────────

    def _warn_once(self, key, message: str) -> None:
        self._log._warn_once(key, message)

    @property
    def log_outputs(self) -> str:
        """What goes to <session>_outputs.csv: 'all' | 'observed' | 'none'."""
        return self._log.log_outputs

    @log_outputs.setter
    def log_outputs(self, value: str) -> None:
        self._log.log_outputs = value

    @property
    def results_dir(self) -> Path | None:
        """Folder of the per-run result files (None disables logging)."""
        return self._log.results_dir

    @results_dir.setter
    def results_dir(self, value) -> None:
        self._log.results_dir = value

    def session_path(self, suffix: str) -> Path | None:
        """Path ``<results_dir>/<session>_<suffix>.csv`` that will be used (nothing is created)."""
        return self._log.session_path(suffix)

    @property
    def session_files(self) -> dict:
        """{'metrics': Path, 'outputs': Path} of the current session ({} when disabled)."""
        return self._log.session_files

    def _append_csv(self, path: Path, header: list, rows: list) -> bool:
        return self._log._append_csv(path, header, rows)

    def flush_log(self) -> bool:
        """Try to write rows buffered while a log file was locked. True if nothing is left."""
        return self._log.flush_log()

    @staticmethod
    def _fmt(v):
        return RunLog._fmt(v)

    @staticmethod
    def _g(v):
        return RunLog._g(v)

    def _logged_metric_names(self) -> List[str] | None:
        return self._log._logged_metric_names()

    def record_run(self, params: dict, scores: dict | None, *, status: str = "ok",
                   error: str | None = None, sim: "pd.Series | None" = None,
                   mode: str = "sequential", reach_id=None,
                   output_variable: str | None = None) -> None:
        """
        Append one run to the per-run log. Public hook for algorithms that run SWAT
        outside run_iteration/run_batch (GLUE uncertainty runs, sensitivity analysis).

        Args:
            params: raw {name: float} or formatted {name: [(value, method[, subs]), ...]}.
            scores: {metric: value} (None for a failed run: NaN in the metric columns).
            sim:    simulated target series already indexed by date (None = no output rows;
                    only written for status 'ok').
        A change of the parameter/metric column set starts a new session. Never raises.
        """
        self._log._record_run(params, scores, status=status, error=error, sim=sim, mode=mode,
                              reach_id=reach_id, output_variable=output_variable)

    def _record_run(self, params, scores, *, status="ok", error=None, sim=None,
                    mode="sequential", reach_id=None, output_variable=None,
                    obs_index=None) -> None:
        self._log._record_run(params, scores, status=status, error=error, sim=sim, mode=mode,
                              reach_id=reach_id, output_variable=output_variable,
                              obs_index=obs_index)

    # ── Unified param_ranges parser ──────────────────────────────────

    _parse_spec = staticmethod(parse_spec)
    _param_columns = staticmethod(param_columns)

    def _format_params(self, raw: dict,
                       methods: dict = None, subbasins: dict = None) -> dict:
        """Convert {name: float} -> {name: [(val, method, [subs])]}."""
        return format_params(raw, methods, subbasins)

    _is_raw = staticmethod(is_raw)

    # ── Core run methods ─────────────────────────────────────────────

    def run_once(self, params: dict, *, reach_id: int = 1,
                 output_variable: str = 'FLOW_OUTcms',
                 methods=None, subbasins=None) -> pd.Series:
        """
        Apply ``params`` to the project's TxtInOut, run SWAT once and return the raw
        simulated series of ``output_variable`` at ``reach_id``.

        The single implementation of the sequential run: every sequential caller
        (run_iteration, sensitivity, GLUE 95PPU, ValidationRunner) goes through it.
        ``params`` is formatted ({name: [(value, method, ...)]}) or raw ({name: value},
        formatted with ``methods`` / ``subbasins``, default absolute 'v').

        Nothing is backed up: wrap the call in ``with manager.sandbox(...)`` unless the
        change must stay. Raises StaleOutputError (a RuntimeError) when SWAT did not
        write a fresh output.rch, so an old result is never read as this run's result.
        """
        formatted = (self._format_params(params, methods, subbasins)
                     if self._is_raw(params) else params)
        self.project.HRU.update_params(formatted)
        out_dir = self._txinout_dir()
        before = _stamp_output_rch(out_dir) if out_dir is not None else None
        self.project.run()
        if out_dir is not None:
            _check_fresh_output_rch(out_dir, before)
        return self.project.Output.read_rch(
            columns=['RCH', 'MON', output_variable], reach_id=reach_id
        )[output_variable]

    @contextmanager
    def sandbox(self, names=None):
        """
        Back up the input files that ``names`` ('name.ext' keys; None = every parameter
        extension) can change, and restore them when the block exits -- normally, on an
        exception or on KeyboardInterrupt. Outputs are never touched.

            with manager.sandbox(names=["CN2.mgt"]):
                sim = manager.run_once({"CN2.mgt": 60.0})
        """
        if names is None:
            self._backup_state()
        else:
            self._backup_state(names=list(names))
        try:
            yield self
        finally:
            self._restore_state()

    def run_iteration(self, param_dict, observed, metric=None,
                      reach_id=1, output_variable='FLOW_OUTcms',
                      methods=None, subbasins=None) -> float:
        formatted = self._format_params(param_dict, methods, subbasins) if self._is_raw(param_dict) else param_dict
        # Resolved before the backup: nothing between backup and restore may raise.
        obs_index = observed.index if isinstance(observed, pd.Series) else None
        self._backup_state(names=formatted.keys())
        err: Exception | None = None
        score = None
        sim_dated = None
        try:
            sim = self.run_once(formatted, reach_id=reach_id, output_variable=output_variable)

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]
            if self.results_dir is not None:
                sim_dated = self._to_model_dates(sim, self._sim_freq(observed))
        except Exception as e:
            err = e
        except BaseException:
            try:
                self._restore_state()
            except Exception as restore_err:
                logger.error(f"Restore after interruption failed: {restore_err}")
            raise

        # Save this run before anything else can go wrong (restore, next run).
        self._record_run(formatted,
                         {metric: np.nan} if err is not None else {metric: score},
                         status="failed" if err is not None else "ok", error=err,
                         sim=sim_dated, mode="sequential", reach_id=reach_id,
                         output_variable=output_variable, obs_index=obs_index)

        # Always restore baseline inputs so that relative-change methods ('r', 'a')
        # start from the original parameter values on the next iteration.
        try:
            self._restore_state()
        except Exception as restore_err:
            if err is not None:
                raise RuntimeError(
                    f"Iteration failed: {err}; additionally the input files could not be "
                    f"restored: {restore_err}"
                ) from err
            raise
        if err is not None:
            raise RuntimeError(f"Iteration failed: {err}") from err
        return score

    def _txinout_dir(self) -> Path | None:
        """The project's TxtInOut directory as a Path (None if it cannot be resolved)."""
        try:
            return Path(self.project.txinout.directory)
        except TypeError:
            return None

    def _input_files(self, names=None) -> List[Path]:
        """
        file.cio + the input files of the extensions that ``names`` ('name.ext' keys) can
        modify; every extension in the parameter file when ``names`` is None.
        """
        tx = self.project.txinout
        directory = Path(tx.directory)
        files: List[Path] = []
        cio = directory / "file.cio"
        if cio.exists():
            files.append(cio)
        param_file = getattr(self.project, "param_file", None)
        if param_file is not None:
            exts = _param_exts(str(param_file.param_path),
                               None if names is None else list(names))
            files.extend(_baseline_files(tx, exts))
        seen, out = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def _backup_state(self, names=None):
        """
        Back up only the input files that calibration can modify (never outputs).

        ``names``: the 'name.ext' keys about to be changed; only their extensions (plus
        file.cio) are copied. None backs up every extension in the parameter file.
        """
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
            for f in self._input_files(names):
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
                    run_error = None
                    sim_dated = None
                    if not res.ok:
                        run_error = res.error
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
                            if self.results_dir is not None:
                                sim_dated = self._to_model_dates(sim, self._sim_freq(observed))
                        except Exception as e:
                            run_error = f"output unreadable: {e}"
                            row = {m: np.nan for m in metrics}
                            logger.warning(
                                f"[run_batch] Run {chunk_start + j + 1} (worker {j+1}) "
                                f"output unreadable: {e}"
                            )
                    batch_scores.append(row)
                    all_rows.append(row)
                    # save every run immediately (before the next job/batch)
                    self._record_run(chunk[j], row, status="ok" if run_error is None else "failed",
                                     error=run_error, sim=sim_dated, mode="parallel",
                                     reach_id=reach_id, output_variable=output_variable,
                                     obs_index=observed.index)

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
            self.flush_log()

        logger.info(f"[run_batch] Done — {total} runs complete")
        return pd.DataFrame(all_rows, columns=metrics)

    _FREQ_LEVEL = {'D': 0, 'MS': 1, 'YS': 2}  # IPRINT values accepted from file.cio

    def _sim_freq(self, obs: pd.Series | None = None) -> str:
        """Simulation output frequency from IPRINT in file.cio (contract C4)."""
        # Never inferred from the observations (design rule 6); mocks must stub get_iprint().
        freq = self.project.FileCIO.get_iprint()
        if not isinstance(freq, str) or freq not in self._FREQ_LEVEL:
            raise ValueError(f"Unsupported simulation frequency {freq!r} from file.cio")
        return freq

    def _to_model_dates(self, sim: pd.Series, freq: str) -> pd.Series:
        """Return ``sim`` indexed by the model's own date range (ValueError on length mismatch)."""
        date_range = self.project.get_date_range(freq=freq)
        sim = sim.reset_index(drop=True)
        if len(sim) != len(date_range):
            raise ValueError(
                f"Simulated series has {len(sim)} values but the simulation period "
                f"(file.cio, freq={freq}) has {len(date_range)} expected values. "
                f"Partial-year runs (IDAF/IDAL) are not supported."
            )
        sim.index = date_range
        return sim

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
        sim = self._to_model_dates(sim, freq)

        common = obs.index.intersection(sim.index)
        if len(common) == 0:
            raise ValueError(
                f"No common dates between observations "
                f"({obs.index.min()} .. {obs.index.max()}) and simulation "
                f"({sim.index.min()} .. {sim.index.max()})."
            )
        return obs.loc[common], sim.loc[common]
