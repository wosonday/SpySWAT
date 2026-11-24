# API-3C — four follow-ups from review API-3B-1

## Report (worker-mid)

### Files changed
- `spyswat/swat_calib/analysis/sensitivity.py`
  - `_batch_scores` now passes `_reported(metric, metrics)` (imported from
    `analysis.algorithms.dds`) instead of `[metric] if metrics is None else list(metrics)`:
    a bare string `metrics="kge"` is one name (never `['k', 'g', 'e']`) and `metric` is
    always reported first.
  - `_resolve_sens_observed` passes `stacklevel=4` to `_resolve_observed`, so the
    `observed_series` / `reach_id`+`output_variable` `DeprecationWarning` points at the
    caller of `SWATSensitivity.one_at_a_time` / `morris_method` / `morris_salib` /
    `sobol_method`, not inside `sensitivity.py`.
- `spyswat/swat_calib/analysis/algorithms/glue.py`
  - `GLUE.run` builds `rng = np.random.default_rng(seed)` and passes that `Generator` to
    `_generate_samples(...)`, which forwards it to `scipy.stats.qmc.LatinHypercube(seed=rng)`.
- `tests/test_algorithms_vocabulary.py`
  - `test_optimize_passes_new_vocabulary_through` now asserts the forwarded call really
    carries the `observed` dict, `weights` and `metric` (was: unused `seen`, only
    `call_count >= 1`).
  - New `SWATSensitivity` tests (all mocked `run_batch`, no SWAT):
    `test_sensitivity_passes_new_vocabulary_through` (parametrised over `one_at_a_time`,
    `morris_method`, `morris_salib` (skipped without SALib), `sobol_method` ×
    `metrics=None` → `["rmse"]` and `metrics="kge"` → `["rmse", "kge"]`; asserts the dict
    `observed`, `weights`, `metric` and the reported metric list reach `run_batch`),
    `test_sensitivity_old_and_new_names_raise_typeerror` (both `observed`+`observed_series`
    and `outputs`+`reach_id`/`output_variable`, all four methods; raised before SALib is
    imported so it runs without SALib), `test_sensitivity_deprecation_warning_points_at_caller`
    (warning file is this test file), and `test_glue_passes_a_generator_to_lhs`
    (`_generate_samples` receives an `np.random.Generator`, result `seed` stays 42).

### Commands + result lines
- `python -m pytest tests/test_algorithms_vocabulary.py -q -p no:cacheprovider`
  → `43 passed, 4 skipped` (before the fixes: `4 failed, 39 passed, 4 skipped`; the four
  failures were exactly the four findings — the `metrics="kge"` split, the stacklevel, the
  GLUE generator; SALib vocabulary cases skip because SALib is not installed here).
- `python -m pytest tests/ -q -p no:cacheprovider`
  → `638 passed, 15 skipped, 6 warnings, 28 subtests passed` (main baseline 628 passed,
  11 skipped; +10 passing tests, +4 SALib skips from the new parametrised cases).
- `python -m pytest tests/ -q -p no:cacheprovider -W error::DeprecationWarning:spyswat`
  → `638 passed, 15 skipped, 6 warnings, 28 subtests passed`.
- `git diff --check` → clean (no output).

### Decisions / deviations
1. **GLUE sample values change for the same seed.** `scipy.stats.qmc` maps an `int` seed to a
   legacy `RandomState` and a `Generator` seed to that `Generator`, so switching to
   `default_rng(seed)` (as the review asked) changes the concrete LHS draws for a given seed.
   Determinism (same seed → same proposed sets, and `seed=None` → resolved int → exact replay)
   is unchanged and covered by the existing tests. No other code depended on the old values.
2. **No change to `statistics._generate_samples`** (out of scope): it already forwards `seed`
   to `LatinHypercube`, so passing the `Generator` from `glue.py` is enough.
3. **SALib tests are skip-only here** (SALib not installed); the old+new `TypeError` cases for
   `morris_salib`/`sobol_method` still execute because `_resolve_sens_observed` runs before the
   SALib import.
