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

---

## Rework round 1 (worker-strong) — review API-2B-1 (FAIL)

### Findings fixed (exactly as proposed)
- **Major 1 (silent fallback).** `_new_path` now also takes `valid_period`/`step`/`agg`
  (both entry points), `metric`/`run_ids`/`is_initial` (run_batch) and `run_id`/`is_initial`
  (run_iteration); `run_iteration` deliberately does NOT key on `metric` (legacy positional).
- **Major 2 (extract unexercised).** `_install_fake_run_parallel` now round-trips `extract`
  through `pickle.loads(pickle.dumps(...))` and invokes `extract(str(wdir))`, with
  `cm.OutputFileManager` patched to a fake reading plain-number `output.rch`; added direct
  `_extract_outputs` unit test + a picklability test for `partial(_extract_outputs, ...)`.
- **Minor 1 (config misclassified).** New `scoring._validate_config(valid_period, step, agg)`
  runs in `_run_iteration_multi`/`_run_batch_multi` before any SWAT run; `_run_batch_multi`
  re-raises `ValueError` instead of wrapping it as `"output unreadable"`.
- **Minor 2 (mutate before validate).** `run_once` normalises `outputs` via
  `_normalise_outputs` before `_apply_and_run`.
- **Minor 3 (empty observed).** `normalise_observed({})` and `preflight({}, ...)` now raise
  `ValueError("observed must contain at least one site.")`.
- **Minor 4 (missing tests).** Added tests for failed worker (`status="failed"`, NaN score/row),
  `run_iteration` failure with store, ungauged site (outputs superset of observed), `step="M"`
  aggregation, and `calib_period=None` + `valid_period`.
- **Minor 5 (duplicated deprecation logic).** Extracted module-level
  `_resolve_deprecated_reach(reach_id, output_variable)` (stacklevel=3); used by `run_once`,
  `run_iteration`, `run_batch`.

### Files changed (this round)
- `spyswat/swat_calib/calibration/scoring.py` — empty-observed guard, `_validate_config`.
- `spyswat/swat_calib/calibration/calib_manager.py` — `_resolve_deprecated_reach`, `_new_path`
  extension, `_normalise_outputs` in `run_once`, `_validate_config` calls, `ValueError` re-raise.
- `tests/test_scoring.py` — +8 tests (empty dict, `_validate_config`, `step="M"`,
  `calib_period=None`+`valid_period`).
- `tests/test_calib_multisite.py` — +10 tests (extract, failed worker, iteration failure,
  ungauged site, Major-1 routing, pre-run valid_period failure).

### Commands + result lines
- `python -m pytest tests/test_scoring.py tests/test_calib_multisite.py -q -p no:cacheprovider`
  → `59 passed` (41 original + 18 new).
- `python -m pytest tests/ -q -p no:cacheprovider`
  → `574 passed, 11 skipped, 47 warnings` (baseline f84f789: 556 passed, 11 skipped, 47 warnings;
  +18 new tests, warning count unchanged — no new code path emits DeprecationWarning).
- `git diff --check` → clean (only pre-existing LF→CRLF informational warnings on the three
  LF-authored files from the previous round; no trailing whitespace / conflict markers).
