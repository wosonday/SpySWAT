# Review PAR-1 round 3 — FAIL (1 Major, 1 Minor)

- Reviewer: `gemini-4-hydrogen-high` via `agy --mode plan --sandbox` (independent, fresh session), static review of a file snapshot of `feat/PAR-1` at 97be029; saved verbatim by the Architect (local paths stripped).
- Architect note: Major 1 was also found by the Architect before this review. Root cause is the Architect's own round-3 spec, item 2 ("harvest all remaining futures (each recorded as failed)"), which the worker followed literally.


Static read-only review of `feat/PAR-1` at `97be029` (`VERSION.txt:1`); no files were modified and no commands were run.

> **Scope & Uncertainty Note:** Audit test counts (`354 passed / 11 skipped` on `97be029`) come from the prompt and `.agents/log/PAR-1.md:262-265`. `tests/test_scenario_scheduler.py` and `spyswat/swat_calib/core/workingFolder_manager.py` are not standalone files in this folder (`test_scenario_scheduler.py` was inspected via `PAR-1-full.diff:1174-1260`). Behavior of CPython `ProcessPoolExecutor` under `BrokenProcessPool` is inferred from standard library semantics rather than executed here beyond the logged test runs.

---

## 1. Round 2 Findings Check (`.agents/reviews/PAR-1-2.md`)

| Round 2 Finding | Status | Evidence & Test Assessment |
|---|---|---|
| **Major 1** (`save(final=True)` inside `except BaseException:` masks original exception) | **DONE** | `spyswat/swat_calib/scenarios/batch.py:689-696` wraps `save(final=True)` in `try/except Exception` (logs `WARNING`) and re-raises `orig_exc`, leaving normal-exit `save(final=True)` at `spyswat/swat_calib/scenarios/batch.py:700` unchanged. **Truly proven** by `test_keyboardinterrupt_not_masked_by_save_failure` (`tests/test_scenarios.py:748-773`): raises `KeyboardInterrupt` from `wait` on call 2 while jobs are active/pending, forces `_atomic_csv` to always raise `OSError("disk full")`, and asserts `KeyboardInterrupt` wins (does not assert the warning log or `shutdown` args, though `shutdown` runs before `save`). |
| **Major 2** (`_dispatch` inside `done_futures` loop drops other `done_futures` & inconsistent `BrokenProcessPool`) | **DONE (with Major regression)** | `for fut in done_futures:` (`spyswat/swat_calib/scenarios/batch.py:652-667`) harvests all `done_futures` before `_dispatch` (`spyswat/swat_calib/scenarios/batch.py:682-683`), and `BrokenProcessPool` stops dispatching and records failures instead of raising (`spyswat/swat_calib/scenarios/batch.py:656-681`). **Regression:** remaining futures in `futures` that already completed with `WorkerResult(ok=True, ...)` have their return value discarded and their `series/<job_id>.csv` deleted (see **Major 1** below). |
| **Minor 1** (`test_exception_mid_batch_saves_finished_rows_and_resume_skips` didn't exercise active interruption / partial resume) | **DONE (via new tests)** | Original test unchanged (`tests/test_scenarios.py:622-655`); mid-batch interruption with pending/running jobs is now covered by `test_keyboardinterrupt_not_masked_by_save_failure` (`tests/test_scenarios.py:748-773`), and partial resume (`["skipped", "ok", "ok", "ok"]`) by `test_broken_process_pool_fails_remaining_jobs` (`tests/test_scenarios.py:743-745`). |
| **Minor 2** (Unreachable `sched.is_base_bad` branch in `_dispatch`) | **DONE** | Removed from `_dispatch` (`PAR-1-round3.diff:243-246`). |

---

## 2. Round 3 Fix Spec & Tests Check (`.agents/decisions/PAR-1.md:89-117`)

| Spec Item / Test | Status | Evidence & Whether Test Truly Proves It |
|---|---|---|
| **Item 1** (Harvest, then dispatch) | **DONE** | `spyswat/swat_calib/scenarios/batch.py:651-683`: `freed_slots` collects slot indices across all `done_futures` first; `_dispatch(slot_idx)` runs only after the harvest loop and broken-pool check. No `iterdir`/`submit` runs between harvests. |
| **Item 2** (Broken pool = results, not exception) | **DONE (per literal spec; see Major 1)** | `spyswat/swat_calib/scenarios/batch.py:656-660,668-681,697-698`: catches `BrokenProcessPool`, records that job failed with `broken_err`, drains remaining `futures` as failed with `broken_err`, drains `sched.drain_all_pending()` with `"worker pool broke (<error>); re-run with resume=True"`, `break`s to `executor.shutdown(wait=True)` and returns `BatchResult`. *(Follows the spec's literal "each recorded as failed" phrasing, which causes **Major 1** if any future in `futures` had already succeeded.)* |
| **Item 3** (`weather_dir` `OSError` in `_dispatch` fails job, keeps slot consistent) | **DONE** | `spyswat/swat_calib/scenarios/batch.py:588-594`: wraps `Path(wd).iterdir()` in `try/except OSError`, calls `_record_failure(j, f"weather_dir unreadable: {exc}")`, calls `sched.finish(slot_idx, ok=False)` (so `needs_reseed=True` forces reseed on next `sched.take`, even if `sched.take` already mutated `slot.base`), and `continue`s. (See **Minor 1** on `results_since_save`.) |
| **Item 4** (Emergency save never masks) | **DONE** | `spyswat/swat_calib/scenarios/batch.py:689-696,700`. |
| **Item 5** (Remove unreachable `sched.is_base_bad` branch in `_dispatch`, keep `Scheduler.is_base_bad`) | **DONE** | Removed from `_dispatch` (`PAR-1-round3.diff:243-246`); `Scheduler.is_base_bad` preserved at `spyswat/swat_calib/scenarios/scheduler.py:50-51` and used by `_mark_base_bad` (`spyswat/swat_calib/scenarios/batch.py:568`) and unit test (`PAR-1-full.diff:1249`). |
| **Test (a)** (`test_broken_process_pool_fails_remaining_jobs`) | **DONE (partial proof)** | `tests/test_scenarios.py:707-745`: **proves** `p1` ok, `p2` crashes via `os._exit(1)`, `p3` (running) and `p4` (pending) fail, `run()` returns `BatchResult`, and `resume=True` runs only `p2..p4`. Does **not** test a simultaneous/already-finished sibling future in `done_futures` or in `futures` when the pool breaks. |
| **Test (b)** (`test_keyboardinterrupt_not_masked_by_save_failure`) | **DONE** | `tests/test_scenarios.py:748-773`: **truly proves** `KeyboardInterrupt` mid-batch wins over failing `save(final=True)`. |
| **Test (c)** (`test_unreadable_weather_dir_fails_its_jobs_others_ok`) | **DONE** | `tests/test_scenarios.py:776-789`: **proves** deleted `weather_dir` fails only `"wet"` jobs in `_dispatch` with `"weather_dir unreadable"` while `"base"` jobs succeed (stubs `_scenario_sig` because `_scenario_sig` at `spyswat/swat_calib/scenarios/batch.py:227-235` runs before the pool). |

---

## 3. Regression Hunt & Findings

### Regression Checks Summary
- **Harvest-then-dispatch (`spyswat/swat_calib/scenarios/batch.py:651-683`):** Solid. All `done_futures` are harvested before any `_dispatch`, `if broken_err is not None:` aborts dispatch before `freed_slots` is used, and if a prior harvest in `done_futures` made all slots unusable (`sched.mark_slot_unusable`), `_dispatch` returns `(None, False)` cleanly and the next iteration hits `if not futures:` (`spyswat/swat_calib/scenarios/batch.py:644-648`).
- **Overlay failure & slot state (`spyswat/swat_calib/scenarios/batch.py:588-594`, `spyswat/swat_calib/scenarios/scheduler.py:66-77`):** Slot state remains safe. Even when `sched.take(slot_idx)` mutates `slot.base` to a new base before `weather_dir` raises `OSError`, `sched.finish(slot_idx, ok=False)` sets `slot.needs_reseed = True`, forcing `reseed=True` on the slot's next `sched.take(slot_idx)`.
- **Emergency save (`spyswat/swat_calib/scenarios/batch.py:689-696`):** Safe. Preserves `orig_exc` (and does not catch a second `KeyboardInterrupt` during `save`), while `save(final=True)` writes `summary.csv` and `metrics.csv` in plan order when writable.
- **Broken-pool handling (`spyswat/swat_calib/scenarios/batch.py:656-681`):** Futures in `done_futures` that succeeded (`ok=True`) are preserved even if an earlier future in `done_futures` raised `BrokenProcessPool` (because line 660 uses `continue`). **However**, futures still in `futures` (not yet returned in `done_futures`) suffer from **Major 1** below. *(Note also: when another worker is still in-flight at `break` on line 681, `executor.shutdown(wait=True)` at line 698 waits for that worker to exit; if that worker was already inside `_extract_dispatch`, it may write `series/<job_id>.csv` after `_record_failure` ran `sf.unlink()`, leaving an unreferenced CSV file on disk—benign for `resume=True` since line 495 requires `old["status"] == "ok"`.)*

---

### Major 1 — Broken-pool drain discards `WorkerResult` of already-finished futures in `futures` and deletes their `series/<job_id>.csv`
- **Location:** `spyswat/swat_calib/scenarios/batch.py:672-678` and `spyswat/swat_calib/scenarios/batch.py:546-555`.
- **Evidence:**
  When `concurrent.futures.wait(futures, return_when=FIRST_COMPLETED)` returns `done_futures`, another worker's future remaining in `futures` may have already completed (its result popped from `pending_work_items` and set on the future before the pool broke, or returned by `wait` later because `FIRST_COMPLETED` woke on the crashed future first). For those futures, `fut.result()` at line 675 **returns a valid `WorkerResult(ok=True, ...)` without raising**, and their `series/<job_id>.csv` is already on disk.
  However, lines 674-678 ignore the return value of `fut.result()` and unconditionally call `_record_failure(j, broken_err)`:
  ```python
  for fut in list(futures):
      slot_idx, j = futures.pop(fut)
      try:
          fut.result()
      except Exception:  # noqa: BLE001 - pool is already broken
          pass
      _record_failure(j, broken_err)
  ```
  `_record_failure` marks the finished job `"failed"`, drops its metrics, and executes `sf.unlink()` (`spyswat/swat_calib/scenarios/batch.py:552-555`), destroying valid completed simulation output. *(Uncertainty: whether a simultaneously finishing worker lands in `done_futures` or remains in `futures` depends on OS pipe/event wakeup ordering, which is why `test_broken_process_pool_fails_remaining_jobs` with slow `p3` did not hit it.)*
- **Concrete fix:** Inspect `fut.result()` in the remaining-futures loop and record any completed `WorkerResult` via `_record_result` (and add a unit/integration test where a future remaining in `futures` already holds a `WorkerResult(ok=True, ...)` when another future raises `BrokenProcessPool`, asserting it stays `"ok"` with its `series/<job_id>.csv` intact):
  ```python
  for fut in list(futures):
      slot_idx, j = futures.pop(fut)
      try:
          w = fut.result()
      except BrokenProcessPool:
          _record_failure(j, broken_err)
      except Exception as exc:  # noqa: BLE001 - unpicklable result
          w = WorkerResult(False, f"{type(exc).__name__}: {exc}", 0.0, "", None)
          _record_result(j, slot_idx, w)
      else:
          _record_result(j, slot_idx, w)
  ```

### Minor 1 — `_dispatch` overlay `OSError` omits `results_since_save` and progress logging
- **Location:** `spyswat/swat_calib/scenarios/batch.py:591-594`.
- **Evidence:** When `Path(wd).iterdir()` raises `OSError`, `_dispatch` calls `_record_failure` (`done += 1`) without incrementing `results_since_save` or logging `"[Scenarios] %d/%d jobs done"`. Periodic `save()` still runs on the `_SAVE_INTERVAL_S` (10 s) timer and `save(final=True)` runs at exit, so no results are lost.
- **Concrete fix:** Optionally declare `nonlocal results_since_save` in `_dispatch` and increment `results_since_save += 1` (and log progress) on overlay failure.

---

## Next
1. Fix **Major 1** in `spyswat/swat_calib/scenarios/batch.py:672-678` so already-finished futures remaining in `futures` are recorded via `_record_result` (preserving `"ok"` status and `series/<job_id>.csv`) instead of overwritten by `_record_failure`.
2. Add a regression test in `tests/test_scenarios.py` covering a completed sibling future when `BrokenProcessPool` occurs (both in `done_futures` after the broken future and still in `futures`), verifying its status remains `"ok"` and its `series/<job_id>.csv` survives.
3. Re-run `python -m pytest tests/ -q` and `git diff --check main...HEAD`.
