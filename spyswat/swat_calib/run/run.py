import subprocess
from pathlib import Path
import logging


logger = logging.getLogger(__name__)

class SWATRun:
    """
        >>> runner = SWATRun("D:/SWAT/swat2012.exe")
        >>> runner.run("D:/SWAT/project/TxtInOut")
    """
    def __init__(self, swat_exe_path):
        self.swat_exe_path = Path(swat_exe_path)

    def run(self, txinout_path: str, capture_output: bool = False):
        if not (txinout_path / "file.cio").exists():
            raise RuntimeError("file.cio not found in TxtInOut")

        logger.info(f"Executing SWAT: {self.swat_exe_path}")
        logger.info(f"Working directory: {txinout_path}")
        try:
            result = subprocess.run(
                    [str(self.swat_exe_path)],
                    cwd=str(txinout_path),
                    capture_output=capture_output,
                    check=True,
                    text=True
            )
            if capture_output:
                return result

        except subprocess.CalledProcessError as e:
            logger.error(f"SWAT execution failed: {e}")
            if capture_output and e.stderr:
                logger.error(f"STDERR: {e.stderr}")
            raise

