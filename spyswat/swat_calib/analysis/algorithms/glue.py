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

from spyswat.swat_calib.core.run_state import StaleOutputError
from spyswat.swat_calib.analysis.statistics import (
    best_index, is_maximize, to_objective,
)
from spyswat.swat_calib.analysis.algorithms.dds import (
    _MISSING, _batch_scores, _reported, _resolve_observed, _resolve_seed, _runs_frame,
)

logger = logging.getLogger(__name__)


class GLUE:
    """
    Generalized Likelihood Uncertainty Estimation.

    Generates n_samples parameter sets via Latin Hypercube Sampling, evaluates
    them in parallel through CalibrationManager.run_batch, filters behavioral
    sets (score at least as good as the threshold in the metric's direction:
    score >= threshold for nse/r2/kge/correlation, score <= threshold for
    rmse/mae/rsr, |pbias| <= threshold for pbias), and optionally computes the 95% Prediction
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
        observed=_MISSING,
        n_samples: int = 1000,
        threshold: float = 0.5,
        metric: str = "nse",
        output_variable=_MISSING,
        reach_id=_MISSING,
        seed: Optional[int] = None,
        compute_uncertainty: bool = False,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
        observed_series=_MISSING,
        *,
        outputs=None,
        weights=None,
        metrics=None,
        calib_period=None,
        valid_period=None,
        step=None,
        agg=None,
        store=None,
    ) -> Dict:
        """
        Run GLUE sampling and return results dict.

        Returns
        -------
        dict with keys (standard contract):
            best_params         : dict  {name: [(val, method, [subs])]}
            best_score          : float  best real metric value across all_results
                                  (closest to 0 for pbias)
        dict with keys (GLUE-specific):
            all_results         : pd.DataFrame  (n_samples x params + metric)
            behavioral_results  : pd.DataFrame  (n_behavioral x params + metric)
            behavioral_ratio    : float
            parameter_ranges    : dict (bounds only)
            threshold           : float
            seed                : int   concrete seed (resolved from None)
            runs                : pd.DataFrame  (params + score + per-site columns)
            [uncertainty_band, p_factor, r_factor  -- if compute_uncertainty=True]
        """
        observed, outputs = _resolve_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is _MISSING:
            raise TypeError(
                "observed is required: pass a pandas Series or a dict keyed "
                "(variable, reach)."
            )
        seed = _resolve_seed(seed)
        to_objective(metric, 0.0)  # validates the metric name (ValueError if unknown)
        logger.info("GLUE: starting with " + str(n_samples) + " samples")

        # Parse unified spec; explicit kwargs override spec values
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}

        param_names = list(bounds.keys())
        rng         = np.random.default_rng(seed)
        samples_df  = self._analysis._generate_samples(
            bounds, n_samples, method="lhs", seed=rng
        )

        # Pre-format so callers/mocks of run_batch always see {name: [(val, method, ...)]}
        param_sets = [
            self._manager._format_params({name: float(row[name]) for name in param_names},
                                         methods, subbasins)
            for row in samples_df.to_dict("records")
        ]

        batch_df = self._manager.run_batch(
            param_sets, observed, _reported(metric, metrics),
            metric=metric, outputs=outputs, weights=weights,
            calib_period=calib_period, valid_period=valid_period,
            step=step, agg=agg, store=store,
            methods=methods, subbasins=subbasins, is_initial=True,
        )
        scores = _batch_scores(batch_df, metric)

        results_df            = samples_df.copy()
        results_df[metric]    = scores
        # NaN (failed run) compares False in both branches -> never behavioural
        if is_maximize(metric):
            behavioral_mask   = scores >= threshold
        else:
            behavioral_mask   = to_objective(metric, scores) <= threshold
        behavioral_mask       = pd.Series(behavioral_mask, index=results_df.index)
        behavioral_df         = results_df[behavioral_mask]
        n_behavioral          = len(behavioral_df)

        logger.info(
            "GLUE: " + str(n_behavioral) + "/" + str(n_samples) + " behavioral "
            "(" + str(round(100 * n_behavioral / n_samples, 1)) + "%)"
        )

        # ── best_params / best_score (standard contract) ──────────────
        best_pos    = best_index(results_df[metric], metric)   # RuntimeError if all runs failed
        best_row    = results_df.iloc[best_pos]
        best_raw    = {name: float(best_row[name]) for name in param_names}
        best_params = self._manager._format_params(best_raw, methods, subbasins)
        best_score  = float(best_row[metric])

        result = {
            "best_params":        best_params,
            "best_score":         best_score,
            "all_results":        results_df,
            "behavioral_results": behavioral_df,
            "behavioral_ratio":   n_behavioral / n_samples,
            "parameter_ranges":   bounds,
            "threshold":          threshold,
            "seed":               seed,
            "runs":               _runs_frame(samples_df, batch_df, metric),
        }

        if compute_uncertainty and n_behavioral > 0:
            unc = self.uncertainty_band(
                behavioral_df, observed,
                metric=metric, outputs=outputs,
                param_methods=methods, param_subbasins=subbasins,
            )
            result.update(unc)

        return result

    def uncertainty_band(
        self,
        behavioral_df: pd.DataFrame,
        observed=_MISSING,
        metric: str = "nse",
        output_variable=_MISSING,
        reach_id=_MISSING,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
        observed_series=_MISSING,
        *,
        outputs=None,
        weights=None,
        metrics=None,
        calib_period=None,
        valid_period=None,
        step=None,
        agg=None,
        store=None,
    ) -> Dict:
        """
        Compute 95PPU, p-factor, r-factor from behavioral parameter sets.

        Runs n_behavioral SWAT simulations sequentially; the baseline TxtInOut is
        backed up and restored around EVERY run so relative ('r'/'a') changes
        always start from the original values. param_methods / param_subbasins
        must be those of the GLUE run (default: absolute 'v' for all).
        Uses weighted CDF approach (Beven & Binley 1992):
          - Weights = normalised likelihood scores (clipped >= 0) for
            maximised metrics; equal weights for rmse/mae/rsr/pbias
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
        observed, outputs = _resolve_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is _MISSING:
            raise TypeError(
                "observed is required: pass a pandas Series or a dict keyed "
                "(variable, reach)."
            )
        # The 95PPU band is a single-site quantity: resolve the one observed site.
        if isinstance(observed, pd.Series):
            if outputs is None:
                outputs = {"FLOW_OUTcms": [1]}
            sites = [(v, r) for v in sorted(outputs) for r in outputs[v]]
            if len(sites) != 1:
                raise ValueError(
                    "uncertainty_band needs exactly one site in outputs for a bare "
                    f"observed Series; got {len(sites)} sites from {outputs!r}."
                )
            site_key = sites[0]
            obs_series = observed
        else:
            site_key = next(iter(observed))
            obs_series = observed[site_key]
            var, reach = site_key
            if outputs is None:
                outputs = {var: [reach]}
            elif var not in outputs:
                outputs = dict(outputs)
                outputs[var] = [reach]
            elif reach not in outputs[var]:
                outputs = dict(outputs)
                outputs[var] = list(outputs[var]) + [reach]
        var, reach = site_key

        param_names = [c for c in behavioral_df.columns if c != metric]
        if is_maximize(metric):
            weights = np.array(behavioral_df[metric].clip(lower=0).tolist(), dtype=float)
        else:
            weights = np.zeros(len(behavioral_df))
        w_sum       = weights.sum()
        weights     = weights / w_sum if w_sum > 0 else np.ones(len(weights)) / len(weights)

        # Each run is aligned to the observations by the manager (single source of
        # truth for frequency handling); keep only timesteps present in every run.
        sims: List[pd.Series] = []
        kept: List[int] = []
        n_stale = 0
        obs_aligned: Optional[pd.Series] = None
        for pos, (_, row) in enumerate(behavioral_df.iterrows()):
            raw = {name: float(row[name]) for name in param_names}
            formatted = self._manager._format_params(raw, param_methods, param_subbasins)
            try:
                with self._manager.sandbox():
                    sim_dict = self._manager.run_once(formatted, outputs=outputs)
                    sim_raw = sim_dict[site_key]
            except StaleOutputError as exc:          # no result: leave it out of the band
                n_stale += 1
                self._manager.record_run(
                    formatted, None, status="failed", error=str(exc), sim=None,
                    mode="uncertainty_band", reach_id=reach,
                    output_variable=var,
                )
                logger.warning("GLUE 95PPU: behavioural run %d excluded (%s)", pos, exc)
                continue
            except Exception as exc:
                self._manager.record_run(
                    formatted, None, status="failed", error=str(exc), sim=None,
                    mode="uncertainty_band", reach_id=reach,
                    output_variable=var,
                )
                raise
            obs_a, sim_a = self._manager._align_series(obs_series, sim_raw)
            self._manager.record_run(
                formatted, None, status="ok", sim=sim_a, mode="uncertainty_band",
                reach_id=reach, output_variable=var,
            )
            obs_aligned = obs_a
            sims.append(sim_a)
            kept.append(pos)

        if n_stale:
            logger.warning(
                "GLUE 95PPU: %d of %d behavioural runs had no fresh output and were "
                "excluded from the band", n_stale, len(behavioral_df)
            )
        if kept:
            weights = weights[kept]
            w_sum   = weights.sum()
            weights = weights / w_sum if w_sum > 0 else np.ones(len(weights)) / len(weights)

        common = None
        for sim_a in sims:
            common = sim_a.index if common is None else common.intersection(sim_a.index)
        simulations = [sim_a.reindex(common).values for sim_a in sims] if sims else []

        if not simulations:
            return {"uncertainty_band": None, "p_factor": float("nan"), "r_factor": float("nan")}

        sim_matrix = np.array(simulations)          # (n_behavioral, T)
        obs_vals   = obs_aligned.reindex(common).values
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
