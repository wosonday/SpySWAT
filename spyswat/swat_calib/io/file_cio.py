from typing import TYPE_CHECKING

import pandas as pd

import numbers

from spyswat.swat_calib.io.readers import ReadFileLine
from spyswat.swat_calib.io.writers import atomic_write_lines, split_terminator
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

    # name -> 0-based line index in file.cio (value in columns 12:16, label after '|')
    _CIO_LINES = {'NBYR': 7, 'IYR': 8, 'IDAF': 9, 'IDAL': 10, 'IPRINT': 58, 'NYSKIP': 59}

    def set(self, **values) -> None:
        """
        Set integer NBYR, IYR, IDAF, IDAL, IPRINT and/or NYSKIP, write file.cio and
        refresh begin_year / year_start / year_end. Unknown keys raise ValueError.
        """
        unknown = sorted(set(values) - set(self._CIO_LINES))
        if unknown:
            raise ValueError(
                f"Unknown file.cio key(s) {unknown}. Allowed: {sorted(self._CIO_LINES)}."
            )
        for key, val in values.items():
            if isinstance(val, bool) or not isinstance(val, numbers.Integral):
                raise ValueError(f"{key} must be an integer, got {val!r}.")
            if val < 0 or val > 9999:
                raise ValueError(f"{key}={val} is outside 0..9999 (4-char field).")
        if 'IPRINT' in values and values['IPRINT'] not in self._IPRINT_TO_FREQ:
            raise ValueError(
                f"IPRINT must be one of {sorted(self._IPRINT_TO_FREQ)}, got {values['IPRINT']}."
            )

        new_lines = list(self.lines)
        for key, val in values.items():
            idx = self._CIO_LINES[key]
            if idx >= len(new_lines) or key not in new_lines[idx].split('|', 1)[-1]:
                raise ValueError(
                    f"file.cio line {idx + 1} does not hold {key}: "
                    f"{new_lines[idx].rstrip() if idx < len(new_lines) else '<missing>'!r}"
                )
            new_lines[idx] = self.__replaced(new_lines[idx], idx, 12, 16, int(val))
        self.lines = new_lines
        self._write_file()
        self.__update_metadata()

    @staticmethod
    def __replaced(line: str, line_idx: int, start: int, end: int, value: int) -> str:
        body, term = split_terminator(line)
        if len(body) < end:
            raise ValueError(f"file.cio line {line_idx + 1} too short: {body!r}")
        return body[:start] + f"{value:4d}" + body[end:] + term

    def set_year_skip(self, num_skip: int=2):
        if num_skip < 0:
            raise ValueError("num_skip must be >= 0")
        self.set(NYSKIP=num_skip)

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
        self.lines[line_idx] = self.__replaced(self.lines[line_idx], line_idx, start, end, value)

    def _write_file(self):
        atomic_write_lines(self.file_path, self.lines)

    def __get_begin_year_sim(self):
        year_line = self.lines[8][12:16].strip()
        return int(year_line)

    def __get_number_year_skip(self):
        year_skip = self.lines[59][12:16].strip()
        return int(year_skip)

    def __get_number_of_year_sim(self):
        return int(self.lines[7][12:16].strip())

    def __extract_pcp_first_yr(self, date_list):
        if not date_list:
            raise ValueError("The .pcp file has no data rows.")
        first_year = date_list[0][:4]

        for i, d in enumerate(date_list):
            if d[:4] != first_year:
                return date_list[:i][-1]
        return date_list[-1]  # a single year: still a string, never a list

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

    # ── Public IPRINT API ────────────────────────────────────────────

    _FREQ_TO_IPRINT = {'D': 1, 'MS': 0, 'M': 0, 'YS': 2}
    _IPRINT_TO_FREQ = {1: 'D', 0: 'MS', 2: 'YS'}

    def get_iprint(self) -> str:
        """Return current output frequency as freq string ('D', 'MS', 'YS')."""
        iprint = int(self.lines[58][12:16].strip())
        if iprint not in self._IPRINT_TO_FREQ:
            raise ValueError(
                f"Unknown IPRINT code {iprint} in {self.file_path}; "
                f"expected one of {sorted(self._IPRINT_TO_FREQ)}."
            )
        return self._IPRINT_TO_FREQ[iprint]

    def set_iprint(self, freq: str) -> None:
        """
        Set IPRINT in file.cio and save — does NOT touch NBYR/IYR/IDAL.

        Parameters
        ----------
        freq : 'D'  → daily output   (IPRINT=1)
               'MS' → monthly output  (IPRINT=0)
               'M'  → alias for 'MS'
               'YS' → annual output   (IPRINT=2)
        """
        iprint = self._FREQ_TO_IPRINT.get(freq)
        if iprint is None:
            raise ValueError(f"Unsupported freq '{freq}'. Use 'D', 'MS', or 'YS'.")
        self.__set_frequency_of_sim(freq)
        self._write_file()

    # ── Private helpers ───────────────────────────────────────────────

    def __set_frequency_of_sim(self, freq: str = 'D'):
        iprint = self._FREQ_TO_IPRINT.get(freq, 1)
        self.__replace_value(58, 12, 16, iprint)
