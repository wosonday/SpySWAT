# API-5A — resume by replay (cursor, manager and algorithms)

## Files changed
- `spyswat/swat_calib/calibration/replay.py` (new): `ResumeMismatchError`,
  `StoredRun`, `ReplayCursor` (ordered cursor, contiguity `1..k` check, canonical
  `-0.0 -> 0.0` float comparison, `remaining`/`next_run_id`), `check_param_order`.
- `spyswat/swat_calib/calibration/calib_manager.py`: `run_batch`/`run_iteration`
  accept keyword-only `replay`; `_new_path` routes on `replay is not None`;
  `_run_batch_multi`/`_run_iteration_multi` replay a committed prefix without
  running SWAT or `store.add_run`, sync `_store_counter`, and (run_batch) bypass
  workers/queue when the whole batch is replayed.
- `spyswat/swat_calib/analysis/algorithms/{glue,pso,parallel_de,dds}.py`: each
  accepts keyword-only `replay=None` and forwards it to the manager.
- `tests/test_resume_replay.py` (new): 20 tests (see below).
- `.agents/log/API-5A.md` (this file).

## Commands + result lines
- `python -m pytest tests/test_resume_replay.py -q -p no:cacheprovider` -> `20 passed`
- `python -m pytest tests/ -q -p no:cacheprovider` -> `701 passed, 15 skipped, 12 warnings`
- `git diff --check` -> clean (no output)

## Coverage of the acceptance criteria (5a)
- Reference vs interrupted+resumed identical for glue/pso/de/dds (multi-site,
  multiple metrics, `KeyboardInterrupt` at eval k+1): `test_resume_matches_reference`,
  plus mid-chunk with n_workers=2: `test_glue_mid_chunk_interrupt_discards_partial_chunk`.
- Completed session -> 0 runner calls; empty session -> run_id=1 and runs all N:
  `test_resume_completed_session_makes_zero_runner_calls`,
  `test_resume_empty_session_runs_all_from_run_id_1`.
- Failed runs: `test_run_batch_replays_failed_run_as_nan_not_retried`,
  `test_dds_failed_run_penalize_replays_nan`,
  `test_dds_failed_run_raise_reraises_without_retry`.
- Integrity: `test_replay_cursor_rejects_noncontiguous_run_ids` (gap/duplicate/non-1),
  `test_replay_cursor_param_mismatch_names_run_and_values`,
  `test_replay_cursor_minus_zero_matches_zero`, `test_replay_cursor_param_order_mismatch`,
  `test_replay_cursor_exhaustion_returns_none_and_tracks_remaining`,
  `test_check_param_order_rejects_reordered_keys`,
  `test_torn_tail_ignored_and_overwritten_on_resume`.

Facade-specific criteria (seed=None through the facade, FileNotFoundError/FileExistsError,
signature check, param-order wiring into `project.calibration`) are API-5b and not tested here.

## Open questions
- None. The log file for this task is `API-5A.md` (the task file wrote `API-5.md` /
  `api-5:` but the id is `api-5a` and the branch is `feat/api-5a`; commit prefix and
  log name follow the task id).
