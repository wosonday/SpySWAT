"""
Calibration algorithms for SWAT model
"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple
import logging
from scipy.optimize import minimize, differential_evolution

from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.analysis.statistics import SWATAnalysis

logger = logging.getLogger(__name__)


class SWATCalibration:
    def __init__(self, project, analysis=None):
        self.project = project
        self.analysis = analysis or SWATAnalysis(project)
        self._manager = CalibrationManager(project)
        self.optimization_history = []

    # ==================== Optimization Methods ====================

    def optimize(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: pd.Series,
            method: str = 'differential_evolution',
            metric: str = 'nse',
            max_iter: int = 100,
            reach_id: int = 1,
            output_variable: str = 'FLOW_OUTcms'
            ) -> Dict:
        """
        Tối ưu hoá tham số sử dụng scipy.optimize.
        Luồng thực thi:
          1. Xây dựng objective function thông qua CalibrationManager
          2. Gọi differential_evolution hoặc minimize
          3. Ghi lại lịch sử tối ưu
          4. Trả về best_parameters và best_objective_value
        """
        names = list(param_ranges.keys())
        bounds = [param_ranges[n] for n in names]

        def objective(x):
            params = dict(zip(names, x))
            score = self._manager.run_iteration(
                params, observed_series, metric, reach_id, output_variable
            )
            self.optimization_history.append({'params': params, 'score': score})
            return -score if metric in ('nse', 'r2', 'kge') else score

        if method == 'differential_evolution':
            result = differential_evolution(objective, bounds, maxiter=max_iter)
        else:
            x0 = [(b[0] + b[1]) / 2 for b in bounds]
            result = minimize(objective, x0, bounds=bounds)

        best_params = dict(zip(names, result.x))
        logger.info(f"Best {metric}: {-result.fun:.4f}")
        logger.info(f"Best parameters: {best_params}")
        return {
            'best_parameters': best_params,
            'best_objective_value': -result.fun,
            'history': self.optimization_history,
            'scipy_result': result
        }

    # ==================== GLUE Method ====================

    def glue_analysis(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: pd.Series,
            n_samples: int = 1000,
            threshold: float = 0.5,
            metric: str = 'nse',
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1
    ) -> Dict:
        """
        Generalized Likelihood Uncertainty Estimation (GLUE).
        Sinh n_samples bộ tham số LHS, chạy song song, lọc behavioral.

        Returns:
            all_results, behavioral_results, behavioral_ratio,
            parameter_ranges, threshold
        """
        logger.info(f"Starting GLUE analysis with {n_samples} samples")

        param_names = list(param_ranges.keys())
        samples_df = self.analysis._generate_samples(
            param_ranges, n_samples, method='lhs'
        )
        param_sets = [
            {name: [(float(row[name]), 'v')] for name in param_names}
            for row in samples_df.to_dict('records')
        ]

        # run_batch tự gọi setup_parallel nếu chưa có worker dirs
        scores = self._manager.run_batch(
            param_sets, observed_series, metric, reach_id, output_variable
        )

        results_df = samples_df.copy()
        results_df[metric] = scores

        behavioral_mask = results_df[metric] >= threshold
        behavioral_df = results_df[behavioral_mask]
        n_behavioral = len(behavioral_df)
        logger.info(
            f"GLUE: {n_behavioral}/{n_samples} behavioral sets "
            f"({100 * n_behavioral / n_samples:.1f}%)"
        )

        return {
            'all_results': results_df,
            'behavioral_results': behavioral_df,
            'behavioral_ratio': n_behavioral / n_samples,
            'parameter_ranges': param_ranges,
            'threshold': threshold
        }

    # ==================== Unified Workflow ====================

    def analyze(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: pd.Series,
            n_samples: int = 1000,
            threshold: float = 0.5,
            metric: str = 'nse',
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            sensitivity_method: str = 'spearman'
    ) -> Dict:
        """
        Workflow hoàn chỉnh: GLUE parallel -> best params -> sensitivity.
        Chỉ chạy SWAT dung n_samples lan, khong chay them cho sensitivity.

        Returns:
            best_params, best_score, all_results, behavioral_results,
            behavioral_ratio, sensitivity, performance
        """
        logger.info(
            f"SpySWAT analyze: {n_samples} samples, "
            f"{self.project.WorkingFolder.n_parallel} workers, metric={metric}"
        )

        # Buoc 1+2+3: GLUE parallel
        glue_result = self.glue_analysis(
            param_ranges=param_ranges,
            observed_series=observed_series,
            n_samples=n_samples,
            threshold=threshold,
            metric=metric,
            output_variable=output_variable,
            reach_id=reach_id
        )
        all_results = glue_result['all_results']

        # Buoc 3: Best params
        best_idx = all_results[metric].idxmax()
        best_row = all_results.loc[best_idx]
        best_params = {
            name: [(float(best_row[name]), 'v')]
            for name in list(param_ranges.keys())
        }
        best_score = float(best_row[metric])
        logger.info(f"Best {metric} = {best_score:.4f}")

        # Buoc 4: Sensitivity tu cung ket qua (0 SWAT runs them)
        sensitivity = self.analysis.sensitivity_from_results(
            all_results, metric=metric,
            param_names=list(param_ranges.keys()),
            method=sensitivity_method
        )

        # Buoc 5: Danh gia performance voi best params
        self._manager.run_iteration(
            best_params, observed_series, metric, reach_id, output_variable
        )
        sim_best = self.project.Output.read_rch(
            columns=['RCH', 'MON', output_variable], reach_id=reach_id
        )[output_variable]

        # Align obs va sim theo DatetimeIndex
        date_range = self.project.get_date_range(freq='D')
        sim_best = sim_best.reset_index(drop=True)
        if len(sim_best) == len(date_range):
            sim_best.index = date_range
        common = observed_series.index.intersection(sim_best.index)
        obs_a  = observed_series.loc[common]
        sim_a  = sim_best.loc[common]

        performance = self.analysis.evaluate_performance(obs_a, sim_a)

        logger.info(f"Sensitivity top param: {sensitivity.iloc[0]['parameter']}")
        logger.info(f"Performance: {performance}")

        return {
            'best_params':         best_params,
            'best_score':          best_score,
            'all_results':         all_results,
            'behavioral_results':  glue_result['behavioral_results'],
            'behavioral_ratio':    glue_result['behavioral_ratio'],
            'sensitivity':         sensitivity,
            'performance':         performance
        }
