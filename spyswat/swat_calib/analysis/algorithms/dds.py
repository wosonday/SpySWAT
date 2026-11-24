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
import warnings
import numpy as np
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple

from spyswat.swat_calib.analysis.statistics import is_maximize, to_objective

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared vocabulary helpers (imported by the other algorithms, SWATCalibration
# and SWATSensitivity).  Kept here because ``dds`` is the leaf module of the
# algorithms package (no sibling imports), so importing from it cannot create a
# cycle.
# ---------------------------------------------------------------------------

#: Sentinel for "this deprecated keyword was not passed".
_MISSING = object()


def _resolve_seed(seed):
    """Resolve ``seed=None`` to a concrete int before the first draw.

    The concrete integer is ``int(np.random.SeedSequence().entropy % 2**63)`` so
    a resumed run (API-5) can pass it back and replay the exact same sequence.
    """
    if seed is None:
        return int(np.random.SeedSequence().entropy % 2 ** 63)
    return int(seed)


def _resolve_observed(observed, observed_series, reach_id, output_variable, outputs,
                      stacklevel=3):
    """Map the deprecated ``observed_series`` / ``reach_id``+``output_variable`` args.

    Returns ``(observed, outputs)``.  Emits one ``DeprecationWarning`` per
    deprecated input and raises ``TypeError`` when an old name and its new
    counterpart are both given.
    """
    if observed_series is not _MISSING:
        if observed is not _MISSING and observed is not None:
            raise TypeError(
                "pass either 'observed' or the deprecated 'observed_series', not both"
            )
        warnings.warn(
            "'observed_series' is deprecated; use 'observed' instead.",
            DeprecationWarning, stacklevel=stacklevel,
        )
        observed = observed_series
    if reach_id is not _MISSING or output_variable is not _MISSING:
        if outputs is not None:
            raise TypeError(
                "pass either 'outputs' or the deprecated 'reach_id'/'output_variable', "
                "not both"
            )
        var = "FLOW_OUTcms" if output_variable is _MISSING else output_variable
        rid = 1 if reach_id is _MISSING else reach_id
        warnings.warn(
            f"'reach_id' and 'output_variable' are deprecated; pass "
            f"outputs={{{var!r}: [{rid}]}} instead.",
            DeprecationWarning, stacklevel=stacklevel,
        )
        outputs = {var: [rid]}
    return observed, outputs


def _reported(metric, metrics):
    """Reported metric names as a list, ``metric`` always first and included."""
    if metrics is None:
        return [metric]
    if isinstance(metrics, str):
        names = [metrics]
    else:
        names = list(metrics)
    return [metric] + [n for n in names if n != metric]


def _batch_scores(batch_df, metric):
    """Per-run score as a float ndarray from a ``run_batch`` result.

    The multi-site path returns a ``score`` column; legacy single-site callers
    (and old-style mocks) may return the bare ``metric`` column or a plain list.
    """
    if hasattr(batch_df, "columns"):
        col = "score" if "score" in batch_df.columns else metric
        return np.asarray(batch_df[col].tolist(), dtype=float)
    return np.asarray(list(batch_df), dtype=float)


def _params_frame(names, population):
    """Raw parameter columns for one batch (population ndarray of shape (n, d))."""
    return pd.DataFrame({name: population[:, j] for j, name in enumerate(names)})


def _runs_frame(param_df, batch_df, metric):
    """One batch as ``runs`` rows: params + ``score`` + per-site columns."""
    runs = param_df.reset_index(drop=True).copy()
    if hasattr(batch_df, "columns"):
        src = batch_df.reset_index(drop=True)
        if "score" in src.columns:
            runs["score"] = src["score"]
        elif metric in src.columns:
            runs["score"] = src[metric]
        else:
            runs["score"] = np.nan
        for col in src.columns:
            if col in ("score", metric):
                continue
            runs[col] = src[col].tolist()
    else:
        runs["score"] = list(batch_df)
    return runs


def _single_site(observed, outputs):
    """The single ``(variable, reach)`` implied by ``observed``/``outputs``.

    Used for the scalar "performance" read in ``analyze``.  ``outputs`` defaults
    to ``{"FLOW_OUTcms": [1]}`` for a bare ``observed`` Series; a dict ``observed``
    contributes its first site.
    """
    if isinstance(observed, pd.Series):
        if outputs is None:
            return "FLOW_OUTcms", 1
        sites = [(v, r) for v in sorted(outputs) for r in outputs[v]]
        if len(sites) != 1:
            raise ValueError(
                f"a bare observed Series needs exactly one output site; got "
                f"{len(sites)} from {outputs!r}."
            )
        return sites[0]
    return next(iter(observed))


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
    score_key : Callable[[float], float] | None
        Optional ranking key where SMALLER IS BETTER (e.g. ``|pbias|``); when
        given it replaces ``maximize``. Reported scores stay the raw values.
    A NaN/inf score (failed run) is always ranked worst.
    """

    def __init__(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        objective: Callable[[Dict[str, float]], float],
        n_iterations: int = 200,
        r: float = 0.2,
        seed: Optional[int] = None,
        maximize: bool = True,
        score_key: Optional[Callable[[float], float]] = None,
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
        self.score_key = score_key

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
            history      : pd.DataFrame      -- columns = "iteration", param names,
                                                "score" (this evaluation) and
                                                "best_score" (running best so far)

        Raises RuntimeError when every evaluation failed (NaN).
        """
        try:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=self.n_iterations, desc="DDS", unit="iter")
        except ImportError:
            pbar = None

        x_best = self._random_uniform()
        f_best = self._evaluate(x_best)
        history: List[Dict] = [self._row(x_best, f_best, f_best)]
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
            if self._is_better(f_new, f_best):
                x_best, f_best = x_new, f_new
                logger.info(
                    "DDS iter %d/%d | improved score=%.4f", i, self.n_iterations, f_best
                )
            history.append(self._row(x_new, f_new, f_best))

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(best=f"{f_best:.4f}")

        if pbar is not None:
            pbar.close()

        if not np.isfinite(self._key(f_best)):
            raise RuntimeError(
                f"all runs failed: DDS got no valid score in {self.n_iterations} evaluations"
            )
        best_dict  = dict(zip(self._names, x_best.tolist()))
        history_df = pd.DataFrame(history)
        history_df.insert(0, "iteration", range(1, len(history_df) + 1))
        return {
            "best_params": best_dict,
            "best_score":  float(f_best),
            "history":     history_df,   # columns: iteration, [params...], score, best_score
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

    def _key(self, f: float) -> float:
        """Ranking key, smaller is better; NaN/inf (failed run) -> +inf (worst)."""
        if not np.isfinite(f):
            return np.inf
        if self.score_key is not None:
            return float(self.score_key(f))
        return -f if self.maximize else f

    def _is_better(self, f_new: float, f_best: float) -> bool:
        return self._key(f_new) < self._key(f_best)

    def _row(self, x: np.ndarray, score: float, best: float) -> Dict:
        row = dict(zip(self._names, x.tolist()))
        row["score"] = score
        row["best_score"] = best
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
        observed=_MISSING,
        n_iterations: int = 200,
        r: float = 0.2,
        seed: Optional[int] = None,
        metric: str = "nse",
        output_variable=_MISSING,
        reach_id=_MISSING,
        maximize: Optional[bool] = None,
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
    ) -> dict:
        """
        Run DDS calibration.

        on_failure      : "raise" (default) -- an exception from run_iteration
                          propagates, and a non-finite score raises RuntimeError;
                          "penalize" -- the run counts as failed (NaN, ranked worst)
                          and the search continues.

        Parameters
        ----------
        param_ranges    : dict  Supports three formats (mixable):
                            "CN2.mgt": (60, 98)                       # bounds only
                            "CN2.mgt": ((60, 98), "r")                # + method
                            "CN2.mgt": ((60, 98), "r", [71, 45, 70]) # + subbasins
        observed        : pd.Series or {(variable, reach): pd.Series}  observed
        n_iterations    : int   total evaluation budget (recommended >= 200)
        r               : float perturbation size as fraction of range (0, 1]
        seed            : int | None  random seed for reproducibility
        metric          : str   objective metric (direction from the metric registry:
                                nse/r2/kge/correlation maximised, rmse/mae/rsr minimised,
                                pbias -> |pbias| minimised)
        maximize        : bool | None  explicit override of the direction (plain
                                maximise / minimise of the raw score); default None
                                = derive from ``metric``
        param_methods   : optional override for method per param (v/r/a)
        param_subbasins : optional override for subbasin list per param
        outputs, weights, metrics, calib_period, valid_period, step, agg, store :
                                the multi-site vocabulary passed through to
                                ``run_iteration`` (see CalibrationManager).

        Returns
        -------
        dict with keys: best_params, best_score, history (pd.DataFrame),
                        seed (int), runs (pd.DataFrame)
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

        # Parse unified spec; explicit kwargs override spec values
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        methods   = {**_m, **(param_methods   or {})}
        subbasins = {**_s, **(param_subbasins or {})}
        names     = list(bounds.keys())

        if on_failure not in ("raise", "penalize"):
            raise ValueError(f"on_failure must be 'raise' or 'penalize', got {on_failure!r}")
        to_objective(metric, 0.0)  # validates the metric name (ValueError if unknown)

        first = [True]

        # DDS passes {name: float}; manager.run_iteration auto-formats it
        def objective(params: dict) -> float:
            is_initial = first[0]
            first[0] = False
            common = dict(
                metric=metric, outputs=outputs, weights=weights, metrics=metrics,
                calib_period=calib_period, valid_period=valid_period, step=step,
                agg=agg, store=store, methods=methods, subbasins=subbasins,
                is_initial=is_initial,
            )
            if on_failure == "penalize":
                try:
                    return float(self._manager.run_iteration(params, observed, **common))
                except Exception as exc:  # failed run -> NaN -> ranked worst
                    logger.warning("DDS: run failed (%s)", exc)
                    return float("nan")
            score = float(self._manager.run_iteration(params, observed, **common))
            if not np.isfinite(score):
                raise RuntimeError(
                    f"run produced no valid score ({metric}={score}); "
                    "use on_failure='penalize' to continue past failed runs"
                )
            return score

        if maximize is None:
            dds = DDS(
                param_ranges = bounds,
                objective    = objective,
                n_iterations = n_iterations,
                r            = r,
                seed         = seed,
                maximize     = is_maximize(metric),
                score_key    = lambda s: to_objective(metric, s),
            )
        else:
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
        result["best_params"] = self._manager._format_params(
            result["best_params"], methods, subbasins
        )
        result["seed"] = seed
        result["runs"] = result["history"][names + ["score"]].copy()
        return result
