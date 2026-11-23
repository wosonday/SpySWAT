# Log PAR-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 1/N — task brief
- Branch `feat/PAR-1` from `main` at `b814f18`.
- Read `AGENTS.md`, `.agents/tasks/PAR-1.md`, `.agents/decisions/PAR-1.md`.
- Skills: `tdd` (test-driven-development) loaded; `verification-before-completion` is not
  an installed skill id, so the TDD red→green loop is applied with explicit verification
  steps (recorded counts) instead.
- Goal: `ScenarioBatch.run()` runs the whole job list on one `ProcessPoolExecutor`, with a
  free slot taking the next job at once — no barrier between chunks or between base groups.
  Public API, written files, resume and per-job failure isolation stay unchanged.
- Files changed: `.agents/tasks/PAR-1.md`, `.agents/decisions/PAR-1.md` (committed unchanged),
  `.agents/log/PAR-1.md` (new).
- Checks: none yet (brief only).
- Previous commit: `b814f18`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 2/N — RED tests
- Added the scheduling tests before any implementation (TDD red→green).
- New unit tests `tests/test_scenario_scheduler.py` for a `Scheduler` (pure dispatch:
  same-base preference, reseed on base switch and after failure, unusable slot, bad-base
  drain, drain-all).
- New integration tests in `tests/test_scenarios.py` (existing assertions untouched;
  added `import time` and two module-level fake runners `timing_runner` / `marker_runner`):
  - `test_all_jobs_overlap_across_two_bases` (2 bases x 2 sets, n_parallel=4 → 4 jobs overlap)
  - `test_no_barrier_short_jobs_flow_while_long_runs` (n_parallel=2, one 1.8s job, three 0.6s)
  - `test_reseed_on_base_switch_sees_only_that_bases_files` (marker file per base)
  - `test_bad_base_fails_its_jobs_others_ok`
- RED (failure lines recorded on `main` code, HEAD `212cc06`):
  - `tests/test_scenario_scheduler.py:5` — `ModuleNotFoundError: No module named
    'spyswat.swat_calib.scenarios.scheduler'` (collection error).
  - `tests/test_scenarios.py:527` `test_all_jobs_overlap_across_two_bases` —
    `assert max(starts) < min(ends)` → `1795448118.867288 < 1795448115.771066` (two
    sequential base groups: base A's jobs finish before base B's start).
  - `tests/test_scenarios.py:548` `test_no_barrier_short_jobs_flow_while_long_runs` —
    `assert float(r[1]) < long_end` → short job starts at 1795448057.52 after the long
    job ends at 1795448054.39 (chunk barrier).
- Files changed: `tests/test_scenario_scheduler.py` (new), `tests/test_scenarios.py`.
- Checks: `pytest tests/test_scenario_scheduler.py -q` → 1 error (import);
  `pytest tests/test_scenarios.py -k "overlap_across_two_bases or no_barrier or
  reseed_on_base_switch or bad_base" -q` → 2 failed / 2 passed (the two scheduling
  tests fail, the marker + bad-base regression tests already pass on the chunked code).
- Previous commit: `212cc06`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 3/N — implement (green)
- Implemented the single-pool job queue; scheduler unit tests and the four integration
  tests now pass.
- `spyswat/swat_calib/scenarios/scheduler.py` (new): `Scheduler` + `Slot` — pure dispatch
  bookkeeping (same-base preference, reseed on base switch / after a failure, unusable
  slot, bad-base drain, drain-all). No filesystem/process access.
- `spyswat/swat_calib/scenarios/batch.py`:
  - Imported `WorkerResult`, `_OUTPUT_IGNORE`, `_rmtree`, `_worker_job` from
    `core.workingFolder_manager` (private helpers imported, not edited) and `Scheduler`.
  - New module-level `_seed_and_run(slot_dir, base_dir, reseed, *job_args)`: removes the
    slot folder and re-copies the base (same output-ignore rule) when `reseed`, then calls
    the unchanged `_worker_job`. Never raises; seed failures are prefixed
    `_SLOT_LOCKED_PREFIX` (folder locked → slot unusable) or `_SEED_FAILED_PREFIX`
    (base copy failed → base marked bad).
  - Replaced the per-base group/chunk loop with one `ProcessPoolExecutor(max_workers=n_parallel)`
    for the whole call. `_dispatch` feeds a free slot the next same-base pending job (else
    the first of any base with a reseed); `_record_result` classifies each future. Bad
    bases are drained to `setup of <base> failed: ...`; all-slots-unusable fails the rest
    with one message. Save cadence: after `n_parallel` results or 10 s, and always at the
    end; `KeyboardInterrupt` cancels pending futures, saves the finished rows, re-raises.
  - `save()` now writes `summary.csv` and `metrics.csv` rows in plan order (the chunked
    code appended in plan order), so the file layout is unchanged by async completion.
  - `WorkingFolderManager` / `run_parallel` are no longer used in batch.py and are
    untouched elsewhere (calibration still uses them).
- RED → GREEN: `tests/test_scenario_scheduler.py` (7) + the 4 new integration tests all
  pass; the two timing tests now show all 4 jobs overlapping and the short jobs flowing
  on the second slot while the 1.8s job runs.
- Files changed: `spyswat/swat_calib/scenarios/batch.py`,
  `spyswat/swat_calib/scenarios/scheduler.py` (new).
- Checks:
  - `pytest tests/test_scenario_scheduler.py -q` → 7 passed.
  - `pytest tests/test_scenarios.py -q` → 20 passed, ×3 runs in a row.
  - `pytest tests/ -q` → **347 passed / 11 skipped / 0 failed** (336 baseline + 11 new),
    174 s.
  - `git diff --check main...HEAD` → 0.
  - Product diff (tests excluded): batch.py 211+/99- and scheduler.py 94 lines ≈ 404
    lines (just over the ~400 target).
- Decision: kept `summary.csv`/`metrics.csv` in plan order even though rows arrive in
  completion order, to honour "files written stay exactly as today".
- Previous commit: `e3e3d03`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 4/N — verification
- Re-ran after the plan-order fix for `summary.csv`/`metrics.csv`.
- `pytest tests/test_scenarios.py -q` → 20 passed, ×3 runs in a row (timing tests stable).
- `pytest tests/ -q` → **347 passed / 11 skipped / 0 failed** (336 baseline + 11 new),
  174 s; 5 pre-existing warnings.
- `git diff --check main...HEAD` → 0; `git status` clean.
- Files changed in this task (committed): `.agents/tasks/PAR-1.md`,
  `.agents/decisions/PAR-1.md`, `.agents/log/PAR-1.md`,
  `spyswat/swat_calib/scenarios/batch.py`,
  `spyswat/swat_calib/scenarios/scheduler.py` (new),
  `tests/test_scenario_scheduler.py` (new), `tests/test_scenarios.py`.
- Product diff (tests excluded): batch.py 216+/99- + scheduler.py 94 new = 409 lines
  (slightly over the "~400" soft target; flagged rather than trimming readability).
- Acceptance criteria: all checked except the line-count target is 409 vs "under ~400".
- Previous commit: `1e307f1`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 5/N — report blocked
- Work is complete and committed; attempted the handoff report twice:
  `agm send t81 --type "BÁO CÁO" --task par-1 "see .agents/log/PAR-1.md"` → both failed with
  `hc status_mismatch: t81 is working, not idle` (the CEO terminal is busy).
- Fallback `hc send t81 "see .agents/log/PAR-1.md"` was rejected by this non-interactive
  run (permission). Not forced, not retried further.
- Pointer for the CEO/manager: branch `feat/PAR-1` at `ebcf6df`, log
  `.agents/log/PAR-1.md`. Files changed (see log): batch.py, scheduler.py (new),
  test_scenario_scheduler.py (new), test_scenarios.py, + .agents task/decision/log.
  `pytest tests/ -q` → 347 passed / 11 skipped / 0 failed.
- Previous commit: `ebcf6df`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 6/N — rework round 1: RED tests
- Review `.agents/reviews/PAR-1-1.md` (verdict FAIL: 3 Major, 4 Minor). Rework fixes Major 1, 2,
  3, Minor 1, 3, 4; Minor 2 (409-line diff) accepted unchanged.
- TDD red→green: added the failing tests before touching product code.
- `tests/test_scenarios.py`:
  - new module-level runners `completion_runner` / `leftover_runner` / `lock_runner`.
  - `test_exception_mid_batch_saves_finished_rows_and_resume_skips` (Major 1 + Minor 1):
    a non-KeyboardInterrupt exception mid-batch must save the finished rows (summary.csv +
    metrics.csv in plan order) and `resume=True` must skip them.
  - `test_no_pool_when_everything_resumed` (Minor 3): a resume run with nothing left must
    not construct a `ProcessPoolExecutor`.
  - `test_failed_job_reseeds_slot_before_next_job` (Major 3b): a failed job's leftover file
    must not reach the next job on the same slot (n_parallel=1).
  - `test_locked_slot_unusable_then_remaining_fail_with_message` (Major 3c): a slot whose
    folder cannot be removed becomes unusable and the remaining jobs fail with the
    all-unusable message (Windows open-file locking).
  - Minor 4: `_TIMING_SLEEP` long job 1.8 s → 2.4 s (wider CI margin).
- RED failure lines on HEAD `2f6ef4a` (`pytest tests/test_scenarios.py -k
  "exception_mid_batch or no_pool_when or reseeds_slot or locked_slot" -q` → 2 failed / 2 passed):
  - `test_exception_mid_batch_saves_finished_rows_and_resume_skips` — `FileNotFoundError:
    [Errno 2] ...\\res\\summary.csv` (Major 1: a non-KeyboardInterrupt exception left the
    finished rows unsaved).
  - `test_no_pool_when_everything_resumed` — `RuntimeError: pool must not start when nothing
    to run` (Minor 3: the pool is still constructed when `todo` is empty).
  - `test_failed_job_reseeds_slot_before_next_job` and
    `test_locked_slot_unusable_then_remaining_fail_with_message` PASS on the current code
    (coverage only; they lock in the existing behaviour).
- Files changed: `tests/test_scenarios.py`.
- Previous commit: `2f6ef4a`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 7/N — rework round 1: fix (green)
- `spyswat/swat_calib/scenarios/batch.py`:
  - Major 1: `except KeyboardInterrupt:` → `except BaseException:` — the pool is shut down
    (`wait=False, cancel_futures=True`) and `save(final=True)` runs on every exit path, then
    the exception is re-raised (`else: executor.shutdown(wait=True)`).
  - Major 2: `_mark_base_bad` now calls `sched.mark_base_bad(base)` and checks
    `sched.is_base_bad(base)`; the duplicate local `bad_bases` set is removed; `_dispatch`
    uses `sched.is_base_bad`. `_record_result` returns the number of results recorded
    (including the drained bad-base jobs) so `results_since_save` counts them and a periodic
    save is not skipped after a drain.
  - Minor 1: metrics sorting moved into `save()` (before writing) so interrupted / periodic
    saves also write `metrics.csv` in plan order; the post-loop sort was removed.
  - Minor 3: the pool/dispatch loop is guarded by `if todo:` — nothing left to run means no
    `ProcessPoolExecutor` is constructed.
- Committed the review `.agents/reviews/PAR-1-1.md` unchanged (as received).
- GREEN: `pytest tests/test_scenarios.py tests/test_scenario_scheduler.py -q` → 31 passed.
  `pytest tests/test_scenarios.py -k "exception_mid_batch or no_pool_when or reseeds_slot or
  locked_slot" -q` → 4 passed.
- Files changed: `spyswat/swat_calib/scenarios/batch.py`, `.agents/reviews/PAR-1-1.md` (new,
  unchanged), `.agents/log/PAR-1.md`.
- Previous commit: `a3fdb78`

## 2026-11-23 · opencode-go/deepseek-v4-pro (worker-strong) · step 8/N — rework round 1: verification
- Full suite: `python -m pytest tests/ -q` → **351 passed / 11 skipped / 0 failed** (347
  baseline + 4 new) in 215 s; 5 pre-existing warnings.
- Stability: `pytest tests/test_scenarios.py -q` → 24 passed (second green run; timing tests
  stable with the widened margin).
- `git diff --check main...HEAD` → clean; `git status` clean.
- Product diff (tests excluded): `batch.py` 215+/95- + `scheduler.py` 94 new ≈ 404 lines
  (unchanged from the already-accepted Minor 2 soft-target overrun).
- Files changed this rework: `spyswat/swat_calib/scenarios/batch.py`,
  `tests/test_scenarios.py`, `.agents/reviews/PAR-1-1.md` (committed unchanged),
  `.agents/log/PAR-1.md`.
- Done. No `agm send` / `hc send` per rework instructions; pointer for the manager: branch
  `feat/PAR-1` at `8c76920`.
- Previous commit: `8c76920`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 9/N — rework round 2: brief
- Review `.agents/reviews/PAR-1-2.md` (FAIL: 2 Major, 2 Minor) and the "Round 3 fix spec"
  at the end of `.agents/decisions/PAR-1.md`. Implement exactly items 1-5 + tests a-c.
- Skill: `tdd` (only). Shell: one plain command per call from the worktree root.
- Committed (unchanged, as received/written): `.agents/reviews/PAR-1-2.md` (new),
  `.agents/decisions/PAR-1.md` (Round 3 fix spec appended by the Architect).
- Fix plan (items 1-5, `spyswat/swat_calib/scenarios/batch.py`):
  1. Harvest every `done_futures` future first (collect freed slot indexes), dispatch only
     after the harvest loop.
  2. `BrokenProcessPool` → results, not an exception: record the broken job, stop
     dispatching, drain remaining futures + pending jobs with a "worker pool broke (...)"
     message, return the `BatchResult`; shutdown on the normal path.
  3. `weather_dir` overlay listing `OSError` → record that job failed
     (`"weather_dir unreadable: <error>"`), `sched.finish(slot_idx, ok=False)`, continue.
  4. `except BaseException:` → keep `shutdown(wait=False, cancel_futures=True)`, then
     `save(final=True)` inside `try/except Exception` (log WARNING), then re-raise.
  5. Remove the unreachable `sched.is_base_bad` branch in `_dispatch`; keep
     `Scheduler.is_base_bad` for the unit test.
- Tests a-c (RED first), fake runners only, in `tests/test_scenarios.py`.
- Previous commit: `b7ce905`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 10/N — rework round 2: RED tests
- Added the three regression tests before any product change (TDD red→green).
- `tests/test_scenarios.py`: new module-level `break_runner` (CN2=35 fast + drops a
  marker; CN2=50 waits for the marker then `os._exit(1)`; CN2=60/70 slow so they are still
  running when the pool breaks) and:
  - `test_broken_process_pool_fails_remaining_jobs` (a): 4 jobs, `n_parallel=2`; job 2's
    worker dies → `run()` must return with job 1 `ok`, jobs 2-4 `failed`
    (`BrokenProcessPool`/`pool broke`), and `resume=True` runs only the not-ok jobs.
  - `test_keyboardinterrupt_not_masked_by_save_failure` (b): monkeypatches
    `concurrent.futures.wait` to raise `KeyboardInterrupt` on its 2nd call **and**
    `_atomic_csv` to always raise `OSError`; asserts the original `KeyboardInterrupt` wins.
  - `test_unreadable_weather_dir_fails_its_jobs_others_ok` (c): weather_dir deleted after
    the Scenario is built (with `_scenario_sig` stubbed so planning/signature succeed) →
    its jobs `failed` with `weather_dir unreadable`, the other base's jobs `ok`.
- RED failure lines on HEAD `2f1d024`:
  - `test_broken_process_pool_fails_remaining_jobs` — `concurrent.futures.process.
    BrokenProcessPool: A child process terminated abruptly, the process pool is not usable
    anymore` raised at `batch.py:602` (`executor.submit` inside `_dispatch`): the loop
    keeps dispatching onto the broken pool. (First cut of the runner showed
    `['ok','failed','ok','ok']`; jobs 3/4 were finishing before the 2 s `os._exit`, so the
    runner was reworked to gate the kill on job 1's marker and keep jobs 3/4 slow.)
  - `test_keyboardinterrupt_not_masked_by_save_failure` — `OSError: disk full` masks the
    injected `KeyboardInterrupt`; raised at `batch.py:469` (`_atomic_csv(df, alt)` inside
    `save(final=True)`) called from `except BaseException` at `batch.py:665`.
  - `test_unreadable_weather_dir_fails_its_jobs_others_ok` — `FileNotFoundError:
    [WinError 3] ... 'wet'` at `batch.py:591` (`Path(wd).iterdir()` in `_dispatch`): the
    overlay listing aborts the whole batch.
- Checks: `python -m pytest tests/test_scenarios.py -k "broken_process_pool" -q` → 1 failed
  (BrokenProcessPool); `-k "broken_process_pool or keyboardinterrupt_not_masked or
  unreadable_weather_dir" -q` → 3 failed.
- Files changed: `tests/test_scenarios.py`.
- Previous commit: `2f1d024`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 11/N — rework round 2: fix (green)
- `spyswat/swat_calib/scenarios/batch.py` (items 1-5 of the Round 3 fix spec):
  1. **Harvest, then dispatch** — the main loop collects `freed_slots` for every future in
     `done_futures` (recording each result) and only then calls `_dispatch` per freed slot;
     nothing that can raise runs between the two harvest phases.
  2. **Broken pool = results** — `fut.result()` raising
     `concurrent.futures.process.BrokenProcessPool` records that job as failed with the
     error text, sets `broken_err`, stops dispatching, consumes + records every remaining
     future as failed with the same text, drains the pending jobs with
     `"worker pool broke (<error>); re-run with resume=True"`, breaks out of the loop and
     returns the `BatchResult` (pool shut down on the normal path, `wait=True`).
  3. **Overlay OSError cannot abort the batch** — the `weather_dir` listing in `_dispatch`
     is wrapped; `OSError` records that job failed (`"weather_dir unreadable: <error>"`),
     calls `sched.finish(slot_idx, ok=False)` and continues with the next pending job.
  4. **Emergency save never masks** — `except BaseException as orig_exc:` keeps
     `shutdown(wait=False, cancel_futures=True)`, then `save(final=True)` inside
     `try/except Exception` that logs a WARNING, then re-raises the original exception.
     The normal-exit `save(final=True)` is unchanged.
  5. Removed the unreachable `sched.is_base_bad(base)` branch from `_dispatch` (drain still
     happens in `_record_result`); `Scheduler.is_base_bad` is kept (unit test +
     `_mark_base_bad`).
- GREEN: the three new tests pass; full suite below.
- Files changed: `spyswat/swat_calib/scenarios/batch.py`.
- Previous commit: `02a12d6`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 12/N — rework round 2: verification
- `python -m pytest tests/ -q` → **354 passed / 11 skipped / 0 failed** (351 baseline + 3 new)
  in 168 s; 5 pre-existing warnings.
- `python -m pytest tests/test_scenarios.py -q` → **27 passed** three times in a row
  (87.5 s, 89.2 s, 91.2 s) — timing and broken-pool tests stable.
- `git diff --check main...HEAD` → clean; `git status` clean after commit.
- Product diff (tests excluded): `batch.py` +44/-10 ≈ 54 lines (items 1-5 only; the
  ~400-line target from round 1 is unchanged elsewhere).
- Files changed this rework: `spyswat/swat_calib/scenarios/batch.py`,
  `tests/test_scenarios.py`, `.agents/reviews/PAR-1-2.md` (committed unchanged),
  `.agents/decisions/PAR-1.md` (Round 3 fix spec, committed unchanged),
  `.agents/log/PAR-1.md`.
- Done. No `agm send` / `hc send` per rework instructions; pointer for the manager: branch
  `feat/PAR-1` at `d7e4587`.
- Previous commit: `02a12d6`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 13/N — rework round 3: brief
- Review `.agents/reviews/PAR-1-3.md` (FAIL: 1 Major, 1 Minor) and the "Round 4 correction"
  at the end of `.agents/decisions/PAR-1.md`. Implement exactly items 1-3, nothing else.
- Skill: `tdd` (only). Shell: one plain command per call from the worktree root.
- Fix plan:
  1. Broken-pool drain loop reads `fut.result()`: a returned `WorkerResult` goes through
     `_record_result` (an `ok` job stays `ok`, its `series/<job>.csv` is kept); only
     `BrokenProcessPool` records `failed` with `broken_err`; any other exception becomes
     `WorkerResult(False, ...)` through `_record_result`, as in the main harvest loop.
  2. Minor 1: an overlay `OSError` in `_dispatch` also counts in `results_since_save` and
     logs the progress line.
  3. Test (RED first, deterministic, no timing race): `n_parallel=2`, p1 fast+ok, p2 sleeps
     then `os._exit(1)`; monkeypatch `concurrent.futures.wait` to wait ALL_COMPLETED then
     return only the broken future as `done`, leaving the finished p1 future in `futures`.
- Previous commit: `97be029`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 14/N — rework round 3: RED tests
- Added the regression test before any product change (TDD red→green).
- `tests/test_scenarios.py`: new module-level `drain_break_runner` (p1 CN2=35 fast+ok and
  drops a marker; p2 CN2=50 waits for the marker, sleeps 0.5 s, then `os._exit(1)`) and:
  - `test_broken_pool_drain_keeps_finished_sibling_job`: `n_parallel=2`, 2 jobs;
    `concurrent.futures.wait` is monkeypatched to wait `ALL_COMPLETED` and return only the
    broken future as `done`, leaving the finished p1 future in `futures`. Asserts p1 stays
    `ok` with its series file present and p2 is `failed` with `BrokenProcessPool`.
- RED failure line on HEAD `fa4e812`:
  `tests/test_scenarios.py:841` — `assert ['failed', 'failed'] == ['ok', 'failed']`
  (the drain loop recorded the already-finished p1 as `failed` with `broken_err` and
  deleted its `series/base__p1.csv`, instead of reading its `WorkerResult`).
- Checks: `python -m pytest tests/test_scenarios.py::test_broken_pool_drain_keeps_finished_sibling_job -q`
  → 1 failed in 9.26 s.
- Files changed: `tests/test_scenarios.py`.
- Previous commit: `fa4e812`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 15/N — rework round 3: fix (green)
- `spyswat/swat_calib/scenarios/batch.py` (items 1-2 of the Round 4 correction):
  1. **Broken-pool drain reads `fut.result()`** — the drain loop now inspects each remaining
     future's result: a returned `WorkerResult` goes through `_record_result` (an `ok` job
     stays `ok` and its `series/<job>.csv` is kept), `BrokenProcessPool` records `failed`
     with `broken_err`, and any other exception becomes `WorkerResult(False, ...)` through
     `_record_result` — the same classification as the main harvest loop.
  2. **Minor 1** — `_dispatch` declares `nonlocal results_since_save`; an overlay `OSError`
     now also does `results_since_save += 1` and logs the `%d/%d jobs done` progress line.
- GREEN: the new regression test passes; `pytest tests/test_scenarios.py -q` → 28 passed
  (27 + 1 new).
- Files changed: `spyswat/swat_calib/scenarios/batch.py`.
- Previous commit: `199e023`

## 2026-11-24 · opencode-go/deepseek-v4-pro (worker-strong) · step 16/N — rework round 3: verification
- `python -m pytest tests/ -q` → **355 passed / 11 skipped / 0 failed** (354 baseline + 1 new)
  in 176.84 s; 5 pre-existing warnings.
- `python -m pytest tests/test_scenarios.py -q` → **28 passed** three times in a row
  (92.69 s, 92.85 s, 94.41 s) — timing, broken-pool and drain tests stable.
- `git diff --check main...HEAD` → clean; `git status` clean after commit.
- Product diff (tests excluded): `batch.py` +13/-4 (items 1-2 only).
- Files changed this rework: `spyswat/swat_calib/scenarios/batch.py`,
  `tests/test_scenarios.py`, `.agents/reviews/PAR-1-3.md` (committed unchanged),
  `.agents/decisions/PAR-1.md` (Round 4 correction, committed unchanged),
  `.agents/log/PAR-1.md`.
- Done. No `agm send` / `hc send` per the rework instructions; pointer for the manager:
  branch `feat/PAR-1` at `9dfbbbf`. Items 1-3 of the Round 4 correction implemented and
  verified; nothing else changed.
- Previous commit: `9dfbbbf`
