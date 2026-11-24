# API-2B review round 2 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

Round-1 Major findings (`_new_path` routing for keyword-only vocabulary args, and `_extract_outputs` picklability + invocation in `_install_fake_run_parallel`) and all five Minor findings (`_validate_config`, `ValueError` re-raise in `_run_batch_multi`, `run_once` early `_normalise_outputs`, empty-`observed` guard, missing test cases, and `_resolve_deprecated_reach` helper) are resolved. Hand-checked numeric cases in `tests/test_scoring.py` (`NSE = 0.8` and `0.875` -> `0.8375`, `0.25/0.75` weighted `0.85625`, signed `pbias = -10.0` / `+8.3333` -> `|pbias|` score `9.1667`, valid `NSE = 0.2`, leap-year monthly slices `31/29/31`) are exact; `METRIC_DIRECTIONS` and `evaluate()` are used, `TxtInOut` is restored in `run_iteration`, error messages are English, scope is clean, and no secrets appear.

### Critical
None.

### Major
None.

### Minor
1. **`metric`/`metrics` not validated before SWAT runs in `run_iteration` (`spyswat/swat_calib/calibration/calib_manager.py:440`)**
   `_run_batch_multi` calls `_resolve_metrics(metric, metrics)` up front (`calib_manager.py:542`), whereas `_run_iteration_multi` skips it. An unknown `metric` or `metrics` entry runs SWAT first and is then caught and wrapped as `RuntimeError("Iteration failed: ...")` (and recorded as `status="failed"` in `store`) instead of failing fast with `ValueError`; similarly, passing `metrics=...` alone to `run_iteration` without another new kwarg does not trigger `_new_path` (`calib_manager.py:327`).
   **Fix:** Call `_resolve_metrics(metric, metrics)` right after `_validate_config` in `_run_iteration_multi` and include `metrics is not None` in `run_iteration`'s `_new_path` check.

2. **`_whole_overlap` relies on exact index intersection (`spyswat/swat_calib/calibration/scoring.py:249`)**
   When `calib_period=None` and `valid_period` is set, `_whole_overlap` computes `obs.index.intersection(sim[key].index)`. If `step="M"` is used with daily `sim` and month-end or mid-month `obs` timestamps (or monthly `MS` `sim` with non-`MS` `obs`), the intersection is empty and returns `(start, start)`.
   **Fix:** Derive the overlap from `[max(start, obs_min), min(sim_max, obs_max)]` across observed sites when timestamps do not share exact alignment.

3. **`test_preflight_runs_before_any_swat_run` does not assert SWAT was skipped (`tests/test_calib_multisite.py:336`)**
   The test sets `proj.run_impl = _run_writes_rch` and checks `ValueError`, without verifying `run_impl` was never invoked (unlike `test_run_once_non_mapping_outputs_fails_before_run`).
   **Fix:** Record calls in `proj.run_impl` (or assert `(proj.txinout.directory / "output.rch")` was not written) to prove no SWAT run occurred.

## CEO triage
PASS. Auditor: full suite on ebe7d37 = 574 passed, 11 skipped. Minor 1 and 3 go to follow-up task API-2C (parallel with API-3b, disjoint files). Minor 2 not needed: month-end monthly observations are already rejected by check_observation_step (AGENTS.md rule 6).
