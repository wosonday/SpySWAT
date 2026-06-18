from typing import Optional, Dict
from spyswat.logger import Logger
from pandas import DataFrame

from ..io.mapping_output import OutputFileReader ,SWATReaderCache
from .txinout import TxInOut

Logger.init(log_dir="logs", log_file="run.log", level="WARNING")
logger = Logger.get_logger(__name__)


_SUB_DEFAULT_COLS = ['SUB', 'MON']
_RCH_DEFAULT_COLS = ['RCH', 'MON']
_SED_DEFAULT_COLS = ['RCH', 'MON']
_HRU_DEFAULT_COLS = ['HRU', 'SUB', 'MON']

class OutputFileManager:

    def __init__(self, txinout: TxInOut, use_cache: bool = True):
        self.txinout = txinout
        self._cache = SWATReaderCache() if use_cache else None
        self._readers: Dict[str, OutputFileReader] = {}


    def _get_reader(self, file_type: str) -> Optional[OutputFileReader]:
        if file_type not in self._readers:
            file_path = self.txinout.get_output_file(file_type)
            self._readers[file_type] = OutputFileReader(file_path, cache=self._cache)

        return self._readers[file_type]

    def read_rch(self, columns: Optional[str | list] = None,
                 reach_id: Optional[int | list] = None, freq = 'D') -> DataFrame:

        if isinstance(columns, str):
            columns = [columns]
        if isinstance(reach_id, int):
            reach_id = [reach_id]
        if columns is not None:
            columns = _RCH_DEFAULT_COLS + [c for c in columns if c not in _RCH_DEFAULT_COLS]
        df = self._get_reader('.rch').read(columns)
        if freq == 'MS':
            df = df.loc[df['MON'] <= 12]
        else:
            df = df.loc[df['MON'] <= 366]

        if reach_id is not None:
            df = df[df['RCH'].isin(reach_id)]
        return df


    def read_sed(self, columns: Optional[str | list] = None,
                 reach_id: Optional[int | list] = None) -> DataFrame:
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(reach_id, int):
            reach_id = [reach_id]
        if columns is not None:
            columns = _SED_DEFAULT_COLS + [c for c in columns if c not in _SED_DEFAULT_COLS]
        df = self._get_reader('.sub').read(columns)
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
        return self._get_reader('.dat').read(columns)


    def __repr__(self):
        cached = list(self._cache.keys()) if self._cache else []
        return "SWATOutputManager(cached=" + str(cached) + ")"
