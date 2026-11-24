# API-1 review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: FAIL

### Major

1. **`spyswat/swat_calib/analysis/evaluate.py:120-133` — `sim_min`/`sim_max` and `_infer_freq` run before `step="M"` aggregation and include unobserved `sim` keys.**
   - If a daily `sim` starts mid-month (e.g. `2000-01-15`), `_aggregate_to_months` shifts its index to `2000-01-01`, while `sim_min` stays `2000-01-15`—so `periods=None` silently drops the first month and explicit periods starting `2000-01-01` raise `ValueError`.
   - Including unobserved `sim` keys violates "Sim keys without observations are ignored" when an unobserved site has a different frequency or date range.
   - **Fix:** Restrict `sim_sites` to `obs_sites.keys()` right after `_normalise_sites`, infer `print_step` on those sites, run `_aggregate_to_months` before computing `sim_min`/`sim_max`, and then call `_resolve_periods`.

2. **`spyswat/swat_calib/analysis/evaluate.py:318-326` — `periods=None` crashes on non-overlapping `sim`/`obs` or `warmup_end` past `obs`.**
   - `max(series.index.min(), min(series.index.max(), sim_max))` exceeds `sim_max` when `obs` starts after `sim_max`, triggering `ValueError` in `_validate_period`. When `obs` ends before `sim_min` or `warmup_end`, `start > end` raises `Period 'all' is reversed` instead of returning `n=0` and `NaN` metrics.
   - **Fix:** For `periods is None`, compute `start = sim_min if warmup is None else max(sim_min, warmup)`, find common dates across sites in `[start, sim_max]`, and if empty use `(start, start)` (no exception, `n=0`, `NaN` metrics); otherwise use `(first_common, last_common)`.

### Minor

3. **`spyswat/swat_calib/analysis/evaluate.py:137-161` — Duplicate metric names in `metrics` crash `pd.DataFrame` construction.**
   - `values` is keyed by `name`, so `metrics=("nse", "nse")` appends twice per row to `values["nse"]`.
   - **Fix:** Deduplicate `names` preserving order (`tuple(dict.fromkeys(names))`) or reject duplicates in `_check_metrics`.

4. **`spyswat/swat_calib/analysis/evaluate.py:308-310` — `resample("MS").agg("sum")` turns empty/all-NaN months into `0.0`.**
   - **Fix:** Use `series.resample("MS").sum(min_count=1)` when `how == "sum"` (and `.mean()` for `"mean"`).

5. **`spyswat/swat_calib/analysis/evaluate.py:198-206` & `248-256` — Minor input validation gaps.**
   - Non-mapping `agg` raises `AttributeError` on `.items()`, and an empty `sim` series leaves `sim_min`/`sim_max` as `pd.NaT`.
   - **Fix:** Check `isinstance(agg, Mapping)` in `_check_step` and reject empty `sim` series in `_check_time_series`.

### Verified
- Hand-checked `tests/test_evaluate.py` math: `pair` NSE = `1 - 1/5 = 0.8`, `SED_OUTtons` NSE = `1 - 25/200 = 0.875`, `valid` NSE = `1 - 4/5 = 0.2`, `step="M"` sum PBIAS = `100 * (-15 - 75) / 30 = -300.0`.
- Scope (`evaluate.py`, `analysis/__init__.py`, `test_evaluate.py`, `.agents/log/API-1.md`), `check_observation_step` reuse, `METRIC_DIRECTIONS` usage, English messages, and absence of secrets/TxtInOut mutation look clean.

## CEO triage → rework round (worker-mid)
Fix all five findings (1-2 Major, 3-5 Minor) exactly as proposed above, test-first: add a regression test for each
(mid-month daily start with step="M"; unobserved sim site with another frequency ignored; periods=None with
no overlap → n=0/NaN; duplicate metric names; all-NaN month with sum stays NaN; non-mapping agg; empty sim).
