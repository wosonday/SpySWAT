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

## 2026-11-20 · OpenCode / GPT-6.1 Sol · step 2c — extraction and verification in progress
- Step 2b committed as `b2f7b5c` after checking `git log -1` against `69596b5`.
- Structural RED probe for 2c asserted the `run_log` module exists and failed
  before its implementation.
- Moved result/session state and logging methods to `RunLog(project)`;
  `MAX_PENDING_ROWS` remains 10,000. Manager methods/properties delegate to it.
- Kept exactly the five approved session properties as explicit read/write
  forwarders; no catch-all attributes and no extra state forwarders.
- RunLog calls the pure parameter helpers directly. Its logger retains the old
  `spyswat.swat_calib.calibration.calib_manager` category to preserve log output.
- Test edits only redirect the moved logging monkeypatch targets and pending
  buffer access, plus the necessary `run_log` import. No assertions were weakened.
- `python -m pytest tests/test_calib_manager.py -k "locked_log or pending_buffer or session_file or column_change or outputs_options or reading_properties or results_dir_none" -q`
  → **7 passed / 47 deselected / 0 failed**, 11.00 s.
- AST verification: every moved logging method matches its original after the
  required pure-helper calls and constant rename. All 12 execution/alignment
  methods remain exactly unchanged. No RunLog lambdas or nested functions.
- Pickle round trips succeed for the extracted class/static functions and the
  manager class. Step 2a already verified public helper/exception pickling;
  Windows spawned-worker tests are included in the full suite.
- Differential synthetic log scenario against the pre-split manager at `ecf4041`
  with frozen timestamps: **4 CSV files byte-identical**, covering raw/formatted
  specs, column switches, failed/invalid records, observed/none output policies,
  best-parameter CSV append, flush and disabled logging.
- `calib_manager.py` reduced from **780 to 554 lines**; no CSV/session or
  parameter-spec implementation remains there, only the approved delegates.
- Full-suite command `python -m pytest tests/ -q` is running. Do not claim the
  336-pass gate or commit 2c before its completed result.

## 2026-11-20 · OpenCode / GPT-6.1 Sol · step 2c gate
- `python -m pytest tests/ -q` completed:
  **336 passed / 11 skipped / 0 failed**, 5 existing warnings, 258.97 s.
- The count is unchanged from step 1, including Windows spawned-worker coverage.
- `git diff --check` → 0. Test diff contains only the authorized moved-target
  replacements plus the necessary import; session-race tests remain unchanged.
- Files changed by 2c:
  - `spyswat/swat_calib/calibration/run_log.py` (new)
  - `spyswat/swat_calib/calibration/calib_manager.py`
  - `tests/test_calib_manager.py`
  - `.agents/log/ARCH-1.md`

## 2026-11-20 · OpenCode / GPT-6.1 Sol · step 2d — documentation
- Architect explicitly added the documentation assignment in task commit
  `81b4f87`; that announced HEAD change was accepted before committing 2c.
- Step 2c committed as `8e42746` after checking `git log -1` against `81b4f87`.
- Updated the module trees, run primitive/sandbox composition, RunLog delegation
  and measured **336 passed / 11 skipped** count in `AGENTS.md`.
- Added the public API/exception, module extraction, unchanged CSV format and
  sensitivity/GLUE post-restore logging notes to `[Unreleased]` in `CHANGELOG.md`.
- Updated the calibration-manager/API sections, module tree, backup/restore and
  logging rationale in `ARCHITECTURE.md`, preserving Vietnamese prose.
- Documentation accurately distinguishes `run_once` (no backup, metrics or log)
  from `sandbox`, and `run_iteration`'s explicit backup/restore for combined errors.
- Checks:
  - Documentation-only diff; all referenced new modules/API names exist.
  - New sandbox/run_once example parses; Markdown code fences are balanced.
  - `python -m pytest tests/test_run_once.py -q` → **9 passed**, 3.93 s.
  - Requested `pickle.dumps(r.copy_over)` command → 0.
  - `git diff --check` → 0.
- No source changes after the successful full-suite run for 2c.
- Files changed by 2d:
  - `AGENTS.md`
  - `ARCHITECTURE.md`
  - `CHANGELOG.md`
  - `.agents/log/ARCH-1.md` (this documentation entry)
- The unrelated untracked `.agents/tasks/MERGE-2.md` belongs to coordination
  outside this assignment. It is neither edited nor staged by this worker;
  report it to the Architect instead of claiming a clean integration handoff.
- No push or merge. Expected HEAD before the documentation commit: `8e42746`.
- Architect announced and committed the separate step-2d task amendment as
  `81b4f87`; this is the expected HEAD for the 2c commit guard, not an unexplained
  writer change. Its untracked `MERGE-2.md` task is outside worker scope.
- Docs step 2d is now assigned explicitly to OpenCode: update only `AGENTS.md`,
  `ARCHITECTURE.md`, `CHANGELOG.md` and this append-only docs log, in a separate
  `ARCH-1: docs: ...` commit after 2c. No source changes in that commit.
