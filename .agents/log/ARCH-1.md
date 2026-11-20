# Log ARCH-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-20 · claude-opus-5.5 · step 1/2 — run_once + sandbox
- Branch `feat/ARCH-1` from `main` at `bdcd3f4` (the MERGE-1 merge commit; Copilot
  reported 327 passed / 11 skipped on main).
- RED: `tests/test_run_once.py` failed at import (`StaleOutputError` did not exist).
  After the primitive was added, the 3 guard cases still failed until the callers
  were migrated.
- Done:
  - `StaleOutputError(RuntimeError)` in `core/workingFolder_manager.py`; old
    `except RuntimeError` code still catches it.
  - `CalibrationManager.run_once` (no backup) and `sandbox(names=None)` (backup/restore
    context manager). `sandbox()` calls `_backup_state()` with no arguments when `names` is
    None, so mocks with zero-argument backups keep working.
  - `run_iteration` uses `run_once`. It keeps its own backup/restore so that the combined
    "Iteration failed ...; additionally ... could not be restored" error stays.
  - `_sequential_mean`, `GLUE.uncertainty_band` and `ValidationRunner.run` use
    `sandbox()` + `run_once()`. GLUE catches `StaleOutputError` (run left out of the band)
    instead of re-checking freshness itself. ValidationRunner uses
    `sandbox() if restore else nullcontext()`.
  - Removed the private stamp/fresh imports from those three modules and the unused
    `Path` import from glue.
- Decision refinement: the approved design named `run_once(..., keep=False)`. I split it
  into `run_once` (state-free) + `sandbox()` (state) instead. Callers compose them, and
  "keep the change" is simply not using `sandbox` (ValidationRunner's default).
- Behaviour notes:
  - sensitivity and GLUE now record a run after the restore, not before. A failed
    restore is therefore recorded as a failed run. It used to be recorded "ok" and then
    raised.
- Files changed:
  - `calibration/calib_manager.py`, `calibration/validation_runner.py`
  - `core/workingFolder_manager.py`
  - `analysis/sensitivity.py`, `analysis/algorithms/glue.py`
  - `tests/test_run_once.py` (new)
  - `.agents/tasks/ARCH-1.md`, `.agents/log/ARCH-1.md`
- Checks:
  - `pytest tests/ -q` → **336 passed / 11 skipped / 0 failed** (327 + 9 new), 303 s;
  - `git diff --check` → 0.
