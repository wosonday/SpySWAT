"""
Calibration algorithms for SWAT model
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
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
            reach_id: int = 1,
            seed: int = None,
            compute_uncertainty: bool = False,
            param_methods: Dict[str, str] = None
    ) -> Dict:
        """
        Generalized Likelihood Uncertainty Estimation (GLUE).
        Sinh n_samples bộ tham số LHS, chạy song song, lọc behavioral.

        Args:
            seed:                Seed cho LHS de tai lap ket qua.
            compute_uncertainty: Neu True, tinh 95PPU / p-factor / r-factor
                                 tu cac bo behavioral (them n_behavioral SWAT runs).

        Returns:
            all_results, behavioral_results, behavioral_ratio,
            parameter_ranges, threshold
            [+ uncertainty_band, p_factor, r_factor neu compute_uncertainty=True]
            param_methods: dict map ten tham so -> phuong phap ('v', 'r', 'a').
                           Mac dinh 'v' (thay the gia tri tuyet doi).
        """
        logger.info("Starting GLUE analysis with " + str(n_samples) + " samples")

        param_names = list(param_ranges.keys())
        samples_df = self.analysis._generate_samples(
            param_ranges, n_samples, method='lhs', seed=seed
        )
        _pm = param_methods or {}
        param_sets = [
            {name: [(float(row[name]), _pm.get(name, 'v'))] for name in param_names}
            for row in samples_df.to_dict('records')
        ]

        # run_batch normalises metric string to [metric] internally
        batch_df = self._manager.run_batch(
            param_sets, observed_series, [metric], reach_id, output_variable
        )
        # batch_df is a DataFrame; extract the metric column as a list
        if hasattr(batch_df, 'columns'):
            scores = batch_df[metric].tolist()
        else:
            scores = list(batch_df)   # fallback if mock returns list

        results_df = samples_df.copy()
        results_df[metric] = scores

        behavioral_mask = results_df[metric] >= threshold
        behavioral_df = results_df[behavioral_mask]
        n_behavioral = len(behavioral_df)
        logger.info(
            "GLUE: " + str(n_behavioral) + "/" + str(n_samples) + " behavioral sets "
            "(" + str(round(100 * n_behavioral / n_samples, 1)) + "%)"
        )

        result = {
            'all_results': results_df,
            'behavioral_results': behavioral_df,
            'behavioral_ratio': n_behavioral / n_samples,
            'parameter_ranges': param_ranges,
            'threshold': threshold
        }

        if compute_uncertainty and n_behavioral > 0:
            unc = self._compute_uncertainty_band(
                behavioral_df, observed_series, metric, output_variable, reach_id,
                param_methods=param_methods
            )
            result.update(unc)

        return result

    def _compute_uncertainty_band(
            self,
            behavioral_df: pd.DataFrame,
            observed_series: pd.Series,
            metric: str = 'nse',
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            param_methods: Dict[str, str] = None
    ) -> Dict:
        """
        Tính 95PPU, p-factor, r-factor tu cac bo tham so behavioral.
        Chay n_behavioral SWAT runs (sequential, co backup/restore).

        Args:
            behavioral_df: DataFrame voi cot tham so + cot metric.
            observed_series: Chuoi quan trac (DatetimeIndex).

        Returns:
            uncertainty_band: DataFrame voi cot lower/upper/obs (aligned).
            p_factor: ty le quan trac nam trong dai 95PPU (0-1).
            r_factor: do rong dai chuan hoa theo std(obs).

        Ref: Beven & Binley (1992); Abbaspour et al. (2007).
        """
        param_names = [c for c in behavioral_df.columns if c != metric]
        weights = np.array(behavioral_df[metric].clip(lower=0).tolist(), dtype=float)
        w_sum = weights.sum()
        if w_sum > 0:
            weights = weights / w_sum
        else:
            weights = np.ones(len(weights)) / len(weights)

        # Backup TxtInOut once before loop
        self._manager._backup_state()
        simulations = []
        try:
            for _, row in behavioral_df.iterrows():
                _pm2 = param_methods or {}
                params = {name: [(float(row[name]), _pm2.get(name, 'v'))] for name in param_names}
                self._manager.project.HRU.update_params(params)
                self._manager.project.run()
                sim_raw = self._manager.project.Output.read_rch(
                    columns=['RCH', 'MON', output_variable], reach_id=reach_id
                )[output_variable]
                # Align sim to observed DatetimeIndex
                date_range = self._manager.project.get_date_range(freq='D')
                sim_raw = sim_raw.reset_index(drop=True)
                if len(sim_raw) == len(date_range):
                    sim_raw.index = date_range
                common = observed_series.index.intersection(sim_raw.index)
                simulations.append(sim_raw.reindex(common).values)
        finally:
            self._manager._restore_state()

        if not simulations:
            return {'uncertainty_band': None, 'p_factor': np.nan, 'r_factor': np.nan}

        sim_matrix = np.array(simulations)   # (n_behavioral, T)
        obs_vals = observed_series.reindex(common).values

        # Weighted percentiles (2.5% and 97.5%)
        # Sorted weighted CDF approach (Beven & Binley 1992)
        T = sim_matrix.shape[1]
        ppu_lower = np.empty(T)
        ppu_upper = np.empty(T)
        for t in range(T):
            vals = sim_matrix[:, t]
            order = np.argsort(vals)
            sorted_w = np.cumsum(weights[order])
            ppu_lower[t] = vals[order[np.searchsorted(sorted_w, 0.025)]]
            ppu_upper[t] = vals[order[np.searchsorted(sorted_w, 0.975, side='right') - 1]]

        # p-factor: fraction of obs within band
        in_band = (obs_vals >= ppu_lower) & (obs_vals <= ppu_upper)
        p_factor = float(in_band.mean())

        # r-factor: mean band width / std(obs)  (Abbaspour et al. 2007)
        std_obs = float(np.std(obs_vals))
        r_factor = float((ppu_upper - ppu_lower).mean() / std_obs) if std_obs > 0 else np.nan

        band_df = pd.DataFrame({
            'lower': ppu_lower,
            'upper': ppu_upper,
            'obs': obs_vals,
        }, index=common)

        logger.info(
            "Uncertainty: p-factor=" + str(round(p_factor, 3)) +
            ", r-factor=" + str(round(r_factor, 3))
        )
        return {
            'uncertainty_band': band_df,
            'p_factor': p_factor,
            'r_factor': r_factor,
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
            sensitivity_method: str = 'spearman',
            seed: int = None,
            param_methods: Dict[str, str] = None
    ) -> Dict:
        """
        Workflow hoàn chỉnh: GLUE parallel -> best params -> sensitivity.
        Chỉ chạy SWAT dung n_samples lan, khong chay them cho sensitivity.

        Args:
            seed: Seed cho LHS — truyền vào để tái lập kết quả.

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
            reach_id=reach_id,
            seed=seed,
            param_methods=param_methods
        )
        all_results = glue_result['all_results']

        # Buoc 3: Best params
        best_idx = all_results[metric].idxmax()
        best_row = all_results.loc[best_idx]
        _pm_a = param_methods or {}
        best_params = {
            name: [(float(best_row[name]), _pm_a.get(name, 'v'))]
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

    # ==================== Parallel Differential Evolution ====================

    def parallel_de(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            observed_series: pd.Series,
            metric: str = 'nse',
            output_variable: str = 'FLOW_OUTcms',
            reach_id: int = 1,
            pop_size: int = None,
            max_generations: int = 20,
            F: float = 0.8,
            CR: float = 0.9,
            strategy: str = 'rand/1/bin',
            seed: int = None,
            param_methods: Dict[str, str] = None,
            tol: float = 1e-6,
            patience: int = 5
    ) -> Dict:
        """
        Parallel Differential Evolution calibration.

        Moi the he, toan bo NP candidate vectors duoc evaluate song song
        thong qua CalibrationManager.run_batch, tan dung cac worker SWAT
        da duoc setup.

        Thuat toan: Storn & Price (1997), Journal of Global Optimization, 11, 341-359.
        Strategy 'rand/1/bin'  — de-facto standard.
        Strategy 'best/1/bin'  — hoi tu nhanh hon, it da dang hon.

        Args:
            param_ranges:    Dict ten tham so -> (min, max).
            observed_series: Chuoi quan trac (DatetimeIndex).
            metric:          Ham muc tieu ('nse', 'kge', 'r2', ...).
            pop_size:        Kich co quan the. Mac dinh max(10, 5*d).
            max_generations: So the he toi da.
            F:               He so nhiem (mutation factor, 0 < F <= 2).
            CR:              Ti le lai ghep (crossover rate, 0 <= CR <= 1).
            strategy:        'rand/1/bin' hoac 'best/1/bin'.
            seed:            Seed ngau nhien.
            param_methods:   Dict ten tham so -> phuong phap ('v', 'r', 'a').
            tol:             Nguong hoi tu (max(f) - min(f) < tol).
            patience:        Dung som neu best score khong cai thien trong n the he.

        Returns:
            best_params:   Dict tham so tot nhat.
            best_score:    Gia tri metric tot nhat.
            history:       DataFrame (generation, best_score, mean_score, std_score).
            all_evaluations: DataFrame tat ca cac tham so + score da thu.

        References:
            Storn, R., & Price, K. (1997). Differential evolution: A simple
            and efficient heuristic for global optimization over continuous
            spaces. Journal of Global Optimization, 11(4), 341-359.
            https://doi.org/10.1023/A:1008202821328
        """
        names = list(param_ranges.keys())
        d = len(names)
        lower = np.array([param_ranges[n][0] for n in names], dtype=float)
        upper = np.array([param_ranges[n][1] for n in names], dtype=float)
        NP = pop_size or max(10, 5 * d)
        rng = np.random.default_rng(seed)
        _pm = param_methods or {}

        if not (0 < F <= 2):
            raise ValueError("F must be in (0, 2].")
        if not (0 <= CR <= 1):
            raise ValueError("CR must be in [0, 1].")
        if strategy not in ('rand/1/bin', 'best/1/bin'):
            raise ValueError("strategy must be 'rand/1/bin' or 'best/1/bin'.")

        def to_param_sets(population):
            """Convert (NP, d) array to list of param dicts."""
            result = []
            for row in population:
                ps = {
                    names[j]: [(float(row[j]), _pm.get(names[j], 'v'))]
                    for j in range(d)
                }
                result.append(ps)
            return result

        def evaluate_population(pop):
            """Run all NP candidates via run_batch; return scores array."""
            param_sets = to_param_sets(pop)
            batch_df = self._manager.run_batch(
                param_sets, observed_series, [metric], reach_id, output_variable
            )
            if hasattr(batch_df, 'columns'):
                return np.array(batch_df[metric].tolist(), dtype=float)
            return np.array(list(batch_df), dtype=float)

        # ── Initialization ────────────────────────────────────────────────
        u = rng.random((NP, d))
        population = lower + u * (upper - lower)
        scores = evaluate_population(population)

        gen_history = []
        all_rows = []
        for k in range(NP):
            row = dict(zip(names, population[k].tolist()))
            row.update({'score': scores[k], 'generation': 0})
            all_rows.append(row)

        gen_history.append({
            'generation': 0,
            'best_score': float(scores.max()),
            'mean_score': float(scores.mean()),
            'std_score':  float(scores.std()),
        })
        logger.info(
            "DE gen 0 | best=%.4f mean=%.4f NP=%d d=%d strategy=%s",
            scores.max(), scores.mean(), NP, d, strategy
        )

        no_improve = 0
        best_score_prev = scores.max()

        # ── Main loop ─────────────────────────────────────────────────────
        for gen in range(1, max_generations + 1):
            best_idx = int(np.argmax(scores))
            trials = np.empty_like(population)

            for i in range(NP):
                # Select three distinct indices != i
                candidates = [j for j in range(NP) if j != i]
                r1, r2, r3 = rng.choice(candidates, 3, replace=False)

                # Mutation
                if strategy == 'rand/1/bin':
                    base = population[r1]
                else:   # best/1/bin
                    base = population[best_idx]
                mutant = base + F * (population[r2] - population[r3])
                # Clip to bounds
                mutant = np.clip(mutant, lower, upper)

                # Crossover (binomial)
                j_rand = rng.integers(0, d)
                cross_mask = (rng.random(d) < CR)
                cross_mask[j_rand] = True
                trials[i] = np.where(cross_mask, mutant, population[i])

            # Evaluate all trials in parallel
            trial_scores = evaluate_population(trials)
            for k in range(NP):
                row = dict(zip(names, trials[k].tolist()))
                row.update({'score': trial_scores[k], 'generation': gen})
                all_rows.append(row)

            # Selection
            improve_mask = trial_scores >= scores
            population = np.where(improve_mask[:, None], trials, population)
            scores = np.where(improve_mask, trial_scores, scores)

            current_best = float(scores.max())
            gen_history.append({
                'generation': gen,
                'best_score': current_best,
                'mean_score': float(scores.mean()),
                'std_score':  float(scores.std()),
            })
            logger.info(
                "DE gen %d/%d | best=%.4f mean=%.4f",
                gen, max_generations, current_best, scores.mean()
            )

            # Early stopping: convergence
            if (scores.max() - scores.min()) < tol:
                logger.info("DE converged at gen %d (tol=%.2e)", gen, tol)
                break

            # Early stopping: patience
            if current_best > best_score_prev + tol:
                best_score_prev = current_best
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    logger.info("DE early stop at gen %d (patience=%d)", gen, patience)
                    break

        best_idx = int(np.argmax(scores))
        best_params = {
            names[j]: [(float(population[best_idx, j]), _pm.get(names[j], 'v'))]
            for j in range(d)
        }

        return {
            'best_params':      best_params,
            'best_score':       float(scores[best_idx]),
            'history':          pd.DataFrame(gen_history),
            'all_evaluations':  pd.DataFrame(all_rows),
        }

