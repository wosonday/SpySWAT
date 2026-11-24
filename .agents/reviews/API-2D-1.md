# API-2D review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Critical
None.

## Major
None.

## Minor
- `spyswat/swat_calib/calibration/calib_manager.py:64`: In `_raw_param_values`, if `spec` contains an empty inner sequence (e.g. `[()]`), `first` is `()` so `isinstance(first, (list, tuple))` is `True` and `first[0]` raises `IndexError`.
  - Concrete fix: Guard the inner index with `out[name] = (first[0] if first else None) if isinstance(first, (list, tuple)) else first`.
- `tests/test_calib_multisite.py:241-243`: Modified outside `Files in scope`, though justified because `test_run_batch_multisite_fake_store_receives_runs_in_order` asserted the old buggy formatted tuples (`[{"CN2.mgt": [(50.0, "v")]}, ...]`) and had to be updated to raw floats (`{"CN2.mgt": 50.0}`) for the suite to pass.
  - Concrete fix: No code change needed if scope exception is accepted; otherwise note it in the PR/merge description.

## Verification Summary
- **Spec & Design alignment**: `_raw_param_values` converts `{name: [(value, method[, subs])]}` to `{name: value}` (first element of first tuple) and passes raw `{name: float}` dicts through unchanged. Wiring it into `_add_run_to_store` (`spyswat/swat_calib/calibration/calib_manager.py:446`) covers the `store.add_run` choke point for both `run_batch` and `run_iteration`.
- **Numeric hand-check**: For `{"CN2.mgt": [(70.75, "r", [1, 2])]}`, `spec` is a `list`, `first = (70.75, "r", [1, 2])` is a `tuple`, and `first[0]` yields `70.75`; for `{"CN2.mgt": 48.5}`, the `else` branch preserves `48.5` for `SessionStore` float serialization.
- **Tests & Rules**: `tests/test_store_raw_params.py:1-119` exercises real `SessionStore` round-trips (`open().runs()`) across `run_batch` and `run_iteration` with raw inputs, formatted inputs (`"r"`, subbasins), and `methods`/`subbasins` kwargs, without `swat.exe` or `TxtInOut` mutation. English messages/docstrings, picklable module-level helper, and no secrets confirmed. Reported run in `.agents/log/API-2D.md`: 643 passed, 15 skipped, `git diff --check` clean.

## CEO: PASS; Auditor full suite on 1e50e5f = 643 passed, 15 skipped. Scope exception accepted (the edited test asserted the bug). Empty-tuple guard Minor: not reachable from format_params; skipped.
