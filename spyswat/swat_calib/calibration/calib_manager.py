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

    def run_iteration(self, param_dict, observed, metric='nse',
                      reach_id=1, output_variable='FLOW_OUTcms') -> float:
        self._backup_state()
        try:
            # Dùng đúng API hiện có của HRUManager
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
        """Tạo worker directories cho parallel execution. Gọi một lần trước khi run_batch."""
        self.project.WorkingFolder.setup(overwrite=overwrite)
        logger.info(
            f"Parallel setup: {self.project.WorkingFolder.n_parallel} workers tại "
            f"{self.project.WorkingFolder.working_dir}"
        )

    def run_batch(
        self,
        param_sets: List[dict],
        observed: pd.Series,
        metric: str = 'nse',
        reach_id: int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> List[float]:
        """
        Chạy N bộ tham số song song, trả về N scores.

        Tự động chia param_sets thành các chunk theo n_parallel.
        Không cần backup/restore vì mỗi worker dùng thư mục riêng.

        Args:
            param_sets: Danh sách dict tham số, format: {'CN2': [(75.0, 'v')], ...}
            observed:   Series quan trắc (index là DatetimeIndex)
            metric:     'nse' | 'kge' | 'r2' | 'rmse' | 'pbias'
            reach_id:   ID reach cần đọc
            output_variable: Biến output SWAT

        Returns:
            Danh sách scores, cùng thứ tự với param_sets
        """
        wf = self.project.WorkingFolder
        if not wf.worker_dirs:
            self.setup_parallel(overwrite=False)

        n_workers = wf.n_parallel
        all_scores: List[float] = []
        bad_score = float('-inf') if metric in ('nse', 'kge', 'r2') else float('inf')

        for chunk_start in range(0, len(param_sets), n_workers):
            chunk = param_sets[chunk_start: chunk_start + n_workers]
            logger.info(
                f"Batch [{chunk_start + 1}–{chunk_start + len(chunk)}] / {len(param_sets)}"
            )

            # Chạy SWAT song song cho chunk này
            wf.run_parallel(self.project.swat_exe.swat_exe_path, param_sets=chunk)

            # Đọc output + tính score từng worker
            for j in range(len(chunk)):
                try:
                    w_proj = self.project.worker(j + 1)
                    sim = w_proj.Output.read_rch(
                        columns=['RCH', 'MON', output_variable],
                        reach_id=reach_id
                    )[output_variable]
                    obs_a, sim_a = self._align_series(observed, sim)
                    score = w_proj.Statistic.calculate_statistics(
                        obs_a, sim_a, metrics=[metric]
                    )[metric]
                except Exception as e:
                    logger.warning(f"Worker {j + 1} failed: {e}")
                    score = bad_score
                all_scores.append(score)

        return all_scores

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        # Gắn date_range vào sim trước khi align
        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)
        if len(sim) == len(date_range):
            sim.index = date_range
        common = obs.index.intersection(sim.index)
        return obs.loc[common], sim.loc[common]