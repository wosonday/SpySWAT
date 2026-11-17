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
            observed_series: pd.Series,
            method: str = "differential_evolution",
            metric: str = "nse",
            max_iter: int = 100,
            reach_id: int = 1,
            output_variable: str = "FLOW_OUTcms",
            param_methods: Optional[Dict[str, str]] = None,
            param_subbasins: Optional[Dict[str, list]] = None,
            on_failure: str = "raise",
    ) -> Dict:
        """
        Single-threaded scipy optimisation (DE or Nelder-Mead/SLSQP).

        on_failure : "raise" (default) -- an exception from run_iteration propagates;
                     "penalize" -- the run is recorded as NaN, treated as the worst
                     value and the search continues.
        A non-finite score returned under "raise" raises RuntimeError.
        """
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
            if on_failure == "penalize":
                try:
                    score = float(self.manager.run_iteration(
                        raw, observed_series, metric, reach_id, output_variable,
                        methods=methods, subbasins=subbasins
                    ))
                except Exception as exc:
                    logger.warning("optimize: run failed (%s)", exc)
                    score = float("nan")
            else:
                score = float(self.manager.run_iteration(
                    raw, observed_series, metric, reach_id, output_variable,
                    methods=methods, subbasins=subbasins
                ))
                if not np.isfinite(score):
                    raise RuntimeError(
                        f"run produced no valid score ({metric}={score}); "
                        "use on_failure='penalize' to continue past failed runs"
                    )
            step = len(self.optimization_history) + 1
            self.optimization_history.append({
                "step":  step,
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
            res = minimize(objective, [(b[0] + b[1]) / 2 for b in bounds], bounds=bounds)

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
            observed_series: pd.Series,
            n_samples: int = 1000,
            threshold: float = 0.5,
            metric: str = "nse",
            output_variable: str = "FLOW_OUTcms",
            reach_id: int = 1,
            sensitivity_method: str = "spearman",
            seed: Optional[int] = None,
            param_methods: Optional[Dict[str, str]] = None,
            param_subbasins: Optional[Dict[str, list]] = None,
    ) -> Dict:
        """
        GLUE (parallel) -> best params -> sensitivity -> performance.
        All n_samples SWAT runs happen inside glue.run(); none added for sensitivity.

        param_ranges supports unified format — see class docstring.
        """
        _, _m, _s  = CalibrationManager._parse_spec(param_ranges)
        methods    = {**_m, **(param_methods   or {})}
        subbasins  = {**_s, **(param_subbasins or {})}

        glue_result = self.glue.run(
            param_ranges    = param_ranges,
            observed_series = observed_series,
            n_samples       = n_samples,
            threshold       = threshold,
            metric          = metric,
            output_variable = output_variable,
            reach_id        = reach_id,
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

        self.manager.run_iteration(best_raw, observed_series, metric, reach_id, output_variable,
                                   methods=methods, subbasins=subbasins)
        sim = self.project.Output.read_rch(
            columns=["RCH", "MON", output_variable], reach_id=reach_id
        )[output_variable]
        obs_aligned, sim_aligned = self.manager._align_series(observed_series, sim)
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
