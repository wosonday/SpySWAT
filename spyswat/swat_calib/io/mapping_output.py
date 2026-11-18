import os
import re
import numpy as np

from spyswat.swat_calib.utils import ReachMapping, HRUMapping, SubbasinMapping, WatoutMapping
from spyswat.swat_calib.utils.output_mapping_info import SedimentMapping
from spyswat.logger import Logger
from spyswat.swat_calib.io.readers import ReadFileLine
import pandas as pd
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict

logger = Logger.get_logger(__name__)

# Fortran drops 'E' when exponent has 3+ digits: '0.2746-139' -> '0.2746E-139'
_RE_MISSING_E = re.compile(r'([0-9])([+-]\d{2,})$')

def _fix_fortran_exp(vals: list) -> list:
    """Normalize Fortran fixed-width numbers with missing exponent 'E'.
    Empty or whitespace-only strings are replaced with NaN.
    """
    out = []
    for v in vals:
        if not v or not v.strip():
            out.append(np.nan)
        else:
            out.append(_RE_MISSING_E.sub(r'\1E\2', v))
    return out


# (st_mtime_ns, st_size) of a file; used to detect that SWAT rewrote an output file
FileStamp = Tuple[int, int]


def _file_stamp(path: Path) -> FileStamp:
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size


class SWATReaderCache:
    """Cache of parsed DataFrames.

    Every entry may carry a stamp (mtime_ns, size) of the source file. ``get``
    with a stamp only returns an entry stored with the same stamp. ``set``
    replaces any previous entry under the same key, so the cache never holds
    more than one entry per key.
    """

    def __init__(self):
        self._store: Dict[str, pd.DataFrame] = {}
        self._stamps: Dict[str, Optional[FileStamp]] = {}

    def get(self, key: str, stamp: Optional[FileStamp] = None) -> Optional[pd.DataFrame]:
        df = self._store.get(key)
        if df is None:
            return None
        if stamp is not None and self._stamps.get(key) != stamp:
            return None
        return df.copy()

    def set(self, key: str, df: pd.DataFrame, stamp: Optional[FileStamp] = None):
        self._store[key] = df.copy()
        self._stamps[key] = stamp

    def has(self, key: str) -> bool:
        return key in self._store

    def clear(self, key: str = None):
        if key:
            self._store.pop(key, None)
            self._stamps.pop(key, None)
        else:
            self._store.clear()
            self._stamps.clear()

    def clear_file(self, base_key: str):
        """Drop the full-file entry and every column-subset entry of one file."""
        prefix = base_key + '::'
        for k in [k for k in self._store if k == base_key or k.startswith(prefix)]:
            self.clear(k)

    def keys(self):
        return self._store.keys()

    def info(self) -> Dict:
        return {
            k: {
                'rows': len(df),
                'memory_mb': round(df.memory_usage(deep=True).sum() / 1024**2, 2)
            }
            for k, df in self._store.items()
        }


def _parse_fixed_width(path: Path, lines: List[str], first_line_no: int,
                       names: List[str], colspecs: List[Tuple[int, int]]) -> pd.DataFrame:
    """Slice fixed-width ``lines`` into a float32 DataFrame.

    Errors always name the file, the 1-based line number in the file, the
    column and the raw text. The terminator of a line is never part of a field.
    """
    # trailing blank lines are not data
    while lines and not lines[-1].strip():
        lines = lines[:-1]

    if not lines:
        return pd.DataFrame({n: np.array([], dtype=np.float32) for n in names})

    need = max((e for _, e in colspecs), default=0)
    lens = np.fromiter((len(ln.rstrip('\r\n')) for ln in lines), dtype=np.int64, count=len(lines))
    short = np.nonzero(lens < need)[0]
    if short.size:
        i = int(short[0])
        raise ValueError(
            f"{path}: line {first_line_no + i} is truncated or blank "
            f"({int(lens[i])} characters, at least {need} expected); "
            f"raw text: {lines[i].rstrip(chr(13) + chr(10))[:80]!r}")

    out: Dict[str, np.ndarray] = {}
    for name, (start, end) in zip(names, colspecs):
        raw = [ln[start:end].strip() for ln in lines]
        vals = _fix_fortran_exp(raw)
        try:
            arr = np.array(vals, dtype=np.float64)
        except (ValueError, TypeError):
            arr = None
            for i, v in enumerate(vals):
                try:
                    float(v)
                except (ValueError, TypeError):
                    raise ValueError(
                        f"{path}: line {first_line_no + i}, column '{name}' "
                        f"(characters {start}-{end}): cannot convert {raw[i]!r} to a number"
                    ) from None
            raise  # pragma: no cover - the loop above always finds the culprit
        out[name] = arr.astype(np.float32)
    return pd.DataFrame(out)


def check_output_complete(path: Union[str, Path], skip_header: int,
                          expected_rows: Optional[int] = None) -> int:
    """Stream ``path`` and raise RuntimeError when it is not a usable output.

    Returns the number of data rows. The file is never loaded into pandas.
    """
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"Output file is missing: {path}")
    size = path.stat().st_size
    if size == 0:
        raise RuntimeError(f"Output file is empty (0 bytes): {path}")

    n_rows = 0
    ref_len: Optional[int] = None
    ref_line = 0
    last_raw = b''
    with open(path, 'rb') as f:
        for lineno, raw in enumerate(f, start=1):
            last_raw = raw
            if lineno <= skip_header:
                continue
            length = len(raw.rstrip(b'\r\n'))
            if ref_len is None:
                ref_len, ref_line = length, lineno
            elif length != ref_len:
                raise RuntimeError(
                    f"Output file {path} has data lines of unequal length: line {lineno} "
                    f"has {length} characters but line {ref_line} has {ref_len} "
                    f"(file is truncated or still being written)")
            n_rows += 1

    if not last_raw.endswith(b'\n'):
        raise RuntimeError(
            f"Output file {path} does not end with a newline: the last line is incomplete "
            f"(file is truncated or still being written)")
    if n_rows == 0:
        raise RuntimeError(f"Output file {path} has a header but no data rows")
    if expected_rows is not None and n_rows != expected_rows:
        raise RuntimeError(
            f"Output file {path} has {n_rows} data rows, expected {expected_rows}")
    return n_rows


# GENERIC SWAT READER CLASS
class OutputFileReader:
    MAPPING_CLASSES = { '.rch': ReachMapping, '.hru': HRUMapping,
                        '.sub': SubbasinMapping, '.dat': WatoutMapping,
                        '.sed': SedimentMapping }

    DEFAULT_SKIP_HEADER = { '.rch': 9, '.hru': 9, '.sub': 9, '.dat': 6, '.sed': 1 }

    def __init__(self, filepath: Union[str, Path],
                 cache: Optional[SWATReaderCache] = None,
                 use_cache: bool = True):

        self.filepath = Path(filepath)
        self.file_type = self.filepath.suffix
        self.skip_header = self.DEFAULT_SKIP_HEADER.get(self.file_type)

        self._cache: Optional[SWATReaderCache] = (
            (cache if cache is not None else SWATReaderCache()) if use_cache else None)
        self._cache_key = str(self.filepath.resolve())

        if self.file_type not in self.MAPPING_CLASSES:
            raise ValueError(f"Unsupported file type: {self.file_type}")
        self.mapping_class = self.MAPPING_CLASSES[self.file_type]

        self.data: pd.DataFrame = pd.DataFrame()

    def __repr__(self):
        status = "loaded" if self.data is not None else "not loaded"
        rows = len(self.data) if self.data is not None else 0
        return f"SWATFileReader(type='{self.file_type}', rows={rows}, status='{status}')"

    def read(self, columns: Optional[List[str] | str | None] = None) -> pd.DataFrame:
        if isinstance(columns, str):
            columns = [columns]
        key = self._cache_key if columns is None else f"{self._cache_key}::{','.join(columns)}"

        if self._cache is None:
            return self._parse(columns)

        # stamp BEFORE parsing: if SWAT rewrites the file meanwhile, the next read re-parses
        stamp = _file_stamp(self.filepath)
        cached = self._cache.get(key, stamp)
        if cached is not None:
            return cached
        if self._cache.has(key):
            # the file changed since it was cached: forget everything cached for it
            self._cache.clear_file(self._cache_key)
        df = self._parse(columns)
        self._cache.set(key, df, stamp)
        return df.copy()

    def _parse(self, columns: Optional[List[str]]) -> pd.DataFrame:
        if columns is None:
            names = self.mapping_class.get_column_names()
            colspecs = self.mapping_class.get_all_colspecs()
        else:
            names, colspecs = [], []
            for c in columns:
                info = self.mapping_class.get_column_info(c)
                if info is None:
                    raise ValueError(f"Column not in mapping: {c}")
                names.append(c)
                colspecs.append(info["colspec"])

        skip = self.skip_header or 0
        lines = ReadFileLine._read_file(self.filepath, skiprows=skip)
        self.data = _parse_fixed_width(self.filepath, lines, skip + 1, names, colspecs)
        logger.debug("Read %s: %d rows from %s",
                     self.file_type.upper(), len(self.data), self.filepath.name)
        return self.data
