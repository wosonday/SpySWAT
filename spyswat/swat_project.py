from pathlib import Path
from typing import Optional, Union
import logging

from spyswat.swat_calib.core import TxInOut, OutputFileManager, HRUManager, WorkingFolderManager
from spyswat.swat_calib.io import SWATParam, FileCIO
from spyswat.swat_calib.run import SWATRun
from spyswat.swat_calib.analysis import SWATAnalysis

logger = logging.getLogger(__name__)



class SWATProject:
    """
        >>> project = SWATProject(
        ...     project_dir="D:/SWAT/my_project",
        ...     swat_exe="D:/SWAT/swat2012.exe"
        ... )
        >>> project.HRU.update_params({'CN2.mgt': [(75, 'v')]})
        >>> project.run()
        >>> df = project.Output.read_rch()
    """

    def __init__(
            self,
            txinout_dir: Union[str, Path],
            working_dir: Union[str, Path],
            swat_exe:    Union[str, Path],
            param_file:  Optional[str] = None,
            n_parallel: int = 1
            ):
        self.txinout        = TxInOut(str(txinout_dir))
        self.working_folder = Path(working_dir)
        self.param_file     = SWATParam(param_file)
        self.swat_exe       = SWATRun(swat_exe)

        # ==========================================

        self._hru_manager     = HRUManager(self.txinout, self.param_file)
        self._file_cio        = FileCIO(self.txinout)
        self._output_manager  = OutputFileManager(self.txinout)


        # ============= Statistic ======================
        self._statistic     = SWATAnalysis(self.txinout)

        self._wf_manager = WorkingFolderManager(
            txinout      = self.txinout,
            working_dir  = self.working_folder,
            n_parallel   = n_parallel,
            param_path   = param_file
        )
        #============================================

        logger.info(f"SWAT Project initialized: {self.txinout}")
        logger.info(f"Found {self.txinout.number_hru} HRUs in {self.txinout.number_sub} subbasins")

    # ================ Read data =============================
    def worker(self, index: int) -> "SWATProject":
        worker_dirs = self._wf_manager.worker_dirs
        if not worker_dirs:
            raise RuntimeError("Chưa gọi setup(). Hãy gọi setup() trước.")
        if index < 1 or index > len(worker_dirs):
            raise IndexError(f"Worker index {index} không hợp lệ. "
                             f"Có {len(worker_dirs)} workers (1..{len(worker_dirs)}).")

        target_dir = worker_dirs[index - 1]  # TxInOut1 → index 0
        return SWATProject(
            txinout_dir=target_dir,
            working_dir=self.working_folder,
            swat_exe= self.swat_exe.swat_exe_path,
            param_file=self.param_file.param_path if self.param_file else None,
            n_parallel=1
            )

    def get_date_range(self, freq: str='D', year_start_non_skip: bool=False):
        return self._file_cio.get_date_range_sim(freq, year_start_non_skip)

    def read_params_values(self, param: list):
        return self._hru_manager.read_muti_hru_param_values(param)

    def run(self):
        return self.swat_exe.run(self.txinout.directory)

    def info(self):
        """Print project information"""
        print(f"TxtInOut: {self.txinout.directory}")
        print("=" * 20)
        print(f"SWAT Executable: {self.swat_exe}")
        self.txinout.info()

    def __working_folder(self):
        return self.working_folder


    def __repr__(self):
        return (f"SWATProject '{self.txinout.directory}')', "
                f"\n hrs={self.txinout.number_hru}, "
                f"\n subs={self.txinout.number_sub})")

    @property
    def HRU(self):
        return self._hru_manager

    @property
    def Output(self):
        return self._output_manager

    @property
    def Statistic(self):
        return self._statistic

    @property
    def FileCIO(self):
        return self._file_cio

    @property
    def WorkingFolder(self):
        return self._wf_manager
