# Review PAR-1 round 4 — PASS (0 Critical, 0 Major, 0 Minor)

- Reviewer: `gemini-4-hydrogen-high` via `agy --mode plan --sandbox` (independent, fresh session), static delta review of `feat/PAR-1` 97be029..8dfeac0; saved verbatim by the Architect (local paths stripped).


Static read-only review of `PAR-1-round4.diff` (`97be029..8dfeac0` per `VERSION.txt:1`) against the `Round 4 correction` section of `.agents/decisions/PAR-1.md:119-135`, using `spyswat/swat_calib/scenarios/batch.py` and `tests/test_scenarios.py` for context. No files were modified and no commands were run.

> **Uncertainty & Scope Note:** `spyswat/swat_calib/scenarios/scheduler.py` is not present in this review folder, so `Scheduler.finish`, `Scheduler.drain_bad_base_jobs`, and `Scheduler.drain_all_pending` behavior is inferred from their call sites in `spyswat/swat_calib/scenarios/batch.py:615-690` and `.agents/reviews/PAR-1-3.md:43`. Test execution results (`355 passed / 11 skipped / 0 failed` and 3× `28 passed` in `tests/test_scenarios.py`) are taken from the diff of `.agents/log/PAR-1.md` in `PAR-1-round4.diff:84-88`, not executed here.

---

## 1. Round 3 Findings & Round 4 Spec Check

| Item | Status | Evidence & Determinism Assessment |
|---|---|---|
| **Major 1** (Broken-pool drain reads `fut.result()`) | **FIXED** | `spyswat/swat_calib/scenarios/batch.py:676-687` now captures `w = fut.result()`: `BrokenProcessPool` calls `_record_failure(j, broken_err)`, any other `Exception` wraps `WorkerResult(False, ...)` and calls `_record_result(j, slot_idx, w)`, and a returned `WorkerResult` goes through `_record_result(j, slot_idx, w)` in `else:`, matching the main harvest loop (`spyswat/swat_calib/scenarios/batch.py:658-668`) and `.agents/decisions/PAR-1.md:125-128`. |
| **Minor 1** (`_dispatch` overlay `OSError` save count & progress log) | **FIXED** | `spyswat/swat_calib/scenarios/batch.py:580-598` declares `nonlocal results_since_save` at line 581 and on `OSError` (lines 592–598) increments `results_since_save += 1` and logs `"[Scenarios] %d/%d jobs done (%.1fs)"`, matching `.agents/decisions/PAR-1.md:129-130`. |
| **New Test** (`test_broken_pool_drain_keeps_finished_sibling_job`) | **FIXED** | `tests/test_scenarios.py:794-844` implements `drain_break_runner` and `test_broken_pool_drain_keeps_finished_sibling_job` per `.agents/decisions/PAR-1.md:131-135`. **Determinism:** `fake_wait` (`test_scenarios.py:823-836`) deterministically eliminates the parent-side `FIRST_COMPLETED` wakeup race by waiting `ALL_COMPLETED` and placing only raising futures (`p2`) in `done` while leaving the finished `p1` future in `not_done` (`futures`), forcing the drain loop to process `p1`. *(Minor worker-side timing note: `p1` writes `E5_DRAIN_MARKER` at line 802 before `_extract_dispatch` and IPC delivery finish, so `p2`'s `time.sleep(0.5)` at line 808 assumes extraction + IPC completes within 0.5 s; under severe CPU starvation `p1` would also raise `BrokenProcessPool` and fail the assertion rather than false-passing.)* |

Diff scope check: `PAR-1-round4.diff` modifies only `.agents/decisions/PAR-1.md`, `.agents/log/PAR-1.md`, `.agents/reviews/PAR-1-3.md`, `spyswat/swat_calib/scenarios/batch.py`, and `tests/test_scenarios.py`.

---

## 2. Regression Checks on Changed Lines

- **Scope of `nonlocal results_since_save` (`spyswat/swat_calib/scenarios/batch.py:574-598`):** No regression. `results_since_save = 0` is bound inside `ScenarioBatch.run` under `if todo:` (line 577) before `_dispatch` is defined (line 580) or called (lines 644, 692). When overlay `OSError` increments `results_since_save` during post-harvest dispatch (line 692), the periodic `save()` check immediately follows at lines 693–697; if all jobs fail during initial priming (line 644), `save(final=True)` at line 709 writes all rows.
- **Double recording of a job (`spyswat/swat_calib/scenarios/batch.py:656-690`):** No regression. Every future in `done_futures` is removed via `futures.pop(fut)` at line 657 (with `continue` after `BrokenProcessPool` at line 664 so it never falls through to `_record_result` at line 668), and every remaining future is popped once in the drain loop (line 677), taking exactly one branch (`_record_failure` or `_record_result`). Pending jobs not yet taken by `sched.take` are drained once via `sched.drain_bad_base_jobs()` (if triggered) or `sched.drain_all_pending()` (line 688).
- **`sched.finish` calls in the drain loop (`spyswat/swat_calib/scenarios/batch.py:676-690`):** No regression. `_record_result` (called at lines 685 and 687) calls `sched.finish(slot_idx, ok=...)` once for that slot's in-flight job. Because `_dispatch` only runs after the `done_futures` loop and line 690 breaks before `_dispatch`, each slot has at most one active future in `futures` and `sched.finish` is never called twice for the same assignment; after `drain_all_pending()` (line 688) and `break` (line 690), `sched` is not used again. *(Inferred for `Scheduler` internals as `scheduler.py` is absent from this folder.)*
- **Series files (`spyswat/swat_calib/scenarios/batch.py:519-555,676-687`):** No regression. Finished `ok` futures in the drain loop go through `_record_result` → `_record_success`, preserving `series/<job_id>.csv`, recording `series_file` and metrics, and leaving `resume=True` (`batch.py:495`) able to skip them. Failed / `BrokenProcessPool` futures still unlink `series/<job_id>.csv` via `_record_failure`.

---

## 3. Findings

No Critical, Major, or Minor findings. (Non-blocking observation only: the `0.5` s sleep in `drain_break_runner` at `tests/test_scenarios.py:808` assumes `p1` finishes `_extract_dispatch` and IPC delivery within 0.5 s of writing the marker; this matches the Round 4 spec and cannot false-pass.)
