import shutil
from pathlib import Path

class Weather:

    @staticmethod
    def copy(pcp_in, pcp_out):
        dest = Path(pcp_out)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pcp_in, pcp_out)
