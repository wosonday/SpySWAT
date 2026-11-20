# Log OPT-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-20 · claude-opus-5.5 · step 1/1
- RED: `test_optimize_local_method_is_the_one_requested` failed on the old code (the spy
  saw no `method` and no `options`).
- Done: `optimize` passes `method` and `options={"maxiter": max_iter}` to
  `scipy.optimize.minimize`. `"minimize"` (the README value) maps to `method=None`, which
  is scipy's default L-BFGS-B, so existing scripts keep their behaviour. The docstring now
  lists the methods and warns that a local method cannot leave a region where every run
  fails.
- Tests:
  - `test_optimize_local_method_is_the_one_requested` (Nelder-Mead and the `"minimize"` alias);
  - `test_optimize_partial_failures_return_best_valid_row` (DE / Nelder-Mead / Powell,
    every 4th run crashes, all real RMSE values > 1e6). It checks that the returned
    score/params equal the best finite history row.
- Decision: no method whitelist under `penalize`; see the correction in
  `.agents/reviews/coord-1-1.md`.
- Known noise: Powell's parabolic step emits `RuntimeWarning: invalid value` when a
  bracket point is `inf`; the result is still the best valid row.
- Files changed: `spyswat/swat_calib/analysis/calibration.py`, `tests/test_metrics.py`,
  `README.md`, `README_VI.md`, `CHANGELOG.md`, `AGENTS.md` (expected test count)
- Checks:
  - `pytest tests/ -q` → **327 passed / 11 skipped / 0 failed**, 5 warnings, 278 s;
  - `git diff --check` → exit 0.
- Not committed.
