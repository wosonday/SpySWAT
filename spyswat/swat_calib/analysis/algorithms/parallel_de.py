"""
Parallel Differential Evolution (DE/rand/1/bin, DE/best/1/bin).

Reference:
    Storn, R., & Price, K. (1997). Differential evolution: A simple and
    efficient heuristic for global optimization over continuous spaces.
    Journal of Global Optimization, 11(4), 341-359.
    https://doi.org/10.1023/A:1008202821328

Key difference from scipy.optimize.differential_evolution:
    Each generation evaluates the entire NP-candidate population in parallel
    via CalibrationManager.run_batch, making full use of SWAT worker directories.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ParallelDE:
    """
    Parallel Differential Evolution calibration.

    Each generation, ALL NP trial vectors are evaluated simultaneously through
    CalibrationManager.run_batch, which distributes SWAT runs across parallel
    worker directories.

    Parameters
    ----------
    manager : CalibrationManager
        Infrastructure layer that owns run_batch.

    Usage
    -----
    >>> from spyswat.swat_calib.analysis.algorithms import ParallelDE
    >>> from spyswat.swat_calib.calibration import CalibrationManager
    >>>
    >>> manager = CalibrationManager(project)
    >>> de = ParallelDE(manager)
    >>> result = de.run(
    ...     param_ranges    = param_ranges,
    ...     observed_series = obs,
    ...     pop_size        = 20,
    ...     max_generations = 40,
    ...     seed            = 42,
    ... )
    """

    VALID_STRATEGIES = ("rand/1/bin", "best/1/bin")

    def __init__(self, manager):
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
        pop_size: Optional[int] = None,
        max_generations: int = 20,
        F: float = 0.8,
        CR: float = 0.9,
        strategy: str = "rand/1/bin",
        seed: Optional[int] = None,
        param_methods: Optional[Dict[str, str]] = None,
        param_subbasins: Optional[Dict[str, list]] = None,
        tol: float = 1e-6,
        patience: int = 5,
    ) -> Dict:
        """
        Run Parallel DE and return results dict.

        Parameters
        ----------
        param_ranges    : dict  Supports three formats (mixable):
                            "CN2.mgt": (60, 98)                       # bounds only
                            "CN2.mgt": ((60, 98), "r")                # + method
                            "CN2.mgt": ((60, 98), "r", [71, 45, 70]) # + subbasins
        param_methods   : optional override for method per param (v/r/a)
        param_subbasins : optional override for subbasin list per param
        pop_size        : population size NP; default max(10, 5*d)
        max_generations : maximum number of generations
        F               : mutation factor in (0, 2]
        CR              : crossover rate in [0, 1]
        strategy        : 'rand/1/bin' (diverse) or 'best/1/bin' (fast convergence)
        seed            : random seed for reproducibility
        tol             : early stop when max(scores) - min(scores) < tol
        patience        : early stop after N generations without improvement

        Returns
        -------
        dict with keys:
            best_params      : dict  (name -> [(value, method[, subbasins])])
            best_score       : float
            history          : pd.DataFrame  (generation, best_score, mean_score, std_score)
            all_evaluations  : pd.DataFrame  (all params + score + generation)
        """
        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(
                "strategy must be one of " + str(self.VALID_STRATEGIES) +
                ", got '" + strategy + "'"
            )
        if not (0 < F <= 2):
            raise ValueError("F must be in (0, 2].")
        if not (0 <= CR <= 1):
            raise ValueError("CR must be in [0, 1].")

        # Parse unified spec; explicit kwargs override spec values
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        self._manager._methods   = {**_m, **(param_methods   or {})}
        self._manager._subbasins = {**_s, **(param_subbasins or {})}

        names  = list(bounds.keys())
        d      = len(names)
        lower  = np.array([bounds[n][0] for n in names], dtype=float)
        upper  = np.array([bounds[n][1] for n in names], dtype=float)
        NP     = pop_size or max(10, 5 * d)
        rng    = np.random.default_rng(seed)

        def to_param_sets(population: np.ndarray) -> List[Dict]:
            # Pass raw {name: float} — manager formats on the fly in run_batch
            return [
                {names[j]: float(row[j]) for j in range(d)}
                for row in population
            ]

        def evaluate(pop: np.ndarray) -> np.ndarray:
            batch_df = self._manager.run_batch(
                to_param_sets(pop), observed_series, [metric], reach_id, output_variable
            )
            if hasattr(batch_df, "columns"):
                return np.array(batch_df[metric].tolist(), dtype=float)
            return np.array(list(batch_df), dtype=float)

        # ── Initialisation ──────────────────────────────────────────────
        population = lower + rng.random((NP, d)) * (upper - lower)
        scores     = evaluate(population)

        gen_history: List[Dict] = []
        all_rows:    List[Dict] = []

        for k in range(NP):
            row = dict(zip(names, population[k].tolist()))
            row.update({"score": scores[k], "generation": 0})
            all_rows.append(row)

        gen_history.append({
            "generation": 0,
            "best_score": float(scores.max()),
            "mean_score": float(scores.mean()),
            "std_score":  float(scores.std()),
        })
        logger.info(
            "DE gen 0 | best=%.4f mean=%.4f NP=%d d=%d strategy=%s",
            scores.max(), scores.mean(), NP, d, strategy,
        )

        no_improve      = 0
        best_score_prev = float(scores.max())

        try:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=max_generations, desc="DE Gen", unit="gen")
        except ImportError:
            pbar = None

        # ── Main loop ───────────────────────────────────────────────────
        for gen in range(1, max_generations + 1):
            best_idx = int(np.argmax(scores))
            trials   = np.empty_like(population)

            for i in range(NP):
                candidates = [j for j in range(NP) if j != i]
                r1, r2, r3 = rng.choice(candidates, 3, replace=False)

                base   = population[best_idx] if strategy == "best/1/bin" else population[r1]
                mutant = np.clip(base + F * (population[r2] - population[r3]), lower, upper)

                j_rand     = rng.integers(0, d)
                cross_mask = rng.random(d) < CR
                cross_mask[j_rand] = True
                trials[i]  = np.where(cross_mask, mutant, population[i])

            trial_scores = evaluate(trials)
            for k in range(NP):
                row = dict(zip(names, trials[k].tolist()))
                row.update({"score": trial_scores[k], "generation": gen})
                all_rows.append(row)

            improve_mask = trial_scores >= scores
            population   = np.where(improve_mask[:, None], trials, population)
            scores       = np.where(improve_mask, trial_scores, scores)

            current_best = float(scores.max())
            gen_history.append({
                "generation": gen,
                "best_score": current_best,
                "mean_score": float(scores.mean()),
                "std_score":  float(scores.std()),
            })
            logger.info(
                "DE gen %d/%d | best=%.4f mean=%.4f",
                gen, max_generations, current_best, scores.mean(),
            )

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(best=f"{current_best:.4f}", mean=f"{scores.mean():.4f}")

            if (scores.max() - scores.min()) < tol:
                logger.info("DE converged at gen %d (tol=%.2e)", gen, tol)
                break

            if current_best > best_score_prev + tol:
                best_score_prev, no_improve = current_best, 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    logger.info("DE early stop at gen %d (patience=%d)", gen, patience)
                    break

        if pbar is not None:
            pbar.close()

        best_idx    = int(np.argmax(scores))
        best_raw    = {names[j]: float(population[best_idx, j]) for j in range(d)}
        best_params = self._manager._format_params(best_raw)

        return {
            "best_params":     best_params,
            "best_score":      float(scores[best_idx]),
            "history":         pd.DataFrame(gen_history),
            "all_evaluations": pd.DataFrame(all_rows),
        }
