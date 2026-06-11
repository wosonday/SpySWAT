"""
Calibration algorithms for SWAT model
"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Callable
import logging
from scipy.optimize import minimize, differential_evolution

from spyswat.swat_calib.calibration import CalibrationManager
logger = logging.getLogger(__name__)


class SWATCalibration:
    def __init__(self, project, analysis=None):
        self.project = project
        self.analysis = analysis or SWATAnalysis(project)
        self._manager = CalibrationManager(project)
        self.optimization_history = []

    # ==================== Objective Functions ====================
    def create_objective_function(
            self,
            observed_series: pd.Series,
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            metric: str = 'nse',
            maximize: bool = True
    ) -> Callable:
        """
        Create objective function for optimization
        Args:
            observed_series: Observed data
            output_variable: SWAT output variable
            reach_id: Reach ID
            metric: Metric to optimize ('nse', 'rmse', etc.)
            maximize: True for maximization, False for minimization

        Returns:
            Objective function
        """

        def objective(params_array, param_names):
            """Objective function for optimization"""
            # Convert array to dict
            params = {name: val for name, val in zip(param_names, params_array)}

            try:
                # Update parameters
                self.project.update_parameters(params)

                # Run simulation
                self.project.run(clear_output_cache=True)

                # Get simulated output
                sim_df = self.project.output.read_reach(reach_id=reach_id)
                sim_series = sim_df[output_variable]

                # Calculate metric
                stats = self.analysis.calculate_statistics(
                        observed_series, sim_series, metrics=[metric]
                )
                value = stats[metric]

                # Record history
                result = params.copy()
                result['objective_value'] = value
                result['iteration'] = len(self.optimization_history) + 1
                self.optimization_history.append(result)

                logger.info(f"Iteration {len(self.optimization_history)}: {metric}={value:.4f}")

                # Return negative for maximization (optimizers minimize)
                return -value if maximize else value

            except Exception as e:
                logger.error(f"Error in objective function: {e}")
                return 1e10 if not maximize else -1e10
        return objective

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
            self.optimization_history.append({
                'params': params, 'score': score
                })

            # scipy minimize → nên trả về -score nếu metric cần maximize
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
        Generalized Likelihood Uncertainty Estimation (GLUE)

        Args:
            param_ranges: Parameter ranges
            observed_series: Observed data
            n_samples: Number of Monte Carlo samples
            threshold: Behavioral threshold for metric
            metric: Performance metric
            output_variable: Output variable
            reach_id: Reach ID

        Returns:
            Dictionary with behavioral parameters and uncertainty bounds
        """
        logger.info(f"Starting GLUE analysis with {n_samples} samples")

        # Sinh LHS samples (trả về DataFrame)
        param_names = list(param_ranges.keys())
        samples_df = self.analysis._generate_samples(
            param_ranges, n_samples, method='lhs'
        )
        # Chuyển sang format run_batch: [{'CN2': [(val, 'v')], ...}, ...]
        param_sets = [
            {name: [(float(row[name]), 'v')] for name in param_names}
            for row in samples_df.to_dict('records')
        ]

        # Chạy song song qua CalibrationManager.run_batch
        self._manager.setup_parallel(overwrite=False)
        scores = self._manager.run_batch(
            param_sets, observed_series, metric, reach_id, output_variable
        )

        # Tổng hợp kết quả
        results_df = samples_df.copy()
        results_df[metric] = scores

        # Lọc behavioral parameter sets
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
        Workflow hoàn chỉnh: GLUE parallel → best params → sensitivity.
        Chỉ chạy SWAT đúng n_samples lần, không chạy thêm cho sensitivity.

        Luồng:
            1. Sinh n_samples bộ tham số (LHS)
            2. Chạy song song qua n_parallel workers
            3. Tính scores → best_params
            4. Tính sensitivity từ cùng kết quả (Spearman/PRCC)
            5. Đánh giá hiệu suất với best_params

        Args:
            param_ranges:       {param_name: (min, max)}
            observed_series:    Chuỗi quan trắc (DatetimeIndex)
            n_samples:          Số mẫu Monte Carlo (khuyến nghị 500–2000)
            threshold:          Ngưỡng behavioral (ví dụ NSE >= 0.5)
            metric:             Metric tối ưu ('nse', 'kge', 'r2')
            output_variable:    Biến output SWAT
            reach_id:           ID reach
            sensitivity_method: 'spearman' hoặc 'prcc'

        Returns:
            Dict:
                'best_params'      : Dict tham số tốt nhất
                'best_score'       : Giá trị metric tốt nhất
                'all_results'      : DataFrame toàn bộ kết quả
                'behavioral_results': DataFrame các bộ tham số behavioral
                'behavioral_ratio' : Tỉ lệ behavioral
                'sensitivity'      : DataFrame sensitivity indices
                'performance'      : Dict đánh giá hiệu suất (Moriasi 2007)
        """
        logger.info(
            f"SpySWAT analyze: {n_samples} samples, "
            f"{self.project.WorkingFolder.n_parallel} workers, metric={metric}"
        )

        # Bước 1+2+3: GLUE parallel
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

        # Bước 3: Best params
        best_idx = all_results[metric].idxmax()
        best_row = all_results.loc[best_idx]
        best_params = {
            name: [(float(best_row[name]), 'v')]
            for name in list(param_ranges.keys())
        }
        best_score = float(best_row[metric])
        logger.info(f"Best {metric} = {best_score:.4f}")

        # Bước 4: Sensitivity từ cùng kết quả
        sensitivity = self.analysis.sensitivity_from_results(
            all_results, metric=metric,
            param_names=list(param_ranges.keys()),
            method=sensitivity_method
        )

        # Bước 5: Đánh giá performance với best params
        self._manager.run_iteration(
            best_params, observed_series, metric, reach_id, output_variable
        )
        sim_best = self.project.Output.read_rch(
            columns=['RCH', 'MON', output_variable], reach_id=reach_id
        )[output_variable]
        obs_a, sim_a = self._manager._align_series(observed_series, sim_best)
        performance = self.analysis.evaluate_performance(obs_a, sim_a)

        logger.info(f"Sensitivity top param: {sensitivity.iloc[0]['parameter']}")
        logger.info(f"Performance: {performance}")

        return {
            'best_params':        best_params,
            'best_score':         best_score,
            'all_results':        all_results,
            'behavioral_results': glue_result['behavioral_results'],
            'behavioral_ratio':   glue_result['behavioral_ratio'],
            'sensitivity':        sensitivity,
            'performance':        performance
        }

    # ==================== Particle Swarm Optimization ====================

    def _particle_swarm_optimization(
            self,
            objective_func: Callable,
            bounds: list,
            max_iter: int = 100,
            n_particles: int = 30,
            w: float = 0.7,
            c1: float = 1.5,
            c2: float = 1.5
    ):
        """
        Particle Swarm Optimization implementation

        Args:
            objective_func: Objective function to minimize
            bounds: List of (min, max) tuples
            max_iter: Maximum iterations
            n_particles: Number of particles
            w: Inertia weight
            c1: Cognitive parameter
            c2: Social parameter
        """
        n_dims = len(bounds)

        # Initialize particles
        particles = np.random.uniform(
                low=[b[0] for b in bounds],
                high=[b[1] for b in bounds],
                size=(n_particles, n_dims)
        )

        velocities = np.zeros((n_particles, n_dims))

        # Evaluate initial positions
        fitness = np.array([objective_func(p) for p in particles])

        # Initialize best positions
        p_best = particles.copy()
        p_best_fitness = fitness.copy()

        g_best_idx = np.argmin(fitness)
        g_best = particles[g_best_idx].copy()
        g_best_fitness = fitness[g_best_idx]

        # PSO main loop
        for iteration in range(max_iter):
            for i in range(n_particles):
                # Update velocity
                r1, r2 = np.random.random(2)
                cognitive = c1 * r1 * (p_best[i] - particles[i])
                social = c2 * r2 * (g_best - particles[i])
                velocities[i] = w * velocities[i] + cognitive + social

                # Update position
                particles[i] = particles[i] + velocities[i]

                # Apply bounds
                particles[i] = np.clip(
                        particles[i],
                        [b[0] for b in bounds],
                        [b[1] for b in bounds]
                )

                # Evaluate fitness
                fitness[i] = objective_func(particles[i])

                # Update personal best
                if fitness[i] < p_best_fitness[i]:
                    p_best[i] = particles[i].copy()
                    p_best_fitness[i] = fitness[i]

                # Update global best
                if fitness[i] < g_best_fitness:
                    g_best = particles[i].copy()
                    g_best_fitness = fitness[i]

            if (iteration + 1) % 10 == 0:
                logger.info(f"PSO Iteration {iteration + 1}: "
                            f"Best fitness = {g_best_fitness:.4f}")

        # Create result object similar to scipy.optimize
        class OptimizeResult:
            def __init__(self, x, fun):
                self.x = x
                self.fun = fun

        return OptimizeResult(g_best, g_best_fitness)

