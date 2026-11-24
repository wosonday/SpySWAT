# API-2C review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Critical
None.

## Major
None.

## Minor
- `spyswat/swat_calib/calibration/calib_manager.py:400` — `_new_path` docstring groups `metrics` under `(run_batch)`, though `run_iteration` now passes `metrics=metrics` as well. Concrete fix: update the parenthetical in `_new_path`'s docstring to note `metrics` applies to both `run_iteration` and `run_batch`.

## Verification Notes
- **Spec & design compliance**: `_resolve_metrics(metric, metrics)` runs immediately after `_validate_config` in `_run_iteration_multi` (`spyswat/swat_calib/calibration/calib_manager.py:443`), failing with `ValueError` before parameter formatting or any SWAT run. `run_iteration` passes `metrics=metrics` to `_new_path` (`spyswat/swat_calib/calibration/calib_manager.py:330`), and `_new_path` checks `metrics is not None` (`spyswat/swat_calib/calibration/calib_manager.py:414`).
- **Numeric hand-check**: In `tests/test_calib_multisite.py:356-362`, `obs = 0..9` has mean `4.5` and `SST = 2 * (20.25 + 12.25 + 6.25 + 2.25 + 0.25) = 82.5`; constant `sim = 3.0` gives `SSE = 9+4+1+0+1+4+9+16+25+36 = 105`; `NSE = 1 - 105 / 82.5 = -0.2727...`, matching `pytest.approx(1 - 105 / 82.5)` and confirming `metrics=("nse",)` alone enters the multi-site `evaluate` path.
- **Test quality & constraints**: `test_preflight_runs_before_any_swat_run`, `test_run_iteration_unknown_metric_fails_before_run`, and `test_run_iteration_unknown_reported_metric_fails_before_run` record `proj.run_impl` calls and assert `ran == []`. Scope is limited to the three task-spec files; English messages, no `TxtInOut` mutation, no picklability issues, and no secrets.
- **Recorded checks** (from `.agents/log/API-2C.md`): `tests/test_calib_multisite.py` (`27 passed`), full `tests/` (`595 passed, 11 skipped`), `git diff --check` clean.

## CEO: PASS; Auditor full suite on e70a547 = 595 passed, 11 skipped. Docstring Minor left (cosmetic).
