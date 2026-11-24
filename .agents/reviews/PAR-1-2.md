# Review PAR-1 round 2 — FAIL (2 Major, 2 Minor)

- Reviewer: `gemini-4-hydrogen-high` via `agy --mode plan --sandbox` (independent, fresh session), static review of a file snapshot of `feat/PAR-1` at b7ce905; saved verbatim by the Architect (local paths stripped). Line numbers refer to b7ce905.
- Architect check: both Majors confirmed by reading `batch.py` (save inside `except BaseException`; `_dispatch` called inside the `done_futures` harvest loop).


Reviewed snapshot at `b7ce905` (per `VERSION.txt:1`), read-only without executing commands.

> **Scope & Uncertainty Note:** Static read-only review only; no tests or git commands were executed. The `351 passed / 11 skipped` count on `b7ce905` is taken from the audit note in the prompt (matching the `8c76920` run recorded in `.agents/log/PAR-1.md:168`). `tests/test_scenarios.py`, `tests/test_scenario_scheduler.py`, and `spyswat/swat_calib/core/workingFolder_manager.py` are not present as standalone files in this folder; the test files were inspected via `PAR-1-rework.diff` and `PAR-1-full.diff`, while `workingFolder_manager.py` internals remain unverified here.

---

## Round 1 Findings Check (`.agents/reviews/PAR-1-1.md`)

| Round 1 Finding | Status | Evidence & Test Assessment |
|---|---|---|
| **Major 1** (Non-`KeyboardInterrupt` pool shutdown & save) | **FIXED** *(with regressions — see Major 1 & Major 2 below)* | Replaced `except KeyboardInterrupt:` with `except BaseException:` calling `executor.shutdown(wait=False, cancel_futures=True)`, `save(final=True)`, and `raise` (`spyswat/swat_calib/scenarios/batch.py:663-668`). **Test assessment:** `test_exception_mid_batch_saves_finished_rows_and_resume_skips` (`PAR-1-rework.diff:460-493`) proves a `RuntimeError` inside `try:` saves `summary.csv` and `metrics.csv` and allows `resume=True` to skip them, **but only weakly**: because `n=2` and `_atomic_csv` only raises on its first call after both `p0` and `p1` have already finished (`results_since_save == 2`), no in-flight/pending futures exist to cancel, `shutdown` is not asserted, `KeyboardInterrupt`/`BrokenProcessPool` are not tested, and `state["raised"]` disables the fault before `save(final=True)` runs. |
| **Major 2** (`sched.mark_base_bad` never called / `drain_bad_base_jobs` dead) | **FIXED** | Local `bad_bases` set removed; `_mark_base_bad` now calls `sched.mark_base_bad(base)` (`spyswat/swat_calib/scenarios/batch.py:564-571`), `_dispatch` checks `sched.is_base_bad(base)` (`spyswat/swat_calib/scenarios/batch.py:585`), and `_record_result` drains via `sched.drain_bad_base_jobs()` returning `1 + len(drained)` (`spyswat/swat_calib/scenarios/batch.py:624-627`). **Test assessment:** Unit-proven by `test_bad_base_drains_its_pending_jobs` (`PAR-1-full.diff:1004-1012`) and end-to-end by `test_bad_base_fails_its_jobs_others_ok` (`PAR-1-full.diff:1178-1190`). |
| **Major 3** (Missing integration tests: exit-path, post-failure reseed, locked slot) | **FIXED** *(with Minor coverage note)* | Added 4 integration tests (`PAR-1-rework.diff:460-540`): (a) `test_exception_mid_batch_saves_finished_rows_and_resume_skips` (caveats noted under Major 1), (b) `test_failed_job_reseeds_slot_before_next_job` (**proves** `leftover.tmp` from a failed job on `n=1` does not leak to the next job on the same base), and (c) `test_locked_slot_unusable_then_remaining_fail_with_message` (**proves** Windows open-file lock marks slot unusable and drains remaining jobs with `_ALL_UNUSABLE_MSG`; only covers `n=1`, not partial-slot loss with `n > 1`). |
| **Minor 1** (`metrics.csv` order on interrupt/periodic save) | **FIXED** | `metrics_df` is now sorted by `job_order` inside `save()` before writing (`spyswat/swat_calib/scenarios/batch.py:458-461`). **Test assessment:** `test_exception_mid_batch_saves_finished_rows_and_resume_skips` (`PAR-1-rework.diff:464-488`) puts slow `p0` (2.0 s) before fast `p1` (0.5 s) and asserts `metrics.csv` rows are `["base__p0", "base__p1"]` — **proves it**. |
| **Minor 2** (Product diff ~409 lines vs ~400 target) | **ACCEPTED** | Accepted by Architect (~404 lines noted in `.agents/log/PAR-1.md:173-174`). |
| **Minor 3** (Pool started when `todo` is empty) | **FIXED** | Pool construction and dispatch loop are guarded by `if todo:` (`spyswat/swat_calib/scenarios/batch.py:573`). **Test assessment:** `test_no_pool_when_everything_resumed` (`PAR-1-rework.diff:496-511`) monkeypatches `ProcessPoolExecutor` to raise/record and asserts `calls == []` — **proves it**. |
| **Minor 4** (Tight timing margin in no-barrier test) | **FIXED** | Long job `_TIMING_SLEEP[40.0]` widened from `1.8` s to `2.4` s vs `0.6` s short jobs (`PAR-1-rework.diff:408`). |

---

## Specific Checks Requested

- **`results_since_save` accounting:** **Accurate on the active paths.** `_record_result` (`spyswat/swat_calib/scenarios/batch.py:609-634`) returns `1` for normal success/failure/locked-slot and `1 + len(drained)` when `sched.drain_bad_base_jobs()` runs (`spyswat/swat_calib/scenarios/batch.py:624-627`), and `spyswat/swat_calib/scenarios/batch.py:654` adds that return value to `results_since_save`. The `drain_all_pending` path (`spyswat/swat_calib/scenarios/batch.py:643-645`) breaks immediately to `save(final=True)` (`spyswat/swat_calib/scenarios/batch.py:670`). (See Minor 2 for the dead `_dispatch` bad-base branch.)
- **`save(final=True)` inside `except BaseException:`:** **Can mask the original exception** (Major 1).
- **Worker process crash (`BrokenProcessPool`) + next `submit`:** **Loses other completed futures in `done_futures` and behaves inconsistently depending on whether jobs remain in `sched`** (Major 2).

---

## Findings (Round 2)

### Major 1 — `save(final=True)` inside `except BaseException:` can mask the original exception
- **Location:** `spyswat/swat_calib/scenarios/batch.py:663-666` and `save(final=True)` at `spyswat/swat_calib/scenarios/batch.py:462-476`.
- **Evidence:** Inside `save(final=True)`, if `_atomic_csv(df, path)` raises `OSError`, it tries `_atomic_csv(df, alt)` (`spyswat/swat_calib/scenarios/batch.py:469`), which intentionally raises if the fallback also fails (required on normal exit by `test_fallback_write_failing_too_raises`, `PAR-1-full.diff:1110-1113`). However, when `save(final=True)` is called from `except BaseException:` (`spyswat/swat_calib/scenarios/batch.py:665`), any `OSError` from an unwritable/full `results_dir` (or any other `Exception` during `save`) propagates out of `save(final=True)` and **replaces/masks the original `KeyboardInterrupt`, `SystemExit`, `BrokenProcessPool`, or `OSError`** (and skips saving `summary.csv` if `metrics.csv` failed). `test_exception_mid_batch_saves_finished_rows_and_resume_skips` only hid this because its `boom` stub cleared `state["raised"]` after the first raise.
- **Concrete fix:** Guard `save(final=True)` inside `except BaseException:` so an emergency-save error is logged as a warning instead of masking the original exception (leaving normal-exit `save(final=True)` at `spyswat/swat_calib/scenarios/batch.py:670` unchanged):
  ```python
  except BaseException as orig_exc:
      executor.shutdown(wait=False, cancel_futures=True)
      try:
          save(final=True)
      except Exception as save_exc:  # noqa: BLE001 - preserve original exception
          logger.warning("[Scenarios] could not save partial results during %s: %s",
                         type(orig_exc).__name__, save_exc)
      raise
  ```

### Major 2 — `_dispatch(slot_idx)` inside `for fut in done_futures:` drops other completed `done_futures` on `BrokenProcessPool` / `OSError` and handles broken pools inconsistently
- **Location:** `spyswat/swat_calib/scenarios/batch.py:648-657` and `_dispatch` at `spyswat/swat_calib/scenarios/batch.py:579-607`.
- **Evidence:**
  1. When `concurrent.futures.wait(..., FIRST_COMPLETED)` returns multiple completed futures in `done_futures`, the loop calls `_dispatch(slot_idx)` immediately after each future (`spyswat/swat_calib/scenarios/batch.py:657`) before recording the rest of `done_futures`. If a worker crashed (`BrokenProcessPool` caught by `fut.result()` at `spyswat/swat_calib/scenarios/batch.py:651-653`) and `sched` still has pending jobs, `_dispatch(slot_idx)` pops the next job (`sched.take`, `spyswat/swat_calib/scenarios/batch.py:581`) and calls `executor.submit(...)` (`spyswat/swat_calib/scenarios/batch.py:602`) on the broken pool, raising `BrokenProcessPool` (the same applies if `Path(wd).iterdir()` at `spyswat/swat_calib/scenarios/batch.py:591` raises `OSError`). Any already-completed `ok` futures remaining in `done_futures` are **never recorded** in `rows`/`metrics_df` before `except BaseException:` saves and exits (losing finished work even though their `series/<job_id>.csv` files are already on disk). *(Uncertainty: whether another in-flight worker's future lands in the same `done_futures` set when a worker dies depends on OS process-teardown timing, but for any simultaneous completions or `weather_dir` `OSError` the remaining `done_futures` are dropped.)*
  2. In addition, `BrokenProcessPool` handling is inconsistent: if no jobs remain in `sched` when the crash occurs, `sched.take` returns `(None, False)`, `executor.submit` is skipped, and `ScenarioBatch.run()` returns a `BatchResult` (`status="failed"`); if any job remains in `sched`, `executor.submit` raises `BrokenProcessPool` out of `run()`.
- **Concrete fix:**
  1. Record all `done_futures` first (collecting `freed_slots.append(slot_idx)`), and dispatch `for slot_idx in freed_slots: _dispatch(slot_idx)` only after the harvest loop finishes.
  2. Do not call `executor.submit` after a `BrokenProcessPool` (either re-raise `BrokenProcessPool` cleanly after recording all non-broken `done_futures` and saving, or fail remaining `futures`/`sched` jobs consistently). Also add a unit/integration test covering mid-batch interruption/pool error *while* jobs are still pending/running and verifying both `save(final=True)` fault isolation and `done_futures` preservation.

### Minor 1 — `test_exception_mid_batch_saves_finished_rows_and_resume_skips` does not exercise active-future cancellation or partial resume
- **Location:** `PAR-1-rework.diff:460-493`.
- **Evidence:** Both jobs (`p0`, `p1`) finish before the first `save()` triggers `boom`, so `resume=True` yields `["skipped", "skipped"]` and neither pending-job preservation nor active-future shutdown (`wait=False, cancel_futures=True`) is exercised.
- **Concrete fix:** Use e.g. 4 jobs with `n=2` (or raise `KeyboardInterrupt` / `BrokenProcessPool` / `OSError` on `results_since_save == 2` while jobs 3–4 remain), and verify the finished subset is `"skipped"` on `resume=True` while the remaining jobs run to `"ok"`.

### Minor 2 — Unreachable `if sched.is_base_bad(base):` branch in `_dispatch` omits `results_since_save` and progress logging
- **Location:** `spyswat/swat_calib/scenarios/batch.py:585-588`.
- **Evidence:** Because `_mark_base_bad` (`spyswat/swat_calib/scenarios/batch.py:568`) and `sched.drain_bad_base_jobs()` (`spyswat/swat_calib/scenarios/batch.py:624`) run together inside `_record_result`, `sched._pending` never holds a bad-base job when `_dispatch` runs; if it ever did, `_dispatch` returns `None` without updating `results_since_save`.
- **Concrete fix:** Either track the count or drop the dead branch if `drain_bad_base_jobs()` remains the single drain path.

---

## Next
- Fix **Major 1** and **Major 2** in `spyswat/swat_calib/scenarios/batch.py` and add regression tests in `tests/test_scenarios.py` (guarding `save(final=True)` failure inside `except BaseException:`, harvesting `done_futures` before `_dispatch`, and interrupting while jobs remain pending/running).
- Re-run `python -m pytest tests/ -q` and `git diff --check main...HEAD`, then re-submit for round 3.
