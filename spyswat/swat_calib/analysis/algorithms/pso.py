"""
Particle Swarm Optimization (PSO) — Kennedy & Eberhart (1995).

Reference:
    Kennedy, J., & Eberhart, R. (1995).
    Particle swarm optimization.
    Proceedings of ICNN'95 - International Conference on Neural Networks,
    4, 1942-1948.
    https://doi.org/10.1109/ICNN.1995.488968

    Shi, Y., & Eberhart, R. (1998).
    A modified particle swarm optimizer.
    Proceedings of IEEE World Congress on Computational Intelligence,
    69-73.
    https://doi.org/10.1109/ICEC.1998.699146

PSO is a population-based stochastic optimisation algorithm inspired by the
social behaviour of bird flocking. Each particle maintains a position (candidate
parameter set) and a velocity updated at every iteration according to:

    v_i = w*v_i + c1*r1*(pbest_i - x_i) + c2*r2*(gbest - x_i)
    x_i = clip(x_i + v_i, lower, upper)

where:
    w   -- inertia weight, decays linearly from w_max to w_min (Shi & Eberhart 1998)
    c1  -- cognitive coefficient (attraction to personal best)
    c2  -- social coefficient    (attraction to global best)
    r1, r2 -- uniform random vectors in [0, 1]

Key properties:
  - No gradient required; effective for non-smooth, non-convex spaces.
  - Swarm-level parallelism: all n_particles positions can be evaluated
    simultaneously via CalibrationManager.run_batch.
  - Early stopping via tolerance (swarm spread) and patience (no improvement).
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standalone PSO  (no SWAT dependency — objective is a callable)
# ---------------------------------------------------------------------------

class PSO:
    """
    Particle Swarm Optimiser.

    Parameters
    ----------
    param_ranges : dict[str, (float, float)]
        Parameter names mapped to (min, max) bounds.
        Keys must use name.ext format (e.g. "CN2.mgt").
    objective : Callable[[dict], float]
        Function that accepts {name: float} and returns a scalar score
        (higher is better, e.g. NSE). Typically wraps
        CalibrationManager.run_iteration for sequential evaluation.
    n_particles : int
        Swarm size (default: max(10, 5*d)).
    max_iterations : int
        Maximum number of iterations (default: 100).
    w_max : float
        Initial inertia weight (default: 0.9, Shi & Eberhart 1998).
    w_min : float
        Final inertia weight (default: 0.4, Shi & Eberhart 1998).
    c1 : float
        Cognitive coefficient (default: 2.0).
    c2 : float
        Social coefficient (default: 2.0).
    v_max_ratio : float
        Maximum velocity as fraction of parameter range (default: 0.2).
    seed : int | None
        Random seed for reproducibility.
    maximize : bool
        True (default) -- objective is maximised (NSE, KGE, R2).
        False          -- objective is minimised (RMSE, PBIAS).
    tol : float
        Early-stop tolerance: stop when best improvement < tol over
        `patience` consecutive iterations (default: 1e-6).
    patience : int
        Number of iterations without improvement before early stop (default: 10).
    """

    def __init__(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        objective: Callable[[Dict[str, float]], float],
        n_particles: Optional[int] = None,
        max_iterations: int = 100,
        w_max: float = 0.9,
        w_min: float = 0.4,
        c1: float = 2.0,
        c2: float = 2.0,
        v_max_ratio: float = 0.2,
        seed: Optional[int] = None,
        maximize: bool = True,
        tol: float = 1e-6,
        patience: int = 10,
    ) -> None:
        if not param_ranges:
            raise ValueError("param_ranges must not be empty.")
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1.")
        if not (0.0 <= w_min <= w_max <= 1.5):
            raise ValueError("Must satisfy 0 <= w_min <= w_max <= 1.5.")
        if c1 <= 0 or c2 <= 0:
            raise ValueError("c1 and c2 must be positive.")
        if not (0.0 < v_max_ratio <= 1.0):
            raise ValueError("v_max_ratio must be in (0, 1].")

        self.param_ranges   = param_ranges
        self.objective      = objective
        self.max_iterations = max_iterations
        self.w_max          = w_max
        self.w_min          = w_min
        self.c1             = c1
        self.c2             = c2
        self.v_max_ratio    = v_max_ratio
        self.rng            = np.random.default_rng(seed)
        self.maximize       = maximize
        self.tol            = tol
        self.patience       = patience

        self._names: List[str] = list(param_ranges.keys())
        self._lower = np.array([param_ranges[k][0] for k in self._names], dtype=float)
        self._upper = np.array([param_ranges[k][1] for k in self._names], dtype=float)
        self._d     = len(self._names)
        self._NP    = n_particles or max(10, 5 * self._d)
        self._v_max = v_max_ratio * (self._upper - self._lower)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Dict:
        """
        Execute PSO and return a results dictionary.

        Returns
        -------
        dict with keys:
            best_params  : dict[str, float]  -- best parameter set found (raw floats)
            best_score   : float             -- corresponding objective value
            history      : pd.DataFrame      -- columns: iteration, best_score,
                                                mean_score, std_score
        """
        try:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=self.max_iterations, desc="PSO", unit="iter")
        except ImportError:
            pbar = None

        # ── Initialisation ──────────────────────────────────────────────
        positions  = self._lower + self.rng.random((self._NP, self._d)) * (self._upper - self._lower)
        velocities = self.rng.uniform(-self._v_max, self._v_max, (self._NP, self._d))

        scores   = np.array([self._evaluate(positions[i]) for i in range(self._NP)])
        pbest_x  = positions.copy()
        pbest_f  = scores.copy()

        gbest_idx = int(np.argmax(pbest_f) if self.maximize else np.argmin(pbest_f))
        gbest_x   = pbest_x[gbest_idx].copy()
        gbest_f   = float(pbest_f[gbest_idx])

        history: List[Dict] = [{
            "iteration":  0,
            "best_score": gbest_f,
            "mean_score": float(scores.mean()),
            "std_score":  float(scores.std()),
        }]
        logger.info(
            "PSO iter 0 | best=%.4f mean=%.4f NP=%d d=%d",
            gbest_f, scores.mean(), self._NP, self._d,
        )

        no_improve = 0
        prev_best  = gbest_f

        # ── Main loop ───────────────────────────────────────────────────
        for t in range(1, self.max_iterations + 1):
            # Linearly decaying inertia (Shi & Eberhart 1998)
            w = self.w_max - (self.w_max - self.w_min) * t / self.max_iterations

            r1 = self.rng.random((self._NP, self._d))
            r2 = self.rng.random((self._NP, self._d))

            velocities = (
                w          * velocities
                + self.c1 * r1 * (pbest_x - positions)
                + self.c2 * r2 * (gbest_x - positions)
            )
            # Clamp velocity to v_max
            velocities = np.clip(velocities, -self._v_max, self._v_max)

            positions  = np.clip(positions + velocities, self._lower, self._upper)
            scores     = np.array([self._evaluate(positions[i]) for i in range(self._NP)])

            # Update personal bests
            if self.maximize:
                improve = scores > pbest_f
            else:
                improve = scores < pbest_f
            pbest_x[improve] = positions[improve]
            pbest_f[improve] = scores[improve]

            # Update global best
            new_gbest_idx = int(np.argmax(pbest_f) if self.maximize else np.argmin(pbest_f))
            new_gbest_f   = float(pbest_f[new_gbest_idx])
            if (self.maximize and new_gbest_f > gbest_f) or \
               (not self.maximize and new_gbest_f < gbest_f):
                gbest_x, gbest_f = pbest_x[new_gbest_idx].copy(), new_gbest_f
                logger.info(
                    "PSO iter %d/%d | improved best=%.4f",
                    t, self.max_iterations, gbest_f,
                )

            history.append({
                "iteration":  t,
                "best_score": gbest_f,
                "mean_score": float(scores.mean()),
                "std_score":  float(scores.std()),
            })

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(best=f"{gbest_f:.4f}", mean=f"{scores.mean():.4f}")

            # Early stopping — patience
            if abs(gbest_f - prev_best) > self.tol:
                prev_best, no_improve = gbest_f, 0
            else:
                no_improve += 1
                if no_improve >= self.patience:
                    logger.info(
                        "PSO early stop at iter %d (patience=%d)", t, self.patience
                    )
                    break

        if pbar is not None:
            pbar.close()

        best_dict = dict(zip(self._names, gbest_x.tolist()))
        return {
            "best_params": best_dict,
            "best_score":  gbest_f,
            "history":     pd.DataFrame(history),  # iteration, best_score, mean_score, std_score
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _evaluate(self, x: np.ndarray) -> float:
        param_dict = dict(zip(self._names, x.tolist()))
        return float(self.objective(param_dict))


# ---------------------------------------------------------------------------
# PSOCalibration  (SWAT-backed, uses run_batch for swarm-level parallelism)
# ---------------------------------------------------------------------------

class PSOCalibration:
    """
    PSO backed by CalibrationManager — same interface as GLUE and ParallelDE.

    Each iteration the entire swarm (n_particles positions) is submitted to
    CalibrationManager.run_batch so that all SWAT runs execute in parallel
    across worker directories.

    Parameters
    ----------
    manager : CalibrationManager
        Infrastructure layer that owns run_batch.

    Usage
    -----
    >>> from spyswat.swat_calib.analysis.algorithms import PSOCalibration
    >>>
    >>> pso = PSOCalibration(manager)
    >>> result = pso.run(param_ranges, obs, n_particles=20, max_iterations=50)

    # Or via the SWATCalibration facade:
    >>> calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50)
    """

    def __init__(self, manager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        param_ranges: Dict[str, Tuple],
        observed_series: pd.Series,
        metric: str = "nse",
        output_variable: str = "FLOW_OUTcms",
        reach_id: int = 1,
        n_particles: Optional[int] = None,
        max_iterations: int = 50,
        w_max: float = 0.9,
        w_min: float = 0.4,
        c1: float = 2.0,
        c2: float = 2.0,
        v_max_ratio: float = 0.2,
        seed: Optional[int] = None,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
        tol: float = 1e-6,
        patience: int = 10,
    ) -> Dict:
        """
        Run PSO calibration with full swarm evaluated in parallel each iteration.

        Parameters
        ----------
        param_ranges    : dict  Supports three formats (mixable):
                            "CN2.mgt": (60, 98)                       # bounds only
                            "CN2.mgt": ((60, 98), "r")                # + method
                            "CN2.mgt": ((60, 98), "r", [71, 45, 70]) # + subbasins
        observed_series : pd.Series  Observed discharge with DatetimeIndex.
        metric          : str    Objective metric, higher = better
                                 (use 'rmse' / 'pbias' with maximize=False).
        n_particles     : int    Swarm size; default max(10, 5*d).
        max_iterations  : int    Maximum number of iterations.
        w_max, w_min    : float  Inertia weight range (Shi & Eberhart 1998).
        c1              : float  Cognitive coefficient.
        c2              : float  Social coefficient.
        v_max_ratio     : float  Max velocity as fraction of parameter range.
        seed            : int | None  Random seed for reproducibility.
        param_methods   : optional override for method per param (v/r/a).
        param_subbasins : optional override for subbasin list per param.
        tol             : float  Early-stop tolerance on best score improvement.
        patience        : int    Iterations without improvement before early stop.

        Returns
        -------
        dict with keys:
            best_params      : dict  {name: [(value, method[, subbasins])]}
            best_score       : float
            history          : pd.DataFrame  (iteration, best_score, mean_score, std_score)
            all_evaluations  : pd.DataFrame  (all params + score + iteration)
        """
        if not (0.0 <= w_min <= w_max <= 1.5):
            raise ValueError("Must satisfy 0 <= w_min <= w_max <= 1.5.")
        if c1 <= 0 or c2 <= 0:
            raise ValueError("c1 and c2 must be positive.")
        if not (0.0 < v_max_ratio <= 1.0):
            raise ValueError("v_max_ratio must be in (0, 1].")

        # ── Parse unified spec ──────────────────────────────────────────
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}

        names  = list(bounds.keys())
        d      = len(names)
        lower  = np.array([bounds[n][0] for n in names], dtype=float)
        upper  = np.array([bounds[n][1] for n in names], dtype=float)
        NP     = n_particles or max(10, 5 * d)
        v_max  = v_max_ratio * (upper - lower)
        rng    = np.random.default_rng(seed)

        maximize = metric in ("nse", "r2", "kge", "pbias") and metric != "pbias"
        # pbias: closer to 0 is better; treat as minimise |pbias| elsewhere —
        # here we keep convention: nse/r2/kge are maximise, rmse/pbias minimise
        maximize = metric in ("nse", "r2", "kge")

        def to_param_sets(pop: np.ndarray) -> List[Dict]:
            return [
                self._manager._format_params(
                    {names[j]: float(pop[i, j]) for j in range(d)},
                    methods, subbasins,
                )
                for i in range(len(pop))
            ]

        def evaluate_swarm(pop: np.ndarray) -> np.ndarray:
            batch_df = self._manager.run_batch(
                to_param_sets(pop), observed_series, [metric], reach_id, output_variable
            )
            if hasattr(batch_df, "columns"):
                return np.array(batch_df[metric].tolist(), dtype=float)
            return np.array(list(batch_df), dtype=float)

        # ── Initialisation ──────────────────────────────────────────────
        positions  = lower + rng.random((NP, d)) * (upper - lower)
        velocities = rng.uniform(-v_max, v_max, (NP, d))

        scores   = evaluate_swarm(positions)
        pbest_x  = positions.copy()
        pbest_f  = scores.copy()

        gbest_idx = int(np.argmax(pbest_f) if maximize else np.argmin(pbest_f))
        gbest_x   = pbest_x[gbest_idx].copy()
        gbest_f   = float(pbest_f[gbest_idx])

        history: List[Dict] = [{
            "iteration":  0,
            "best_score": gbest_f,
            "mean_score": float(scores.mean()),
            "std_score":  float(scores.std()),
        }]
        all_rows: List[Dict] = []
        for i in range(NP):
            row = {names[j]: float(positions[i, j]) for j in range(d)}
            row.update({"score": scores[i], "iteration": 0})
            all_rows.append(row)

        logger.info(
            "PSO iter 0 | best=%.4f mean=%.4f NP=%d d=%d metric=%s",
            gbest_f, scores.mean(), NP, d, metric,
        )

        no_improve = 0
        prev_best  = gbest_f

        try:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=max_iterations, desc="PSO", unit="iter")
        except ImportError:
            pbar = None

        # ── Main loop ───────────────────────────────────────────────────
        for t in range(1, max_iterations + 1):
            w = w_max - (w_max - w_min) * t / max_iterations

            r1 = rng.random((NP, d))
            r2 = rng.random((NP, d))

            velocities = (
                w    * velocities
                + c1 * r1 * (pbest_x - positions)
                + c2 * r2 * (gbest_x - positions)
            )
            velocities = np.clip(velocities, -v_max, v_max)
            positions  = np.clip(positions + velocities, lower, upper)

            scores = evaluate_swarm(positions)

            for i in range(NP):
                row = {names[j]: float(positions[i, j]) for j in range(d)}
                row.update({"score": scores[i], "iteration": t})
                all_rows.append(row)

            # Update personal bests
            improve = scores > pbest_f if maximize else scores < pbest_f
            pbest_x[improve] = positions[improve]
            pbest_f[improve] = scores[improve]

            # Update global best
            new_idx   = int(np.argmax(pbest_f) if maximize else np.argmin(pbest_f))
            new_gbest = float(pbest_f[new_idx])
            if (maximize and new_gbest > gbest_f) or (not maximize and new_gbest < gbest_f):
                gbest_x, gbest_f = pbest_x[new_idx].copy(), new_gbest
                logger.info(
                    "PSO iter %d/%d | improved best=%.4f", t, max_iterations, gbest_f
                )

            history.append({
                "iteration":  t,
                "best_score": gbest_f,
                "mean_score": float(scores.mean()),
                "std_score":  float(scores.std()),
            })

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(best=f"{gbest_f:.4f}", mean=f"{scores.mean():.4f}")

            if abs(gbest_f - prev_best) > tol:
                prev_best, no_improve = gbest_f, 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    logger.info(
                        "PSO early stop at iter %d (patience=%d)", t, patience
                    )
                    break

        if pbar is not None:
            pbar.close()

        best_raw    = {names[j]: float(gbest_x[j]) for j in range(d)}
        best_params = self._manager._format_params(best_raw, methods, subbasins)

        return {
            "best_params":     best_params,
            "best_score":      gbest_f,
            "history":         pd.DataFrame(history),
            "all_evaluations": pd.DataFrame(all_rows),
        }
