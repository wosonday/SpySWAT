# API-1 review round 2 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: FAIL

### Major

1. `spyswat/swat_calib/analysis/evaluate.py:122-131` — `step="M"` shifts `sim_max` back to the 1st of the last month, rejecting periods that end on the simulation's last day.
   - Aggregating a daily simulation covering `2000-01-01`..`2005-12-31` to `"MS"` moves `sim.index.max()` from `2005-12-31` to `2005-12-01`. Calling `evaluate(..., periods={"valid": ("2004-01-01", "2005-12-31")}, step="M")` (standard for `API-4` `valid_period`) then fails `_validate_period` (`end > sim_max`). Even `test_step_m_aggregates_before_deriving_the_simulation_bounds` (`tests/test_evaluate.py:259-274`) only passed `"2000-01-31"` because February existed (`sim_max = 2000-02-01`); `"2000-02-04"` would raise.
   - **Fix:** Record `raw_max = max(s.index.max() for s in sim_sites.values())` before `_aggregate_to_months`, and set `sim_max = max(raw_max, max(s.index.max() for s in sim_sites.values()))` (keeping post-aggregation `sim_min` so mid-month starts still include their first month). Add a test with `step="M"` where a period ends on the final day of the simulation's last month (e.g. `"2000-02-04"` or `"2000-12-31"`).

### Minor

2. `spyswat/swat_calib/analysis/evaluate.py:132,356` — `None` or `pd.NaT` in `periods` bounds or `warmup_end` silently produces `pd.NaT`, making all `<`/`>` comparisons in `_validate_period` (`378-397`) evaluate `False` and returning `n=0` instead of raising `ValueError`.
   - **Fix:** Raise `ValueError` if `pd.isna(start)` or `pd.isna(end)` (and if `warmup_end is not None and pd.isna(warmup)`).

3. `spyswat/swat_calib/analysis/evaluate.py:235-236` — `_sorted_keys` sorts by `(str(k[0]), str(k[1]))`, which orders reach `10` before reach `2`.
   - **Fix:** Sort by `(str(k[0]), k[1] is None, k[1])`.

### Verified (from diff inspection; no commands run)
- **Hand-checked numerics:** `test_step_m_sum_aggregation_is_explicit` (`tests/test_evaluate.py:211-217`) sums `[2,4,6,8]`→`20` and `[10,20,30,40]`→`100` vs `obs=[5,25]`; `PBIAS = 100 * ((5-20) + (25-100)) / (5+25) = -300.0`, matching `pytest.approx(-300.0)`. `test_step_m_sum_keeps_an_all_nan_month_nan` keeps all-NaN Jan as `NaN` via `min_count=1`, scoring Feb `12` vs `12` (`n=1`, `pbias=0.0`).
- **Round-1 fixes & spec:** Unobserved `sim` sites are dropped before freq/bounds; `periods=None` with no overlap or `warmup_end` past `sim_max` returns `n=0`/NaN; duplicate `metrics` collapse cleanly; non-mapping `agg` and empty `sim` raise `ValueError`; `check_observation_step`, `METRIC_DIRECTIONS`, `known_metrics()`, and `SWATAnalysis` are reused.
- **Scope & AGENTS.md:** Changes are limited to `evaluate.py`, `analysis/__init__.py`, `tests/test_evaluate.py`, `.agents/log/API-1.md` (plus `.agents/reviews/API-1-1.md`); English error messages, picklable top-level callables, no `TxtInOut` mutation, no secrets. `.agents/log/API-1.md` reports `34 passed` (`test_evaluate.py`), `498 passed / 11 skipped` (`tests/`), and clean `git diff --check`.

## CEO triage → rework round 2 (worker-mid)
Fix findings 1 (Major) and 2-3 (Minor) exactly as proposed, test-first: period ending on the last simulated day with step="M"
(e.g. "2000-02-04" and a full-year case ending "2000-12-31"); NaT/None bounds and NaT warmup_end raise; reach 2 sorts before reach 10.
Auditor note: full suite on 86cd09a = 498 passed, 11 skipped (CEO re-run).
