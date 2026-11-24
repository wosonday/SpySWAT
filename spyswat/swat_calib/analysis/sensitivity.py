"""Sensitivity analysis for SWAT parameters"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging

from spyswat.swat_calib.analysis.algorithms.dds import (
    _MISSING, _reported, _resolve_observed,
)


logger = logging.getLogger(__name__)


def _resolve_sens_observed(observed, observed_series, reach_id, output_variable, outputs):
    """Resolve sensitivity args to ``(observed, outputs, single_site)``.

    ``observed`` may be absent/None for the sequential (mean output) path, in which
    case ``single_site`` is the one ``(variable, reach)`` to evaluate.  When
    ``observed`` is present, ``single_site`` is ``None``.
    """
    observed, outputs = _resolve_observed(
        observed, observed_series, reach_id, output_variable, outputs, stacklevel=4
    )
    if observed is _MISSING:
        observed = None
    if observed is None:
        if outputs is None:
            single = ("FLOW_OUTcms", 1)
        else:
            sites = [(v, r) for v in sorted(outputs) for r in outputs[v]]
            if len(sites) != 1:
                raise ValueError(
                    "sequential sensitivity (no observations) needs exactly one output "
                    f"site, got {len(sites)} from {outputs!r}."
                )
            single = sites[0]
        return None, outputs, single
    return observed, outputs, None


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
        # Raw samples / scores (NaN = failed run) of the last Sobol / Morris (SALib) batch,
        # kept so that an expensive batch is never lost when the analysis aborts.
        self.last_samples: Optional[np.ndarray] = None
        self.last_scores: Optional[np.ndarray] = None

    @staticmethod
    def _log_failures(label: str, scores) -> int:
        """Log ``failed X of N runs`` (WARNING when X > 0); return X. NaN/inf count as failed."""
        arr = np.asarray(scores, dtype=float)
        n_failed = int((~np.isfinite(arr)).sum())
        msg = f"{label}: failed {n_failed} of {arr.size} runs"
        if n_failed:
            logger.warning(msg)
        else:
            logger.info(msg)
        return n_failed

    def _sequential_mean(self, params: dict, output_variable: str, reach_id: int) -> float:
        """One sequential run (no observations) returning the mean output; inputs are
        backed up before and restored after, so the user's TxtInOut is left untouched."""
        key = f"mean_{output_variable}"
        try:
            with self._manager.sandbox():               # stale output.rch = failed run
                self._manager._apply_and_run(params)
                sim = self.project.Output.read_rch(
                    columns=['RCH', 'MON', output_variable], reach_id=reach_id
                )[output_variable]
            value = float(sim.mean())
        except Exception as exc:
            self._manager.record_run(
                params, None, status="failed", error=str(exc), sim=None,
                mode="sensitivity", reach_id=reach_id, output_variable=output_variable,
            )
            raise
        self._manager.record_run(
            params, {key: value}, status="ok", sim=None,
            mode="sensitivity", reach_id=reach_id, output_variable=output_variable,
        )
        return value

    def _batch_scores(self, param_sets, observed, metric, outputs, weights=None,
                      metrics=None, calib_period=None, valid_period=None, step=None,
                      agg=None, store=None) -> np.ndarray:
        """Run a batch and return the ``score`` column as a float array (NaN = failed run)."""
        res = self._manager.run_batch(
            param_sets, observed, _reported(metric, metrics),
            metric=metric, outputs=outputs, weights=weights,
            calib_period=calib_period, valid_period=valid_period,
            step=step, agg=agg, store=store,
        )
        if hasattr(res, 'columns'):
            res = res['score'] if 'score' in res.columns else res[metric]
        return np.asarray(list(res), dtype=float)

    # ==================== One-At-A-Time (OAT) ====================
    def one_at_a_time(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            n_steps: int = 10,
            baseline_params: Optional[Dict] = None,
            observed=_MISSING,
            output_variable=_MISSING,
            reach_id=_MISSING,
            metric: str = 'nse',
            observed_series=_MISSING,
            *,
            outputs=None,
            weights=None,
            metrics=None,
            calib_period=None,
            valid_period=None,
            step=None,
            agg=None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        One-At-a-Time sensitivity analysis (parallel).
        Tất cả (param, value) combinations được chạy song song qua run_batch.
        """
        observed, outputs, seq_site = _resolve_sens_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
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

        if observed is not None:
            # Parallel: chạy tất cả qua run_batch
            self._manager.setup_parallel(overwrite=False)
            param_sets = [cfg[2] for cfg in all_configs]
            scores = self._batch_scores(
                param_sets, observed, metric, outputs, weights=weights,
                metrics=metrics, calib_period=calib_period, valid_period=valid_period,
                step=step, agg=agg,
            )
        else:
            # Không có quan trắc: chạy tuần tự, dùng mean output
            var, reach = seq_site
            scores = []
            for param_name, value, params in all_configs:
                try:
                    scores.append(self._sequential_mean(params, var, reach))
                except Exception as e:
                    logger.error(f"OAT {param_name}={value}: {e}")
                    scores.append(float('nan'))

        n_failed = self._log_failures("OAT", scores)
        if n_failed:
            logger.warning("OAT: failed runs are reported as NaN and excluded from the "
                           "sensitivity of their parameter")
        results = [
            {'parameter': name, 'value': value, 'metric': score}
            for (name, value, _), score in zip(all_configs, scores)
        ]
        results_df = pd.DataFrame(results)
        sensitivity_indices = self._calculate_oat_sensitivity(results_df)
        return results_df, sensitivity_indices

    def _calculate_oat_sensitivity(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """
        Sensitivity indices from OAT results.

        sensitivity_index = metric_range of the parameter's sweep divided by the
        largest metric_range over all parameters (the most influential parameter
        gets 1.0, 0 means no effect); rows are ranked by it. metric_range and
        metric_std are kept, and range_over_std (the former index, which does not
        depend on the size of the effect) is listed for transparency only.
        A parameter with fewer than 2 successful runs gets NaN (and a warning),
        never 0.
        """
        rows = []
        for param in results_df['parameter'].unique():
            d = results_df[results_df['parameter'] == param]['metric'].dropna()
            if len(d) < 2:
                logger.warning(
                    f"OAT: parameter '{param}' has {len(d)} successful run(s); "
                    "sensitivity is NaN"
                )
                rows.append({'parameter': param, 'metric_range': np.nan,
                             'metric_std': np.nan, 'range_over_std': np.nan})
                continue
            metric_range = float(d.max() - d.min())
            metric_std = float(d.std())
            rows.append({
                'parameter': param,
                'metric_range': metric_range,
                'metric_std': metric_std,
                'range_over_std': metric_range / metric_std if metric_std > 0 else 0.0,
            })
        out = pd.DataFrame(rows)
        ranges = out['metric_range']
        top = ranges.max()   # NaN-skipping; NaN when every parameter failed
        if pd.isna(top):
            out['sensitivity_index'] = np.nan
        elif top > 0:
            out['sensitivity_index'] = ranges / top
        else:
            out['sensitivity_index'] = ranges.where(ranges.isna(), 0.0)
        out = out[['parameter', 'metric_range', 'metric_std', 'range_over_std',
                   'sensitivity_index']]
        return out.sort_values('sensitivity_index', ascending=False, na_position='last')

    # ==================== Morris Method ====================
    def morris_method(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            n_trajectories: int = 10,
            n_levels: int = 4,
            observed=_MISSING,
            output_variable=_MISSING,
            reach_id=_MISSING,
            metric: str = 'nse',
            seed: Optional[int] = None,
            observed_series=_MISSING,
            *,
            outputs=None,
            weights=None,
            metrics=None,
            calib_period=None,
            valid_period=None,
            step=None,
            agg=None,
    ) -> Dict:
        """
        Morris sensitivity analysis (Elementary Effects).
        Các trajectory được đánh giá song song qua run_batch.
        """
        observed, outputs, seq_site = _resolve_sens_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
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
        if observed is not None:
            self._manager.setup_parallel(overwrite=False)
            all_scores = self._batch_scores(
                all_steps, observed, metric, outputs, weights=weights,
                metrics=metrics, calib_period=calib_period, valid_period=valid_period,
                step=step, agg=agg,
            )
        else:
            var, reach = seq_site
            all_scores = []
            for ps in all_steps:
                try:
                    all_scores.append(self._sequential_mean(ps, var, reach))
                except Exception as e:
                    logger.error(f"Morris step error: {e}")
                    all_scores.append(float('nan'))

        self._log_failures("Morris", all_scores)

        # Tái cấu trúc scores theo trajectory
        traj_metrics: Dict[int, List[float]] = {i: [] for i in range(n_trajectories)}
        traj_params: Dict[int, List[dict]] = {i: [] for i in range(n_trajectories)}
        for (t_idx, _), score, ps in zip(step_index, all_scores, all_steps):
            traj_metrics[t_idx].append(score)
            traj_params[t_idx].append({k: v[0][0] for k, v in ps.items()})

        # Drop every trajectory that contains a failed run (never substitute a value)
        valid_traj = [t for t in range(n_trajectories)
                      if np.all(np.isfinite(np.asarray(traj_metrics[t], dtype=float)))]
        n_dropped = n_trajectories - len(valid_traj)
        if n_dropped:
            logger.warning(
                f"Morris: dropped {n_dropped} of {n_trajectories} trajectories containing failed runs"
            )
        if len(valid_traj) < 2:
            raise RuntimeError(
                f"Morris: only {len(valid_traj)} of {n_trajectories} trajectories have no "
                f"failed run (need at least 2); dropped {n_dropped}"
            )

        # Tính Elementary Effects
        elementary_effects = {name: [] for name in param_names}
        for t_idx in valid_traj:
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
            observed=_MISSING,
            n_trajectories: int = 10,
            num_levels: int = 4,
            optimal_trajectories: 'Optional[int]' = None,
            num_resamples: int = 1000,
            conf_level: float = 0.95,
            output_variable=_MISSING,
            reach_id=_MISSING,
            metric: str = 'nse',
            observed_series=_MISSING,
            *,
            outputs=None,
            weights=None,
            metrics=None,
            calib_period=None,
            valid_period=None,
            step=None,
            agg=None,
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
        observed, outputs, _ = _resolve_sens_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is None:
            raise TypeError(
                "observed is required for morris_salib: pass a Series or a dict "
                "keyed (variable, reach)."
            )
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
        Y = self._batch_scores(
            param_sets, observed, metric, outputs, weights=weights,
            metrics=metrics, calib_period=calib_period, valid_period=valid_period,
            step=step, agg=agg,
        )

        self.last_samples, self.last_scores = X, Y.copy()
        self._log_failures("Morris (SALib)", Y)

        # Rows come in blocks of k+1 per trajectory: drop every block with a failed run
        # (no substitute value is ever fed to SALib).
        block      = k + 1
        n_traj     = n_runs // block
        ok_rows    = np.isfinite(Y).reshape(n_traj, block).all(axis=1)
        n_dropped  = int((~ok_rows).sum())
        if n_dropped:
            logger.warning(
                f"Morris (SALib): dropped {n_dropped} of {n_traj} trajectories containing failed runs"
            )
        if int(ok_rows.sum()) < 2:
            raise RuntimeError(
                f"Morris (SALib): only {int(ok_rows.sum())} of {n_traj} trajectories have no "
                f"failed run (need at least 2); dropped {n_dropped}. Raw samples and scores "
                "are available as last_samples / last_scores."
            )
        keep = np.repeat(ok_rows, block)
        X, Y = X[keep], Y[keep]

        # --- Phân tích Morris qua SALib ---
        Si = morris_analyze.analyze(
            problem, X, Y,
            conf_level=conf_level,
            num_levels=num_levels,
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
            observed=_MISSING,
            N: int = 1000,
            calc_second_order: bool = False,
            num_resamples: int = 1000,
            conf_level: float = 0.95,
            output_variable=_MISSING,
            reach_id=_MISSING,
            metric: str = 'nse',
            observed_series=_MISSING,
            *,
            outputs=None,
            weights=None,
            metrics=None,
            calib_period=None,
            valid_period=None,
            step=None,
            agg=None,
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
        observed, outputs, _ = _resolve_sens_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is None:
            raise TypeError(
                "observed is required for sobol_method: pass a Series or a dict "
                "keyed (variable, reach)."
            )
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
        Y = self._batch_scores(
            param_sets, observed, metric, outputs, weights=weights,
            metrics=metrics, calib_period=calib_period, valid_period=valid_period,
            step=step, agg=agg,
        )

        self.last_samples, self.last_scores = X, Y.copy()
        n_failed = self._log_failures("Sobol (SALib)", Y)
        if n_failed:
            raise RuntimeError(
                f"Sobol: {n_failed} of {len(Y)} runs failed; Sobol indices cannot be computed "
                "with missing runs. The sample matrix and raw scores (NaN = failed) are kept "
                "in self.last_samples / self.last_scores."
            )

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
