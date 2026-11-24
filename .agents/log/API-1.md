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
