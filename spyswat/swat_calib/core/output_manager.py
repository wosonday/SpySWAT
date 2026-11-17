from typing import Optional, Dict
import numpy as np
from spyswat.logger import Logger
from pandas import DataFrame

from ..io.mapping_output import OutputFileReader, SWATReaderCache, check_output_complete
from .txinout import TxInOut

logger = Logger.get_logger(__name__)


_SUB_DEFAULT_COLS = ['SUB', 'MON']
_RCH_DEFAULT_COLS = ['RCH', 'MON']
_SED_DEFAULT_COLS = ['RCH', 'MON']
_HRU_DEFAULT_COLS = ['HRU', 'SUB', 'MON']
_WATOUT_DEFAULT_COLS = ['YEAR', 'DAY', 'STEP', 'FLOW_OUTcms']

class OutputFileManager:

    def __init__(self, txinout: TxInOut, use_cache: bool = True):
        self.txinout = txinout
        self._use_cache = use_cache
        self._cache = SWATReaderCache() if use_cache else None
        self._readers: Dict[str, OutputFileReader] = {}

    def _get_reader(self, file_type: str) -> Optional[OutputFileReader]:
        if file_type not in self._readers:
            file_path = self.txinout.get_output_file(file_type)
            self._readers[file_type] = OutputFileReader(
                file_path, cache=self._cache, use_cache=self._use_cache)

        return self._readers[file_type]

    def invalidate(self) -> None:
        """Drop every cached frame (call after SWAT has rewritten the outputs)."""
        if self._cache is not None:
            self._cache.clear()

    def _file_freq(self) -> str:
        """Print frequency of the simulation ('D', 'MS', 'YS'), read fresh from file.cio."""
        # FileCIO caches the file lines at init, so build a new one on every call.
        from ..io.file_cio import FileCIO
        return FileCIO(self.txinout).get_iprint()

    def check_complete(self, file_type: str = '.rch', expected_rows: Optional[int] = None) -> int:
        """Raise RuntimeError with a specific reason if the output file is not usable.

        The file is streamed, not loaded into pandas. Returns the number of data rows.
        """
        skip = OutputFileReader.DEFAULT_SKIP_HEADER.get(file_type)
        if skip is None:
            raise ValueError(f"Unsupported file type: {file_type}")
        return check_output_complete(self.txinout.get_output_file(file_type), skip, expected_rows)

    @staticmethod
    def _split_monthly_rch(df: DataFrame) -> DataFrame:
        """Keep only the 12 monthly blocks of every year of a monthly (IPRINT=0) output.rch.

        Layout: per year 12 monthly blocks and one annual block (MON holds the year),
        then one average-annual block (MON holds the number of simulated years, which
        can be <= 12 or > 12, so MON alone cannot identify it). Blocks are located by
        the repetition of the first reach number.
        """
        n_rows = len(df)
        if n_rows == 0:
            raise ValueError("Monthly output.rch has no data rows")
        rch = df['RCH'].to_numpy()
        mon = df['MON'].to_numpy()
        repeats = np.nonzero(rch[1:] == rch[0])[0]
        n = int(repeats[0]) + 1 if repeats.size else n_rows
        if n_rows % n:
            raise ValueError(
                f"Monthly output.rch: {n_rows} rows cannot be split into blocks of {n} reaches "
                f"(first reach {int(rch[0])} repeats after {n} rows); the file looks truncated")
        n_blocks = n_rows // n
        if n_blocks < 14 or (n_blocks - 1) % 13:
            raise ValueError(
                f"Monthly output.rch: found {n_blocks} blocks of {n} reaches; expected 13 per "
                f"year (12 monthly + 1 annual) plus one trailing average-annual block, i.e. "
                f"13*years+1 blocks")
        blocks = np.arange(n_rows) // n
        pos = blocks % 13
        years = (n_blocks - 1) // 13
        last = n_blocks - 1

        for b in range(n_blocks):
            sl = slice(b * n, (b + 1) * n)
            if not np.array_equal(rch[sl], rch[:n]):
                raise ValueError(
                    f"Monthly output.rch: block {b} does not list the same reaches as block 0")
            vals = np.unique(mon[sl])
            if vals.size != 1:
                raise ValueError(
                    f"Monthly output.rch: block {b} holds several MON values {vals[:5].tolist()}")
            if b == last:
                continue  # average-annual block: single value, any magnitude
            if pos[b * n] < 12:
                if vals[0] != pos[b * n] + 1:
                    raise ValueError(
                        f"Monthly output.rch: block {b} should be month {int(pos[b * n]) + 1} "
                        f"but MON is {vals[0]:g}")
            elif vals[0] <= 12:
                raise ValueError(
                    f"Monthly output.rch: block {b} should be an annual block (MON = year) "
                    f"but MON is {vals[0]:g}")

        keep = (pos < 12) & (blocks != last)
        out = df.loc[keep]
        assert len(out) == n * 12 * years
        return out

    def read_rch(self, columns: Optional[str | list] = None,
                 reach_id: Optional[int | list] = None,
                 freq: Optional[str] = None) -> DataFrame:
        """Read output.rch in file order.

        freq=None uses the frequency recorded in file.cio (IPRINT). An explicit freq
        must agree with it. Monthly files are returned without the annual and the
        average-annual rows; yearly (IPRINT=2) files are not supported.
        """
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(reach_id, int):
            reach_id = [reach_id]

        file_freq = self._file_freq()
        if freq is not None:
            wanted = 'MS' if freq == 'M' else freq
            if wanted not in ('D', 'MS', 'YS'):
                raise ValueError(f"Unsupported freq '{freq}'. Use 'D', 'MS' or 'YS'.")
            if wanted != file_freq:
                raise ValueError(
                    f"freq='{freq}' contradicts file.cio: IPRINT says the output is "
                    f"'{file_freq}'")
        if file_freq == 'YS':
            raise NotImplementedError(
                "Reading yearly output.rch (IPRINT=2) is not supported; use IPRINT=0 or 1")

        if columns is not None:
            columns = _RCH_DEFAULT_COLS + [c for c in columns if c not in _RCH_DEFAULT_COLS]
        df = self._get_reader('.rch').read(columns)
        if file_freq == 'MS':
            df = self._split_monthly_rch(df)

        if reach_id is not None:
            df = df[df['RCH'].isin(reach_id)]
        return df

    def read_sed(self, columns: Optional[str | list] = None,
                 reach_id: Optional[int | list] = None) -> DataFrame:
        """Read output.sed (daily print only; layout verified on a daily file)."""
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(reach_id, int):
            reach_id = [reach_id]
        file_freq = self._file_freq()
        if file_freq != 'D':
            raise NotImplementedError(
                f"output.sed was only verified for daily print (IPRINT=1); this simulation is "
                f"'{file_freq}'. Use read_rch(columns='SED_OUTtons', ...) instead")
        if columns is not None:
            columns = _SED_DEFAULT_COLS + [c for c in columns if c not in _SED_DEFAULT_COLS]
        df = self._get_reader('.sed').read(columns)
        if reach_id is not None:
            df = df[df['RCH'].isin(reach_id)]
        return df

    def read_hru(self, columns: Optional[str | list] = None,
                 hru_id: Optional[int | list] = None) -> DataFrame:
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(hru_id, int):
            hru_id = [hru_id]
        if columns is not None:
            columns = _HRU_DEFAULT_COLS + [c for c in columns if c not in _HRU_DEFAULT_COLS]
        df = self._get_reader('.hru').read(columns)
        if hru_id is not None:
            df = df[df['HRU'].isin(hru_id)]
        return df

    def read_sub(self, columns: Optional[str | list] = None,
                 sub_id: Optional[int | list] = None) -> DataFrame:
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(sub_id, int):
            sub_id = [sub_id]
        if columns is not None:
            columns = _SUB_DEFAULT_COLS + [c for c in columns if c not in _SUB_DEFAULT_COLS]
        df = self._get_reader('.sub').read(columns)
        if sub_id is not None:
            df = df[df['SUB'].isin(sub_id)]
        return df

    def read_watout(self, columns: Optional[str | list] = None) -> DataFrame:
        if isinstance(columns, str):
            columns = [columns]
        if columns is not None:
            columns = _WATOUT_DEFAULT_COLS + [c for c in columns if c not in _WATOUT_DEFAULT_COLS]
        return self._get_reader('.dat').read(columns)

    def __repr__(self):
        cached = list(self._cache.keys()) if self._cache else []
        return "SWATOutputManager(cached=" + str(cached) + ")"

