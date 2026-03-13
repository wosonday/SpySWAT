import shutil
from pathlib import Path

class Weather:
    def __init__(self):
        pass

    def replace(self, path, txinout):
        shutil.copy2(Path(path), txinout)