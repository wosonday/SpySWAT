# Decision ARCH-1: one public "sequential run" primitive; split CalibrationManager

- Date: 2026-11-18 · Author: Architect (Claude Opus 5.5)
- Status: **approved by the user 2026-11-20**. To be done on `feat/ARCH-1`, branched from
  `main` after `fix/phase1-correctness` is merged (`.agents/tasks/MERGE-1.md`).

## Context

Measured on `fix/phase1-correctness` (b91512a + DOCS-1):

1. The sequence *backup → update_params → stamp output.rch → run → check fresh output →
   read_rch → record_run → restore* is hand-written four times:
   - `CalibrationManager.run_iteration` (calib_manager.py)
   - `SWATSensitivity._sequential_mean` (sensitivity.py:38) — **no freshness check**
   - `GLUE.uncertainty_band` (glue.py ~200-245)
   - `ValidationRunner.run` (validation_runner.py:66-108)
   Each copy differs slightly; the missing freshness check is the kind of drift this causes.
2. Other modules call 30+ *private* members of `CalibrationManager`
   (`_backup_state`, `_restore_state`, `_parse_spec`, `_format_params`, `_align_series`,
   `_record_run`, `_append_csv`, `_fmt`, `_param_columns`, ...). `ValidationRunner` alone uses
   15. The private names are the real internal API, but nothing marks or tests them as such.
3. `calib_manager.py` (735 lines, 31 methods) holds three jobs: parameter-spec parsing (pure),
   run execution (backup/restore/align), and the CSV run log (sessions, buffering).
4. `calib_manager.py` and `glue.py` import private helpers from `workingFolder_manager.py`
   (`_stamp_output_rch`, `_check_fresh_output_rch`, `_copy_over`, `_param_exts`,
   `_baseline_files`).

## Options

1. **Leave as is.** No churn. Drift between the four copies continues; every new feature
   (e.g. a fifth caller) copies the sequence again.
2. **Public primitive only.** Add `CalibrationManager.run_once(...)` and make the four callers
   use it. Small, high value, fixes the drift. Keeps the file large.
3. **Primitive + split (recommended).**
   - `calibration/param_spec.py`: `parse_spec`, `format_params`, `is_raw` (pure functions,
     re-exported as the old private methods for one release).
   - `calibration/run_log.py`: `RunLog` (sessions, append/buffer/flush, `record`).
     `CalibrationManager.record_run` delegates to it.
   - `core/run_state.py`: the public versions of the stamp / fresh / copy helpers.
   - `CalibrationManager.run_once(params, *, reach_id, output_variable, keep=False,
     mode="sequential") -> pd.Series` (and `sandbox()` context manager for backup/restore).
4. **Full rewrite of the calibration layer.** Not justified: the phase-1 behaviour is tested
   (327 tests) and correct apart from the drift above.

## Decision (approved 2026-11-20)

Option 3, in two commits so each is reviewable:
1. `run_once` + `sandbox()`; migrate the four callers; test that every caller rejects stale
   output (the test that `_sequential_mean` would fail today).
2. Move code into `param_spec.py`, `run_log.py`, `core/run_state.py`; keep thin private
   aliases so external user code keeps working; no behaviour change (full suite must stay
   at the merged baseline, 327 passed / 11 skipped, plus the new tests).

## Risks and follow-up

- Behaviour must not change: compare `<session>_metrics.csv` columns and test counts before
  and after.
- Picklability: nothing moved may become a closure (workers import these modules).
- Docs: AGENTS.md design rules 4 and 10, ARCHITECTURE §2.3 and §5.6/5.12 need updating.
- Worker skills for the implementation task: `test-driven-development` +
  `verification-before-completion` (tier: strong; multi-file refactor).

## Step 2 clarification (2026-11-20, Architect, answering OpenCode `[HỎI arch-1]`)

`tests/test_calib_manager.py:523-626` sets `_session_base`, `_session_id`, `_session_dir`,
`_session_claimed` and `_session_n` directly on a manager to simulate session races.
These tests stay unchanged.

**Approved:** `CalibrationManager` keeps exactly these five names as thin read/write
forwarders to `self._log`.

- They may be written as properties or as one small class-level descriptor, for example
  `_session_n = _ForwardToLog("_session_n")`.
- No `__getattr__`/`__setattr__` catch-all: an unknown attribute must still raise.
- No other run-log state gets a forwarder unless a test or another module needs it.
  Record each addition in `log/ARCH-1.md`.
