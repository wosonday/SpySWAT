import os
import sys
import json
import stat
import shutil
import time
import multiprocessing
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from spyswat.swat_calib.run import SWATRun
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.io import SWATParam
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)

MANIFEST_NAME = ".spyswat_manifest.json"
# Heavy SWAT outputs that are never copied into / restored in worker folders.
_OUTPUT_IGNORE = shutil.ignore_patterns("output.*", "watout.dat", MANIFEST_NAME)
_OLD_MTIME = 946684800  # 2000-01-01, used to "age" output.rch before a run


# ══════════════════════════════════════════════════════════════════════
#  Result container (contract C6)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class WorkerResult:
    ok: bool
    error: Optional[str]
    duration_s: float
    worker_dir: str
    payload: Any = None


# ══════════════════════════════════════════════════════════════════════
#  File helpers (shared with calibration.calib_manager)
# ══════════════════════════════════════════════════════════════════════

def _rmtree(path: Path, **kw) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove, **kw)
    else:
        shutil.rmtree(path, onerror=_force_remove, **kw)


def _force_remove(func, path, _):
    """onexc handler: unlock read-only files before retry (Windows PermissionError)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass  # best-effort; rmtree continues with remaining files


def _copy_over(src, dst, retries: int = 4) -> None:
    """Copy ``src`` over ``dst`` even if ``dst`` is read-only (retry on PermissionError)."""
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            if os.path.exists(dst):
                os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
            shutil.copyfile(src, dst)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.1 * (attempt + 1))
    assert last is not None
    raise last


def _rch_signature(directory) -> Optional[Tuple[int, int]]:
    p = Path(directory) / "output.rch"
    try:
        st = p.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _stamp_output_rch(directory) -> Optional[Tuple[int, int]]:
    """
    Age an existing output.rch (so a fresh write always changes its mtime, even on
    file systems with coarse timestamps) and return its (mtime_ns, size) signature,
    or None when it is absent.
    """
    p = Path(directory) / "output.rch"
    if p.exists():
        try:
            os.utime(p, (_OLD_MTIME, _OLD_MTIME))
        except OSError:
            pass
    return _rch_signature(directory)


def _check_fresh_output_rch(directory, before: Optional[Tuple[int, int]]) -> None:
    """Raise RuntimeError unless output.rch was (re)written since ``before``."""
    after = _rch_signature(directory)
    if after is None or after[1] == 0 or (before is not None and after[0] == before[0]):
        raise RuntimeError("SWAT ended without writing a fresh output.rch")


def _ext_with_dot(ext: str) -> str:
    return ext if ext.startswith('.') else f".{ext}"


def _param_exts(param_path: Optional[str], names=None) -> List[str]:
    """Extensions of the parameters in ``names`` (all parameters when names is None)."""
    if not param_path:
        return []
    swat_param = SWATParam(param_path)
    keys = swat_param.available_keys() if names is None else list(names)
    exts = {_ext_with_dot(swat_param.get(k).ext) for k in keys}
    return sorted(exts)


def _baseline_files(txinout: TxInOut, exts) -> List[Path]:
    files: List[Path] = []
    for ext in exts:
        found = txinout.get_hru_file(ext) or []
        files.extend(Path(f) for f in found)
    return [f for f in files if f.exists()]


def _read_manifest(worker_dir: Path) -> Optional[dict]:
    try:
        with open(worker_dir / MANIFEST_NAME, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_manifest(worker_dir: Path, exts, overlay_names) -> None:
    tmp = worker_dir / (MANIFEST_NAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"extensions": sorted(exts), "overlays": sorted(overlay_names)}, fh)
    os.replace(tmp, worker_dir / MANIFEST_NAME)


def _restore_worker_dir(baseline_dir: Path, worker_dir: Path,
                        exts, prev_overlays) -> int:
    """Copy file.cio + all baseline files of ``exts`` over the worker copy."""
    baseline = TxInOut(str(baseline_dir))
    n = 0
    cio = baseline_dir / "file.cio"
    if cio.exists():
        _copy_over(cio, worker_dir / "file.cio")
        n += 1
    for src in _baseline_files(baseline, exts):
        _copy_over(src, worker_dir / src.name)
        n += 1
    for name in prev_overlays:
        src = baseline_dir / name
        dst = worker_dir / name
        if src.exists():
            _copy_over(src, dst)
            n += 1
        elif dst.exists():
            try:
                os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
                dst.unlink()
            except OSError:
                pass
    return n


# ══════════════════════════════════════════════════════════════════════
#  Worker function (module level: picklable, never raises)
# ══════════════════════════════════════════════════════════════════════

def _worker_job(worker_dir: str, baseline_dir: str, swat_exe: str,
                params: Optional[dict], param_path: Optional[str],
                overlay: Optional[Dict[str, str]],
                prepare: Optional[Callable], extract: Optional[Callable],
                runner: Optional[Callable], timeout_s: Optional[float],
                log_queue=None) -> WorkerResult:
    t0 = time.perf_counter()
    wdir = Path(worker_dir)

    def _fail(msg: str) -> WorkerResult:
        return WorkerResult(False, msg, time.perf_counter() - t0, worker_dir, None)

    try:
        if log_queue is not None:
            Logger.init_worker(log_queue)

        # 1. busy probe -------------------------------------------------
        rch = wdir / "output.rch"
        if rch.exists():
            try:
                with open(rch, "ab"):
                    pass
            except PermissionError:
                return _fail(
                    f"{worker_dir}: output.rch is locked - another process (probably an "
                    f"orphaned swat.exe) is still using this folder"
                )

        # 2. restore from the baseline ----------------------------------
        manifest = _read_manifest(wdir)
        cur_exts = _param_exts(param_path, params.keys()) if params else []
        if params and not param_path:
            return _fail("param_path is required when param_sets are given")
        overlay = dict(overlay or {})
        if manifest is None:
            # Unknown history (fresh dir or one compounded by the old code): heal fully.
            exts = set(_param_exts(param_path)) | set(cur_exts)
            prev_overlays: List[str] = []
        else:
            exts = set(manifest.get("extensions", [])) | set(cur_exts)
            prev_overlays = list(manifest.get("overlays", []))
        _restore_worker_dir(Path(baseline_dir), wdir, sorted(exts),
                            prev_overlays + list(overlay))

        # 3. manifest first, then overlay files -------------------------
        _write_manifest(wdir, cur_exts, overlay.keys())
        for dest_name, src_path in overlay.items():
            _copy_over(src_path, wdir / dest_name)

        # 4. prepare ----------------------------------------------------
        if prepare is not None:
            prepare(worker_dir)

        # 5. apply params ----------------------------------------------
        if params:
            hru_mgr = HRUManager(TxInOut(worker_dir), SWATParam(param_path))
            hru_mgr.update_params(params)

        # 6. stamp, 7. run ---------------------------------------------
        before = _stamp_output_rch(wdir)
        if runner is not None:
            runner(worker_dir)
        else:
            SWATRun(swat_exe).run(worker_dir, timeout=timeout_s)

        # 8. freshness --------------------------------------------------
        _check_fresh_output_rch(wdir, before)

        # 9. extract ----------------------------------------------------
        payload = extract(worker_dir) if extract is not None else None
        return WorkerResult(True, None, time.perf_counter() - t0, worker_dir, payload)

    except BaseException as exc:  # noqa: BLE001 - a job must never raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _fail(f"{type(exc).__name__}: {exc}")


def _in_child_process() -> bool:
    return multiprocessing.parent_process() is not None


_CHILD_MSG = (
    "{what} was called inside a child process. This happens on Windows when the "
    "script that starts the calibration is not protected: put your code under\n"
    "    if __name__ == \"__main__\":\n"
    "    main()\n"
    "so that spawned worker processes do not re-run it."
)


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
        if _in_child_process():
            raise RuntimeError(_CHILD_MSG.format(what="WorkingFolderManager.setup()"))

        self.working_dir.mkdir(parents=True, exist_ok=True)
        self._worker_dirs = []

        logger.info(f"[Setup] Preparing {self.n_parallel} worker dirs in {self.working_dir}")
        t0 = time.perf_counter()

        for i in range(1, self.n_parallel + 1):
            dest = self.working_dir / f"TxInOut{i}"

            if dest.exists():
                if overwrite:
                    _rmtree(dest)
                    if dest.exists():
                        raise RuntimeError(
                            f"Cannot remove worker directory {dest}. Probably a swat.exe "
                            f"is still running in it or a file inside is locked by another "
                            f"program. Stop the process (or close the program) and retry."
                        )
                    logger.info(f"[Setup] [{i}/{self.n_parallel}] Removed & rebuilding: {dest.name}")
                else:
                    logger.info(f"[Setup] [{i}/{self.n_parallel}] Already exists (skip): {dest.name}")
                    self._worker_dirs.append(dest)
                    continue

            shutil.copytree(src=self.txinout_dir, dst=dest, ignore=_OUTPUT_IGNORE)
            logger.info(f"[Setup] [{i}/{self.n_parallel}] Created: {dest.name}")
            self._worker_dirs.append(dest)

        elapsed = time.perf_counter() - t0
        logger.info(f"[Setup] Done — {len(self._worker_dirs)} workers ready ({elapsed:.1f}s)")
        return self._worker_dirs

    # ------------------------------------------------------------------

    def run_parallel(self, swat_exe: Union[str, Path],
                           param_sets: Optional[List[dict]] = None,
                           log_queue=None, *,
                           overlays: Optional[List[Dict[str, Any]]] = None,
                           prepare: Optional[Callable[[str], Any]] = None,
                           extract: Optional[Callable[[str], Any]] = None,
                           runner: Optional[Callable[[str], Any]] = None,
                           timeout_s: Optional[float] = None) -> List[WorkerResult]:
        """
        Run jobs in parallel, one per worker directory.

        Every job starts from the baseline TxtInOut (never modified here), so
        'relative'/'add' parameter changes never compound between batches.
        A failing job never raises: it yields ``WorkerResult(ok=False, error=...)``.

        Args:
            swat_exe:   Path to the SWAT executable.
            param_sets: Formatted param dicts, one per worker (may be fewer than
                        n_parallel). None = run every worker dir without changes.
            log_queue:  Queue from Logger.init_queue_listener(); worker processes
                        route their log records through it.
            overlays:   Optional list (one per job) of {dest_file_name: source_path}
                        copied into the worker dir before the run.
            prepare:    Optional picklable ``prepare(worker_dir)`` run before params.
            extract:    Optional picklable ``extract(worker_dir) -> payload`` run after
                        a successful run (payload must be picklable).
            runner:     Optional picklable ``runner(worker_dir)``; default runs SWAT.
            timeout_s:  Kill the default SWAT run after this many seconds.

        Returns:
            list[WorkerResult] index-aligned with ``param_sets`` (or with the worker dirs).
        """
        if _in_child_process():
            raise RuntimeError(_CHILD_MSG.format(what="WorkingFolderManager.run_parallel()"))

        if not self._worker_dirs:
            raise RuntimeError("Worker dirs not initialised. Call setup() first.")

        if param_sets is not None and len(param_sets) > len(self._worker_dirs):
            raise ValueError(
                f"param_sets ({len(param_sets)}) exceeds n_parallel ({self.n_parallel}). "
                f"Use run_batch() to handle chunking automatically."
            )

        n = len(param_sets) if param_sets is not None else len(self._worker_dirs)
        if n == 0:
            return []
        if overlays is not None and len(overlays) != n:
            raise ValueError(f"overlays has {len(overlays)} entries, expected {n}")

        active_dirs   = self._worker_dirs[:n]
        active_params = list(param_sets) if param_sets is not None else [None] * n
        active_over   = list(overlays) if overlays is not None else [None] * n

        param_path_str = str(self._param_path) if self._param_path else None
        baseline_str   = str(self.txinout_dir)

        logger.info(f"[Parallel] Starting {n} workers ...")
        t_batch = time.perf_counter()
        results: List[Optional[WorkerResult]] = [None] * n
        done_count = 0

        executor = concurrent.futures.ProcessPoolExecutor(max_workers=n)
        try:
            future_to_idx = {
                executor.submit(
                    _worker_job,
                    str(active_dirs[i]), baseline_str, str(swat_exe),
                    active_params[i], param_path_str, active_over[i],
                    prepare, extract, runner, timeout_s, log_queue,
                ): i
                for i in range(n)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                i = future_to_idx[future]
                done_count += 1
                try:
                    res = future.result()
                except Exception as exc:  # broken pool, unpicklable payload, ...
                    res = WorkerResult(False, f"{type(exc).__name__}: {exc}", 0.0,
                                       str(active_dirs[i]), None)
                results[i] = res
                if res.ok:
                    logger.info(
                        f"[Parallel] [{done_count}/{n}] {active_dirs[i].name} OK "
                        f"({res.duration_s:.1f}s)"
                    )
                else:
                    logger.error(
                        f"[Parallel] [{done_count}/{n}] {active_dirs[i].name} FAILED: {res.error}"
                    )
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

        total = time.perf_counter() - t_batch
        logger.info(f"[Parallel] Batch done — {n} workers in {total:.1f}s")
        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        if self.working_dir.exists():
            _rmtree(self.working_dir)
            logger.info(f"Cleaned up working dir: {self.working_dir}")

    @property
    def worker_dirs(self) -> List[Path]:
        return list(self._worker_dirs)
