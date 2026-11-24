# FIX-1 — work log (append-only)

## 2026-11-24 — worker-fast (DeepSeek V4.1 Flash), TDD

Task: F5 (ScenarioBatch worker logging) and F6 (per-batch work dir), per
`.agents/tasks/FIX-1.md` and findings F5/F6 in `.agents/decisions/PAR-1.md`.

### Cycle 1 — red

Added three tests to `tests/test_scenarios.py` first:

- `test_run_passes_log_queue_to_every_job` — real spawned workers, a Manager queue passed
  as `log_queue=`; a `logging_runner` emits one record per job from inside the worker.
  Fails before the fix: `TypeError: ... unexpected keyword argument 'log_queue'`.
- `test_run_defaults_to_the_logger_queue_and_starts_no_listener` — `Logger._log_queue`
  monkeypatched to a Manager queue, `log_queue` omitted; asserts the worker record reaches
  that queue and that `Logger._listener` is still `None` (no listener started in `run()`).
  Fails before the fix (no records in the queue).
- `test_work_dir_is_keyed_by_results_dir` — one project, two `results_dir`s: each gets its
  own folder under `<working_folder>/_scenario_batch/`, names match `[0-9a-f]{10}`, exactly
  one new folder for a second results dir, and re-running the first results dir adds none.
  Fails before the fix (old layout put `TxInOut1` directly under `_scenario_batch`).

Command: `python -m pytest tests/test_scenarios.py -q -k "log_queue or logger_queue or
work_dir"` → 3 failed.

### Cycle 2 — green

`spyswat/swat_calib/scenarios/batch.py`:

- new module-level `_work_dir_key(results_dir)` = first 10 hex chars of
  `sha1(str(Path(results_dir).resolve()).lower())`; `WORK_SUBDIR` constant name unchanged.
- `run()`: `work_dir = Path(proj.working_folder) / WORK_SUBDIR / _work_dir_key(res_dir)`;
  `res_dir` is now computed before `work_dir`.
- `run(..., log_queue=None)`: `log_q = Logger._log_queue if log_queue is None else
  log_queue`, passed to every `executor.submit(_seed_and_run, ...)` (replaces the literal
  `None`, which lost worker records under spawn). No listener is started inside `run()`.
- class docstring and `run()` Args docstring updated for both changes.

Command: `python -m pytest tests/test_scenarios.py -q -k "log_queue or logger_queue or
work_dir"` → 3 passed.

### Files changed

- `spyswat/swat_calib/scenarios/batch.py`
- `tests/test_scenarios.py` (3 tests added, no existing test weakened)
- `.agents/log/FIX-1.md` (this file)

### Commands run and counts

| Command | Result |
|---|---|
| `python -m pytest tests/test_scenarios.py -q -k "log_queue or logger_queue or work_dir"` (before fix) | 3 failed |
| `python -m pytest tests/test_scenarios.py -q -k "log_queue or logger_queue or work_dir"` (after fix) | 3 passed, 28 deselected |
| `python -m pytest tests/test_scenarios.py tests/test_scenario_scheduler.py -q` | 38 passed |
| `python -m pytest tests/ -q` | 454 passed, 11 skipped, 24 subtests passed (baseline 451/11 + 3 new) |
| `git diff --check` | clean (no output) |

### Acceptance criteria

- [x] `run(..., log_queue=q)` passes `q` to every submitted job (test above; no SWAT exe).
- [x] `log_queue` omitted + `Logger._log_queue` set → that queue is used.
- [x] Different `results_dir` → different work dirs; same `results_dir` → same one.
- [x] `tests/test_scenarios.py tests/test_scenario_scheduler.py` and the full suite pass
      (counts above).
- [x] `git diff --check` clean.

### Notes / open questions (out of scope, not changed)

- `docs_impact: yes` but `docs/` has no mention of `_scenario_batch`, `ScenarioBatch(` or
  `log_queue`, so no doc edit is needed here; Docs Updater may want to document the new
  `log_queue=` argument if `ScenarioBatch` usage is ever added to docs.
- Existing batches started before this change left slot folders directly under
  `<working_folder>/_scenario_batch/`. They are orphaned (never removed) but harmless; a
  cleanup is a separate task if wanted.
- `ScenarioBatch.run()` records metrics for the batch; it does not call
  `Logger.stop_listener()` either — the caller keeps owning the listener lifetime, matching
  `CalibrationManager.run_batch()`.

## 2026-11-24 20:31 — Docs Updater (agy gemini-4-hydrogen-medium, accept-edits)

- CHANGELOG.md: two bullets under [Unreleased] / Changed (log_queue, per-results_dir work dir).
- No other doc mentions `_scenario_batch` or `ScenarioBatch(` log setup; nothing else changed.
- Review round 1: PASS (agy Hydrogen High), see `.agents/reviews/FIX-1-1.md`.
