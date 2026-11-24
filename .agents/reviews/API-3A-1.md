# API-3A review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

Implementation matches the API-3a spec and design (`regression_sensitivity` signature, `parse_spec` reuse, NaN-row dropping, `[0, 1]` scaling, OLS with `n - k - 1` dof, `|t|` ranking, `n_runs` attribute, English `ValueError` guards, minimal `__init__.py` export, and scoped log/tests). Hand-check on `n=4, k=1` (`x=[0, 1, 1, 2]` in `[0, 2]`, `y=[1, 2, 4, 5]`) yields `coef=4.0`, `sigma2=1.0`, `se=sqrt(2)`, `t_stat=2*sqrt(2)`, `p_value≈0.1056`, matching the code path. No secrets or out-of-scope changes found.

### Critical
None.

### Major
None.

### Minor
- `spyswat/swat_calib/analysis/regression_sensitivity.py:2`: Unused import `from typing import Dict`.
  - **Fix:** Remove line 2.
- `spyswat/swat_calib/analysis/regression_sensitivity.py:64-65`: Computing `pinv(design.T @ design)` squares the condition number, and an exact zero-residual fit (`sigma2 == 0`) divides `coef[1:]` by `0.0` (emitting `RuntimeWarning` and producing `inf`/`nan` in `t_stat` and `p_value`).
  - **Fix:** Derive `(X^T X)^+` from `np.linalg.svd(design, full_matrices=False)` (`V^T.T @ diag(1 / s**2) @ V^T` for `s > rcond`) and guard `se == 0` (e.g., `np.where(se > 0, coef[1:] / se, np.inf * np.sign(coef[1:]))` or `np.nan` when `coef == 0`).
- `tests/test_regression_sensitivity.py:19-94`: Covers positive coefficients and all listed acceptance cases, but does not exercise negative slopes (`|t_stat|` ranking when `coef < 0`) or a missing `score_col`.
  - **Fix:** Add assertions or a short test with a negative dominant coefficient and a missing `score_col` case.

## CEO triage → rework round (worker-fast)
1. Remove the unused import.
2. Zero-residual fit: no division by zero / RuntimeWarning; `se == 0` → `t_stat = ±inf` (sign of coef), `p_value = 0.0`; coef == 0 and se == 0 → `t_stat = 0`, `p_value = NaN`. Use an SVD-based pseudo-inverse.
3. Tests: negative dominant coefficient ranks first by |t|; missing `score_col` raises; exact-fit case gives no warning.
4. Design decision 11: also set `result.attrs["r2"]`, `["n_used"]`, `["n_dropped"]` (keep `n_runs` = n_used for compatibility); test them.
