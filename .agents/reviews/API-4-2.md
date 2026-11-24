# API-4 review round 2 — agy gemini-4-neon-high (plan, sandbox, diff inlined)

Verdict: FAIL

## Critical
None.

## Major
- **`spyswat/swat_project.py:316-333` — `session.json` signature omits `observed_hash`, `options`, and `numpy_version`:** Task spec assigns Decision 8 (SHA-256 over sorted `(variable, reach)` + ISO index + float64 bytes), Storage layout (`options`, `observed hashes`, `library version`), and Decision 9's signature (`numpy_version`), yet `signature` omits `observed_hash`, `algorithm_options` (except `on_failure`), and `numpy_version`.
  **Fix:** Compute `observed_hash` per Decision 8 from `observed_dict`, include `"options": algorithm_options`, `"observed_hash": ...`, and `"numpy_version": np.__version__` (and library `__version__` if not already written by `SessionStore`) in `signature`, and assert them in `tests/test_project_facade.py`.
- **`spyswat/swat_calib/calibration/result.py:179-193` — `constant_parameters()` drops all parameters when `len(data) == 1` (breaks DDS `sensitivity_status`):** For a 1-row `data` frame (every DDS calibration has only 1 `is_initial=True` row), `np.all(col == col[0])` is vacuously `True` for every parameter, so `usable` becomes `[]` and `_regression_sensitivity` calls `regression_for_store(store, {})` instead of triggering `"Not enough usable runs"` → `"insufficient runs"` (Decision 11). `tests/test_project_facade.py:155` only asserts truthiness of `sensitivity_status`, masking this.
  **Fix:** Change `if data.empty:` to `if len(data) < 2:` in `constant_parameters()`, and assert `res.sensitivity_status == "insufficient runs"` for DDS in `tests/test_project_facade.py`.
- **`spyswat/swat_project.py:491-493` — `sensitivity(..., method="regression", calib_period=...)` raises `TypeError`:** `self.calibration(param_ranges, observed, None, ..., **options)` passes `calib_period` positionally, so passing `calib_period=` in `**options` fails with `multiple values for argument 'calib_period'`.
  **Fix:** Extract `calib_period = options.pop("calib_period", None)` before calling `self.calibration(param_ranges, observed, calib_period, ...)` and add a test passing `calib_period=`.

## Minor
- **`spyswat/swat_project.py:510-512` — `scenarios()` fails on a bare `CalibrationResult` or `ParamSet`:** Iterating `for ps in param_sets:` triggers `CalibrationResult.__getitem__(0)` (`KeyError: 0`) when a single result is passed directly (Design: accepts a `CalibrationResult`).
  **Fix:** If `isinstance(param_sets, (ParamSet, CalibrationResult))`, call `_to_param_sets(param_sets)` directly; otherwise iterate as today.
- **`spyswat/swat_project.py:537-547` — `apply()` silently overwrites non-`"v"` methods when `subbasins=` is passed without `methods=`:** `elif methods is not None or subbasins is not None:` runs before `_non_v_methods(x)`, so `apply({"CN2.mgt": [(0.1, "r")]}, subbasins={"CN2.mgt": [1]})` silently resets `"r"` to `"v"`.
  **Fix:** Check `if methods is None and _non_v_methods(x): raise ValueError(...)` before reformatting with `subbasins`.
- **`spyswat/swat_calib/calibration/result.py:381-396,433` & `spyswat/swat_project.py:343` — Minor consistency cleanups:** `CalibrationResult.load()` sets `sensitivity_status=""` even when `sensitivity.csv` is loaded (in-memory sets `"ok"`); `select()` returns `[]` silently on an unknown metric column rather than failing explicitly; `result = algo.run(...)` is unused.
  **Fix:** Set `sensitivity_status="ok" if sensitivity is not None else ""` in `load()`, validate requested metric columns in `_site_metric_values()`, and drop the unused `result =` binding.

## Notes
- **Round-1 fixes verified:** `param_methods`/`param_subbasins` forwarding, `period == "calib"` NaN-only fallback guard, Timestamp/date period ISO serialization, `on_failure` signature capture, and `de` / `step="M"` / bare-Series coverage are all in place.
- **Hand-checks:** `tests/test_project_facade.py:235-259` scales `K1 in [0,1]` and `K2 = 2*K1 + 1 in [1,3]` to identical `[0.1..0.8]` vectors (`resid = 0 <= 1e-10`), dropping `K2` and reinserting `t=0, p=NaN, rank=2`; `tests/test_project_facade.py:187-198` uses 91 daily dates for leap-year Jan–Mar 2000 (`31+29+31`), giving `n=3` months under `"MS"`; `tests/test_project_facade.py:370-379` gives `35.0 * 1.1 = 38.5` on subbasin 1 and `35.0` on subbasin 2.
- **Rules/scope/secrets:** English messages, picklable module-level helpers, metric registry used, TxtInOut untouched during calibration, no secrets, scope clean.

## CEO triage → rework round 2 (agy Hydrogen edits, CEO runs tests)
Fix all three Majors and all Minors exactly as proposed, with the tests named. Auditor: full suite on the round-1 rework = 676 passed, 15 skipped.
