# Log API-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-24 · deepseek-v4.1-flash (worker-mid) · step 1/1

- RED first: `python -m pytest tests/test_evaluate.py -q` → collection error
  `ImportError: cannot import name 'EvaluationResult' from 'spyswat.swat_calib.analysis'`
  (25 tests written before any implementation).
- Done: new pure module `spyswat/swat_calib/analysis/evaluate.py` with
  `EvaluationResult(table)`/`to_csv(path)` and
  `evaluate(sim, observed, periods=None, *, metrics=("nse","kge","pbias","r2"), freq=None,
  step=None, agg=None, warmup_end=None)`; exported from
  `spyswat/swat_calib/analysis/__init__.py`.
  - Series pair → one site keyed `(None, None)`; dicts keyed `(variable, reach)`; every
    observed key must exist in `sim` (ValueError names the missing `(variable, reach)`,
    unobserved sim keys are ignored); mixing Series and dict raises.
  - `freq` accepts `"daily"`/`"monthly"` (the literal spec strings) and also `"D"`/`"MS"`;
    `None` infers with `check_observation_step`'s own monthly rule (month-start midnight,
    unique months). Step checking always reuses `check_observation_step` (imported from
    `calibration/calib_manager.py`, not copied); `step="M"` checks observations with `"MS"`.
  - `step="M"` aggregates the **simulation** with `Series.resample("MS")` (mean, sum for
    `SED_*` / `*tons` / `*kg`); `agg` overrides per variable; no-op for a monthly sim;
    observations are never resampled. `agg` without `step="M"` and unknown agg methods raise.
  - Periods: inclusive, `None` → `{"all": (sim start, last common date)}`; a period starting
    before `sim.index.min()`, ending after `sim.index.max()`, starting before `warmup_end`,
    or reversed raises a ValueError naming the period and the reason. With `warmup_end` the
    default period starts at the warm-up end so warm-up dates are never scored.
  - Metrics: names validated against `METRIC_DIRECTIONS`/`known_metrics()` before any
    computation; values computed with `SWATAnalysis`'s metric functions (no direction is
    hard-coded, no rounding, no printing). NaN pairs dropped; `n` = pairs; empty period →
    NaN metrics with `n = 0`.
- Files changed: `spyswat/swat_calib/analysis/evaluate.py` (new),
  `spyswat/swat_calib/analysis/__init__.py`, `tests/test_evaluate.py` (new),
  `.agents/log/API-1.md`.
- Checks:
  - `python -m pytest tests/test_evaluate.py -q` → **26 passed** in 3.44 s;
  - `python -m pytest tests/ -q` → **490 passed / 11 skipped / 0 failed**, 5 warnings,
    231 s (baseline 464 passed + 26 new);
  - `git diff --check` → exit 0.
- Open questions for the reviewer (choices documented in the module docstring):
  - `freq` literal strings in the task are `"daily"`/`"monthly"`, while
    `check_observation_step` takes `"D"`/`"MS"`; both spellings are accepted.
  - `periods=None` with `warmup_end` is clamped to start at `warmup_end` (otherwise the
    default "all" period would itself violate the warm-up guard). Explicit periods before
    `warmup_end` still raise.
  - Multi-site default period: start = earliest simulated date; end = the latest of each
    site's last common date. A site with a shorter observation record simply gets fewer
    pairs (`n`), never an exception.
  - `agg` without `step="M"` raises instead of being silently ignored.

## 2026-11-25 · deepseek-v4.1-flash (worker-mid) · rework round 1

Fix all five findings of `.agents/reviews/API-1-1.md`, test-first (8 new regression
tests added before any code change).

- RED: `python -m pytest tests/test_evaluate.py -q` → **8 failed, 26 passed**; every
  failure matched its finding (mid-month `step="M"` start dropped the first month;
  unobserved daily sim site forced `print_step="D"` and raised on monthly observations;
  no-overlap and warm-up-past-record defaults raised `after the simulation end` /
  `reversed`; duplicate `metrics` → DataFrame length mismatch; all-NaN January summed to
  `0.0` (n=2 instead of 1); non-mapping `agg` → `AttributeError`; empty sim → no raise).
- Major 1 (bounds/freq from unobserved, pre-aggregation sim): `_normalise_sites` now
  drops unobserved sim keys before validating/inferring, so `_infer_freq` and the
  `sim_min`/`sim_max` bounds only see scored sites; `evaluate()` aggregates `step="M"`
  before computing the bounds.
- Major 2 (`periods=None` crash): default period = `max(sim_min, warmup_end)` to
  `sim_max`; `_resolve_periods` now receives `sim_sites`, finds the scored dates in that
  window (`_common_dates`, union across sites) and returns `(start, start)` when empty so
  the result is NaN metrics with `n=0` instead of `ValueError`. Default periods are not
  re-validated; explicit periods keep every guard and message.
- Minor 3: `_check_metrics` collapses duplicates in order (`dict.fromkeys`).
- Minor 4: `_aggregate_to_months` uses `sum(min_count=1)` (mean stays `.mean()`), so an
  empty/all-NaN month stays NaN.
- Minor 5: `_check_step` rejects a non-`Mapping` `agg` with a `ValueError`; `_check_time_series`
  rejects an empty series.
- Files changed: `spyswat/swat_calib/analysis/evaluate.py`, `tests/test_evaluate.py`,
  `.agents/log/API-1.md`.
- Checks:
  - `python -m pytest tests/test_evaluate.py -q` → **34 passed** in 2.74 s;
  - `python -m pytest tests/ -q` → **498 passed / 11 skipped / 0 failed**, 5 warnings,
    229.12 s (baseline 490 after the first round + 8 regressions);
  - `git diff --check` → exit 0 (only Git LF→CRLF warnings).
- Open questions: none; the log entries above still describe the accepted choices.

## 2026-11-25 · deepseek-v4.1-flash (worker-mid) · rework round 2

Fix the three findings of `.agents/reviews/API-1-2.md`, test-first (6 new regression
tests added before any code change).

- RED: `python -m pytest tests/test_evaluate.py -q` → **6 failed, 34 passed**: the
  full-year `step="M"` period ending `2000-12-31` and the mid-last-month period ending
  `2000-02-04` both failed with `after the simulation end`; `None`/`NaT` period bounds and
  `warmup_end=pd.NaT` returned `n=0` instead of raising; reach `10` sorted before reach `2`.
- Major 1 (last simulated day lost by aggregation): `evaluate()` records
  `raw_max = max(s.index.max() ...)` before `_aggregate_to_months` and uses
  `sim_max = max(raw_max, post-aggregation max)`; `sim_min` stays the post-aggregation
  (month-start) bound so a mid-month start still includes its first month.
- Minor 2 (`NaT` bounds): new `_period_bounds()` raises
  `ValueError: Period '<name>' needs two real dates` when `pd.isna(start)` or
  `pd.isna(end)`; `warmup_end` converts and raises
  `ValueError: warmup_end must be a real date` when `pd.isna(...)`.
- Minor 3 (reach order): `_sorted_keys` sorts by `(str(variable), reach is None, reach)`,
  so reach 2 precedes reach 10 and a missing reach sorts last.
- Files changed: `spyswat/swat_calib/analysis/evaluate.py`, `tests/test_evaluate.py`,
  `.agents/log/API-1.md`.
- Checks:
  - `python -m pytest tests/test_evaluate.py -q` → **40 passed** in 2.38 s;
  - `python -m pytest tests/ -q` → **504 passed / 11 skipped / 0 failed**, 5 warnings,
    28 subtests passed, 235.03 s (baseline 498 + 6 new regressions);
  - `git diff --check` → exit 0 (only Git LF→CRLF warnings).
- Open questions: none.
