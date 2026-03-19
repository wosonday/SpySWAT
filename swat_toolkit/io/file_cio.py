from swat_toolkit.io.readers import ReadFileLine



class FileCIO(ReadFileLine):
    def __init__(self, filecio_path):
        self.lines = self._read_file(filecio_path)

    def get_begin_year_sim(self):
        year_line = self.lines[8][12:16].strip()
        return int(year_line)

    def get_number_year_skip(self):
        year_skip = self.lines[59][12:16].strip()
        return int(year_skip)

    def get_year(self):
        return self.get_begin_year_sim() + self.get_number_year_skip()