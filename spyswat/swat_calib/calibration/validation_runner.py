# spyswat/swat_calib/calibration/validation_runner.py

from dataclasses import dataclass
import pandas as pd

from spyswat.swat_calib.calibration import CalibrationManager


@dataclass
class PeriodConfig:
    calib_start: str   # 'YYYY-MM-DD'
    calib_end:   str
    valid_start: str
    valid_end:   str


class ValidationRunner:
    """
    Chay hieu chinh + kiem dinh trong mot lenh.
    Su dung Differential Evolution cho hieu chinh.
    Neu can GLUE song song, dung SWATCalibration.analyze() + run_iteration() truc tiep.
    """

    def __init__(self, project, param_ranges: dict, observed: pd.Series,
                 period: PeriodConfig):
        self.project      = project
        self.param_ranges = param_ranges
        self.observed     = observed
        self.period       = period

    def run(self, metric='nse', method='differential_evolution',
            max_iter=100, reach_id=1) -> dict:
        """
        Returns:
            best_parameters, calibration: {metric: score}, validation: {all metrics}
        """
        # 1. Hieu chinh (calibration period)
        obs_calib = self.observed.loc[self.period.calib_start:self.period.calib_end]
        best_params, calib_score = self._calibrate(
            obs_calib, metric, method, max_iter, reach_id
        )

        # 2. Ap dung best params va chay SWAT
        self.project.HRU.update_params(best_params)
        self.project.run()

        sim = self.project.Output.read_rch(
            columns=['RCH', 'MON', 'FLOW_OUTcms'], reach_id=reach_id
        )['FLOW_OUTcms']
        sim.index = self.project.get_date_range()

        # 3. Kiem dinh (validation period)
        obs_valid = self.observed.loc[self.period.valid_start:self.period.valid_end]
        common = obs_valid.index.intersection(sim.index)
        valid_stats = self.project.Statistic.calculate_statistics(
            obs_valid.loc[common], sim.loc[common]
        )

        return {
            'best_parameters': best_params,
            'calibration':     {metric: calib_score},
            'validation':      valid_stats,
        }

    def _calibrate(self, obs_calib, metric, method, max_iter, reach_id):
        from spyswat.swat_calib.analysis.calibration import SWATCalibration
        calib = SWATCalibration(self.project)
        result = calib.optimize(
            self.param_ranges, obs_calib,
            method=method, metric=metric,
            max_iter=max_iter, reach_id=reach_id
        )
        return result['best_parameters'], result['best_objective_value']
