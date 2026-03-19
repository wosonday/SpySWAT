from swat_toolkit.utils import ReachMapping, HRUMapping, SubbasinMapping, WatoutMapping
import pandas as pd
from swat_toolkit.utils.logger import Logger
from pathlib import Path
from typing import List, Optional, Union

logger = Logger.get_logger(__name__)



# GENERIC SWAT READER CLASS
class SWATOutputFileReader:
    # Mapping file type với class
    MAPPING_CLASSES = {
        'rch': ReachMapping,
        'hru': HRUMapping,
        'sub': SubbasinMapping,
        'dat': WatoutMapping,
    }
    # Default skip header rows
    DEFAULT_SKIP_HEADER = {
        'rch': 9,
        'hru': 9,
        'sub': 9,
        'sed': 9,
        'dat': 6,
    }
    def __init__(self, filepath: Union[str, Path], file_type: str, 
                 skip_header = None):
        self.filepath = Path(filepath)
        self.file_type = file_type.lower()
        self.skip_header = self.DEFAULT_SKIP_HEADER.get(self.file_type)

        if self.file_type not in self.MAPPING_CLASSES:
            raise logger.exception(f"Unsupported file type: {self.file_type}")

        self.mapping_class = self.MAPPING_CLASSES[self.file_type]
        self.data: Optional[pd.DataFrame] = None

    def __repr__(self):
        status = "loaded" if self.data is not None else "not loaded"
        rows = len(self.data) if self.data is not None else 0
        return f"SWATFileReader(type='{self.file_type}', rows={rows}, status='{status}')"

    def read(self, columns: List[str] = None) -> pd.DataFrame:
        try:
            if columns is None:
                self.__read_all()

            return self.__read_by_col(columns)
        except Exception as e:
            logger.exception(e)
            raise


    def get_data(self) -> pd.DataFrame:
        """Trả về data"""
        if self.data is None:
            self.read()
        return self.data

    def _convert_dtypes(self):
        dtypes = self.mapping_class.get_dtypes()
        for col, dtype in dtypes.items():
            if col in self.data.columns:
                if dtype == 'float':
                    self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
                elif dtype == 'int':
                    self.data[col] = pd.to_numeric(self.data[col], errors='coerce').astype('Int64')
                elif dtype == 'str':
                    self.data[col] = self.data[col].astype(str).str.strip()

    def __read_all(self) -> pd.DataFrame:
        self.data = pd.read_fwf(
            self.filepath,
            colspecs=self.mapping_class.get_colspecs(),
            names=self.mapping_class.get_column_names(),
            skiprows=self.skip_header,
            na_values=['', ' ', 'NA', 'nan']
        )
        self._convert_dtypes()
        print(f"Read {self.file_type.upper()}: {len(self.data)} rows from {self.filepath.name}")
        return self.data

    def __read_by_col(self, columns: List[str]) -> pd.DataFrame:
        colspecs = []
        names = []
        for c in columns:
            info = self.mapping_class.get_column_info(c)

            if info is None:
                raise logger.exception(f"Column not in mapping: {c}")
            colspecs.append(info["colspec"])
            names.append(c)

        self.data = pd.read_fwf(
            self.filepath,
            colspecs=colspecs,
            names=names,
            skiprows=self.skip_header,
            na_values=["", " ", "NA", "nan"],
            )

        # self._convert_dtypes()
        return self.data
