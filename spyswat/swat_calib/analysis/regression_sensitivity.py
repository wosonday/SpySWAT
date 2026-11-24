"""Regression-based sensitivity analysis of calibration runs (SWAT-CUP 'global')."""
from typing import Dict

import numpy as np
import pandas as pd
from scipy import stats

from spyswat.swat_calib.calibration.param_spec import parse_spec


def regression_sensitivity(
    runs: pd.DataFrame,
    param_ranges: dict,
    score_col: str = "score",
) -> pd.DataFrame:
    """
    OLS regression of ``score`` on the parameters scaled to [0, 1].

    One row per run in ``runs`` (a column per key of ``param_ranges`` and
    ``score_col``). Rows with a NaN score or parameter are dropped. Returns one row
    per parameter with ``parameter, coef, t_stat, p_value, rank`` (rank 1 = most
    sensitive, i.e. largest |t|), plus ``result.attrs["n_runs"]``.

    Raises ``ValueError`` when there are too few usable rows (``n <= k + 1``),
    a parameter column is missing, or a parameter is constant (zero variance).
    """
    bounds, _, _ = parse_spec(param_ranges)
    params = list(bounds)

    missing = [name for name in params if name not in runs.columns]
    if missing:
        raise ValueError(
            f"Missing parameter column(s) in runs: {', '.join(missing)}"
        )
    if score_col not in runs.columns:
        raise ValueError(f"Missing score column in runs: {score_col}")

    data = runs[params + [score_col]].apply(pd.to_numeric, errors="coerce").dropna()
    n, k = len(data), len(params)
    if n <= k + 1:
        raise ValueError(
            f"Not enough usable runs for regression sensitivity: "
            f"n={n} rows, k={k} parameters (need n > k + 1)"
        )

    scaled = np.empty((n, k), dtype=float)
    for j, name in enumerate(params):
        lo, hi = bounds[name]
        span = hi - lo
        if span == 0:
            raise ValueError(f"Parameter '{name}' is constant (zero variance)")
        column = data[name].to_numpy(dtype=float)
        scaled[:, j] = (column - lo) / span
        if np.all(scaled[:, j] == scaled[0, j]):
            raise ValueError(f"Parameter '{name}' is constant (zero variance)")

    design = np.column_stack([np.ones(n), scaled])
    y = data[score_col].to_numpy(dtype=float)
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)

    resid = y - design @ coef
    dof = n - k - 1
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(design.T @ design)))[1:]
    t_stat = coef[1:] / se
    p_value = 2.0 * stats.t.sf(np.abs(t_stat), dof)

    order = np.argsort(-np.abs(t_stat), kind="stable")
    rank = np.empty(k, dtype=int)
    rank[order] = np.arange(1, k + 1)
    result = pd.DataFrame({
        "parameter": params,
        "coef": coef[1:],
        "t_stat": t_stat,
        "p_value": p_value,
        "rank": rank,
    }).sort_values("rank", ignore_index=True)
    result.attrs["n_runs"] = n
    return result
