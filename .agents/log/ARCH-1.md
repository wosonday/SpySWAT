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

## 2026-11-20 · OpenCode / GPT-6.1 Sol · step 2 preparation
- Assignment received from the Architect: implement only step 2a/2b/2c on
  `feat/ARCH-1`, one scoped commit per move, no push or merge.
- Starting HEAD `ecf4041`; `git status --short --branch` is clean.
- Read the approved task/design and the two specified skills
  (`test-driven-development`, `verification-before-completion`).
- Structural RED check for 2a:
  `python -c "from importlib.util import find_spec; assert find_spec('spyswat.swat_calib.core.run_state') is not None, 'Step 2a: shared run_state module is missing'"`
  fails with the expected assertion before any implementation.
- Started the step-2a targeted suite on the unchanged source as a baseline.
- Compatibility detail discovered for 2c: existing tests outside the permitted
  edit range directly set `_session_base`, `_session_id`, `_session_dir`,
  `_session_claimed` and `_session_n`. These must continue forwarding to RunLog;
  changing those tests is not authorized. Request Architect confirmation of
  thin compatibility properties while continuing the independent 2a/2b moves.

## 2026-11-20 · Architect clarification for step 2c
- Architect approved exactly five read/write compatibility forwarders:
  `_session_base`, `_session_id`, `_session_dir`, `_session_claimed`, `_session_n`.
- Read the appended "Step 2 clarification" in `.agents/decisions/ARCH-1.md`.
- No catch-all `__getattr__`/`__setattr__`, and no extra run-log state forwarders.
- Existing session-race tests remain unchanged; only the explicitly authorized
  moved logging monkeypatch targets will be edited.

## 2026-11-20 · OpenCode / GPT-6.1 Sol · step 2a — shared run state
- Baseline on unchanged source:
  `python -m pytest tests/test_working_folder.py tests/test_run_once.py tests/test_calib_manager.py -q`
  → **80 passed / 1 skipped / 0 failed**, 107.77 s.
- Moved the copy/freshness helpers and `StaleOutputError` to `core/run_state.py`.
  `workingFolder_manager.py` retains `_OLD_MTIME` and all original private names
  as import/assignment aliases. `calib_manager.py` keeps its module-level targets
  unchanged, including `cm._copy_over`. GLUE imports the public exception location.
- AST comparison against starting HEAD: moved bodies are identical after only
  the specified function renames and internal `rch_signature` reference rename.
- Pickle round trips of all moved functions/the exception succeed; old aliases
  resolve to the exact new objects. No test edits.
- Same targeted suite after the move:
  **80 passed / 1 skipped / 0 failed**, 104.94 s.
- `git diff --check` → 0 (only automatic CRLF conversion notices).
- Files changed by 2a:
  - `spyswat/swat_calib/core/run_state.py` (new)
  - `spyswat/swat_calib/core/workingFolder_manager.py`
  - `spyswat/swat_calib/analysis/algorithms/glue.py`
  - `.agents/log/ARCH-1.md`
- Architect separately committed its clarification in `32b3af8`; it was not
  staged or modified by this worker.
- Structural RED check for the next step also confirms `param_spec` is absent.

## 2026-11-20 · OpenCode / GPT-6.1 Sol · writer guard and step 2b
- Unexpected commit `69596b5` appeared while preparing the 2a commit. Stopped
  source edits and notified the Architect rather than overwriting/resetting it.
- Architect independently reviewed that commit, accepted it as step 2a, confirmed
  this session is the only writer, and explicitly authorized removal of the
  uncommitted duplicate 2a log entry. The committed entry remains unchanged.
- Check `git log -1` immediately before each remaining commit; stop again if HEAD
  changes unexpectedly. Expected HEAD before the 2b commit: `69596b5`.
- Step 2b RED probe asserted `param_spec` exists and failed before implementation.
- Extracted `parse_spec`, `format_params`, `is_raw`, `param_columns` into
  `calibration/param_spec.py`. The manager retains the three static aliases and
  the instance `_format_params` wrapper. Other callers and tests are unchanged.
- AST check: executable bodies identical to the originals; normalized docstrings
  also identical (a first unnormalized check detected only method-to-function
  docstring indentation). Aliases, wrapper results and pickle round trips pass.
- `python -m pytest tests/test_calib_manager.py tests/test_metrics.py tests/test_calibration.py -q`
  → **145 passed / 0 failed**, 5 existing warnings, 91.59 s.
- Files changed by 2b:
  - `spyswat/swat_calib/calibration/param_spec.py` (new)
  - `spyswat/swat_calib/calibration/calib_manager.py`
  - `.agents/log/ARCH-1.md`
