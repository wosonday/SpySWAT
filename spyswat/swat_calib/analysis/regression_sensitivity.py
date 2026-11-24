"""Regression-based sensitivity analysis of calibration runs (SWAT-CUP 'global')."""

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
    sensitive, i.e. largest |t|). ``result.attrs`` reports ``n_runs`` (= ``n_used``),
    ``n_used``, ``n_dropped`` and the regression ``r2``.

    An exact fit (zero standard error) reports ``t_stat`` as +/-inf with the sign of
    the coefficient and ``p_value = 0.0``; a zero coefficient with a zero standard
    error reports ``t_stat = 0`` and ``p_value = NaN``.

    Raises ``ValueError`` when there are too few usable rows (``n <= k + 1``),
    a parameter column (or ``score_col``) is missing, or a parameter is constant
    (zero variance).
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
    n_total, n = len(runs), len(data)
    k = len(params)
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
    sse = float(resid @ resid)
    sigma2 = sse / dof

    # (X^T X)^+ from the SVD of X: avoids squaring the condition number.
    _, singular, vt = np.linalg.svd(design, full_matrices=False)
    tol = np.finfo(float).eps * max(design.shape) * singular[0]
    inv_sq = np.zeros_like(singular)
    keep = singular > tol
    inv_sq[keep] = 1.0 / singular[keep] ** 2
    se = np.sqrt(np.clip(sigma2 * np.diag((vt.T * inv_sq) @ vt)[1:], 0.0, None))

    coefs = coef[1:]
    t_stat = np.empty(k, dtype=float)
    p_value = np.empty(k, dtype=float)
    positive_se = se > 0.0
    t_stat[positive_se] = coefs[positive_se] / se[positive_se]
    p_value[positive_se] = 2.0 * stats.t.sf(np.abs(t_stat[positive_se]), dof)

    # Zero standard error (exact fit): t is unbounded, so keep the coefficient sign.
    if not positive_se.all():
        zero_coefs = coefs[~positive_se]
        t_stat[~positive_se] = np.where(
            zero_coefs > 0.0, np.inf, np.where(zero_coefs < 0.0, -np.inf, 0.0)
        )
        p_value[~positive_se] = np.where(zero_coefs == 0.0, np.nan, 0.0)

    order = np.argsort(-np.abs(t_stat), kind="stable")
    rank = np.empty(k, dtype=int)
    rank[order] = np.arange(1, k + 1)
    result = pd.DataFrame({
        "parameter": params,
        "coef": coefs,
        "t_stat": t_stat,
        "p_value": p_value,
        "rank": rank,
    }).sort_values("rank", ignore_index=True)

    sst = float(((y - y.mean()) ** 2).sum())
    if sst > 0.0:
        r2 = 1.0 - sse / sst
    else:
        r2 = 1.0 if sse == 0.0 else 0.0

    result.attrs["n_runs"] = n
    result.attrs["n_used"] = n
    result.attrs["n_dropped"] = n_total - n
    result.attrs["r2"] = r2
    return result
