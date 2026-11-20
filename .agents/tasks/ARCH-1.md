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

## Step 2: module split (no behaviour change) — writer: OpenCode, reviewer: Architect

Move code without changing any behaviour, output or message. Do one move at a time in the
order 2a → 2b → 2c, and run the listed tests after each one.

### 2a. `spyswat/swat_calib/core/run_state.py` (new)
- Move these from `core/workingFolder_manager.py` with their bodies unchanged:
  - `_OLD_MTIME`
  - `_copy_over`, which becomes `copy_over`
  - `_rch_signature`, which becomes `rch_signature`
  - `_stamp_output_rch`, which becomes `stamp_output_rch`
  - `StaleOutputError`
  - `_check_fresh_output_rch`, which becomes `check_fresh_output_rch`
- In `workingFolder_manager.py`, import them back and keep the old private names as
  aliases (`_copy_over = copy_over`, and so on). Spawned workers and
  `tests/test_working_folder.py` (`wfm._copy_over`) use those names.
- `calib_manager.py` keeps importing the **names** `_copy_over`, `_stamp_output_rch` and
  `_check_fresh_output_rch` at module level, because `tests/test_calib_manager.py`
  monkeypatches `cm._copy_over`.
- `analysis/algorithms/glue.py` imports `StaleOutputError` from `core.run_state`.
- Tests: `pytest tests/test_working_folder.py tests/test_run_once.py tests/test_calib_manager.py -q`

### 2b. `spyswat/swat_calib/calibration/param_spec.py` (new, pure functions)
- `parse_spec(param_ranges)` is the body of `CalibrationManager._parse_spec`.
- `format_params(raw, methods=None, subbasins=None)` is the body of `_format_params`.
- `is_raw(param_dict)` is the body of `_is_raw`.
- `param_columns(params)` is the body of `_param_columns`.
- Keep these aliases on `CalibrationManager`, because other modules call them:
  - `_parse_spec = staticmethod(parse_spec)`
  - `_is_raw = staticmethod(is_raw)`
  - `_param_columns = staticmethod(param_columns)`
  - `_format_params(self, raw, methods=None, subbasins=None)`, a method that returns
    `format_params(...)` (tests replace it on instances).
- Callers stay as they are; changing them is out of scope.
- Tests: `pytest tests/test_calib_manager.py tests/test_metrics.py tests/test_calibration.py -q`

### 2c. `spyswat/swat_calib/calibration/run_log.py` (new): `class RunLog`
- Move the per-run result log out of `CalibrationManager` into `RunLog(project)`:
  - the state: `_results_dir`, `_session_*`, `_prev_metrics`, `_run_counter`,
    `_log_columns`, `_warned`, `_pending`, `_pending_header`, `_log_outputs`;
  - `MAX_PENDING_ROWS = 10_000`;
  - the methods: `_warn_once`, `log_outputs`, `results_dir` (getter and setter,
    including the default `<project.working_folder>/calibration_results`),
    `_plan_session`, `_claim_session`, `session_path`, `session_files`, `_append_csv`,
    `flush_log`, `_fmt`, `_g`, `_logged_metric_names`, `_record_run`.
- `RunLog` holds no lambdas or closures. It uses `param_spec.format_params`, `is_raw` and
  `param_columns`.
- `CalibrationManager.__init__` sets `self._log = RunLog(project)`.
- `CalibrationManager` keeps the same public and private surface, each as a thin
  delegate to `self._log`:
  - the properties `log_outputs` and `results_dir`, both with setters;
  - `session_path`, `session_files`, `flush_log` and `record_run`;
  - `_record_run`, `_append_csv`, `_fmt`, `_g`, `_logged_metric_names` and `_warn_once`.

  `ValidationRunner` calls `manager._fmt`, `_append_csv`, `_record_run` and
  `_logged_metric_names`.
- Allowed test edits, limited to where a monkeypatch target moved
  (`tests/test_calib_manager.py` around lines 450-475):
  - `cm.open` becomes `run_log.open`;
  - `cm.time.sleep` becomes `run_log.time.sleep`;
  - `CalibrationManager._MAX_PENDING_ROWS` becomes `RunLog.MAX_PENDING_ROWS`;
  - `mgr._pending` becomes `mgr._log._pending`.

  No other test may change, and no assertion may be weakened.
- Tests: the full suite.

### Step 2 gate (record each result in `.agents/log/ARCH-1.md`)
- `python -m pytest tests/ -q` gives **336 passed, 11 skipped, 0 failed** (the same counts).
- `git diff --check` is clean.
- `calib_manager.py` is shorter, and has no CSV, session or param-spec code left except
  the delegates.
- Pickling still works: `python -c "import pickle, spyswat.swat_calib.core.run_state as r; pickle.dumps(r.copy_over)"`.
- One commit per sub-step: `ARCH-1: 2a run_state`, `ARCH-1: 2b param_spec`,
  `ARCH-1: 2c run_log`. Stage only these files and `.agents/log/ARCH-1.md`.
- Do not push or merge. Report to the Architect with `hc send t16 "[BÁO CÁO arch-1] ..."`.
  If a gate fails twice, stop and report; never weaken a test.

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

### 2d. Docs (added 2026-11-20 by the Architect; writer: OpenCode)
- `AGENTS.md`:
  - Quick orientation tree: add `core/run_state.py`, `calibration/param_spec.py` and
    `calibration/run_log.py`.
  - Design rule 4: sequential runs go through `run_once` inside `sandbox()`.
  - Common task "Run one SWAT iteration": add a short `sandbox()` + `run_once()` example.
  - Commands: set the expected count to the measured one.
- `CHANGELOG.md` `[Unreleased]`:
  - Added: `run_once`, `sandbox`, `StaleOutputError`.
  - Changed: module split (old private names kept); sensitivity/GLUE record a run after
    the restore.
- `ARCHITECTURE.md`: the calibration-manager section(s) describe the new modules.
  Keep the existing language of each section.
- Commit as `ARCH-1: docs: run_once/sandbox and module split`. Docs only, no code.
