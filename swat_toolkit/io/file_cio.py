from typing import TYPE_CHECKING

import pandas as pd

from swat_toolkit.io.readers import ReadFileLine

if TYPE_CHECKING:
    from swat_toolkit.core.txinout import TxInOut


class FileCIO(ReadFileLine):
    def __init__(self, txinout: "TxInOut"):
        super().__init__()
        self.txinout = txinout
        self.file_path = self.txinout.get_watershed_file('.cio')

        if self.file_path is None:
            raise FileNotFoundError("Cannot locate .cio file from TxInOut")

        self.lines = self._read_file(self.file_path)

        self.begin_year = self.__get_begin_year_sim()

        self.year_start = self.begin_year + self.__get_number_year_skip()
        self.year_end = self.begin_year + self.__get_number_of_year_sim() - 1

    def get_date_range_sim(self, freq: str , year_start_non_skip: bool = False):
        start_year = (self.begin_year if year_start_non_skip else self.year_start)

        if freq == 'D':
            start = pd.Timestamp(start_year, 1, 1)
            end = pd.Timestamp(self.year_end, 12, 31)
        elif freq == 'MS':
            start = pd.Timestamp(start_year, 1, 1)
            end = pd.Timestamp(self.year_end, 12, 1)
        elif freq == 'YS':
            start = pd.Timestamp(start_year, 1, 1)
            end = pd.Timestamp(self.year_end, 1, 1)
        else:
            raise ValueError("Unsupported freq")

        return pd.date_range(start=start, end=end, freq=freq)


    def __get_begin_year_sim(self):
        year_line = self.lines[8][12:16].strip()
        return int(year_line)

    def __get_number_year_skip(self):
        year_skip = self.lines[59][12:16].strip()
        return int(year_skip)

    def __get_number_of_year_sim(self):
        return int(self.lines[7][12:16].strip())