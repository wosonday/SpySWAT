# API-4 review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: FAIL

## Critical
None.

## Major
- **`spyswat/swat_project.py:269-271,324-329` — `param_methods` and `param_subbasins` are not passed to `algo.run()`:** `calibration()` merges `param_methods` and `param_subbasins` into `methods`/`subbasins` for `session.json` and `best_params = format_params(best_raw, methods, subbasins)` (`spyswat/swat_project.py:351`), but `algo.run(param_ranges, ...)` receives the raw `param_ranges` without `param_methods` or `param_subbasins`. SWAT therefore executes using `param_ranges`'s default `"v"` method on all subbasins while `CalibrationResult` and `session.json` report the caller's `param_methods`/`param_subbasins`.
  **Fix:** Forward `param_methods=param_methods, param_subbasins=param_subbasins` to `algo.run(...)` (or normalize `param_ranges` into formatted ranges carrying `methods`/`subbasins` before calling `algo.run`), and add a facade test covering non-`"v"` `param_methods`/`param_subbasins`.

## Minor
- **`spyswat/swat_calib/calibration/result.py:311-314` — `_site_metric_values` fallback can overwrite `valid` metrics:** The `f"{name}@{site[0]}@{site[1]}"` fallback carries calibration-period values, but runs unconditionally without checking `period == "calib"`, so it would overwrite `valid` values if those columns exist on `runs`.
  **Fix:** Guard with `if period == "calib" and fallback in runs.columns:` and fill only indices where `np.isnan(values)`.
- **`spyswat/swat_project.py:386-389` — Constant/collinear parameters in `_regression_sensitivity`:** Decision 11 specifies `t=0, p=NaN` for collinear/constant parameters inside `calibration()`, whereas `_regression_sensitivity` turns any `ValueError` from `regression_sensitivity` into `(None, str(exc))` (matching the task spec's fallback wording).
  **Fix:** If strict Decision 11 parity is desired, filter constant/collinear columns before calling `regression_sensitivity` and reinsert them with `coef=0.0, t_stat=0.0, p_value=np.nan`.
- **`spyswat/swat_project.py:305-306,313` — `signature` serialization and `on_failure`:** `calib_period`/`valid_period` may be `pd.Timestamp` per the vocabulary (risking `json.dumps` `TypeError` unless `SessionStore` stringifies), and `"on_failure": "raise"` ignores `algorithm_options.get("on_failure")`.
  **Fix:** Convert `Timestamp` bounds with `.isoformat()` when building `signature`, and set `"on_failure": algorithm_options.get("on_failure", "raise")`.
- **`spyswat/swat_project.py:504-512` — `apply()` ignores `methods`/`subbasins` for formatted dicts:** When `x` is a non-raw dict and `methods=` is supplied, `updates = x` silently drops `methods`/`subbasins`.
  **Fix:** Reformat via `format_params(raw_params(x), methods, subbasins)` when `methods` or `subbasins` is passed.
- **`tests/test_project_facade.py:140-147` — Coverage gaps:** No test exercises `param_methods`/`param_subbasins` in `calibration()`, `de`, `step="M"`, or bare-Series `observed`.
  **Fix:** Add a test with `param_methods={"CN2.mgt": "r"}` and `param_subbasins` verifying worker updates match.

## Notes
- **Numeric check:** In `tests/test_project_facade.py:190-195`, `obs=[1,2,3,4]` (`mean=2.5`, `SS_tot=5.0`) and `sim=[1,2,3,5]` (`SS_res=1.0`) give `NSE = 1 - 1/5 = 0.8`; in `test_calibration_glue_end_to_end`, constant `sim=c` against `FLOW_OUTcms=[0..9]` (`mean=4.5, SS_tot=82.5`) and `SED_OUTtons=[1,3..19]` (`mean=10, SS_tot=330`) yields `NSE_flow = -10*(c-4.5)^2/82.5` and `NSE_sed = -10*(c-10)^2/330`, monotonically favouring the smallest sampled `CN2.mgt` in `[35, 98]`.
- **Checks/Rules:** Module-level picklable helpers, English messages, no secrets, TxtInOut restored/untouched in calibration, and scope (`scenarios/{model,batch}.py` avoided via `_to_param_sets`) all look clean.

## CEO triage → rework round (worker-strong)
Fix the Major and all five Minors exactly as proposed, test-first. Note: main gained API-3c and the API-2d hotfix (raw params in the store); the CEO merges main into this branch after your rework, do not merge yourself. Auditor: full suite on 141a0eb = 655 passed, 11 skipped.
