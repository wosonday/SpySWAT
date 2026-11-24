# API-2B — vocabulary + multi-site core in `CalibrationManager`

## Report (worker-strong)

### Files changed
- `spyswat/swat_calib/calibration/scoring.py` (new) — pure multi-site scoring helpers:
  `normalise_observed`, `check_weights`, `preflight`, `score_sites` (+ private helpers).
- `spyswat/swat_calib/calibration/calib_manager.py` — `warmup_end()`, `run_once(outputs=…)`,
  `run_iteration(…, outputs/weights/metrics/calib_period/valid_period/step/agg/store/run_id/is_initial)`,
  `run_batch(…, metric/outputs/weights/…/store/run_ids/is_initial)`, module-level picklable
  `_extract_outputs`, `_apply_and_run`, `_run_once_single`, `_store_next_id`,
  `_add_run_to_store`, `_build_multisite_row`, `_new_path`.
- `tests/test_scoring.py` (new) — 25 tests for the pure functions (hand-computed NSE/pbias).
- `tests/test_calib_multisite.py` (new) — 16 tests: run_once dict+dates, warmup_end,
  run_batch columns/submission order/fake store/run_ids, run_iteration restore + store,
  DeprecationWarning only for explicit old kwargs, preflight-before-SWAT.

### Commands + result lines
- `python -m pytest tests/test_scoring.py tests/test_calib_multisite.py -q -p no:cacheprovider`
  → `41 passed` (after fixing the fake `run_parallel` binding and a monotonicity assertion).
- `python -m pytest tests/ -q -p no:cacheprovider`
  → `556 passed, 11 skipped` (baseline on main: 515 passed, 11 skipped; +41 new tests).
- `git diff --check` → clean (no output).

### Decisions / deviations (documented for the reviewer)
1. **Signature vs task spec.** The task's sketched signature places `reach_id`/`output_variable`
   after `*` (keyword-only). That would break the existing *production* callers that pass them
   positionally (`analysis/algorithms/{glue,pso,parallel_de}.py` →
   `run_batch(param_sets, obs, [metric], reach_id, output_variable)`; `analysis/calibration.py`,
   `analysis/algorithms/dds.py` → `run_iteration(raw, obs, metric, reach_id, output_variable, …)`),
   which are **not in scope**. I kept `reach_id`, `output_variable`, `methods`, `subbasins`
   positional-or-keyword in their original slots (sentinel defaults) and made the *new* params
   keyword-only. Old behaviour + `DeprecationWarning`-on-explicit is preserved.
2. **`store.add_run` params** are the formatted param dicts (what the manager actually applies),
   not the raw floats. Duck-typed; documented here as the choice.
3. **`run_batch` column order** is `score`, then site-major (`sorted (variable, reach)`), then
   reported metric order: `score, <metric>@<var>@<reach>, …`.
4. **`warmup_end()`** reads `FileCIO.year_start` (= `IYR + NYSKIP`); returns `None` when the
   project's FileCIO stub has no `year_start` (so existing test stubs keep working).

### Open questions
- None blocking. `store.add_run` error handling swallows-and-warns (mirrors `RunLog` rule 10);
  confirm that is the wanted behaviour for the SessionStore when API-2a lands.
