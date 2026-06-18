"""
GLUE (Generalized Likelihood Uncertainty Estimation) algorithm.

Reference:
    Beven, K. & Binley, A. (1992). The future of distributed models: model
    calibration and uncertainty prediction.
    Hydrological Processes, 6(3), 279-298.

    Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality of
    the pre-alpine/alpine Thur watershed using SWAT.
    Journal of Hydrology, 333, 413-430.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GLUE:
    """
    Generalized Likelihood Uncertainty Estimation.

    Generates n_samples parameter sets via Latin Hypercube Sampling, evaluates
    them in parallel through CalibrationManager.run_batch, filters behavioral
    sets (score >= threshold), and optionally computes the 95% Prediction
    Uncertainty band (95PPU) with p-factor and r-factor.
    """

    def __init__(self, manager, analysis=None):
        self._manager  = manager
        if analysis is None:
            from spyswat.swat_calib.analysis.statistics import SWATAnalysis
            self._analysis = SWATAnalysis(manager.project)
        else:
            self._analysis = analysis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        param_ranges: Dict[str, Tuple],
        observed_series: pd.Series,
        n_samples: int = 1000,
        threshold: float = 0.5,
        metric: str = "nse",
        output_variable: str = "FLOW_OUTcms",
        reach_id: int = 1,
        seed: Optional[int] = None,
        compute_uncertainty: bool = False,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
    ) -> Dict:
        """
        Run GLUE sampling and return results dict.

        Returns
        -------
        dict with keys:
            all_results         : pd.DataFrame  (n_samples x params + metric)
            behavioral_results  : pd.DataFrame  (n_behavioral x params + metric)
            behavioral_ratio    : float
            parameter_ranges    : dict (bounds only)
            threshold           : float
            [uncertainty_band, p_factor, r_factor  -- if compute_uncertainty=True]
        """
        logger.info("GLUE: starting with " + str(n_samples) + " samples")

        # Parse unified spec; explicit kwargs override spec values
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}

        param_names = list(bounds.keys())
        samples_df  = self._analysis._generate_samples(
            bounds, n_samples, method="lhs", seed=seed
        )

        # Pre-format so callers/mocks of run_batch always see {name: [(val, method, ...)]}
        param_sets = [
            self._manager._format_params({name: float(row[name]) for name in param_names},
                                         methods, subbasins)
            for row in samples_df.to_dict("records")
        ]

        batch_df = self._manager.run_batch(
            param_sets, observed_series, [metric], reach_id, output_variable
        )
        scores = (
            batch_df[metric].tolist()
            if hasattr(batch_df, "columns")
            else list(batch_df)
        )

        results_df            = samples_df.copy()
        results_df[metric]    = scores
        behavioral_mask       = results_df[metric] >= threshold
        behavioral_df         = results_df[behavioral_mask]
        n_behavioral          = len(behavioral_df)

        logger.info(
            "GLUE: " + str(n_behavioral) + "/" + str(n_samples) + " behavioral "
            "(" + str(round(100 * n_behavioral / n_samples, 1)) + "%)"
        )

        result = {
            "all_results":        results_df,
            "behavioral_results": behavioral_df,
            "behavioral_ratio":   n_behavioral / n_samples,
            "parameter_ranges":   bounds,
            "threshold":          threshold,
        }

        if compute_uncertainty and n_behavioral > 0:
            unc = self.uncertainty_band(
                behavioral_df, observed_series,
                metric=metric, output_variable=output_variable,
                reach_id=reach_id,
            )
            result.update(unc)

        return result

    def uncertainty_band(
        self,
        behavioral_df: pd.DataFrame,
        observed_series: pd.Series,
        metric: str = "nse",
        output_variable: str = "FLOW_OUTcms",
        reach_id: int = 1,
    ) -> Dict:
        """
        Compute 95PPU, p-factor, r-factor from behavioral parameter sets.

        Runs n_behavioral SWAT simulations sequentially with backup/restore.
        Uses weighted CDF approach (Beven & Binley 1992):
          - Weights = normalised likelihood scores (NSE, clipped >= 0)
          - Per timestep: sorted weighted CDF -> 2.5% and 97.5% quantiles
          - p-factor = mean(obs_t in [lower_t, upper_t])
          - r-factor = mean(upper - lower) / std(obs)  (Abbaspour et al. 2007)

        Returns
        -------
        dict with keys:
            uncertainty_band : pd.DataFrame (columns: lower, upper, obs)
            p_factor         : float  (target >= 0.70)
            r_factor         : float  (target <= 1.50)
        """
        param_names = [c for c in behavioral_df.columns if c != metric]
        weights     = np.array(behavioral_df[metric].clip(lower=0).tolist(), dtype=float)
        w_sum       = weights.sum()
        weights     = weights / w_sum if w_sum > 0 else np.ones(len(weights)) / len(weights)

        # Compute the common date index once from the observed series so that
        # all simulations are aligned to the same index regardless of which
        # SWAT run happens to be last in the loop.
        inferred   = pd.infer_freq(observed_series.index)
        freq       = 'MS' if (inferred and inferred.upper().startswith(('M', 'Q', 'A', 'Y'))) else 'D'
        date_range = self._manager.project.get_date_range(freq=freq)
        _dummy     = pd.Series(np.zeros(len(date_range)), index=date_range)
        common     = observed_series.index.intersection(_dummy.index)

        self._manager._backup_state()
        simulations = []
        try:
            for _, row in behavioral_df.iterrows():
                raw = {name: float(row[name]) for name in param_names}
                self._manager.project.HRU.update_params(self._manager._format_params(raw))
                self._manager.project.run()
                sim_raw = self._manager.project.Output.read_rch(
                    columns=["RCH", "MON", output_variable], reach_id=reach_id
                )[output_variable]
                sim_raw = sim_raw.reset_index(drop=True)
                if len(sim_raw) == len(date_range):
                    sim_raw.index = date_range
                simulations.append(sim_raw.reindex(common).values)
        finally:
            self._manager._restore_state()

        if not simulations:
            return {"uncertainty_band": None, "p_factor": float("nan"), "r_factor": float("nan")}

        sim_matrix = np.array(simulations)          # (n_behavioral, T)
        obs_vals   = observed_series.reindex(common).values
        T          = sim_matrix.shape[1]

        ppu_lower  = np.empty(T)
        ppu_upper  = np.empty(T)
        for t in range(T):
            vals         = sim_matrix[:, t]
            order        = np.argsort(vals)
            sorted_w     = np.cumsum(weights[order])
            ppu_lower[t] = vals[order[np.searchsorted(sorted_w, 0.025)]]
            ppu_upper[t] = vals[order[np.searchsorted(sorted_w, 0.975, side="right") - 1]]

        in_band  = (obs_vals >= ppu_lower) & (obs_vals <= ppu_upper)
        p_factor = float(in_band.mean())
        std_obs  = float(np.std(obs_vals))
        r_factor = (
            float((ppu_upper - ppu_lower).mean() / std_obs)
            if std_obs > 0 else float("nan")
        )

        band_df = pd.DataFrame(
            {"lower": ppu_lower, "upper": ppu_upper, "obs": obs_vals},
            index=common,
        )
        logger.info(
            "95PPU: p-factor=" + str(round(p_factor, 3)) +
            ", r-factor=" + str(round(r_factor, 3))
        )
        return {"uncertainty_band": band_df, "p_factor": p_factor, "r_factor": r_factor}
