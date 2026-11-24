# API-3C review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Findings

### Critical
None.

### Major
None.

### Minor
- `tests/test_algorithms_vocabulary.py:419-421`: `morris_salib` and `sobol_method` cases in `test_sensitivity_passes_new_vocabulary_through` call `pytest.importorskip("SALib")` and were skipped (`4 skipped`) in the reported run because `SALib` is not installed. Run `python -m pytest tests/test_algorithms_vocabulary.py -q` in an environment with `SALib` installed to exercise those two branches end-to-end.
- `tests/test_algorithms_vocabulary.py:449-460`: `test_sensitivity_deprecation_warning_points_at_caller` verifies `stacklevel=4` for `observed_series` on `one_at_a_time` only. Optionally parametrise over `reach_id`+`output_variable` to cover both deprecated forms.

## Verification Summary
- **Task spec & design alignment**:
  1. `spyswat/swat_calib/analysis/sensitivity.py:8,98`: `_batch_scores` imports and calls `_reported(metric, metrics)` from `analysis.algorithms.dds`, preventing bare strings like `metrics="kge"` from splitting into characters (`["rmse", "kge"]`) and keeping `metric` included when `metrics=None` (`["rmse"]`).
  2. `tests/test_algorithms_vocabulary.py:318-335`: `test_optimize_passes_new_vocabulary_through` now captures `run_iteration` calls and asserts `observed` identity, `weights == WEIGHTS`, and `metric == "rmse"`.
  3. `tests/test_algorithms_vocabulary.py:414-447`: Added mocked `run_batch` tests for all four `SWATSensitivity` methods (`one_at_a_time`, `morris_method`, `morris_salib`, `sobol_method`) covering dict `observed`, `weights`, `metric`, `metrics=None` / `metrics="kge"`, and old+new `TypeError` checks.
  4. `spyswat/swat_calib/analysis/sensitivity.py:23`: `_resolve_sens_observed` passes `stacklevel=4` to `_resolve_observed`, verified by `test_sensitivity_deprecation_warning_points_at_caller`.
  5. `spyswat/swat_calib/analysis/algorithms/glue.py:116-118`: `GLUE.run` builds `rng = np.random.default_rng(seed)` and passes it to `self._analysis._generate_samples(..., seed=rng)`, verified by `tests/test_algorithms_vocabulary.py:465-474`.
- **Numeric hand-check**: In `sens_batch` (`tests/test_algorithms_vocabulary.py:399-410`), for `CN2.mgt = 60.0` and `ALPHA_BF.gw = 0.5`, `score = 60.0 + 2.0 * 0.5 = 61.0` and each per-site column `f"{m}@{var}@{reach}"` is `62.0`; `_reported("rmse", "kge")` yields `["rmse", "kge"]`.
- **Rules, scope & tests**: Only the four in-scope files (`sensitivity.py`, `glue.py`, `tests/test_algorithms_vocabulary.py`, `.agents/log/API-3C.md`) are modified; no `TxtInOut` mutation, no unpicklable worker callables, English messages, and no secrets. `.agents/log/API-3C.md` records `43 passed, 4 skipped` on `tests/test_algorithms_vocabulary.py` and `638 passed, 15 skipped, 6 warnings, 28 subtests passed` on the full suite (including with `-W error::DeprecationWarning:spyswat`), plus clean `git diff --check`.

## CEO: PASS; Auditor full suite on c0b0ae4 = 638 passed, 15 skipped (4 new SALib-only skips). Minors are optional; not done.
