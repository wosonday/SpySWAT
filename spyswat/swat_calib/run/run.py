import shutil
import subprocess
import sys
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

    def run(self, txinout_path, capture_output: bool = False,
            timeout: float | None = None):
        """
        Run the SWAT executable inside ``txinout_path``.

        Args:
            txinout_path:   Folder holding file.cio (used as the working directory).
            capture_output: Capture stdout/stderr and return the CompletedProcess.
            timeout:        Seconds before the child is killed and
                            ``subprocess.TimeoutExpired`` is raised (None = no limit).

        Raises:
            FileNotFoundError:            the executable does not exist.
            subprocess.TimeoutExpired:    the run exceeded ``timeout`` (child killed).
            subprocess.CalledProcessError: SWAT returned a non-zero exit code.
        """
        txinout_path = Path(txinout_path)
        if not (txinout_path / "file.cio").exists():
            raise RuntimeError("file.cio not found in TxtInOut")

        exe = self.swat_exe_path
        if not exe.exists() and shutil.which(str(exe)) is None:
            raise FileNotFoundError(f"SWAT executable not found: {exe}")

        cmd = [str(exe)]
        logger.info(f"Executing SWAT: {exe}")
        logger.info(f"Working directory: {txinout_path}")

        pipe = subprocess.PIPE if capture_output else None
        proc = subprocess.Popen(
            cmd,
            cwd=str(txinout_path),
            stdin=subprocess.DEVNULL,
            stdout=pipe,
            stderr=pipe,
            text=True,
        )
        try:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.error(f"SWAT timed out after {timeout}s in {txinout_path}; killing it")
                self._kill(proc)
                raise
        finally:
            # Also covers KeyboardInterrupt and any other exception.
            if proc.poll() is None:
                self._kill(proc)

        if proc.returncode != 0:
            err = subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout, stderr=stderr
            )
            logger.error(f"SWAT execution failed: {err}")
            if capture_output and stderr:
                logger.error(f"STDERR: {stderr}")
            raise err

        if capture_output:
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        return None

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:     # already finished: its pid may be reused
            return
        if sys.platform == "win32":
            # Also end children of the process (e.g. swat.exe started by a .bat wrapper).
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, check=False,
                )
            except Exception:
                pass
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
