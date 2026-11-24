---
id: api-2d
branch: feat/api-2d
tier: fast
skills: test-driven-development
docs_impact: no
gitnexus: none
---

# API-2d (hotfix): store raw parameter values in the session store

Found by the Neon pre-review of API-5: `CalibrationManager` calls `store.add_run(params=formatted)`
(`calib_manager.py` around lines 485 and 827), i.e. `{name: [(value, method[, subbasins])]}`. `SessionStore` then
writes `str([...])` into `runs.csv`, and `SessionStore.open()` / `runs()` crash when parsing floats.

## Do
1. Add a small helper in `calib_manager.py` that turns a formatted parameter dict back into raw
   `{name: float}` (the first element of the first tuple; raw dicts pass through unchanged). Use it for every
   `store.add_run(params=...)` call.
2. Test (new file `tests/test_store_raw_params.py`, real `SessionStore` in `tmp_path`, fake runner as in
   `tests/test_calib_multisite.py`): `run_batch(..., store=store)` with raw and with pre-formatted parameter sets
   (method `"r"`, and one with subbasins) → after `store.close()`, `SessionStore.open(dir).runs()` returns the raw
   float values exactly; same for `run_iteration(..., store=store)`.

## Files in scope
`spyswat/swat_calib/calibration/calib_manager.py`, `tests/test_store_raw_params.py` (new), `.agents/log/API-2D.md`.

## Acceptance criteria
- [ ] New tests fail before the fix and pass after; `python -m pytest tests/ -q -p no:cacheprovider` passes
      (main baseline 638 passed, 15 skipped); `git diff --check` clean.

## Report
Append to `.agents/log/API-2D.md`. Commits `api-2d:`.
