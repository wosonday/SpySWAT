"""
SWATCalibration -- orchestrator and scipy wrapper.

Algorithm instances are accessed directly:
    calib.glue   -> GLUE
    calib.de     -> ParallelDE
    calib.dds    -> DDSCalibration
    calib.manager -> CalibrationManager
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, minimize

from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.analysis.statistics import (
    SWATAnalysis, best_index, to_objective, worst_score,
)
from spyswat.swat_calib.analysis.algorithms.glue import GLUE
from spyswat.swat_calib.analysis.algorithms.parallel_de import ParallelDE
from spyswat.swat_calib.analysis.algorithms.dds import DDSCalibration
from spyswat.swat_calib.analysis.algorithms.pso import PSOCalibration
from spyswat.swat_calib.analysis.algorithms.dds import (
    _MISSING, _resolve_observed, _single_site,
)

logger = logging.getLogger(__name__)


class SWATCalibration:
    """
    Exposes calibration algorithms and an orchestrated workflow.

    Direct use (preferred):
        calib.glue.run(param_ranges, obs, n_samples=500, seed=42)
        calib.de.run(param_ranges, obs, pop_size=20, max_generations=40)
        calib.dds.run(param_ranges, obs, n_iterations=300, seed=42)
        calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50)

    Orchestrated workflow:
        calib.analyze(param_ranges, obs)   # GLUE + sensitivity + performance
        calib.optimize(param_ranges, obs)  # scipy DE / minimize

    Unified param_ranges format (all formats are mixable):
        "CN2.mgt": (60, 98)                        # bounds only (old format)
        "CN2.mgt": ((60, 98), "r")                 # bounds + method
        "CN2.mgt": ((60, 98), "r", [71, 45, 70])  # bounds + method + subbasins
    """

    def __init__(self, project, analysis=None):
        self.project  = project
        self.analysis = analysis or SWATAnalysis(project)
        self.manager  = CalibrationManager(project)

        self.glue = GLUE(self.manager, self.analysis)
        self.de   = ParallelDE(self.manager)
        self.dds  = DDSCalibration(self.manager)
        self.pso  = PSOCalibration(self.manager)

        self.optimization_history = []

    # Keep _manager as alias so CalibrationManager tests still work
    @property
    def _manager(self):
        return self.manager

    # ── scipy optimiser ──────────────────────────────────────────────

    def optimize(
            self,
            param_ranges: Dict[str, Tuple],
            observed=_MISSING,
            method: str = "differential_evolution",
            metric: str = "nse",
            max_iter: int = 100,
            reach_id=_MISSING,
            output_variable=_MISSING,
            param_methods: Optional[Dict[str, str]] = None,
            param_subbasins: Optional[Dict[str, list]] = None,
            on_failure: str = "raise",
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
        Single-threaded scipy optimisation.

        method     : "differential_evolution" (default, global search), "minimize"
                     (scipy's default bounded method, L-BFGS-B) or any
                     ``scipy.optimize.minimize`` method name ("Nelder-Mead", "Powell",
                     ...), started from the middle of the bounds.
                     ``max_iter`` is passed as ``maxiter`` to both.
        on_failure : "raise" (default) -- an exception from run_iteration propagates;
                     "penalize" -- the run is recorded as NaN, scored as the worst
                     value (signed infinity) and the search continues.
        A non-finite score returned under "raise" raises RuntimeError.

        A local ``minimize`` method cannot leave a region where every run fails: if
        the start point fails, the search may end without one valid run (then
        RuntimeError "all runs failed"). Use differential_evolution when parts of the
        parameter space crash SWAT.
        """
        observed, outputs = _resolve_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is _MISSING:
            raise TypeError(
                "observed is required: pass a pandas Series or a dict keyed "
                "(variable, reach)."
            )
        if on_failure not in ("raise", "penalize"):
            raise ValueError(f"on_failure must be 'raise' or 'penalize', got {on_failure!r}")
        to_objective(metric, 0.0)  # validates the metric name (ValueError if unknown)
        self.optimization_history = []
        bounds_dict, _m, _s = CalibrationManager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}

        names  = list(bounds_dict.keys())
        bounds = [bounds_dict[n] for n in names]

        def objective(x):
            raw   = dict(zip(names, x))
            common = dict(
                metric=metric, outputs=outputs, weights=weights, metrics=metrics,
                calib_period=calib_period, valid_period=valid_period, step=step,
                agg=agg, store=store, methods=methods, subbasins=subbasins,
            )
            if on_failure == "penalize":
                try:
                    score = float(self.manager.run_iteration(raw, observed, **common))
                except Exception as exc:
                    logger.warning("optimize: run failed (%s)", exc)
                    score = float("nan")
            else:
                score = float(self.manager.run_iteration(raw, observed, **common))
                if not np.isfinite(score):
                    raise RuntimeError(
                        f"run produced no valid score ({metric}={score}); "
                        "use on_failure='penalize' to continue past failed runs"
                    )
            step_i = len(self.optimization_history) + 1
            self.optimization_history.append({
                "step":  step_i,
                **dict(zip(names, x)),
                "score": score,
            })
            if not np.isfinite(score):
                score = worst_score(metric)
            # scipy minimises: smaller objective is always better (|pbias| for pbias)
            return to_objective(metric, score)

        if method == "differential_evolution":
            res = differential_evolution(objective, bounds, maxiter=max_iter)
        else:
            # "minimize" (documented in the README) = scipy's default bounded method.
            local = None if method == "minimize" else method
            res = minimize(objective, [(b[0] + b[1]) / 2 for b in bounds], method=local,
                           bounds=bounds, options={"maxiter": max_iter})

        # Report the real metric value (not the negated / abs objective) of the
        # best evaluation seen; raises RuntimeError if every run failed.
        history_df = pd.DataFrame(self.optimization_history)
        best_row   = history_df.iloc[best_index(history_df["score"], metric)]
        best_value = float(best_row["score"])
        best_raw   = {n: float(best_row[n]) for n in names}
        return {
            # ── standard contract ─────────────────────────────────────
            "best_params":  best_raw,
            "best_score":   best_value,
            "history":      history_df,
            # ── scipy-specific extras ─────────────────────────────────
            "scipy_result": res,
            # ── backward-compat aliases (deprecated) ─────────────────
            "best_parameters":      best_raw,
            "best_objective_value": best_value,
        }

    # ── unified workflow ─────────────────────────────────────────────

    def analyze(
            self,
            param_ranges: Dict[str, Tuple],
            observed=_MISSING,
            n_samples: int = 1000,
            threshold: float = 0.5,
            metric: str = "nse",
            output_variable=_MISSING,
            reach_id=_MISSING,
            sensitivity_method: str = "spearman",
            seed: Optional[int] = None,
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
        GLUE (parallel) -> best params -> sensitivity -> performance.
        All n_samples SWAT runs happen inside glue.run(); none added for sensitivity.

        param_ranges supports unified format — see class docstring.
        """
        observed, outputs = _resolve_observed(
            observed, observed_series, reach_id, output_variable, outputs
        )
        if observed is _MISSING:
            raise TypeError(
                "observed is required: pass a pandas Series or a dict keyed "
                "(variable, reach)."
            )
        _, _m, _s  = CalibrationManager._parse_spec(param_ranges)
        methods    = {**_m, **(param_methods   or {})}
        subbasins  = {**_s, **(param_subbasins or {})}

        glue_result = self.glue.run(
            param_ranges    = param_ranges,
            observed        = observed,
            n_samples       = n_samples,
            threshold       = threshold,
            metric          = metric,
            outputs         = outputs,
            weights         = weights,
            metrics         = metrics,
            calib_period    = calib_period,
            valid_period    = valid_period,
            step            = step,
            agg             = agg,
            store           = store,
            seed            = seed,
            param_methods   = param_methods,
            param_subbasins = param_subbasins,
        )
        all_results = glue_result["all_results"]

        best_row    = all_results.iloc[best_index(all_results[metric], metric)]
        bounds_dict = glue_result["parameter_ranges"]
        best_raw    = {name: float(best_row[name]) for name in bounds_dict}
        best_params = self.manager._format_params(best_raw, methods, subbasins)
        best_score  = float(best_row[metric])

        sensitivity = self.analysis.sensitivity_from_results(
            all_results, metric=metric,
            param_names=list(bounds_dict.keys()),
            method=sensitivity_method,
        )

        self.manager.run_iteration(
            best_raw, observed, metric=metric, outputs=outputs, weights=weights,
            metrics=metrics, calib_period=calib_period, valid_period=valid_period,
            step=step, agg=agg, store=store, methods=methods, subbasins=subbasins,
        )
        var, reach = _single_site(observed, outputs)
        obs_series = observed if isinstance(observed, pd.Series) else observed[(var, reach)]
        sim = self.project.Output.read_rch(
            columns=["RCH", "MON", var], reach_id=reach
        )[var]
        obs_aligned, sim_aligned = self.manager._align_series(obs_series, sim)
        performance = self.analysis.evaluate_performance(obs_aligned, sim_aligned)

        return {
            "best_params":        best_params,
            "best_score":         best_score,
            "all_results":        all_results,
            "behavioral_results": glue_result["behavioral_results"],
            "behavioral_ratio":   glue_result["behavioral_ratio"],
            "sensitivity":        sensitivity,
            "performance":        performance,
        }
