# API-4 — facade on `SWATProject` + `CalibrationResult`

## Report (worker-strong)

### Files changed
- `spyswat/swat_calib/calibration/result.py` (new) — `CalibrationResult` (fields
  `best_params/best_score/best_run_id/metric/runs/metrics/sensitivity/
  sensitivity_status/session_dir/seed/algorithm/methods/subbasins`), dict-style
  `res["best_params"|"best_score"|"history"]` (`history` == `runs`), `top(n)`
  (drops failed/NaN, best first by the registry direction), `select(**conditions)`
  (`<metric>__<op>` with `gt/gte/lt/lte`, `site=`, `period=`, `how=`), `best_param_set()`,
  `series()`/`site_metrics()` (lazy via the store), and `CalibrationResult.load(session_dir)`
  (metadata eager, series lazy). Also the `RawParamsStore` adapter (converts the manager's
  *formatted* `{name: [(value, method, ...)]}` to raw floats so `runs.csv` stores repr-exact
  values) and the `best_run` / `raw_params_for_run` / `evaluate_best_metrics` /
  `regression_for_store` helpers used by the facade.
- `spyswat/swat_project.py` — `SWATProject.calibration(...)` (algorithm ∈ glue/pso/de/dds;
  resolves seed first, creates the session folder `<results_dir>/<YYYYMMDD_HHMMSS>_<alg>_<metric>`,
  a `SessionStore` with the decision-9 signature, runs the algorithm with `store`, then best-run
  metrics via `evaluate`, regression sensitivity on `is_initial` rows → `sensitivity.csv`,
  `best.csv`, store closed in `finally`; `resume=False` → `FileExistsError`, `resume=True` →
  `NotImplementedError`; never modifies TxtInOut), `evaluate` (fills print step + warm-up end),
  `sensitivity` (`from_session` → regression without SWAT; else oat/morris/morris_salib/sobol/
  regression), `scenarios` (converts `ParamSet`/`CalibrationResult`/lists to `ParamSet`s),
  `apply` (ParamSet / CalibrationResult / dict; non-`"v"` dict without `methods=` raises; logs a
  warning). Module helpers `_to_param_sets`, `_non_v_methods`.
- `spyswat/swat_calib/calibration/__init__.py` — exports `CalibrationResult`.
- `spyswat/__init__.py` — exports `CalibrationResult`.
- `tests/test_calibration_result.py` (new) — 14 tests (dict access, top max/min, select
  score/site/period/how, invalid operator, best_param_set, load round-trip, adapter).
- `tests/test_project_facade.py` (new) — 13 tests (glue/pso/dds end-to-end with a fake runner,
  session layout, best-run metrics with calib+valid rows, sensitivity/status, TxtInOut restore,
  load round-trip, existing-session resume semantics, evaluate, sensitivity from_session /
  regression, scenarios accepts result/top, apply).

### Commands + result lines
- `python -m pytest tests/test_calibration_result.py -q -p no:cacheprovider` → `14 passed`.
- `python -m pytest tests/test_project_facade.py -q -p no:cacheprovider` → `13 passed`.
- `python -m pytest tests/ -q -p no:cacheprovider` → `655 passed, 11 skipped, 28 subtests passed`
  (main baseline: 628 passed, 11 skipped; +27 new tests).
- `git diff --check` → clean (only Git's LF→CRLF autocrlf notice on `calibration/__init__.py`,
  no whitespace errors).

### Decisions / deviations (documented for the reviewer)
1. **`RawParamsStore` bridges formatted → raw.** `CalibrationManager._run_batch_multi` /
   `_run_iteration_multi` pass the *formatted* `{name: [(value, method, subbasins)]}` dict to
   `store.add_run`, but `runs.csv` must store repr-exact floats (decision 9) and `SessionStore.runs()`
   reads them back as floats. `calib_manager.py` and `session_store.py` are outside this task's
   scope, so the facade wraps the `SessionStore` in `RawParamsStore`, which strips the
   method/subbasin metadata to `{name: value}` before delegating `add_run` (and `__getattr__` for
   everything else). `runs`, `best.csv` and `load` therefore round-trip the raw floats exactly.
2. **`runs` = `SessionStore.runs()`** (run_id, time, status, error, is_initial, params, score),
   not the algorithms' `runs` DataFrame (which carries per-site `<metric>@<var>@<reach>` columns
   but no run_id/status). This keeps the in-memory result and `load` byte-identical, and per-site
   metrics stay reachable through `store.site_metrics()` (used by `select`), with the runs
   columns as a fallback for the calib period.
3. **`select` semantics.** `score__op` uses the aggregate `score` column; any other
   `<metric>__op` reads `store.site_metrics()` column `<metric>_<period>` (default `"calib"`).
   Without `site=`, the condition applies to every calibrated (observed) site and `how="all"|"any"`
   combines them; multiple conditions are AND-ed. Failed/NaN runs never match (NaN comparisons
   are False).
4. **Sensitivity errors become a status** (decision 11). `_regression_sensitivity` catches the
   `ValueError`s from `regression_sensitivity` (API-3a raises): "Not enough usable runs" →
   `sensitivity_status == "insufficient runs"`, anything else → the message; any other exception
   is also folded into the status so sensitivity can never break a calibration. `n_used`/`r2`
   warnings (decision 11) are emitted as `UserWarning`s.
5. **`n_parallel`** is recorded in the signature and, for batch algorithms (glue/pso/de), applied
   by setting `WorkingFolderManager.n_parallel` and re-running `setup_parallel`; DDS (sequential)
   needs no workers. Defaults to the project's.
6. **`scenarios`/`apply` do the result→ParamSet conversion** in the facade (`_to_param_sets`), so
   `spyswat/swat_calib/scenarios/{model,batch}.py` needed no change (the task listed them only
   "to accept results as param sets"); the conversion avoids a `scenarios ↔ calibration` import
   cycle.
7. **`method="regression"`** in `project.sensitivity` reuses `calibration(algorithm="glue",
   sensitivity=True, ...)` and returns `res.sensitivity` — the "run a GLUE/LHS sample first" helper.

### Open questions
- None blocking. `CalibrationResult.load` leaves `metrics` as `None` (series are lazy); the
  facade recomputes best-run metrics eagerly on the returned result. If the reviewer wants
  `load` to also rebuild `metrics`, that needs the observed series, which are not stored in the
  session (only their hash) — deferred to API-5 (resume by replay) where `session.json` matching
  is implemented.

## Rework round 1 (worker-strong, review `API-4-1.md`)

### Changes per finding
- **Major (`spyswat/swat_project.py` — `param_methods` / `param_subbasins`):** Verified
  `param_methods=param_methods, param_subbasins=param_subbasins` is forwarded to `algo.run(...)`.
  Added `test_calibration_param_methods_and_subbasins` in `tests/test_project_facade.py`
  confirming worker updates passed to `run_parallel` carry method `"r"` and subbasins `[1]`,
  and `res.best_params` / `res.methods` / `res.subbasins` / `session.json` record them.
- **Minor 1 (`spyswat/swat_calib/calibration/result.py` — `_site_metric_values` fallback):**
  Verified `if period == "calib":` guard and NaN-only fill (`np.isnan(values) & ~np.isnan(vals)`)
  are in place so `valid`-period metrics are never overwritten.
- **Minor 2 (`spyswat/swat_project.py` & `spyswat/swat_calib/calibration/result.py` —
  constant/collinear sensitivity):** Extended `constant_parameters()` in `result.py` to filter
  collinear columns (when `n > len(kept_cols) + 1`) in addition to constant columns, updated
  `reinsert_constant()` to preserve `sens.attrs` (`n_used`, `r2`) and handle empty frames, and
  added `test_calibration_constant_and_collinear_parameter_sensitivity` in
  `tests/test_project_facade.py`.
- **Minor 3 (`spyswat/swat_project.py` — `signature` serialization & `on_failure`):**
  Verified `_serialize_period()` ISO-stringifies `calib_period`/`valid_period` (extended to
  also handle `datetime.date`) and `"on_failure": algorithm_options.get("on_failure", "raise")`.
  Added `test_calibration_timestamp_periods_and_on_failure_signature` in
  `tests/test_project_facade.py`.
- **Minor 4 (`spyswat/swat_project.py` — `apply()` formatted dict + `methods`/`subbasins`):**
  Verified `apply()` reformats formatted dicts via `format_params(raw_params(x), methods, subbasins)`
  when `methods` or `subbasins` is passed. Added
  `test_apply_formatted_dict_with_methods_and_subbasins` in `tests/test_project_facade.py`.
- **Minor 5 (`tests/test_project_facade.py` — coverage gaps):** Added `de` to
  `test_calibration_other_algorithms` and added `test_calibration_param_methods_and_subbasins`
  and `test_calibration_monthly_step_and_bare_series_observed` (covering `step="M"` and bare
  `pd.Series` `observed`).

### Checks
- Tests were **not** run by me (no shell commands allowed in this rework step).
- CEO: Go 5h quota ran out mid-rework (worker-strong stopped with uncommitted edits); agy gemini-4-hydrogen-high finished the edits (no shell). CEO ran `pytest tests/test_project_facade.py tests/test_calibration_result.py` → 33 passed.
