# API-4 review round 3 — agy gemini-4-neon-high (plan, sandbox, diff inlined)

Verdict: PASS

## Critical
None.

## Major
None.

## Minor
- `spyswat/swat_calib/calibration/result.py:331-338` — `select()` does not explicitly filter `status == "ok"` as `top()` does (`result.py:348-349`); it relies on failed runs having `NaN` score/metrics.
  **Fix:** Initialize `keep` with `runs["status"].to_numpy() == "ok"` when `"status" in runs.columns` so `select()` cannot match a failed row even on custom `runs` frames.
- `spyswat/swat_project.py:585-586` — `_hash_observed()` hashes native-endian `np.float64` bytes without normalizing `-0.0`.
  **Fix:** Use `dtype="<f8"` and normalize `-0.0` to `0.0` before calling `.tobytes()` for cross-platform hash stability.

## Verification Notes
- **Round-2 fixes verified:**
  - `spyswat/swat_project.py:317-337,571-587`: `session.json` signature now records `observed_hash` (SHA-256 over sorted `(variable, reach)` + ISO index + float64 bytes), `options`, `on_failure`, and `numpy_version`, covered by `test_calibration_glue_end_to_end`, `test_calibration_timestamp_periods_and_on_failure_signature`, and `test_calibration_observed_hash_order_and_data_sensitivity`.
  - `spyswat/swat_calib/calibration/result.py:179`: `len(data) < 2` guard prevents 1-row DDS `is_initial` data from dropping all parameters as constant, surfacing `sensitivity_status == "insufficient runs"` (asserted in `test_calibration_other_algorithms`).
  - `spyswat/swat_project.py:495-498`: `sensitivity(method="regression", calib_period=...)` pops `calib_period` cleanly (covered by `test_sensitivity_regression_accepts_calib_period`).
  - `spyswat/swat_project.py:517-522,548-560` & `spyswat/swat_calib/calibration/result.py:375-407,443`: bare `ParamSet`/`CalibrationResult` in `scenarios()`, non-`"v"` guard before `subbasins=` reformatting in `apply()`, `sensitivity_status` parity in `load()`, and explicit `ValueError` on unknown `select()` metrics are all implemented and tested.
- **Numeric hand-check:**
  - `tests/test_project_facade.py:343-348`: `obs=[1,2,3,4]` (`mean=2.5`, `SS_tot=5.0`), `sim=[1,2,3,5]` (`SS_res=1.0`) → `NSE = 1 - 1/5 = 0.8`.
  - `tests/test_project_facade.py:266-290`: `K1=[0.1..0.8]` in `[0,1]` and `K2=2*K1+1` in `[1,3]` scale to identical vectors (`resid=0 <= 1e-10`), so `K2` is dropped as collinear and reinserted with `coef=0, t_stat=0, p_value=NaN, rank=2`, `n_used=8`.
  - `tests/test_project_facade.py:449-458`: subbasin 1 `CN2=35.0` with `"r"` `0.1` → `35.0 * 1.1 = 38.5`, subbasin 2 unchanged at `35.0`.
- **Rules / scope / secrets:** English messages, picklable module-level callables, metric registry (`best_index`/`to_objective`), explicit failures, TxtInOut verified byte-identical after all calibration algorithms and only mutated with warning in `apply()`, scope within spec, synthetic fixtures only, no secrets.

## CEO: PASS (Neon). Auditor full suite = 681 passed, 15 skipped. Both Minors (select status filter; hash -0.0/little-endian) move to API-5B, which owns the signature for resume.
