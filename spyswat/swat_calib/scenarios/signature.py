"""Fingerprint the input files of a scenario's base TxtInOut directory.

``ScenarioBatch`` stores one fingerprint per scenario name so ``resume=True`` notices when
a scenario's inputs were edited between two runs. Only file stats are read (a TxtInOut
folder can be many GB); output files and the worker manifest are skipped with the same
patterns the parallel worker folders use.
"""
import hashlib
import json
import os
from pathlib import Path

from spyswat.swat_calib.core.workingFolder_manager import MANIFEST_NAME, _OUTPUT_IGNORE

UNREADABLE_PREFIX = "unreadable:"


def _input_stats(directory) -> list:
    """``(name, size, mtime_ns)`` of every regular input file directly in ``directory``."""
    folder = Path(directory)
    with os.scandir(folder) as entries:
        names = [e.name for e in entries if e.is_file()]
    ignored = _OUTPUT_IGNORE(str(folder), names) | {MANIFEST_NAME}
    rows = []
    for name in sorted(n for n in names if n not in ignored):
        st = os.stat(folder / name)
        rows.append((name, st.st_size, st.st_mtime_ns))
    return rows


def txinout_fingerprint(directory) -> str:
    """SHA-1 hex digest of the sorted ``(name, size, mtime_ns)`` list of input files.

    Changes when an input file is added, removed, resized or re-written (new mtime), and
    stays the same when only SWAT outputs (``output.*``, ``watout.dat``) or the worker
    manifest change. A missing or unreadable directory never raises: it gives the stable
    sentinel ``unreadable:<ExceptionName>``, so a batch with a broken scenario base still
    runs its other jobs (each job's failure stays in its own result) and ``resume``
    compares the sentinel like any other value.
    """
    try:
        stats = _input_stats(directory)
    except OSError as exc:
        return f"{UNREADABLE_PREFIX}{type(exc).__name__}"
    payload = json.dumps(stats, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
