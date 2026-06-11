import shutil
import concurrent.futures
from pathlib import Path
from typing import Optional, Union, List

from spyswat.swat_calib.run import SWATRun
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.io import SWATParam
from spyswat.logger import Logger

Logger.init(log_dir="logs", log_file="run.log")
logger = Logger.get_logger(__name__)

class WorkingFolderManager:

    def __init__(self, txinout: TxInOut,
                       working_dir:  Union[str, Path],
                       n_parallel:   int = 1,
                       param_path:   Optional[Union[str, Path]] = None):
        self.txinout_dir  = txinout.directory
        self.working_dir  = Path(working_dir)
        self.n_parallel   = n_parallel
        self._param_path  = Path(param_path) if param_path else None
        self._worker_dirs: List[Path] = []


    def setup(self, overwrite: bool = False) -> List[Path]:
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self._worker_dirs = []

        for i in range(1, self.n_parallel + 1):
            dest = self.working_dir / f"TxInOut{i}"

            if dest.exists():
                if overwrite:
                    shutil.rmtree(dest)
                    logger.info(f"Removed existing worker dir: {dest}")
                else:
                    logger.info(f"Worker dir already exists (skip copy): {dest}")
                    self._worker_dirs.append(dest)
                    continue

            shutil.copytree(src=self.txinout_dir, dst=dest)
            logger.info(f"Created worker dir [{i}/{self.n_parallel}]: {dest}")
            self._worker_dirs.append(dest)

        return self._worker_dirs


    def run_parallel(self, swat_exe: Union[str, Path],
                           param_sets: Optional[List[dict]] = None) -> List[Path]:
        """
        Chạy SWAT song song trên các worker directories.
        param_sets có thể ít hơn n_parallel (chỉ chạy len(param_sets) workers).
        """
        if not self._worker_dirs:
            raise RuntimeError("Chưa gọi setup(). Hãy gọi setup() trước.")

        if param_sets and len(param_sets) > len(self._worker_dirs):
            raise ValueError(
                f"param_sets ({len(param_sets)}) vượt quá n_parallel ({self.n_parallel}). "
                f"Dùng run_batch() để xử lý tự động."
            )

        # Chỉ chạy đúng số worker cần thiết
        n = len(param_sets) if param_sets else len(self._worker_dirs)
        active_dirs = self._worker_dirs[:n]
        active_params = param_sets if param_sets else [None] * n
        tasks = list(zip(active_dirs, active_params))

        param_path_str = str(self._param_path) if self._param_path else None

        with concurrent.futures.ProcessPoolExecutor(max_workers=n) as executor:
            futures = {
                executor.submit(
                    self._run_single, worker_dir, str(swat_exe), params, param_path_str
                ): worker_dir
                for worker_dir, params in tasks
            }
            for future in concurrent.futures.as_completed(futures):
                worker_dir = futures[future]
                try:
                    future.result()
                    logger.info(f"Finished: {worker_dir.name}")
                except Exception as exc:
                    logger.error(f"FAILED {worker_dir.name}: {exc}")

        return active_dirs

    @staticmethod
    def _run_single(worker_dir: Path, swat_exe: str,
                    params: Optional[dict],
                    param_path: Optional[str] = None) -> None:
        """Ghi tham số (nếu có) và chạy SWAT trong worker_dir."""
        if params:
            txinout = TxInOut(str(worker_dir))
            hru_mgr = HRUManager(txinout, SWATParam(param_path))
            hru_mgr.update_params(params)

        SWATRun(swat_exe).run(str(worker_dir))

    def cleanup(self) -> None:
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir)
            logger.info(f"Cleaned up working dir: {self.working_dir}")

    @property
    def worker_dirs(self) -> List[Path]:
        return list(self._worker_dirs)