# API-2B review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: FAIL

Hand-check & hygiene: numeric cases in `test_scoring.py` check out (`NSE = 1 - 1/5 = 0.8` and `1 - 25/200 = 0.875`, mean `0.8375`; signed `pbias = -10.0` and `+8.3333`, `|pbias|` score `9.1667`; valid `NSE = 1 - 4/5 = 0.2`), English messages, `METRIC_DIRECTIONS` registry used, TxtInOut restored in `run_iteration`, scope clean, no secrets.

### Major

1. **Silent fallback ignores new vocabulary arguments (`spyswat/swat_calib/calibration/calib_manager.py:385`)**
   `_new_path(observed, outputs, weights, calib_period, store)` returns `False` when a caller passes a bare `pd.Series` with default `outputs` and `calib_period=None` alongside `valid_period`, `step="M"`, `agg`, or `run_batch(..., metric="kge")`. Those keyword-only arguments are silently dropped by the old daily single-site path (no `score` column, wrong metric/step).
   **Fix:** Include `valid_period is not None or step is not None or agg is not None` in `_new_path`, plus `metric is not None or run_ids is not None or is_initial` for `run_batch` and `run_id is not None or is_initial` for `run_iteration`.

2. **Worker extraction `_extract_outputs` is unexercised (`tests/test_calib_multisite.py:148`, `spyswat/swat_calib/calibration/calib_manager.py:33`)**
   `_install_fake_run_parallel` ignores its `extract` parameter and builds `payload` inline, so neither `_extract_outputs` nor picklability of `partial(_extract_outputs, outputs=...)` (required for Windows `spawn`) is exercised by any test.
   **Fix:** Round-trip `extract` through `pickle.loads(pickle.dumps(extract))` and invoke `extract(str(wdir))` in `fake_run_parallel` (against a synthetic `output.rch` or patched `OutputFileManager`), plus add a direct unit test for `_extract_outputs`.

### Minor

1. **Configuration errors misclassified after SWAT runs (`spyswat/swat_calib/calibration/calib_manager.py:786`)**
   `valid_period` bounds and `step`/`agg` compatibility with `observed` are only checked inside `score_sites` -> `evaluate()`, where `except Exception` catches them as `"output unreadable: ..."` and returns `NaN` rows after running all batches.
   **Fix:** Validate `valid_period` and `step` before the batch loop (in `preflight` or `_run_batch_multi`), and avoid swallowing `ValueError` from misconfiguration as `"output unreadable"`.

2. **`run_once` mutates `TxtInOut` before validating `outputs` (`spyswat/swat_calib/calibration/calib_manager.py:256`)**
   `run_once(params, outputs={"FLOW_OUTcms": 1})` (scalar reach) or a non-mapping `outputs` runs `_apply_and_run(formatted)` first and crashes afterwards on `outputs.items()` / `for reach in reaches`.
   **Fix:** Normalise `outputs` via `_normalise_outputs(outputs)` before calling `_apply_and_run(formatted)`.

3. **Empty `observed` dict accepted (`spyswat/swat_calib/calibration/scoring.py:79`)**
   `normalise_observed({})` and `preflight({}, ...)` both succeed, running SWAT before producing `NaN` scores.
   **Fix:** Raise `ValueError("observed must contain at least one site.")` when `observed_dict` is empty.

4. **Missing test cases (`tests/test_calib_multisite.py:148`, `tests/test_scoring.py:228`)**
   No tests exercise failed workers (`res.ok=False` -> `status="failed"`, `score=NaN` in store), `run_iteration` failure with `store`, `outputs` as a superset of `observed` (ungauged site stored without metrics), `step="M"`/`agg`, or `calib_period=None` with `valid_period` set.
   **Fix:** Add tests covering those paths in `test_calib_multisite.py` and `test_scoring.py`.

5. **Duplicated deprecation-warning logic (`spyswat/swat_calib/calibration/calib_manager.py:267`)**
   The `_SENTINEL` check and `warnings.warn` block is duplicated verbatim in `run_once`, `run_iteration`, and `run_batch`.
   **Fix:** Extract a shared `_resolve_deprecated_reach(reach_id, output_variable)` helper.

## CEO triage → rework round (worker-strong)
Fix both Major and all five Minor findings exactly as proposed, test-first. Also: Auditor full suite on f84f789 = 556 passed, 11 skipped, 47 warnings (the extra warnings are DeprecationWarnings from the old path; leave existing callers alone, API-3b migrates them, but make sure no NEW code path in this task emits them).
