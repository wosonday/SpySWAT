"""
Dynamically Dimensioned Search (DDS) — Tolson & Shoemaker (2007).

Reference:
    Tolson, B. A., & Shoemaker, C. A. (2007).
    Dynamically dimensioned search algorithm for computationally efficient
    watershed model calibration.
    Water Resources Research, 43(1), W01413.
    https://doi.org/10.1029/2005WR004723

DDS is designed for single-objective calibration of computationally expensive
models when the evaluation budget N is small (100-1000 runs). Key properties:
  - No algorithm parameters to tune (only N and r).
  - Perturbation probability decreases as iterations grow: P_perturb = 1 - ln(i)/ln(N).
  - Neighbour generation: x_new = x_best + r*(x_max - x_min)*N(0,1)
    reflected at bounds.
  - Converges quickly because the "search neighbourhood" shrinks automatically.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DDS:
    """
    Dynamically Dimensioned Search optimiser.

    Parameters
    ----------
    param_ranges : dict[str, (float, float)]
        Parameter names mapped to (min, max) bounds.
        Keys must use name.ext format (e.g. "CN2.mgt").
    objective : Callable[[dict], float]
        Function that accepts {name: float} and returns a scalar score
        (higher is better, e.g. NSE). Typically wraps
        CalibrationManager.run_iteration.
    n_iterations : int
        Total evaluation budget (recommended >= 200).
    r : float
        Perturbation size as fraction of parameter range (default 0.2 per
        Tolson & Shoemaker 2007, Section 3).
    seed : int | None
        Random seed for reproducibility.
    maximize : bool
        True (default) -- objective is maximised (NSE, KGE, R2).
        False          -- objective is minimised (RMSE, PBIAS).
    """

    def __init__(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        objective: Callable[[Dict[str, float]], float],
        n_iterations: int = 200,
        r: float = 0.2,
        seed: Optional[int] = None,
        maximize: bool = True,
    ) -> None:
        if not param_ranges:
            raise ValueError("param_ranges must not be empty.")
        if n_iterations < 2:
            raise ValueError("n_iterations must be >= 2.")
        if not (0.0 < r <= 1.0):
            raise ValueError("r must be in (0, 1].")

        self.param_ranges = param_ranges
        self.objective = objective
        self.n_iterations = n_iterations
        self.r = r
        self.rng = np.random.default_rng(seed)
        self.maximize = maximize

        self._names: List[str] = list(param_ranges.keys())
        self._lower = np.array([param_ranges[k][0] for k in self._names], dtype=float)
        self._upper = np.array([param_ranges[k][1] for k in self._names], dtype=float)
        self._d = len(self._names)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Dict:
        """
        Execute DDS and return a results dictionary.

        Returns
        -------
        dict with keys:
            best_params  : dict[str, float]  -- best parameter set found (raw floats)
            best_score   : float             -- corresponding objective value
            history      : pd.DataFrame      -- columns = "iteration", param names, "best_score"
        """
        try:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=self.n_iterations, desc="DDS", unit="iter")
        except ImportError:
            pbar = None

        x_best = self._random_uniform()
        f_best = self._evaluate(x_best)
        history: List[Dict] = [self._row(x_best, f_best)]
        logger.info("DDS iter 1/%d | score=%.4f", self.n_iterations, f_best)
        if pbar is not None:
            pbar.update(1)
            pbar.set_postfix(best=f"{f_best:.4f}")

        for i in range(2, self.n_iterations + 1):
            p_perturb = 1.0 - np.log(i) / np.log(self.n_iterations)

            perturb_mask = self.rng.random(self._d) < p_perturb
            if not perturb_mask.any():
                perturb_mask[self.rng.integers(0, self._d)] = True

            x_new = x_best.copy()
            for j in np.where(perturb_mask)[0]:
                x_new[j] = self._perturb(x_best[j], j)

            f_new = self._evaluate(x_new)
            history.append(self._row(x_new, f_new))

            if self._is_better(f_new, f_best):
                x_best, f_best = x_new, f_new
                logger.info(
                    "DDS iter %d/%d | improved score=%.4f", i, self.n_iterations, f_best
                )

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(best=f"{f_best:.4f}")

        if pbar is not None:
            pbar.close()

        best_dict  = dict(zip(self._names, x_best.tolist()))
        history_df = pd.DataFrame(history)
        history_df.insert(0, "iteration", range(1, len(history_df) + 1))
        return {
            "best_params": best_dict,
            "best_score":  float(f_best),
            "history":     history_df,   # columns: iteration, [params...], best_score
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _random_uniform(self) -> np.ndarray:
        u = self.rng.random(self._d)
        return self._lower + u * (self._upper - self._lower)

    def _perturb(self, x_j: float, j: int) -> float:
        """
        Neighbour generation for dimension j.
        x_new_j = x_best_j + r * (x_max_j - x_min_j) * N(0,1)
        Reflected at bounds (Eq. 4, Tolson & Shoemaker 2007).
        """
        sigma = self.r * (self._upper[j] - self._lower[j])
        x_new = x_j + sigma * self.rng.standard_normal()
        if x_new < self._lower[j]:
            x_new = 2.0 * self._lower[j] - x_new
        if x_new > self._upper[j]:
            x_new = 2.0 * self._upper[j] - x_new
        return float(np.clip(x_new, self._lower[j], self._upper[j]))

    def _evaluate(self, x: np.ndarray) -> float:
        param_dict = dict(zip(self._names, x.tolist()))
        return float(self.objective(param_dict))

    def _is_better(self, f_new: float, f_best: float) -> bool:
        return f_new > f_best if self.maximize else f_new < f_best

    def _row(self, x: np.ndarray, score: float) -> Dict:
        row = dict(zip(self._names, x.tolist()))
        row["best_score"] = score
        return row


# ---------------------------------------------------------------------------

class DDSCalibration:
    """
    DDS backed by CalibrationManager -- same interface as GLUE and ParallelDE.

    Wraps the standalone DDS optimiser and wires CalibrationManager.run_iteration
    as the objective function.

    Parameters
    ----------
    manager : CalibrationManager
        Infrastructure layer that owns run_iteration.

    Usage
    -----
    >>> from spyswat.swat_calib.analysis.algorithms import DDSCalibration
    >>>
    >>> dds = DDSCalibration(manager)
    >>> result = dds.run(param_ranges, obs, n_iterations=300, seed=42)

    # Or via the SWATCalibration facade:
    >>> calib.dds.run(param_ranges, obs, n_iterations=300, seed=42)
    """

    def __init__(self, manager) -> None:
        self._manager = manager

    def run(
        self,
        param_ranges: Dict[str, Tuple],
        observed_series,
        n_iterations: int = 200,
        r: float = 0.2,
        seed: Optional[int] = None,
        metric: str = "nse",
        output_variable: str = "FLOW_OUTcms",
        reach_id: int = 1,
        maximize: bool = True,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
    ) -> dict:
        """
        Run DDS calibration.

        Parameters
        ----------
        param_ranges    : dict  Supports three formats (mixable):
                            "CN2.mgt": (60, 98)                       # bounds only
                            "CN2.mgt": ((60, 98), "r")                # + method
                            "CN2.mgt": ((60, 98), "r", [71, 45, 70]) # + subbasins
        observed_series : pd.Series  observed discharge with DatetimeIndex
        n_iterations    : int   total evaluation budget (recommended >= 200)
        r               : float perturbation size as fraction of range (0, 1]
        seed            : int | None  random seed for reproducibility
        metric          : str   objective metric; higher is better unless maximize=False
        maximize        : bool  True for NSE/KGE/R2, False for RMSE/PBIAS
        param_methods   : optional override for method per param (v/r/a)
        param_subbasins : optional override for subbasin list per param

        Returns
        -------
        dict with keys: best_params, best_score, history (pd.DataFrame)
        """
        # Parse unified spec; explicit kwargs override spec values
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}

        # DDS passes {name: float}; manager.run_iteration auto-formats it
        def objective(params: dict) -> float:
            return self._manager.run_iteration(
                params, observed_series, metric, reach_id, output_variable,
                methods=methods, subbasins=subbasins
            )

        dds = DDS(
            param_ranges = bounds,
            objective    = objective,
            n_iterations = n_iterations,
            r            = r,
            seed         = seed,
            maximize     = maximize,
        )
        result = dds.run()
        # Format raw {name: float} -> {name: [(val, method, ...)]} for consistency
        result["best_params"] = self._manager._format_params(result["best_params"])
        return result
