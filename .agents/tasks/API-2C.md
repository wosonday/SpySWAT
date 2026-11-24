---
id: api-2c
branch: feat/api-2c
tier: fast
skills: test-driven-development
docs_impact: no
gitnexus: none
---

# API-2c: two follow-ups from review API-2B-2 (fail fast on metrics; prove preflight skips SWAT)

Read `.agents/reviews/API-2B-2.md` findings 1 and 3 (merged on main). Do exactly:
1. In `CalibrationManager._run_iteration_multi`, call `_resolve_metrics(metric, metrics)` right after
   `_validate_config`, so an unknown metric raises `ValueError` before any SWAT run; and include
   `metrics is not None` in `run_iteration`'s `_new_path` check.
2. In `tests/test_calib_multisite.py::test_preflight_runs_before_any_swat_run`, record calls of
   `proj.run_impl` and assert it was never called.
3. New test: `run_iteration(..., metric="no_such_metric", outputs=...)` raises ValueError and `run_impl` is never
   called; `run_iteration(..., metrics=("nse",))` alone takes the new path.

## Files in scope
`spyswat/swat_calib/calibration/calib_manager.py`, `tests/test_calib_multisite.py`, `.agents/log/API-2C.md`.

## Acceptance criteria
- [ ] `python -m pytest tests/test_calib_multisite.py -q` then `python -m pytest tests/ -q -p no:cacheprovider` pass
      (record counts); `git diff --check` clean.

## Report
Append to `.agents/log/API-2C.md`: files changed, commands + result lines. Commits `api-2c:`.
