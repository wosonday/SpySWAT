"""
Dynamically Dimensioned Search (DDS) — Tolson & Shoemaker (2007).

Reference:
    Tolson, B. A., & Shoemaker, C. A. (2007).
    Dynamically dimensioned search algorithm for computationally efficient
    watershed model calibration.
    Water Resources Research, 43(1), W01413.
    https://doi.org/10.1029/2005WR004723

DDS is designed for single-objective calibration of computationally expensive
models when the evaluation budget N is small (100–1000 runs). Key properties:
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
        Function that accepts a parameter dict and returns a scalar score
        (higher is better, e.g. NSE).  Typically wraps
        ``CalibrationManager.run_iteration``.
    n_iterations : int
        Total evaluation budget (recommended >= 200).
    r : float
        Perturbation size as fraction of parameter range (default 0.2 per
        Tolson & Shoemaker 2007, Section 3).
    seed : int | None
        Random seed for reproducibility.
    maximize : bool
        True (default) — objective is maximised (NSE, KGE, R2, …).
        False        — objective is minimised (RMSE, PBIAS, …).
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
        self._d = len(self._names)   # number of dimensions

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Dict:
        """
        Execute DDS and return a results dictionary.

        Returns
        -------
        dict with keys:
            best_params  : dict[str, float]  — best parameter set found
            best_score   : float             — corresponding objective value
            history      : pd.DataFrame      — columns = param names + "score"
                           one row per iteration, sorted by iteration order
        """
        # ── Step 1: random initial solution ──────────────────────────
        x_best = self._random_uniform()
        f_best = self._evaluate(x_best)
        history: List[Dict] = [self._row(x_best, f_best)]
        logger.info("DDS iter 1/%d | score=%.4f", self.n_iterations, f_best)

        # ── Step 2: DDS main loop (iterations 2..N) ───────────────────
        for i in range(2, self.n_iterations + 1):
            # Perturbation probability (Eq. 3, Tolson & Shoemaker 2007)
            p_perturb = 1.0 - np.log(i) / np.log(self.n_iterations)

            # Select dimensions to perturb
            perturb_mask = self.rng.random(self._d) < p_perturb
            # Guarantee at least one dimension is perturbed
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

        best_dict = dict(zip(self._names, x_best.tolist()))
        hist_df = pd.DataFrame(history)

        return {
            "best_params": best_dict,
            "best_score": float(f_best),
            "history": hist_df,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _random_uniform(self) -> np.ndarray:
        """Uniform random sample within bounds."""
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

        # Reflect at lower bound
        if x_new < self._lower[j]:
            x_new = 2.0 * self._lower[j] - x_new
        # Reflect at upper bound
        if x_new > self._upper[j]:
            x_new = 2.0 * self._upper[j] - x_new

        # If still outside (double reflection) clip to bound
        x_new = float(np.clip(x_new, self._lower[j], self._upper[j]))
        return x_new

    def _evaluate(self, x: np.ndarray) -> float:
        param_dict = dict(zip(self._names, x.tolist()))
        return float(self.objective(param_dict))

    def _is_better(self, f_new: float, f_best: float) -> bool:
        if self.maximize:
            return f_new > f_best
        return f_new < f_best

    def _row(self, x: np.ndarray, score: float) -> Dict:
        row = dict(zip(self._names, x.tolist()))
        row["score"] = score
        return row
