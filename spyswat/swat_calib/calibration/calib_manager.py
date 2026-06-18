# spyswat/calibration/manager.py
from typing import Dict, List, Optional, Tuple
import pandas as pd
import shutil, tempfile
import logging
from pathlib import Path

from spyswat.logger import Logger

logger = logging.getLogger(__name__)


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
            self.project.run()

            sim = self.project.Output.read_rch(
                columns=['RCH', 'MON', output_variable],
                reach_id=reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]
            return score

        except Exception as e:
            raise RuntimeError(f"Iteration failed: {e}") from e
        finally:
            # Always restore baseline so that relative-change methods ('r', 'a')
            # start from the original parameter values on the next iteration.
            self._restore_state()

    def _backup_state(self):
        if self._backup_dir is not None:
            self._restore_state()
        self._backup_dir = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        shutil.copytree(self.project.txinout.directory, self._backup_dir / "TxtInOut")

    def _restore_state(self):
        if self._backup_dir is None:
            return
        src = self._backup_dir / "TxtInOut"
        dst = self.project.txinout.directory
        shutil.rmtree(dst)
        shutil.copytree(src, dst)
        # Clean up temp dir immediately after restoring to avoid disk accumulation
        shutil.rmtree(self._backup_dir, ignore_errors=True)
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

                wf.run_parallel(
                    self.project.swat_exe.swat_exe_path,
                    param_sets=chunk,
                    log_queue=log_queue,
                )

                # ── read outputs ───────────────────────────────────────
                batch_scores = []
                for j, params in enumerate(chunk):
                    row = {}
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
                        row.update(scores)
                    except Exception as e:
                        logger.warning(f"[run_batch] Worker {j+1} read failed: {e}")
                        for m in metrics:
                            row[m] = float('-inf')
                    batch_scores.append(row)
                    all_rows.append(row)

                # ── progress: tqdm + logger ────────────────────────────
                done = chunk_start + len(chunk)
                score_summary = "  ".join(
                    f"{m}={row.get(m, float('-inf')):.3f}"
                    for m in metrics
                    for row in [batch_scores[-1]]   # last worker in chunk
                    if row.get(m) is not None
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
        return pd.DataFrame(all_rows)

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        inferred = pd.infer_freq(obs.index)
        freq = 'MS' if (inferred and inferred.upper().startswith(('M', 'Q', 'A', 'Y'))) else 'D'
        date_range = self.project.get_date_range(freq=freq)
        sim = sim.reset_index(drop=True)
        if len(sim) == len(date_range):
            sim.index = date_range
        common = obs.index.intersection(sim.index)
        return obs.loc[common], sim.loc[common]
