# Review PAR-2 round 2 — PASS (0 Major, 2 Minor, no rework required)

- Reviewer: `gemini-4-hydrogen-high` via `agy --mode plan --sandbox` (independent, different family from the DeepSeek authors), static read-only review of a file snapshot; saved verbatim by the Architect (local paths stripped).
- Input: trial merge `c4cf3ec` = main 12181ef + feat/PAR-1 2f6ef4a + feat/PAR-2 1ca47c0. Line numbers of `batch.py` refer to that merged tree; `PAR-1.diff`/`PAR-2.diff` = `git diff main...<branch>`.
- Architect check: Major 1 matches the Architect pre-review; Major 2 verified by grep (`sched.mark_base_bad` is never called from `batch.py`).

## Review Summary (`c4cf3ec`)

- **PAR-1 (`feat/PAR-1`, `2f6ef4a`)**: **FAIL** (3 Major, 4 Minor)
- **PAR-2 (`feat/PAR-2`, `1ca47c0`)**: **PASS** (0 Critical, 0 Major, 2 Minor)

> **Scope & Uncertainty Note:** This is a static read-only review; no commands or tests were executed. Test counts (`PAR-1`: 347 passed / 11 skipped; `PAR-2`: 432 / 11; merged: 443 / 11) come from the coordinator prompt and `.agents/log/PAR-1.md` / `.agents/log/PAR-2.md`. Base `tests/test_scenarios.py` (pre-diff) and `spyswat/swat_calib/core/run_state.py` are not present in this folder, so pre-existing `r`/`a` non-compounding coverage and `run_state.py` internals are not directly verified.

---

## Branch 1: PAR-1 (`feat/PAR-1`) — **VERDICT: FAIL**

### Acceptance Criteria & Design Checklist
- **RED first**: Verified in `.agents/log/PAR-1.md:30-43` (`ModuleNotFoundError` for `scheduler` and two timestamp failures on `212cc06`).
- **2 bases × 2 sets, `n_parallel=4` overlap**: Proven by `test_all_jobs_overlap_across_two_bases` in `PAR-1.diff:927-942`.
- **No barrier**: Proven by `test_no_barrier_short_jobs_flow_while_long_runs` in `PAR-1.diff:945-963` (see Minor 4 on timing margin).
- **Reseed on base switch / `r`/`a` non-compounding**: Base-switch marker isolation is proven by `test_reseed_on_base_switch_sees_only_that_bases_files` (`PAR-1.diff:966-984`). `_seed_and_run` and `_worker_job` restore from `base_dir`, preventing `r`/`a` compounding, though post-failure reseed and `r`/`a` non-compounding in the new loop are not directly tested by the new tests (see Major 3).
- **Bad base**: Proven by `test_bad_base_fails_its_jobs_others_ok` (`PAR-1.diff:987-999`), though internal drain bookkeeping is broken (see Major 2).
- **Windows spawn / picklability (Rule 11)**: `_seed_and_run`, `_prepare_dispatch`, `_extract_dispatch`, `WorkerResult`, and `partial(...)` payloads are module-level/picklable, and `multiprocessing.parent_process() is not None` guard is preserved (`spyswat/swat_calib/scenarios/batch.py:373-376`).
- **Pool shutdown & saving on every exit path**: **Fails** on non-`KeyboardInterrupt` exceptions (Major 1).
- **Deterministic output files**: `series/<job_id>.csv` writes via per-PID `.tmp` + `_replace_retry`; `summary.csv` sorts rows by `job_order`; `metrics.csv` sorts by `job_order` on normal exit (not on `KeyboardInterrupt` / periodic save — Minor 1).
- **Product diff size**: 409 lines vs `~400` soft target (Minor 2, disclosed in log).

### Findings (PAR-1)

#### Major 1 — Process pool is not shut down and finished rows are not saved on non-`KeyboardInterrupt` exceptions
- **Location:** `PAR-1.diff:661-666` (merged `spyswat/swat_calib/scenarios/batch.py:670-675`); calls inside `try:` at `spyswat/swat_calib/scenarios/batch.py:598` and `spyswat/swat_calib/scenarios/batch.py:609`.
- **Evidence:** Unlike `WorkingFolderManager.run_parallel` (`spyswat/swat_calib/core/workingFolder_manager.py:401-405`), `ScenarioBatch.run` only catches `except KeyboardInterrupt:`. If any other exception is raised inside `try:` — for example:
  1. A worker crashes so `fut.result()` (`spyswat/swat_calib/scenarios/batch.py:656-659`) catches `BrokenProcessPool`, records that job failed, and `_dispatch(slot_idx)` (`spyswat/swat_calib/scenarios/batch.py:664`) then calls `executor.submit(...)` (`spyswat/swat_calib/scenarios/batch.py:609`) on the broken pool, raising `BrokenProcessPool`;
  2. `Path(wd).iterdir()` (`spyswat/swat_calib/scenarios/batch.py:598`) raises `OSError` if a `weather_dir` becomes unavailable; or
  3. `SystemExit` occurs —
  `executor.shutdown(...)` is skipped (leaking Windows spawned processes/manager thread) and `save(final=True)` is skipped (losing finished rows since the last periodic save).
- **Concrete fix:** Replace `except KeyboardInterrupt:` with `except BaseException:`:
  ```python
  except BaseException:
      executor.shutdown(wait=False, cancel_futures=True)
      save(final=True)
      raise
  else:
      executor.shutdown(wait=True)
  ```

#### Major 2 — `sched.mark_base_bad(base)` is never called, leaving `Scheduler.drain_bad_base_jobs()` dead in `batch.py`
- **Location:** `PAR-1.diff:488-495`, `PAR-1.diff:542-544` (merged `spyswat/swat_calib/scenarios/batch.py:574-581`, `spyswat/swat_calib/scenarios/batch.py:628-630`); `spyswat/swat_calib/scenarios/scheduler.py:82-89`.
- **Evidence:** `_mark_base_bad` adds `base` to the local `bad_bases` set in `run()`, but never calls `sched.mark_base_bad(base)`. Consequently `sched._bad_bases` remains empty and `sched.drain_bad_base_jobs()` (`spyswat/swat_calib/scenarios/batch.py:629`) always returns `[]`. Remaining bad-base jobs stay in `sched._pending` until `_dispatch()` pops them via `sched.take()` (mutating `slot.base` to the bad base before failing them in `if base in bad_bases:`).
- **Concrete fix:** Call `sched.mark_base_bad(base)` inside `_mark_base_bad`, and use `sched.is_base_bad(base)` instead of maintaining a duplicate `bad_bases` set (and update `results_since_save` / progress if drained via `drain_bad_base_jobs()`).

#### Major 3 — Integration tests do not cover exit-path saving/shutdown, post-failure reseed, or unusable/locked slots
- **Location:** `PAR-1.diff:927-999`; requirements in `.agents/tasks/PAR-1.md:33-42` and `.agents/decisions/PAR-1.md:78-80`.
- **Evidence:** The 4 new `tests/test_scenarios.py` integration tests only exercise normal overlap, no-barrier flow, base-switch reseed, and bad-base failure. No `ScenarioBatch.run` test exercises:
  1. `KeyboardInterrupt` or other exception mid-batch (cancelling futures, shutting down pool, saving finished rows so `resume=True` skips them);
  2. A failed job forcing `reseed=True` on the same base+slot (verifying artifacts left by the failed job do not leak to the next job); or
  3. Locked slot (`_SLOT_LOCKED_PREFIX` -> slot marked unusable, remaining jobs continue on other slots or fail with `_ALL_UNUSABLE_MSG`).
- **Concrete fix:** Add integration tests in `tests/test_scenarios.py` for (a) mid-batch `KeyboardInterrupt` and non-`KeyboardInterrupt` exception saving finished rows + resuming, (b) failed-job reseed isolation on the same base, and (c) locked-slot / all-slots-unusable handling.

#### Minor Findings (PAR-1)
- **Minor 1 (`metrics.csv` order on interrupt/periodic save):** `spyswat/swat_calib/scenarios/batch.py:670-681`. `summary.csv` is sorted by `job_order` inside `save()`, whereas `metrics_df` is only sorted after the `try/except/else` block (`batch.py:677-680`). Interrupted or periodic saves write `metrics.csv` in completion order. Fix: sort `metrics_df` by `job_order` inside `save()` before writing.
- **Minor 2 (Product diff size):** `.agents/log/PAR-1.md:98-100`. Product diff is 409 lines vs `~400` target in `.agents/tasks/PAR-1.md:75` (acceptable, already flagged in log).
- **Minor 3 (Pool started when `todo` is empty):** `spyswat/swat_calib/scenarios/batch.py:583-675`. When `resume=True` skips all jobs (`todo == []`), `ProcessPoolExecutor` is still constructed and shut down. Fix: guard the pool block with `if todo:`.
- **Minor 4 (Tight timing margin in no-barrier test):** `PAR-1.diff:880`, `PAR-1.diff:945-963`. Three sequential 0.6 s jobs on slot 1 give ~1.2 s + overhead before the 3rd starts vs `long_end` at ~1.8 s (~0.6 s margin). Fix: make the long job ~2.4 s (or short jobs 0.4 s) for extra CI headroom.

---

## Branch 2: PAR-2 (`feat/PAR-2`) — **VERDICT: PASS**

### Acceptance Criteria & Design Checklist
- **Scope & constraints**: Only `signature.py`, `tests/test_scenario_signature.py`, `.agents/*` (incl. `PAR-2-1.md` committed unchanged), and the 4 allowed locations in `batch.py` (`import`, `_signature_diff`, `new_sig`, `merged`) were modified (`PAR-2.diff:300-346`); `workingFolder_manager.py` and `tests/test_scenarios.py` are untouched.
- **RED first**: Recorded in `.agents/log/PAR-2.md:26-54` and `.agents/log/PAR-2.md:135-159`.
- **Fingerprint behavior**: `spyswat/swat_calib/scenarios/signature.py:18-46` hashes sorted `(name, size, st_mtime_ns)` for regular files directly in `directory`, excluding `_OUTPUT_IGNORE(str(folder), names) | {MANIFEST_NAME}`. Proven by `test_fingerprint_changes_on_added_removed_resized_and_rewritten_inputs` (using `os.utime(..., ns=...)`, no sleep) and `test_fingerprint_ignores_swat_outputs_and_manifest` (`PAR-2.diff:435-464`).
- **Failure isolation (round-1 rework)**: Missing/unreadable directory returns `"unreadable:<ExceptionName>"` instead of aborting `new_sig` (`spyswat/swat_calib/scenarios/signature.py:41-44`); proven by `test_fingerprint_of_a_missing_directory_is_a_stable_sentinel` and `test_missing_scenario_base_fails_only_its_own_jobs` (`PAR-2.diff:467-490`).
- **Resume & backwards compatibility**: `resume=True` raises `ValueError` naming the scenario for both `txinout_dir` and `project.txinout` (`txinout_dir=None`), `resume=False` re-runs, 0.2.6 `.signature.json` without `scenario_inputs` resumes with 1 INFO log, and absent scenario names retain their stored fingerprint in `merged` (`PAR-2.diff:493-554`).
- **Merged tree compatibility**: Merged cleanly with PAR-1 in `spyswat/swat_calib/scenarios/batch.py:283-290` and `spyswat/swat_calib/scenarios/batch.py:428-454`.

### Findings (PAR-2)

- **Minor 1 (Extra `os.stat` syscall per file):** `spyswat/swat_calib/scenarios/signature.py:21-28`. `_input_stats` collects `names` from `os.scandir` and then calls `os.stat(folder / name)` again for each non-ignored file. Reusing `entry.stat()` from `scandir` avoids the second syscall on Windows (still stats-only, so impact is negligible).
- **Minor 2 (INFO log emitted even when `resume=False`):** `spyswat/swat_calib/scenarios/batch.py:284-286`, `spyswat/swat_calib/scenarios/batch.py:440`. Because `_signature_diff` is also called when `resume=False`, running `resume=False` against a 0.2.6 `.signature.json` still logs `"cannot verify that scenario TxtInOut inputs are unchanged..."`. Harmless; no rework needed.

---

> Note: `.agents/tasks/PAR-1.md` and `.agents/tasks/PAR-2.md` both carry `docs_impact: yes` (see also `.agents/log/PAR-2.md:107-111` for `README.md` resume notes) — schedule the Docs Updater (`docs-hyd`) once PAR-1 rework passes review.
