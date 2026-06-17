# spyswat/calibration/manager.py
from typing import Dict, List, Optional, Tuple
import pandas as pd
import shutil, tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CalibrationManager:
    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None
        # Set by algorithms before each run via _parse_spec
        self._methods:   Dict[str, str]  = {}
        self._subbasins: Dict[str, list] = {}

    # ── Unified param_ranges parser ──────────────────────────────────

    @staticmethod
    def _parse_spec(param_ranges: dict) -> Tuple[dict, dict, dict]:
        """
        Parse unified param_ranges into (bounds, methods, subbasins).

        Supported formats (can mix freely in same dict):
            "CN2.mgt": (60, 98)                        # old format — bounds only
            "CN2.mgt": ((60, 98), "r")                 # bounds + method
            "CN2.mgt": ((60, 98), "r", [71, 45, 70])  # bounds + method + subbasins
        """
        bounds, methods, subbasins = {}, {}, {}
        for name, spec in param_ranges.items():
            if isinstance(spec[0], (int, float)):
                # Old format: (min, max)
                bounds[name] = (float(spec[0]), float(spec[1]))
            else:
                # New format: ((min, max), method?, subbasins?)
                bounds[name] = (float(spec[0][0]), float(spec[0][1]))
                if len(spec) >= 2 and spec[1] is not None:
                    methods[name] = spec[1]
                if len(spec) >= 3 and spec[2] is not None:
                    subbasins[name] = spec[2]
        return bounds, methods, subbasins

    def _format_params(self, raw: dict) -> dict:
        """
        Convert {name: float} -> {name: [(val, method, [subs])]}.
        Uses self._methods and self._subbasins set by the calling algorithm.
        """
        out = {}
        for name, val in raw.items():
            method = self._methods.get(name, "v")
            subs   = self._subbasins.get(name)
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
                      reach_id=1, output_variable='FLOW_OUTcms') -> float:
        formatted = self._format_params(param_dict) if self._is_raw(param_dict) else param_dict
        self._backup_state()
        try:
            self.project.HRU.update_params(formatted)
            self.project.run()

            sim = self.project.Output.read_rch(
                columns=['RCH', 'MON', output_variable],
                reach_id=reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            return self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]

        except Exception as e:
            self._restore_state()
            raise RuntimeError(f"Iteration failed: {e}") from e

    def _backup_state(self):
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)
        self._backup_dir = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        shutil.copytree(self.project.txinout.directory, self._backup_dir / "TxtInOut")

    def _restore_state(self):
        if self._backup_dir is None:
            return
        src = self._backup_dir / "TxtInOut"
        dst = self.project.txinout.directory
        shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def setup_parallel(self, overwrite: bool = False) -> None:
        """Create worker directories for parallel execution."""
        self.project.WorkingFolder.setup(overwrite=overwrite)
        logger.info(
            f"Parallel setup: {self.project.WorkingFolder.n_parallel} workers tai "
            f"{self.project.WorkingFolder.working_dir}"
        )

    def run_batch(self, param_sets, observed, metrics=None,
                  reach_id=1, output_variable='FLOW_OUTcms') -> pd.DataFrame:
        """
        Return DataFrame. param_sets can be list of {name: float} (raw) or
        {name: [(val, method, ...)]} (pre-formatted) — both are accepted.
        """
        if metrics is None:
            metrics = ['nse', 'kge', 'r2', 'rmse', 'pbias']
        elif isinstance(metrics, str):
            metrics = [metrics]

        formatted_sets = [
            self._format_params(p) if self._is_raw(p) else p
            for p in param_sets
        ]

        try:
            from tqdm import tqdm
            pbar = tqdm(total=len(formatted_sets), desc="SWAT runs", unit="run")
        except ImportError:
            pbar = None

        all_rows = []
        wf = self.project.WorkingFolder
        n_workers = wf.n_parallel

        for chunk_start in range(0, len(formatted_sets), n_workers):
            chunk = formatted_sets[chunk_start: chunk_start + n_workers]
            wf.run_parallel(self.project.swat_exe.swat_exe_path, param_sets=chunk)

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
                    for m in metrics:
                        row[m] = float('-inf')
                all_rows.append(row)

            if pbar is not None:
                pbar.update(len(chunk))

        if pbar is not None:
            pbar.close()

        return pd.DataFrame(all_rows)

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)
        if len(sim) == len(date_range):
            sim.index = date_range
        common = obs.index.intersection(sim.index)
        return obs.loc[common], sim.loc[common]
