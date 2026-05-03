# swat_toolkit/calibration/manager.py
from typing import Dict
import pandas as pd

class CalibrationManager:
    def __init__(self, project):
        self.project = project
        self._backup_dir = project.project_dir / "_calib_backup"

    def run_iteration(
        self,
        param_dict: Dict[str, float],
        observed: pd.Series,
        metric: str = 'nse',
        reach_id: int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> float:
        self._backup_state()
        try:
            self.project.update_parameters(param_dict)
            self.project.run()
            self.project.output.invalidate_cache()   # << fix vấn đề 4
            sim = self.project.output.read_reach(reach_id)[output_variable]
            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.analysis.calculate_statistics(
                        obs_aligned, sim_aligned, metrics=[metric]
                    )[metric]
            return score
        except Exception as e:
            self._restore_state()
            raise RuntimeError(f"Iteration failed: {e}") from e

    def _backup_state(self): ...    # copy TxtInOut sang _calib_backup
    def _restore_state(self): ...   # copy ngược lại
    def _align_series(self, obs, sim): ...  # căn chỉnh index thời gian