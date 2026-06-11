from typing import TYPE_CHECKING

import pandas as pd

from spyswat.swat_calib.io.readers import ReadFileLine
if TYPE_CHECKING:
    from spyswat.swat_calib.core.txinout import TxInOut


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


    def update(self, freq: str = 'D'):
        IYR, NBYR, IDAL = self.__get_year_pcp()

        self.__replace_value(7, 12, 16, NBYR)
        self.__replace_value(8, 12, 16, IYR)
        self.__replace_value(10, 12, 16, IDAL)

        self.__set_frequency_of_sim(freq)
        self._write_file()

        print('NBYR  :', self.lines[7], end='')
        print('IYR   :', self.lines[8], end='')
        print('IDAL  :', self.lines[10], end='')
        self.__update_metadata()

    def __update_metadata(self):
        self.begin_year = self.__get_begin_year_sim()
        self.year_start = self.begin_year + self.__get_number_year_skip()
        self.year_end = self.begin_year + self.__get_number_of_year_sim() - 1

    def __replace_value(self, line_idx: int, start: int, end: int, value: int):
        line = self.lines[line_idx]
        if len(line) < end:
            raise ValueError(f"Line {line_idx} too short")
        formatted = f"{value:4d}"
        self.lines[line_idx] = line[:start] + formatted + line[end:]

    def _write_file(self):
        with open(self.file_path, 'w') as f:
            f.writelines(self.lines)

    def __get_begin_year_sim(self):
        year_line = self.lines[8][12:16].strip()
        return int(year_line)

    def __get_number_year_skip(self):
        year_skip = self.lines[59][12:16].strip()
        return int(year_skip)

    def __get_number_of_year_sim(self):
        return int(self.lines[7][12:16].strip())

    def __extract_pcp_first_yr(self, date_list):
        first_year = date_list[0][:4]

        for i, d in enumerate(date_list):
            if d[:4] != first_year:
                return date_list[:i][-1]
        return date_list

    def __extract_pcp_last_yr(self, date_list):
        return date_list[-1]

    def __get_year_pcp(self):
        pcp = self.txinout.get_weather_file('.pcp')
        pcp_date = self._read_file(pcp, colspecs=(0,7), skiprows=4)
        IYR = self.__extract_pcp_first_yr(pcp_date)
        yr_end = self.__extract_pcp_last_yr(pcp_date)
        NBYR = int(yr_end[:4]) - int(IYR[:4]) + 1
        IDAL = yr_end[4:]
        return int(IYR[:4]), int(NBYR), int(IDAL)

    def __set_frequency_of_sim(self, freq: str = 'D'):
        line = self.lines[58]
        if freq == 'D':
            self.lines[58] = line[:12] + f'{1:4d}' + line[16:]
        elif freq == 'MS':
            self.lines[58] = line[:12] + f'{0:4d}' + line[16:]
        elif freq == 'YS':
            self.lines[58] = line[:12] + f'{2:4d}' + line[16:]

        return None
