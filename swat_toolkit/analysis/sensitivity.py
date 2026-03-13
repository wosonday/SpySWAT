"""
Sensitivity analysis for SWAT parameters
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SWATSensitivity:
    def __init__(self, project, analysis=None):
        self.project = project
        if analysis is None:
            from .statistics import SWATAnalysis
            self.analysis = SWATAnalysis(project)
        else:
            self.analysis = analysis

    # ==================== One-At-A-Time (OAT) ====================

    def one_at_a_time(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            n_steps: int = 10,
            baseline_params: Optional[Dict] = None,
            observed_series: Optional[pd.Series] = None,
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            metric: str = 'nse'
    ) -> pd.DataFrame:
        # Set baseline
        if baseline_params is None:
            baseline_params = {
                name: (vmin + vmax) / 2
                for name, (vmin, vmax) in param_ranges.items()
            }

        results = []

        for param_name in param_ranges.keys():
            logger.info(f"Analyzing parameter: {param_name}")

            vmin, vmax = param_ranges[param_name]
            param_values = np.linspace(vmin, vmax, n_steps)

            for value in param_values:
                # Create parameter set
                params = baseline_params.copy()
                params[param_name] = value

                try:
                    # Update and run
                    self.project.update_parameters(params)
                    self.project.run(clear_output_cache=True)

                    # Get output
                    sim_df = self.project.output.read_reach(reach_id=reach_id)
                    sim_series = sim_df[output_variable]

                    # Calculate metric
                    if observed_series is not None:
                        stats = self.analysis.calculate_statistics(
                                observed_series, sim_series, metrics=[metric]
                        )
                        metric_value = stats[metric]
                    else:
                        metric_value = sim_series.mean()

                    results.append({
                        'parameter': param_name,
                        'value': value,
                        'metric': metric_value,
                        'output_mean': sim_series.mean(),
                        'output_std': sim_series.std()
                    })

                except Exception as e:
                    logger.error(f"Error with {param_name}={value}: {e}")
                    continue

        results_df = pd.DataFrame(results)

        # Calculate sensitivity indices
        sensitivity_indices = self._calculate_oat_sensitivity(results_df)

        return results_df, sensitivity_indices

    def _calculate_oat_sensitivity(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate sensitivity indices from OAT results"""
        sensitivity = []

        for param in results_df['parameter'].unique():
            param_data = results_df[results_df['parameter'] == param]

            # Calculate range and standard deviation
            metric_range = param_data['metric'].max() - param_data['metric'].min()
            metric_std = param_data['metric'].std()

            sensitivity.append({
                'parameter': param,
                'metric_range': metric_range,
                'metric_std': metric_std,
                'sensitivity_index': metric_range / metric_std if metric_std > 0 else 0
            })

        return pd.DataFrame(sensitivity).sort_values('sensitivity_index', ascending=False)

    # ==================== Morris Method ====================

    def morris_method(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            n_trajectories: int = 10,
            n_levels: int = 4,
            observed_series: Optional[pd.Series] = None,
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            metric: str = 'nse'
    ) -> Dict:
        """
        Morris sensitivity analysis (Elementary Effects)

        Args:
            param_ranges: Parameter ranges
            n_trajectories: Number of trajectories
            n_levels: Number of levels for each parameter
            observed_series: Observed data
            output_variable: Output variable
            reach_id: Reach ID
            metric: Performance metric

        Returns:
            Dictionary with Morris sensitivity indices
        """
        param_names = list(param_ranges.keys())
        n_params = len(param_names)

        # Generate Morris trajectories
        trajectories = self._generate_morris_trajectories(
                param_ranges, n_trajectories, n_levels
        )

        elementary_effects = {name: [] for name in param_names}

        logger.info(f"Running Morris method with {n_trajectories} trajectories")

        for traj_idx, trajectory in enumerate(trajectories):
            logger.info(f"Trajectory {traj_idx + 1}/{n_trajectories}")

            prev_metric = None
            prev_params = None

            for step_params in trajectory:
                try:
                    # Run simulation
                    self.project.update_parameters(step_params)
                    self.project.run(clear_output_cache=True)

                    # Get metric
                    sim_df = self.project.output.read_reach(reach_id=reach_id)
                    sim_series = sim_df[output_variable]

                    if observed_series is not None:
                        stats = self.analysis.calculate_statistics(
                                observed_series, sim_series, metrics=[metric]
                        )
                        current_metric = stats[metric]
                    else:
                        current_metric = sim_series.mean()

                    # Calculate elementary effect
                    if prev_metric is not None:
                        changed_param = self._find_changed_param(prev_params, step_params)
                        if changed_param:
                            delta_param = step_params[changed_param] - prev_params[changed_param]
                            delta_metric = current_metric - prev_metric
                            ee = delta_metric / delta_param
                            elementary_effects[changed_param].append(ee)

                    prev_metric = current_metric
                    prev_params = step_params.copy()

                except Exception as e:
                    logger.error(f"Error in Morris trajectory: {e}")
                    continue

        # Calculate Morris indices
        morris_indices = []
        for param_name in param_names:
            ee_list = elementary_effects[param_name]
            if len(ee_list) > 0:
                mu = np.mean(np.abs(ee_list))
                mu_star = np.mean(np.abs(ee_list))
                sigma = np.std(ee_list)

                morris_indices.append({
                    'parameter': param_name,
                    'mu': mu,
                    'mu_star': mu_star,
                    'sigma': sigma
                })

        results = pd.DataFrame(morris_indices)
        results = results.sort_values('mu_star', ascending=False)

        return {
            'morris_indices': results,
            'elementary_effects': elementary_effects
        }

    def _generate_morris_trajectories(
            self,
            param_ranges: Dict,
            n_trajectories: int,
            n_levels: int
    ) -> List[List[Dict]]:
        """Generate Morris sampling trajectories"""
        param_names = list(param_ranges.keys())
        n_params = len(param_names)
        trajectories = []

        delta = n_levels / (2 * (n_levels - 1))

        for _ in range(n_trajectories):
            # Random base point
            base = np.random.choice(n_levels, n_params) / (n_levels - 1)

            # Random parameter order
            param_order = np.random.permutation(param_names)

            trajectory = []
            current_point = base.copy()

            # Initial point
            params = {}
            for i, pname in enumerate(param_names):
                vmin, vmax = param_ranges[pname]
                params[pname] = vmin + current_point[i] * (vmax - vmin)
            trajectory.append(params)

            # Generate trajectory
            for param_name in param_order:
                param_idx = param_names.index(param_name)
                current_point[param_idx] += delta
                current_point[param_idx] = np.clip(current_point[param_idx], 0, 1)

                params = {}
                for i, pname in enumerate(param_names):
                    vmin, vmax = param_ranges[pname]
                    params[pname] = vmin + current_point[i] * (vmax - vmin)
                trajectory.append(params)

            trajectories.append(trajectory)

        return trajectories

    def _find_changed_param(self, params1: Dict, params2: Dict) -> Optional[str]:
        """Find which parameter changed between two parameter sets"""
        for key in params1.keys():
            if params1[key] != params2[key]:
                return key
        return None
