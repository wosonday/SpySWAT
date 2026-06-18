import os
import stat
import shutil
import time
import concurrent.futures
from pathlib import Path
from typing import Optional, Union, List

from spyswat.swat_calib.run import SWATRun
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.io import SWATParam
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)


def _force_remove(func, path, _):
    """onexc handler: unlock read-only files before retry (Windows PermissionError)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass  # best-effort; rmtree continues with remaining files


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

    # ------------------------------------------------------------------

    def setup(self, overwrite: bool = False) -> List[Path]:
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self._worker_dirs = []

        logger.info(f"[Setup] Preparing {self.n_parallel} worker dirs in {self.working_dir}")
        t0 = time.perf_counter()

        for i in range(1, self.n_parallel + 1):
            dest = self.working_dir / f"TxInOut{i}"

            if dest.exists():
                if overwrite:
                    shutil.rmtree(dest, onexc=_force_remove)
                    logger.info(f"[Setup] [{i}/{self.n_parallel}] Removed & rebuilding: {dest.name}")
                else:
                    logger.info(f"[Setup] [{i}/{self.n_parallel}] Already exists (skip): {dest.name}")
                    self._worker_dirs.append(dest)
                    continue

            shutil.copytree(src=self.txinout_dir, dst=dest)
            logger.info(f"[Setup] [{i}/{self.n_parallel}] Created: {dest.name}")
            self._worker_dirs.append(dest)

        elapsed = time.perf_counter() - t0
        logger.info(f"[Setup] Done — {len(self._worker_dirs)} workers ready ({elapsed:.1f}s)")
        return self._worker_dirs

    # ------------------------------------------------------------------

    def run_parallel(self, swat_exe: Union[str, Path],
                           param_sets: Optional[List[dict]] = None,
                           log_queue=None) -> List[Path]:
        """
        Run SWAT in parallel across worker directories.

        param_sets may be smaller than n_parallel (only len(param_sets) workers are used).

        Args:
            swat_exe:   Path to the SWAT executable.
            param_sets: List of formatted param dicts, one per worker.
            log_queue:  multiprocessing.Queue from Logger.init_queue_listener().
                        When provided, worker processes route their log records
                        through this queue instead of writing directly to the
                        log file (prevents concurrent write corruption).
        """
        if not self._worker_dirs:
            raise RuntimeError("Worker dirs not initialised. Call setup() first.")

        if param_sets and len(param_sets) > len(self._worker_dirs):
            raise ValueError(
                f"param_sets ({len(param_sets)}) exceeds n_parallel ({self.n_parallel}). "
                f"Use run_batch() to handle chunking automatically."
            )

        n = len(param_sets) if param_sets else len(self._worker_dirs)
        active_dirs   = self._worker_dirs[:n]
        active_params = param_sets if param_sets else [None] * n
        tasks = list(zip(active_dirs, active_params))

        param_path_str = str(self._param_path) if self._param_path else None

        logger.info(f"[Parallel] Starting {n} workers ...")
        t_batch = time.perf_counter()
        done_count = 0

        with concurrent.futures.ProcessPoolExecutor(max_workers=n) as executor:
            future_to_info = {
                executor.submit(
                    self._run_single_timed,
                    worker_dir, str(swat_exe), params, param_path_str, log_queue
                ): worker_dir
                for worker_dir, params in tasks
            }
            for future in concurrent.futures.as_completed(future_to_info):
                worker_dir = future_to_info[future]
                done_count += 1
                try:
                    elapsed_w = future.result()
                    logger.info(
                        f"[Parallel] [{done_count}/{n}] {worker_dir.name} OK "
                        f"({elapsed_w:.1f}s)"
                    )
                except Exception as exc:
                    logger.error(
                        f"[Parallel] [{done_count}/{n}] {worker_dir.name} FAILED: {exc}"
                    )

        total = time.perf_counter() - t_batch
        logger.info(f"[Parallel] Batch done — {n} workers in {total:.1f}s")
        return active_dirs

    # ------------------------------------------------------------------

    @staticmethod
    def _run_single_timed(worker_dir: Path, swat_exe: str,
                          params: Optional[dict],
                          param_path: Optional[str] = None,
                          log_queue=None) -> float:
        """
        Write parameters (if any), run SWAT, return wall-clock execution time (seconds).

        Args:
            worker_dir: Path to this worker's TxtInOut copy.
            swat_exe:   Path string to SWAT executable.
            params:     Formatted param dict or None.
            param_path: Path string to the parameter definition file.
            log_queue:  multiprocessing.Queue from Logger.init_queue_listener().
                        When provided, all logging in this subprocess is routed
                        through the queue to the main process's QueueListener,
                        preventing concurrent file writes from multiple workers.
                        When None, workers fall back to default logging (no file output).
        """
        # ── redirect worker logging through the shared queue ──────────
        if log_queue is not None:
            from spyswat.logger import Logger
            Logger.init_worker(log_queue)

        t0 = time.perf_counter()
        if params:
            txinout = TxInOut(str(worker_dir))
            hru_mgr = HRUManager(txinout, SWATParam(param_path))
            hru_mgr.update_params(params)
        SWATRun(swat_exe).run(worker_dir)
        return time.perf_counter() - t0

    # backward-compat alias (old name)
    @staticmethod
    def _run_single(worker_dir: Path, swat_exe: str,
                    params: Optional[dict],
                    param_path: Optional[str] = None) -> None:
        WorkingFolderManager._run_single_timed(worker_dir, swat_exe, params, param_path)

    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir, onexc=_force_remove)
            logger.info(f"Cleaned up working dir: {self.working_dir}")

    @property
    def worker_dirs(self) -> List[Path]:
        return list(self._worker_dirs)
