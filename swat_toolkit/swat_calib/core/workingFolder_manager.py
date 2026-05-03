import shutil
import concurrent.futures
from pathlib import Path
from typing import Optional, Union, List

from swat_toolkit.swat_calib.run import SWATRun
from swat_toolkit.swat_calib.core import TxInOut, HRUManager
from swat_toolkit.swat_calib.io import SWATParam
from swat_toolkit.logger import Logger

Logger.init(log_dir="logs", log_file="run.log")
logger = Logger.get_logger(__name__)

class WorkingFolderManager:

    def __init__(self, txinout: TxInOut,
                       working_dir:  Union[str, Path],
                       n_parallel:   int = 1):
        self.txinout_dir = txinout.directory
        self.working_dir = Path(working_dir)
        self.n_parallel  = n_parallel
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

        if not self._worker_dirs:
            raise RuntimeError("Haven't call setup(). Call setup() first.")

        if param_sets and len(param_sets) != len(self._worker_dirs):
            raise ValueError(
                f"param_sets ({len(param_sets)}) phải bằng n_parallel ({self.n_parallel})"
            )

        tasks = list(zip(self._worker_dirs,
                         param_sets if param_sets else [None] * self.n_parallel))

        with concurrent.futures.ProcessPoolExecutor(max_workers=self.n_parallel) as executor:
            futures = {
                executor.submit(self._run_single, worker_dir, str(swat_exe), params): worker_dir
                for worker_dir, params in tasks
            }
            for future in concurrent.futures.as_completed(futures):
                worker_dir = futures[future]
                try:
                    future.result()
                    logger.info(f"Finished: {worker_dir.name}")
                except Exception as exc:
                    logger.error(f"FAILED {worker_dir.name}: {exc}")

        return self._worker_dirs

    @staticmethod
    def _run_single(worker_dir: Path, swat_exe: str,
                    params: Optional[dict]) -> None:

        if params:
            txinout    = TxInOut(str(worker_dir))
            hru_mgr    = HRUManager(txinout, SWATParam())
            hru_mgr.update_params(params)                        # ghi tham số vào worker dir

        SWATRun(swat_exe).run(str(worker_dir))

    def cleanup(self) -> None:
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir)
            logger.info(f"Cleaned up working dir: {self.working_dir}")

    @property
    def worker_dirs(self) -> List[Path]:
        return list(self._worker_dirs)