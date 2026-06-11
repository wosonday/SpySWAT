# spyswat/calibration/manager.py
from typing import Dict, List, Optional
import pandas as pd
import shutil, tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CalibrationManager:
    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None

    def run_iteration(self, param_dict, observed, metric=None,
                      reach_id=1, output_variable='FLOW_OUTcms') -> float:
        self._backup_state()
        try:
            # Using API of HRUManager
            self.project.HRU.update_params(param_dict)
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
        # Delete old backup
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)
        # Copy all TxtInOut into temp dir
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
            f"Parallel setup: {self.project.WorkingFolder.n_parallel} workers tại "
            f"{self.project.WorkingFolder.working_dir}"
        )

    def run_batch(self, param_sets, observed, metrics=None,
                  reach_id=1, output_variable='FLOW_OUTcms') -> pd.DataFrame:
        """
        Return DataFrame
        """
        if metrics is None:
            metrics = ['nse', 'kge', 'r2', 'rmse', 'pbias']
        elif isinstance(metrics, str):
            metrics = [metrics]

        all_rows = []
        wf = self.project.WorkingFolder
        n_workers = wf.n_parallel

        for chunk_start in range(0, len(param_sets), n_workers):
            chunk = param_sets[chunk_start: chunk_start + n_workers]
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

                    # Tính tất cả metric cùng lúc
                    scores = w_proj.Statistic.calculate_statistics(
                        obs_a, sim_a, metrics=metrics
                        )
                    row.update(scores)
                except Exception as e:
                    for m in metrics:
                        row[m] = float('-inf')
                all_rows.append(row)

        return pd.DataFrame(all_rows)

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        # Gắn date_range vào sim trước khi align
        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)
        if len(sim) == len(date_range):
            sim.index = date_range
        common = obs.index.intersection(sim.index)
        return obs.loc[common], sim.loc[common]