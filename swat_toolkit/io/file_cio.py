from typing import TYPE_CHECKING
from swat_toolkit.io.readers import ReadFileLine

if TYPE_CHECKING:
    from swat_toolkit.core.txinout import TxInOut


class FileCIO(ReadFileLine):
    def __init__(self, txinout: "TxInOut"):
        super().__init__()
        self.txinout = txinout
        file_path = self.txinout.get_output_file('.cio')

        if file_path is not None:
            self.lines = self._read_file(file_path)
        else:
            raise FileNotFoundError(f"{file_path} does not exist")


    def get_begin_year_sim(self):
        year_line = self.lines[8][12:16].strip()
        return int(year_line)

    def get_number_year_skip(self):
        year_skip = self.lines[59][12:16].strip()
        return int(year_skip)

    def get_year(self):
        return self.get_begin_year_sim() + self.get_number_year_skip()