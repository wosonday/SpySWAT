---
id: api-3a
branch: feat/api-3a
tier: fast
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-3a: pure regression sensitivity from calibration runs (SWAT-CUP "global sensitivity")

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` (section API, bullet
`calibration(sensitivity=True)`).

## Build
New module `spyswat/swat_calib/analysis/regression_sensitivity.py`, exported from
`spyswat/swat_calib/analysis/__init__.py`:

```python
def regression_sensitivity(runs: pd.DataFrame, param_ranges: dict, score_col: str = "score")
        -> pd.DataFrame
```
- `runs` has one row per run, a column per key of `param_ranges` (exact key, e.g. `"CN2.mgt"`) and
  `score_col`. Bounds come from `param_ranges` in the unified format (AGENTS.md rule 3); parse them with
  the existing parser in `spyswat/swat_calib/calibration/param_spec.py` (do not re-implement it).
- Drop rows whose score or any parameter is NaN. Scale each parameter to [0, 1] with its bounds.
- OLS `score ~ 1 + x1 + ... + xk` (numpy `lstsq`); t-stat per parameter = coef / standard error;
  two-sided p-value from Student t with `n - k - 1` dof (`scipy.stats.t`). Rank by |t| descending (1 = most
  sensitive).
- Result columns: `parameter, coef, t_stat, p_value, rank`; index 0..k-1 sorted by rank; attribute
  `result.attrs["n_runs"]`.
- ValueError (English) when `n <= k + 1` usable rows, when a parameter column is missing, or when a
  parameter is constant (zero variance).

## Files in scope
`spyswat/swat_calib/analysis/regression_sensitivity.py` (new), `spyswat/swat_calib/analysis/__init__.py`
(export only — another task also adds one export line there; keep your change to one added import line and
one `__all__` entry), `tests/test_regression_sensitivity.py` (new), `.agents/log/API-3A.md`.

## Acceptance criteria
- [ ] Synthetic test: score = 3*x1 + 0.5*x2 + noise (seeded), x3 pure noise → rank x1 > x2 > x3,
      p(x1) < 0.01, p(x3) > 0.05; NaN rows dropped; too-few-rows / missing column / constant param raise;
      method-decorated specs like `((35, 98), "r")` use the inner bounds.
- [ ] `python -m pytest tests/test_regression_sensitivity.py -q` then `python -m pytest tests/ -q` pass
      (baseline 464 passed, 11 skipped); `git diff --check` clean.

## Report
Append to `.agents/log/API-3A.md`: files changed, commands + result lines, open questions. Commits `api-3a:`.
