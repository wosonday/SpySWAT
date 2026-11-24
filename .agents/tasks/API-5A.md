---
id: api-5a
branch: feat/api-5a
tier: strong
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-5a: resume by replay — cursor, manager and algorithms (facade wiring is API-5b)

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` — "Resume by replay" and decision 9.
Builds on merged `SessionStore` (`open`, `runs()`, `series()`, `site_metrics()`, torn-tail handling),
`CalibrationManager` (`store`, `run_ids`, `is_initial`), algorithms with resolved `seed`, and the facade (API-4).


**Split (CEO):** this task (5a) builds Build §1, §2 and the algorithm forwarding, and tests them by calling the
algorithms directly with a real `SessionStore` + `ReplayCursor` (open the store, build the cursor, call
`<Algo>.run(..., store=store, replay=cursor, seed=<stored seed>)`). Build §3 (facade `project.calibration(resume=True)`)
and the facade-specific criteria (seed=None through the facade, FileNotFoundError/FileExistsError from the facade,
signature/param-order checks in the facade) are API-5b: do NOT edit `spyswat/swat_project.py`. Implement the
parameter-order check as a reusable function in `replay.py` (`check_param_order(store, param_ranges)`), which 5b calls.
Issue 1 of the corrections (raw params in the store) is already fixed on main (API-2d).

## Build
1. `spyswat/swat_calib/calibration/replay.py`:
   - `class ResumeMismatchError(ValueError)`.
   - `class ReplayCursor` built from an opened `SessionStore`: stored runs ordered by `run_id` (contiguous from the
     first id; a gap → ResumeMismatchError). `take(param_sets: list[dict]) -> list[StoredRun | None]` consumes the
     cursor in order: entry k of the new execution is compared to stored row k (same parameter order as
     `session.json` `param_names`; canonical floats `0.0 if v == 0 else float(v)`; exact equality) → `StoredRun`
     (run_id, params, status, error, score, is_initial, per-site metric columns) or `None` once the cursor is
     exhausted; a mismatch → `ResumeMismatchError` naming run id, parameter, stored and new values.
     `remaining` property; `next_run_id` = last stored id + 1.
2. `CalibrationManager.run_batch` / `run_iteration` accept `replay: ReplayCursor | None`. For each submitted
   parameter set (submission order), a stored run is returned from the cursor **without running SWAT and without
   `store.add_run`**; only the remaining sets run (in one parallel batch, same order) and are stored with run ids
   continuing from `next_run_id`. The returned DataFrame/score is identical to an uninterrupted run (same columns,
   same values, same order; failed stored runs stay failed with NaN score).
3. Facade `project.calibration(..., session=<existing>, resume=True)`:
   - `SessionStore.open`; when the caller's `seed` is None use the stored seed; build the signature exactly as on
     creation and `check_signature` (ValueError listing differences, e.g. changed `param_ranges`).
   - Pass a `ReplayCursor` to the algorithm run; when the algorithm finishes, the result is built as in API-4.
   - Remove the API-4 `NotImplementedError`. `resume=False` on an existing session still raises FileExistsError.
4. Interruption: the facade closes the store in `finally` (flush), so a `KeyboardInterrupt`/exception mid-batch
   leaves only fully committed runs; the next resume replays them.

## Files in scope
`spyswat/swat_calib/calibration/replay.py` (new), `spyswat/swat_calib/calibration/calib_manager.py`,
`spyswat/swat_calib/analysis/algorithms/{glue,pso,parallel_de,dds}.py` (each accepts keyword-only `replay=None` and forwards it),
`tests/test_resume_replay.py` (new), `.agents/log/API-5.md`.

## Acceptance criteria
- [ ] For each of `glue`, `pso`, `de`, `dds` (tiny sizes, fake runner, fixed seed, including multi-site + multiple `metrics`): reference full run vs. run interrupted after `k` evaluations (fake runner raises `KeyboardInterrupt` at call `k+1`, testing mid-chunk in GLUE and mid-iteration in PSO/DE) then resumed → identical `best_params`, `best_score`, `runs` DataFrame (including `<m>@<var>@<reach>` columns), exact `runs.csv` cell strings excluding `time`, contiguous `run_id`s `1..N`, and fake runner called `N - k_committed` times on resume.
- [ ] Resuming an already-completed session (`k_committed == N`) makes `0` runner calls and returns identical results; resuming a session with `0` committed runs starts at `run_id = 1` and runs all `N`.
- [ ] `seed=None` first run + resume with `seed=None` → identical final result to an uninterrupted run using the stored seed; resume with a different explicit `seed` → `ValueError`.
- [ ] Failed runs: stored failed run in `run_batch` replays with `NaN` score/metrics (not retried); in `dds`, `on_failure="penalize"` replays stored failed run as `NaN` and finishes identically to uninterrupted run, while `on_failure="raise"` re-raises `RuntimeError` without retrying.
- [ ] Validation & integrity: changed `param_ranges` or reordered `param_ranges` keys → `ValueError` (without rewriting session files); `resume=True` on missing session → `FileNotFoundError`; `resume=False` on existing session → `FileExistsError`; tampered param, `-0.0` mismatch test (`-0.0 == 0.0` passes), `run_id` gap/duplicate/non-1 start → `ResumeMismatchError`; torn tail (extra uncommitted `run_id`s in series/metrics CSVs) is ignored and overwritten on resume.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider` pass (record counts); `git diff --check` clean.


## Report
Append to `.agents/log/API-5.md`: files changed, commands + result lines, open questions. Commits `api-5:`.

## Binding corrections from the Neon pre-review (apply all; issue 1 is already fixed on main by API-2d)

1. **`CalibrationManager` writes formatted param tuples to `SessionStore`, breaking `open()`/`runs()` and replay**
   `_run_iteration_multi` and `_run_batch_multi` pass formatted `{name: [(val, method[, subs])]}` dicts to `store.add_run`. `SessionStore._fmt_float` falls back to `str(value)` (`"[(75.0, 'v')]"`), so `SessionStore.open()` and `store.runs()` crash in `_parse_float` with `ValueError`. Likewise, `GLUE`/`PSO`/`DE` pass pre-formatted dicts to `run_batch`.
   - **Spec correction:** Add to Build §1–2: extract raw `{name: float}` from formatted param dicts (when `not is_raw(p)`) in `CalibrationManager` before both `store.add_run(...)` and `replay.take(...)` (and have `ReplayCursor.take` accept raw `{name: float}` or unwrap formatted entries).

2. **Failed runs vs. interruption semantics are broken in `run_iteration` (DDS) and in the test plan**
   In `_run_iteration_multi`, `except Exception` commits the run as `status="failed"` before raising `RuntimeError`; in `_run_batch_multi`, worker `Exception`s become `res.ok=False` rows without aborting. Raising a normal `Exception` at call `k+1` will therefore commit a failed run (DDS) or not interrupt (GLUE/PSO/DE), so resume can never match the reference run. Also, on replay, `run_iteration` returning `NaN` vs. raising `RuntimeError` differs from an uninterrupted failed run.
   - **Spec correction:** In Build §2, distinguish `run_batch` vs. `run_iteration` on stored `status == "failed"`: `run_batch` returns a row with `score=NaN` and `NaN` per-site metrics; `run_iteration` raises `RuntimeError` (matching uninterrupted runs so `DDSCalibration` aborts on `on_failure="raise"` and catches+penalizes to `NaN` on `on_failure="penalize"`), without touching `_backup_state`/`run_once`/`_restore_state`. In Acceptance Criteria, simulate interruption with `KeyboardInterrupt` (a `BaseException`) so run `k+1` is not committed as failed.

3. **Non-monotonic / colliding `run_id`s across multi-batch calls (PSO/DE/DDS) and empty sessions**
   `CalibrationManager._store_counter` starts at `0` on resume. A static `next_run_id = last stored id + 1` fails when 0 runs are committed (no last id) and causes duplicate `run_id`s on subsequent `run_batch`/`run_iteration` calls after the cursor is exhausted. Also `_new_path()` does not check `replay is not None`, so a bare-`Series` caller passing `replay` without `store` silently drops into the legacy single-site path.
   - **Spec correction:** In Build §1, define `next_run_id = 1` when 0 runs are stored, else `last_id + 1`. In Build §2, add `replay is not None` to `_new_path()`, and synchronize `self._store_counter = max(self._store_counter, replay.next_run_id - 1)` before allocating ids for live runs across all subsequent `run_batch`/`run_iteration` calls.

4. **Signature check misses `param_ranges` key order, `seed` resolution order, and mutates disk on mismatch**
   `SessionStore.check_signature` uses `json.dumps(..., sort_keys=True)`, so reordered `param_ranges` keys pass `check_signature` even though every algorithm iterates `list(bounds.keys())` in insertion order (breaking RNG determinism). Also, if `store = SessionStore.open(...)` is inside `try ... finally: store.close()`, a failed `check_signature` still calls `flush()`, which rewrites all CSVs whenever `self._runs` is non-empty.
   - **Spec correction:** In Build §3: (a) open `SessionStore` first, resolve `seed = store.signature["seed"]` **only** when caller's `seed is None` (keep explicit `seed` so mismatches fail `check_signature`, and fail if stored seed is missing); (b) include ordered `param_names` (as a `list`) in the signature or assert `list(bounds.keys()) == store.param_names` (`ValueError`); (c) run `check_signature` before entering the `try ... finally: store.close()` block.

5. **`ReplayCursor` contiguity, `StoredRun.site_metrics` contract, and all-replayed batch handling**
   "Contiguous from the first id" accepts `[2, 3]` (missing run 1) or unsorted/duplicate ids. `StoredRun`'s "per-site metric columns" is underspecified relative to `_build_multisite_row`, which expects `{(var, reach): {"<m>_calib": float}}`. And `_run_batch_multi` must skip `WorkingFolder`/`run_parallel`/queue listener (and avoid `0/0`) when an entire batch is replayed.
   - **Spec correction:** In Build §1: require stored `run_id`s to be exact `1..k` (no gaps, duplicates, or non-1 start; empty `[]` valid); check key-set/order match and `-0.0 -> 0.0` on both sides before advancing cursor; populate `StoredRun.site_metrics` from `store.site_metrics(var, reach)` (handling missing/empty metrics CSVs when all runs failed). In Build §2: when 0 live runs remain in `run_batch`, bypass `WorkingFolder`, `run_parallel`, and log queue setup.

6. **All four algorithm files must forward `replay` (not optional); note `GLUE.uncertainty_band`**
   `glue.py`, `pso.py`, `de.py`, and `dds.py` none accept `replay` yet—every one must accept keyword-only `replay=None` and pass it through to `run_batch`/`run_iteration`. Note `GLUE.uncertainty_band` (`compute_uncertainty=True`) runs `run_once` outside `store`/`replay`.
   - **Spec correction:** Replace "algorithm files only if they need to forward `replay`" with explicit scope: `glue.py`, `pso.py`, `de.py`, `dds.py` each accept `replay=None` and forward it to `CalibrationManager`.

7. **`runs.csv` byte-equality criterion is nondeterministic due to the `time` column**
   `SessionStore.add_run` stamps `time = datetime.now().isoformat(timespec="seconds")`, so reference vs. resumed `runs.csv` bytes differ whenever execution crosses a second boundary.
   - **Spec correction:** Compare `runs.csv` parsed via `csv.reader` with the `time` column excluded (exact cell-string equality on `run_id`, `status`, `error`, `is_initial`, all parameter `repr`s, and `score`), or freeze timestamps in the test.

**Update (CEO, after API-4/6 merged into this branch):** the facade (`project.calibration`) now exists on this branch; still do NOT edit `spyswat/swat_project.py` (API-5b). Also apply these two Minors from review API-4-3 inside `replay.py`/tests only if they concern replay; otherwise leave them to API-5b.
