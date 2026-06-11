import numpy as np

from spyswat.swat_calib.utils import ReachMapping, HRUMapping, SubbasinMapping, WatoutMapping
from spyswat.logger import Logger
from spyswat.swat_calib.io.readers import ReadFileLine
import pandas as pd
from pathlib import Path
from typing import List, Optional, Union, Dict

logger = Logger.get_logger(__name__)



class SWATReaderCache:
    def __init__(self):
        self._store: Dict[str, pd.DataFrame] = {}

    def get(self, key: str) -> Optional[pd.DataFrame]:
        df = self._store.get(key)
        return df.copy() if df is not None else None

    def set(self, key: str, df: pd.DataFrame):
        self._store[key] = df.copy()

    def clear(self, key: str = None):
        if key:
            self._store.pop(key, None)
        else:
            self._store.clear()

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


# GENERIC SWAT READER CLASS
class OutputFileReader:
    MAPPING_CLASSES = { '.rch': ReachMapping, '.hru': HRUMapping,
                        '.sub': SubbasinMapping, '.dat': WatoutMapping }

    DEFAULT_SKIP_HEADER = { '.rch': 9, '.hru': 9, '.sub': 9, '.dat': 6 }

    def __init__(self, filepath: Union[str, Path],
                 cache: Optional[SWATReaderCache] = None):

        self.filepath = Path(filepath)
        self.file_type = self.filepath.suffix
        self.skip_header = self.DEFAULT_SKIP_HEADER.get(self.file_type)


        self._cache = cache or SWATReaderCache()
        self._cache_key = str(self.filepath.resolve())

        if self.file_type not in self.MAPPING_CLASSES:
            raise ValueError(f"Unsupported file type: {self.file_type}")
        self.mapping_class = self.MAPPING_CLASSES[self.file_type]

        self.data: pd.DataFrame = pd.DataFrame()

    def __repr__(self):
        status = "loaded" if self.data is not None else "not loaded"
        rows = len(self.data) if self.data is not None else 0
        return f"SWATFileReader(type='{self.file_type}', rows={rows}, status='{status}')"

    def read(self, columns: Optional[List[str]| str | None] = None) -> pd.DataFrame:
        # full cache
        if columns is None:
            cached = self._cache.get(self._cache_key)
            if cached is not None:
                return cached
            df = self.__read_all()
            self._cache.set(self._cache_key, df)
            return df.copy()

        # column-subset cache
        col_key = f"{self._cache_key}::{','.join(sorted(columns))}"
        cached = self._cache.get(col_key)
        if cached is not None:
            return cached
        df = self.__read_by_col(columns)
        self._cache.set(col_key, df)
        return df.copy()

    def __read_all(self) -> pd.DataFrame:
        cols = self.mapping_class.get_column_names()
        print(cols)
        result = ReadFileLine._read_file(
            self.filepath,
            colspecs    =self.mapping_class.get_all_colspecs(),
            skiprows    =self.skip_header, #type: ignore
            )
        arr = np.array(list(result.values())).T
        self.data = pd.DataFrame(arr, columns=cols, dtype=np.float32)
        print(f"Read {self.file_type.upper()}: {len(self.data)} rows from {self.filepath.name}")
        return self.data

    def __read_by_col(self, columns: Optional[List[str]| str]) -> pd.DataFrame:
        colspecs = []
        names = []
        for c in columns:
            info = self.mapping_class.get_column_info(c)

            if info is None:
                raise logger.exception(f"Column not in mapping: {c}")
            colspecs.append(info["colspec"])
            names.append(c)

        result = ReadFileLine._read_file(
            self.filepath,
            colspecs    =colspecs,
            skiprows    =self.skip_header, #type: ignore
            )
        arr = np.array(list(result.values())).T
        self.data = pd.DataFrame(arr, columns=names, dtype=np.float32)
        print(f"Read {self.file_type.upper()}: {len(self.data)} rows from {self.filepath.name}")
        return self.data

