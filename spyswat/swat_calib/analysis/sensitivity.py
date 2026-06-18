"""Sensitivity analysis for SWAT parameters"""
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
        # CalibrationManager cho parallel execution
        from spyswat.swat_calib.calibration import CalibrationManager
        self._manager = CalibrationManager(project)

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
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        One-At-a-Time sensitivity analysis (parallel).
        Tất cả (param, value) combinations được chạy song song qua run_batch.
        """
        if baseline_params is None:
            baseline_params = {
                name: (vmin + vmax) / 2
                for name, (vmin, vmax) in param_ranges.items()
            }

        # Tập hợp tất cả configs cần chạy
        all_configs: List[Tuple[str, float, dict]] = []
        for param_name in param_ranges:
            vmin, vmax = param_ranges[param_name]
            for value in np.linspace(vmin, vmax, n_steps):
                params = {k: [(v, 'v')] for k, v in baseline_params.items()}
                params[param_name] = [(float(value), 'v')]
                all_configs.append((param_name, float(value), params))

        logger.info(
            f"OAT: {len(all_configs)} runs, "
            f"{self.project.WorkingFolder.n_parallel} workers"
        )

        if observed_series is not None:
            # Parallel: chạy tất cả qua run_batch
            self._manager.setup_parallel(overwrite=False)
            param_sets = [cfg[2] for cfg in all_configs]
            scores = self._manager.run_batch(
                param_sets, observed_series, metric, reach_id, output_variable
            )
        else:
            # Không có quan trắc: chạy tuần tự, dùng mean output
            scores = []
            for param_name, value, params in all_configs:
                try:
                    self.project.HRU.update_params(params)
                    self.project.run()
                    sim = self.project.Output.read_rch(
                        columns=['RCH', 'MON', output_variable],
                        reach_id=reach_id
                    )[output_variable]
                    scores.append(float(sim.mean()))
                except Exception as e:
                    logger.error(f"OAT {param_name}={value}: {e}")
                    scores.append(float('nan'))

        results = [
            {'parameter': name, 'value': value, 'metric': score}
            for (name, value, _), score in zip(all_configs, scores)
        ]
        results_df = pd.DataFrame(results)
        sensitivity_indices = self._calculate_oat_sensitivity(results_df)
        return results_df, sensitivity_indices

    def _calculate_oat_sensitivity(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """Tính sensitivity indices từ kết quả OAT."""
        sensitivity = []
        for param in results_df['parameter'].unique():
            d = results_df[results_df['parameter'] == param]['metric'].dropna()
            metric_range = d.max() - d.min()
            metric_std = d.std()
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
            metric: str = 'nse',
            seed: Optional[int] = None,
    ) -> Dict:
        """
        Morris sensitivity analysis (Elementary Effects).
        Các trajectory được đánh giá song song qua run_batch.
        """
        param_names = list(param_ranges.keys())
        trajectories = self._generate_morris_trajectories(
            param_ranges, n_trajectories, n_levels, seed=seed
        )

        # Flatten tất cả trajectory steps → chạy parallel
        all_steps: List[dict] = []   # mỗi phần tử là param_set
        step_index: List[Tuple[int, int]] = []  # (traj_idx, step_idx)

        for t_idx, trajectory in enumerate(trajectories):
            for s_idx, step_params in enumerate(trajectory):
                param_set = {k: [(float(v), 'v')] for k, v in step_params.items()}
                all_steps.append(param_set)
                step_index.append((t_idx, s_idx))

        logger.info(
            f"Morris: {n_trajectories} trajectories × {len(trajectories[0])} steps "
            f"= {len(all_steps)} runs, {self.project.WorkingFolder.n_parallel} workers"
        )

        # Chạy song song
        if observed_series is not None:
            self._manager.setup_parallel(overwrite=False)
            all_scores = self._manager.run_batch(
                all_steps, observed_series, metric, reach_id, output_variable
            )
        else:
            all_scores = []
            for ps in all_steps:
                try:
                    self.project.HRU.update_params(ps)
                    self.project.run()
                    sim = self.project.Output.read_rch(
                        columns=['RCH', 'MON', output_variable],
                        reach_id=reach_id
                    )[output_variable]
                    all_scores.append(float(sim.mean()))
                except Exception as e:
                    logger.error(f"Morris step error: {e}")
                    all_scores.append(float('nan'))

        # Tái cấu trúc scores theo trajectory
        traj_metrics: Dict[int, List[float]] = {i: [] for i in range(n_trajectories)}
        traj_params: Dict[int, List[dict]] = {i: [] for i in range(n_trajectories)}
        for (t_idx, _), score, ps in zip(step_index, all_scores, all_steps):
            traj_metrics[t_idx].append(score)
            traj_params[t_idx].append({k: v[0][0] for k, v in ps.items()})

        # Tính Elementary Effects
        elementary_effects = {name: [] for name in param_names}
        for t_idx in range(n_trajectories):
            metrics = traj_metrics[t_idx]
            params_list = traj_params[t_idx]
            for s in range(1, len(metrics)):
                changed = self._find_changed_param(params_list[s-1], params_list[s])
                if changed and not np.isnan(metrics[s]) and not np.isnan(metrics[s-1]):
                    delta_p = params_list[s][changed] - params_list[s-1][changed]
                    if delta_p != 0:
                        ee = (metrics[s] - metrics[s-1]) / delta_p
                        elementary_effects[changed].append(ee)

        morris_indices = []
        for name in param_names:
            ee_list = elementary_effects[name]
            if ee_list:
                morris_indices.append({
                    'parameter': name,
                    'mu': float(np.mean(ee_list)),
                    'mu_star': float(np.mean(np.abs(ee_list))),
                    'sigma': float(np.std(ee_list))
                })

        results = pd.DataFrame(morris_indices).sort_values('mu_star', ascending=False)
        return {'morris_indices': results, 'elementary_effects': elementary_effects}

    def _generate_morris_trajectories(
            self,
            param_ranges: Dict,
            n_trajectories: int,
            n_levels: int,
            seed: Optional[int] = None,
    ) -> List[List[Dict]]:
        """Sinh Morris sampling trajectories."""
        param_names = list(param_ranges.keys())
        n_params = len(param_names)
        delta = n_levels / (2 * (n_levels - 1))
        trajectories = []
        rng = np.random.default_rng(seed)

        for _ in range(n_trajectories):
            base = rng.choice(n_levels, n_params) / (n_levels - 1)
            param_order = rng.permutation(param_names)
            trajectory = []
            current = base.copy()

            params = {
                pname: float(param_ranges[pname][0] + current[i] * (
                    param_ranges[pname][1] - param_ranges[pname][0]
                ))
                for i, pname in enumerate(param_names)
            }
            trajectory.append(params)

            for param_name in param_order:
                idx = param_names.index(param_name)
                current[idx] = np.clip(current[idx] + delta, 0, 1)
                params = {
                    pname: float(param_ranges[pname][0] + current[i] * (
                        param_ranges[pname][1] - param_ranges[pname][0]
                    ))
                    for i, pname in enumerate(param_names)
                }
                trajectory.append(params)
            trajectories.append(trajectory)

        return trajectories

    def _find_changed_param(self, params1: Dict, params2: Dict) -> Optional[str]:
        """Tìm tham số thay đổi giữa 2 bộ tham số."""
        for key in params1:
            if params1[key] != params2[key]:
                return key
        return None

    # ==================== SALib helpers ====================

    def _build_problem(self, param_ranges: Dict) -> dict:
        """Chuyển param_ranges sang SALib problem dict."""
        return {
            'num_vars': len(param_ranges),
            'names':    list(param_ranges.keys()),
            'bounds':   [list(v) for v in param_ranges.values()],
        }

    def _X_to_param_sets(self, X: 'np.ndarray', param_names: list) -> list:
        """Chuyển ma trận mẫu SALib (n_runs × n_params) sang List[dict] cho run_batch."""
        return [
            {name: [(float(X[i, j]), 'v')] for j, name in enumerate(param_names)}
            for i in range(len(X))
        ]

    # ==================== Morris (SALib) ====================

    def morris_salib(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: 'pd.Series',
            n_trajectories: int = 10,
            num_levels: int = 4,
            optimal_trajectories: 'Optional[int]' = None,
            num_resamples: int = 1000,
            conf_level: float = 0.95,
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            metric: str = 'nse',
    ) -> 'pd.DataFrame':
        """
        Morris Elementary Effects sensitivity analysis qua SALib.

        Sinh ma trận mẫu bằng SALib (Morris 1991), chạy song song
        qua run_batch, phân tích bằng SALib morris.analyze với
        bootstrap confidence intervals.

        Tổng số lần chạy SWAT = n_trajectories × (k + 1)
        với k = số tham số.

        Args:
            param_ranges:         {param: (min, max)}
            observed_series:      Chuỗi quan trắc (DatetimeIndex)
            n_trajectories:       Số trajectory r (khuyến nghị 10–50)
            num_levels:           Số level p (thường 4)
            optimal_trajectories: Dùng thuật toán chọn trajectory tối ưu
                                  (None = tắt, chậm hơn nhưng tốt hơn)
            num_resamples:        Bootstrap resamples để tính CI
            conf_level:           Mức tin cậy cho CI (mặc định 0.95)
            output_variable:      Biến output SWAT
            reach_id:             ID reach
            metric:               Metric đánh giá

        Returns:
            DataFrame: param | mu | mu_star | sigma | ci_95
        """
        try:
            from SALib.sample import morris as morris_sample
            from SALib.analyze import morris as morris_analyze
        except ImportError:
            raise ImportError(
                "SALib is not installed. Run: pip install SALib"
            )

        problem = self._build_problem(param_ranges)
        param_names = problem['names']
        k = problem['num_vars']

        # --- Sinh ma trận mẫu ---
        X = morris_sample.sample(
            problem,
            N=n_trajectories,
            num_levels=num_levels,
            optimal_trajectories=optimal_trajectories,
        )
        n_runs = len(X)
        logger.info(
            f"Morris (SALib): {n_trajectories} trajectories × {k+1} steps "
            f"= {n_runs} runs, {self.project.WorkingFolder.n_parallel} workers"
        )

        # --- Chạy song song qua run_batch ---
        self._manager.setup_parallel(overwrite=False)
        param_sets = self._X_to_param_sets(X, param_names)
        Y = np.array(
            self._manager.run_batch(
                param_sets, observed_series, metric, reach_id, output_variable
            ),
            dtype=float,
        )

        # Thay NaN/Inf bằng bad score để SALib không lỗi
        bad = -1.0 if metric in ('nse', 'kge', 'r2') else 1e6
        Y = np.where(np.isfinite(Y), Y, bad)

        # --- Phân tích Morris qua SALib ---
        Si = morris_analyze.analyze(
            problem, X, Y,
            conf_level=conf_level,
            print_to_console=False,
            num_resamples=num_resamples,
        )

        results = pd.DataFrame({
            'parameter': param_names,
            'mu':        Si['mu'],
            'mu_star':   Si['mu_star'],
            'sigma':     Si['sigma'],
            'ci_95':     Si['mu_star_conf'],
        }).sort_values('mu_star', ascending=False).reset_index(drop=True)

        logger.info(
            f"Morris top param: '{results.iloc[0]['parameter']}' "
            f"(μ*={results.iloc[0]['mu_star']:.4f})"
        )
        return results

    # ==================== Sobol (SALib) ====================

    def sobol_method(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: 'pd.Series',
            N: int = 1000,
            calc_second_order: bool = False,
            num_resamples: int = 1000,
            conf_level: float = 0.95,
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            metric: str = 'nse',
    ) -> 'pd.DataFrame':
        """
        Sobol variance-based sensitivity analysis qua SALib.

        Tổng số lần chạy SWAT = N × (k + 2) nếu calc_second_order=False,
        hoặc N × (2k + 2) nếu True. Với k=5 tham số và N=1000 → 7000 runs.

        CẢNH BÁO: Đắt hơn Morris nhiều. Dùng cho báo cáo học thuật
        khi cần chỉ số S1 (first-order) và ST (total-order).

        Args:
            param_ranges:        {param: (min, max)}
            observed_series:     Chuỗi quan trắc (DatetimeIndex)
            N:                   Base sample size (khuyến nghị 512–2048)
            calc_second_order:   Tính S2 (tương tác cặp) — tăng chi phí 2×
            num_resamples:       Bootstrap resamples để tính CI
            conf_level:          Mức tin cậy
            output_variable:     Biến output SWAT
            reach_id:            ID reach
            metric:              Metric đánh giá

        Returns:
            DataFrame: param | S1 | S1_conf | ST | ST_conf | interaction
        """
        try:
            try:
                from SALib.sample import sobol as saltelli  # SALib >= 1.4
            except ImportError:
                from SALib.sample import saltelli         # SALib < 1.4
            from SALib.analyze import sobol as sobol_analyze
        except ImportError:
            raise ImportError(
                "SALib is not installed. Run: pip install SALib"
            )

        problem = self._build_problem(param_ranges)
        param_names = problem['names']
        k = problem['num_vars']

        # --- Sinh ma trận Saltelli ---
        X = saltelli.sample(problem, N=N, calc_second_order=calc_second_order)
        n_runs = len(X)
        logger.info(
            f"Sobol (SALib): N={N}, k={k} → {n_runs} runs, "
            f"{self.project.WorkingFolder.n_parallel} workers"
        )

        # --- Chạy song song qua run_batch ---
        self._manager.setup_parallel(overwrite=False)
        param_sets = self._X_to_param_sets(X, param_names)
        Y = np.array(
            self._manager.run_batch(
                param_sets, observed_series, metric, reach_id, output_variable
            ),
            dtype=float,
        )

        bad = -1.0 if metric in ('nse', 'kge', 'r2') else 1e6
        Y = np.where(np.isfinite(Y), Y, bad)

        # --- Phân tích Sobol ---
        Si = sobol_analyze.analyze(
            problem, Y,
            calc_second_order=calc_second_order,
            conf_level=conf_level,
            num_resamples=num_resamples,
            print_to_console=False,
        )

        results = pd.DataFrame({
            'parameter': param_names,
            'S1':        Si['S1'],
            'S1_conf':   Si['S1_conf'],
            'ST':        Si['ST'],
            'ST_conf':   Si['ST_conf'],
        })
        results['interaction'] = results['ST'] - results['S1']
        results = results.sort_values('ST', ascending=False).reset_index(drop=True)

        logger.info(
            f"Sobol top param (ST): '{results.iloc[0]['parameter']}' "
            f"(ST={results.iloc[0]['ST']:.4f})"
        )
        return results

    # ==================== Visualization ====================

    def plot_morris(
            self,
            results_morris: 'pd.DataFrame',
            title: str = 'Morris Sensitivity Analysis',
            save_path: 'Optional[str]' = None,
    ):
        """
        Vẽ 2 biểu đồ Morris:
          - Trái: bar chart μ* với 95% CI (xếp hạng độ nhạy)
          - Phải: μ*–σ scatter (phát hiện tương tác phi tuyến)

        Cách đọc biểu đồ μ*–σ:
          - Điểm gần đường σ=μ*  → tương tác mạnh / phi tuyến
          - Điểm gần trục hoành  → tác động tuyến tính, độc lập

        Args:
            results_morris: DataFrame từ morris_salib() hoặc morris_method()
                            (cần cột: parameter, mu_star, sigma;
                             cột ci_95 tùy chọn)
            title:          Tiêu đề chung
            save_path:      Đường dẫn lưu file PNG (None = không lưu)
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib is not installed. Run: pip install matplotlib")

        df = results_morris.copy()
        has_ci = 'ci_95' in df.columns

        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        fig.suptitle(title, fontsize=13, fontweight='bold', y=1.01)

        # ── Biểu đồ 1: Bar chart μ* ──────────────────────────────
        ax1 = axes[0]
        colors = ['#1D9E75' if i == 0 else '#5BC8A8' for i in range(len(df))]
        ax1.barh(
            df['parameter'], df['mu_star'],
            xerr=df['ci_95'] if has_ci else None,
            color=colors,
            ecolor='#085041', capsize=4, height=0.6,
        )
        ax1.set_xlabel('μ* (Morris Elementary Effect)', fontsize=10)
        ax1.set_title('Parameter Sensitivity Ranking', fontsize=11)
        ax1.invert_yaxis()
        ax1.axvline(0, color='gray', lw=0.8, ls='--')
        ax1.tick_params(axis='y', labelsize=9)

        # ── Biểu đồ 2: μ*–σ scatter ──────────────────────────────
        ax2 = axes[1]
        ax2.scatter(df['mu_star'], df['sigma'], s=80, color='#534AB7', zorder=3)
        for _, row in df.iterrows():
            ax2.annotate(
                row['parameter'],
                (row['mu_star'], row['sigma']),
                textcoords='offset points', xytext=(6, 3), fontsize=9,
            )

        lim = max(df['mu_star'].max(), df['sigma'].max()) * 1.15
        ax2.plot([0, lim], [0, lim], 'k--', lw=0.8, alpha=0.4, label='σ = μ*')
        ax2.set_xlim(left=0)
        ax2.set_ylim(bottom=0)
        ax2.set_xlabel('μ* — Overall influence', fontsize=10)
        ax2.set_ylabel('σ — Non-linearity / interaction', fontsize=10)
        ax2.set_title('Morris μ*–σ Plot', fontsize=11)
        ax2.legend(fontsize=9)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"Morris plot saved: {save_path}")

        plt.show()
        return fig

    def export_results(
            self,
            results_morris: 'pd.DataFrame',
            results_sobol: 'Optional[pd.DataFrame]' = None,
            save_path: str = 'sensitivity_results.csv',
    ) -> 'pd.DataFrame':
        """
        Kết hợp kết quả Morris + Sobol (nếu có) và xuất CSV.

        Args:
            results_morris: DataFrame từ morris_salib()
            results_sobol:  DataFrame từ sobol_method() (tùy chọn)
            save_path:      Đường dẫn file CSV

        Returns:
            DataFrame tổng hợp
        """
        combined = results_morris.copy()

        if results_sobol is not None:
            sobol_cols = results_sobol.set_index('parameter')[
                ['S1', 'ST', 'interaction']
            ]
            combined = combined.set_index('parameter').join(
                sobol_cols, how='left'
            ).reset_index()
            combined.rename(
                columns={'index': 'parameter'}, inplace=True
            )

        combined.to_csv(save_path, index=False, float_format='%.4f')
        logger.info(f"Sensitivity results exported: {save_path}")
        print(combined.to_string(index=False))
        return combined
