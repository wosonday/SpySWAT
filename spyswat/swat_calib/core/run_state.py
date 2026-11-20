"""Shared input-copy and output-freshness helpers for SWAT runs."""

import os
import shutil
import stat
import time
from pathlib import Path
from typing import Optional, Tuple


_OLD_MTIME = 946684800  # 2000-01-01, used to "age" output.rch before a run


def copy_over(src, dst, retries: int = 4) -> None:
    """
    Copy ``src`` over ``dst`` even if ``dst`` is read-only (retry on PermissionError).

    The data goes to a temporary file next to ``dst`` and is moved into place with
    ``os.replace``, so an interrupted copy never leaves a truncated ``dst``.
    """
    dst = Path(dst)
    tmp = dst.with_name(f".{dst.name}.spyswat.tmp")
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            if os.path.exists(dst):
                os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.1 * (attempt + 1))
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
    assert last is not None
    raise last


def rch_signature(directory) -> Optional[Tuple[int, int]]:
    p = Path(directory) / "output.rch"
    try:
        st = p.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def stamp_output_rch(directory) -> Optional[Tuple[int, int]]:
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
    return rch_signature(directory)


class StaleOutputError(RuntimeError):
    """SWAT ended without writing a fresh output.rch (the run produced no result)."""


def check_fresh_output_rch(directory, before: Optional[Tuple[int, int]]) -> None:
    """Raise StaleOutputError unless output.rch was (re)written since ``before``."""
    after = rch_signature(directory)
    if after is None or after[1] == 0 or (before is not None and after[0] == before[0]):
        raise StaleOutputError("SWAT ended without writing a fresh output.rch")
