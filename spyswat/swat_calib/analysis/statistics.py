
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
import logging

from numpy import floating

logger = logging.getLogger(__name__)


class SWATAnalysis:
    """
        >>> analysis = project.analysis
        >>> stats = analysis.calculate_statistics(obs, sim)
        >>> print(f"NSE: {stats['nse']:.3f}")
    """

    def __init__(self, project):
        self.project = project

    # ==================== Statistical Metrics ====================

    def calculate_statistics(
            self,
            observed: Union[pd.Series, np.ndarray],
            simulated: Union[pd.Series, np.ndarray],
            metrics: Optional[List[str]] = None,
            remove_nan: bool = True
    ) -> Dict[str, float]:

        obs = np.array(observed)
        sim = np.array(simulated)

        if remove_nan:
            mask = ~(np.isnan(obs) | np.isnan(sim))
            obs = obs[mask]
            sim = sim[mask]

        if len(obs) == 0:
            logger.warning("No valid data points after removing NaN")
            return {m: np.nan for m in (metrics or self._get_all_metrics())}

        if metrics is None:
            metrics = ['nse', 'r2', 'rmse', 'pbias', 'kge']
        results = {}

        metric_functions = {
            'nse'        : self._nse,
            'r2'         : self._r_squared,
            'rmse'       : self._rmse,
            'mae'        : self._mae,
            'pbias'      : self._pbias,
            'rsr'        : self._rsr,
            'kge'        : self._kge,
            'correlation': self._correlation,
        }

        for metric in metrics:
            if metric in metric_functions:
                try:
                    results[metric] = round(float(metric_functions[metric](obs, sim)), 3)
                except Exception as e:
                    logger.error(f"Error calculating {metric}: {e}")
                    results[metric] = np.nan
            else:
                logger.warning(f"Unknown metric: {metric}")
                results[metric] = np.nan

        df = pd.DataFrame([results], index=["Value"])
        df.columns.name = "Metric"
        print(df.to_string())

        return results

    def evaluate_performance(
            self,
            observed: Union[pd.Series, np.ndarray],
            simulated: Union[pd.Series, np.ndarray]
    ) -> Dict[str, str]:

        stats = self.calculate_statistics(observed, simulated)
        ratings = {}

        nse = stats.get('nse', np.nan)
        if nse > 0.75:
            ratings['nse'] = 'Very Good'
        elif nse > 0.65:
            ratings['nse'] = 'Good'
        elif nse > 0.50:
            ratings['nse'] = 'Satisfactory'
        elif nse > 0.40:
            ratings['nse'] = 'Acceptable'
        else:
            ratings['nse'] = 'Unsatisfactory'

        pbias = abs(stats.get('pbias', np.nan))
        if pbias < 10:
            ratings['pbias'] = 'Very Good'
        elif pbias < 15:
            ratings['pbias'] = 'Good'
        elif pbias < 25:
            ratings['pbias'] = 'Satisfactory'
        else:
            ratings['pbias'] = 'Unsatisfactory'

        rsr = stats.get('rsr', np.nan)
        if rsr <= 0.50:
            ratings['rsr'] = 'Very Good'
        elif rsr <= 0.60:
            ratings['rsr'] = 'Good'
        elif rsr <= 0.70:
            ratings['rsr'] = 'Satisfactory'
        else:
            ratings['rsr'] = 'Unsatisfactory'
        return ratings

    # ==================== Private Statistical Methods ====================

    def _nse(self, obs: np.ndarray, sim: np.ndarray) -> float | Any:
        numerator = np.sum((obs - sim) ** 2)
        denominator = np.sum((obs - np.mean(obs)) ** 2)
        return 1 - (numerator / denominator)

    def _r_squared(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        correlation = np.corrcoef(obs, sim)[0, 1]
        return correlation ** 2

    def _rmse(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        return np.sqrt(np.mean((obs - sim) ** 2))

    def _mae(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        return np.mean(np.abs(obs - sim))

    def _pbias(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        return 100 * np.sum(obs - sim) / np.sum(obs)

    def _rsr(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any] | float:
        rmse = self._rmse(obs, sim)
        std_obs = np.std(obs)
        return rmse / std_obs if std_obs > 0 else np.nan

    def _kge(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        r = np.corrcoef(obs, sim)[0, 1]
        alpha = np.std(sim) / np.std(obs)
        beta = np.mean(sim) / np.mean(obs)
        return 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)

    def _correlation(self, obs: np.ndarray, sim: np.ndarray) -> floating[Any]:
        return np.corrcoef(obs, sim)[0, 1]

    def _get_all_metrics(self) -> List[str]:
        return ['nse', 'r2', 'rmse', 'mae', 'pbias', 'rsr', 'kge', 'correlation']

    # ==================== Sampling Methods ====================

    def _generate_samples(
            self,
            param_ranges: Dict[str, Tuple[float, float]],
            n_samples: int,
            method: str = 'lhs',
            seed: Optional[int] = None
    ) -> pd.DataFrame:

        param_names = list(param_ranges.keys())
        n_params = len(param_names)

        if method == 'lhs':
            from scipy.stats import qmc
            sampler = qmc.LatinHypercube(d=n_params, seed=seed)
            samples = sampler.random(n=n_samples)
        elif method == 'random':
            samples = np.random.random((n_samples, n_params))
        elif method == 'grid':
            n_per_dim = int(np.ceil(n_samples ** (1 / n_params)))
            axes = [np.linspace(0, 1, n_per_dim) for _ in range(n_params)]
            grid = np.meshgrid(*axes)
            samples = np.column_stack([g.ravel() for g in grid])[:n_samples]
        else:
            raise ValueError(f"Unknown sampling method: {method}")

        data = {}
        for i, pname in enumerate(param_names):
            vmin, vmax = param_ranges[pname]
            data[pname] = vmin + samples[:, i] * (vmax - vmin)
        return pd.DataFrame(data)

    # ==================== Sensitivity from MC results ====================

    def sensitivity_from_results(
            self,
            results_df: pd.DataFrame,
            metric: str = 'nse',
            param_names: Optional[List[str]] = None,
            method: str = 'spearman'
    ) -> pd.DataFrame:
        """
        Tinh sensitivity tu ket qua MC/GLUE da co -- khong can chay SWAT them.

        Phuong phap:
            'spearman': Spearman rank correlation (nhanh, phu hop phi tuyen)
            'prcc':     Partial Rank Correlation Coefficient
                         (Saltelli et al. 2008, Helton & Davis 2003)

        Args:
            results_df:  DataFrame gom cot tham so + cot metric
            metric:      Ten cot metric trong results_df
            param_names: Danh sach tham so can phan tich (mac dinh: tat ca tru metric)
            method:      'spearman' hoac 'prcc'

        Returns:
            DataFrame: parameter | sensitivity_index | rank
        """
        if param_names is None:
            param_names = [c for c in results_df.columns if c != metric]

        valid = results_df[param_names + [metric]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(valid) < 10:
            logger.warning(f"Chi co {len(valid)} mau hop le -- ket qua khong dang tin cay.")

        if method == 'spearman':
            scores = []
            for p in param_names:
                r = valid[p].corr(valid[metric], method='spearman')
                scores.append({'parameter': p, 'sensitivity_index': abs(r), 'correlation': r})

        elif method == 'prcc':
            from scipy import stats as sp_stats
            ranked = valid.rank()
            Y_rank = ranked[metric].values
            scores = []
            for p in param_names:
                others = [c for c in param_names if c != p]
                X_rank = ranked[p].values
                if others:
                    X_mat = ranked[others].values
                    A = np.column_stack([np.ones(len(X_mat)), X_mat])
                    r_x = X_rank - A @ np.linalg.lstsq(A, X_rank, rcond=None)[0]
                    r_y = Y_rank - A @ np.linalg.lstsq(A, Y_rank, rcond=None)[0]
                    prcc, _ = sp_stats.pearsonr(r_x, r_y)
                else:
                    prcc, _ = sp_stats.pearsonr(X_rank, Y_rank)
                scores.append({'parameter': p, 'sensitivity_index': abs(prcc), 'correlation': prcc})
        else:
            raise ValueError(f"method phai la 'spearman' hoac 'prcc', nhan: {method!r}")

        result = pd.DataFrame(scores).sort_values('sensitivity_index', ascending=False)
        result['rank'] = range(1, len(result) + 1)
        top_param = result.iloc[0]['parameter']
        logger.info("Sensitivity " + method + ": top param = " + str(top_param))
        return result.reset_index(drop=True)
