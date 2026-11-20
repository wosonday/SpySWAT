---
id: arch-1
branch: feat/ARCH-1
tier: strong
skills: test-driven-development, verification-before-completion
docs_impact: yes
gitnexus: none
---

# ARCH-1: one public sequential-run primitive; split CalibrationManager

Design: `.agents/decisions/ARCH-1.md` (approved by the user 2026-11-20).

## Step 1: `run_once` + `sandbox`
- `CalibrationManager.run_once(params, *, reach_id, output_variable, methods, subbasins)`
  updates, stamps, runs, checks freshness and reads the series. It does not back up anything.
- `CalibrationManager.sandbox(names=None)` is a context manager: backup on enter, restore
  on any exit.
- `StaleOutputError(RuntimeError)` is raised by the freshness check.
- `run_iteration`, `SWATSensitivity._sequential_mean`, `GLUE.uncertainty_band` and
  `ValidationRunner.run` use them.

## Step 2: module split (no behaviour change)
- `calibration/param_spec.py`, `calibration/run_log.py`, `core/run_state.py`.
- Keep thin private aliases on `CalibrationManager`.

## Files in scope
- `spyswat/swat_calib/calibration/**`, `spyswat/swat_calib/core/workingFolder_manager.py`,
  `spyswat/swat_calib/core/run_state.py`, `analysis/sensitivity.py`,
  `analysis/algorithms/glue.py`
- `tests/**`, `AGENTS.md` (design rules 4, 10), `ARCHITECTURE.md`, `CHANGELOG.md`
- `.agents/log/ARCH-1.md`

## Acceptance criteria
- [x] Step 1: tests for run_once/sandbox, plus a guard that the three callers do not
      re-implement the sequence; full suite green.
- [ ] Step 2: same `<session>_metrics.csv` columns; full suite green; pickling unchanged.
