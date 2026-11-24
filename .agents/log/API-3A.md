# API-3A — Work log

## 2026-11-24 — Worker (fast), TDD

### Files changed
- `spyswat/swat_calib/analysis/regression_sensitivity.py` (new): `regression_sensitivity(runs, param_ranges, score_col="score")`.
  Bounds parsed with the existing `calibration/param_spec.parse_spec` (unified format); rows with NaN
  score/parameter dropped; each parameter scaled to [0, 1]; OLS via `numpy.linalg.lstsq`; t-stat =
  coef / SE with `n - k - 1` dof; two-sided p from `scipy.stats.t`; ranked by |t| descending;
  columns `parameter, coef, t_stat, p_value, rank`, index 0..k-1; `result.attrs["n_runs"]`.
  `ValueError` (English) for `n <= k + 1`, a missing parameter column and a constant parameter.
- `spyswat/swat_calib/analysis/__init__.py`: one import line + one `__all__` entry (export only).
- `tests/test_regression_sensitivity.py` (new): 6 tests — rank/p-value on synthetic
  `score = 3*x1 + 0.5*x2 + noise`, NaN-row dropping + `n_runs`, too-few rows, missing column,
  constant parameter, method-decorated specs `((35, 98), "r")` / `((0, 1), "a", [1, 2])`.

### Commands and results
- `python -m pytest tests/test_regression_sensitivity.py -q` → `6 passed`
- `python -m pytest tests/ -q` → `470 passed, 11 skipped, 5 warnings, 28 subtests passed in 237.26s`
- `git diff --check` → clean (no output)

### Open questions
- None. Behaviour of `sensitivity=True` wiring in `project.calibration` is out of scope (API-3b / facade task).

## 2026-11-25 — Worker (fast), rework round for review 1 (items 1-4, TDD)

### Tests first (`tests/test_regression_sensitivity.py`, 5 added)
- `test_negative_dominant_coefficient_ranks_first_by_abs_t`: `score = -4*x1 + 0.3*x2 + noise`
  ranks `K1.mgt` first with a negative coefficient by |t|.
- `test_missing_score_column_raises`: a renamed score column raises `ValueError`
  (message names `score`).
- `test_exact_fit_reports_infinite_t_without_warning`: exact linear fit
  (`score = 1 + 2*x1`, x1 = 0..3) → `coef ≈ 2`, `t_stat = +inf`, `p_value = 0.0`, no
  `RuntimeWarning`.
- `test_zero_residual_zero_coefficient_is_not_significant`: constant zero score →
  `t_stat = 0`, `p_value = NaN`, no `RuntimeWarning`.
- `test_attrs_report_fit_quality_and_run_counts`: 120 rows, 1 NaN score + 2 NaN parameters →
  `n_used = 117`, `n_runs = n_used`, `n_dropped = 3`, `0.9 < r2 < 1.0`.

Red run before the implementation change:
- `python -m pytest tests/test_regression_sensitivity.py -q` → `3 failed, 8 passed in 2.67s`
  (exact-fit warning, zero-coefficient case, missing `n_used` attr).

