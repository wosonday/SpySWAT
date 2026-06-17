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

import pandas as pd
from scipy.optimize import differential_evolution, minimize

from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.analysis.statistics import SWATAnalysis
from spyswat.swat_calib.analysis.algorithms.glue import GLUE
from spyswat.swat_calib.analysis.algorithms.parallel_de import ParallelDE
from spyswat.swat_calib.analysis.algorithms.dds import DDSCalibration

logger = logging.getLogger(__name__)


class SWATCalibration:
    """
    Exposes calibration algorithms and an orchestrated workflow.

    Direct use (preferred):
        calib.glue.run(param_ranges, obs, n_samples=500, seed=42)
        calib.de.run(param_ranges, obs, pop_size=20, max_generations=40)
        calib.dds.run(param_ranges, obs, n_iterations=300, seed=42)

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
    ) -> Dict:
        """Single-threaded scipy optimisation (DE or Nelder-Mead/SLSQP)."""
        bounds_dict, _m, _s = CalibrationManager._parse_spec(param_ranges)
        self.manager._methods   = {**_m, **(param_methods   or {})}
        self.manager._subbasins = {**_s, **(param_subbasins or {})}

        names  = list(bounds_dict.keys())
        bounds = [bounds_dict[n] for n in names]

        def objective(x):
            raw   = dict(zip(names, x))
            score = self.manager.run_iteration(
                raw, observed_series, metric, reach_id, output_variable
            )
            self.optimization_history.append({"params": dict(zip(names, x)), "score": score})
            return -score if metric in ("nse", "r2", "kge") else score

        if method == "differential_evolution":
            res = differential_evolution(objective, bounds, maxiter=max_iter)
        else:
            res = minimize(objective, [(b[0] + b[1]) / 2 for b in bounds], bounds=bounds)

        return {
            "best_parameters":      dict(zip(names, res.x)),
            "best_objective_value": -res.fun,
            "history":              self.optimization_history,
            "scipy_result":         res,
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

        # best_params: raw float dict -> format via manager (methods/subbasins already set by glue.run)
        best_row    = all_results.loc[all_results[metric].idxmax()]
        bounds_dict = glue_result["parameter_ranges"]
        best_raw    = {name: float(best_row[name]) for name in bounds_dict}
        best_params = self.manager._format_params(best_raw)
        best_score  = float(best_row[metric])

        sensitivity = self.analysis.sensitivity_from_results(
            all_results, metric=metric,
            param_names=list(bounds_dict.keys()),
            method=sensitivity_method,
        )

        self.manager.run_iteration(best_raw, observed_series, metric, reach_id, output_variable)
        sim = self.project.Output.read_rch(
            columns=["RCH", "MON", output_variable], reach_id=reach_id
        )[output_variable]
        date_range = self.project.get_date_range(freq="D")
        sim = sim.reset_index(drop=True)
        if len(sim) == len(date_range):
            sim.index = date_range
        common      = observed_series.index.intersection(sim.index)
        performance = self.analysis.evaluate_performance(
            observed_series.loc[common], sim.loc[common]
        )

        return {
            "best_params":        best_params,
            "best_score":         best_score,
            "all_results":        all_results,
            "behavioral_results": glue_result["behavioral_results"],
            "behavioral_ratio":   glue_result["behavioral_ratio"],
            "sensitivity":        sensitivity,
            "performance":        performance,
        }
