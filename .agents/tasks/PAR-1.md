---
id: par-1
branch: feat/PAR-1
tier: strong
skills: test-driven-development, verification-before-completion
docs_impact: yes
gitnexus: none
---

# PAR-1: ScenarioBatch keeps every worker slot busy (one pool, job queue)

Design and evidence: `.agents/decisions/PAR-1.md` (findings F1-F3, user answers 2026-11-23).
Model: `opencode-go/deepseek-v4-pro` (worker-strong). Interactive. Budget: one session plus
one rework round; `agm budget task:par-1` soft 4M / hard 8M tokens.

## Goal
`ScenarioBatch.run()` runs the whole job list on one process pool: a slot that finishes takes
the next job at once. No barrier between chunks or between base TxtInOut groups. The public
API, the files written (`summary.csv`, `metrics.csv`, `series/<job>.csv`, `.signature.json`),
resume, and per-job failure isolation stay exactly as today.

## Design (approved by the user)
1. **Slots.** At most `n_parallel` worker folders `_scenario_batch/TxInOut{i}`. The parent
   tracks per slot: the base it currently holds (or none) and whether it is unusable.
2. **Dispatch.** When a slot is free, give it the next pending job (plan order) **with the
   same base** as the slot; if none, the first pending job of any base, and the slot is
   reseeded for that base. Never more than `n_parallel` jobs running.
3. **Reseed in the worker process, not the parent.** A new module-level (picklable) function,
   e.g. `_seed_and_run(slot_dir, base_dir, reseed, *job_args)`: if `reseed`, remove the slot
   folder and `copytree` the base with the existing output-ignore rule, then call the
   unchanged `_worker_job(...)`. It never raises (returns `WorkerResult(ok=False, ...)`).
   Copies of different slots therefore run in parallel.
4. **After a failed job** the slot is reseeded before its next job. If removing the folder
   fails (locked by an orphan swat.exe), the slot becomes unusable. If every slot is
   unusable, every remaining job fails with one explicit English message.
5. **Bad base.** If seeding fails for a base (missing folder, copy error), mark the base bad:
   its remaining jobs fail with the same `setup of <base> failed: ...` text used today; other
   bases continue.
6. **Saving.** Save `metrics.csv` then `summary.csv` (existing `save()` and its locked-file
   handling) when at least `n_parallel` results arrived since the last save or 10 s passed,
   and always at the end. On `KeyboardInterrupt`: cancel pending futures, save the finished
   rows, re-raise.
7. One `ProcessPoolExecutor(max_workers=n_slots)` for the whole call; `prepare`/`extract`
   partials built per job (keyed by that job's slot dir). `_worker_job` and
   `WorkingFolderManager.run_parallel` are **not** changed (calibration uses them).

## Files in scope
- `spyswat/swat_calib/scenarios/batch.py`
- `spyswat/swat_calib/scenarios/scheduler.py` (new, optional: slot/dispatch logic)
- `tests/test_scenarios.py`, `tests/test_scenario_scheduler.py` (new)
- `.agents/log/PAR-1.md`; commit `.agents/tasks/PAR-1.md` and `.agents/decisions/PAR-1.md`
  unchanged in the first commit.

Anything else (incl. `core/workingFolder_manager.py`, F4-F6, docs) is out of scope: propose it
in the log. Import private helpers from `workingFolder_manager.py` instead of editing it.

## Constraints
- Design rules in `AGENTS.md` (5, 9, 11): module-level picklable workers, `__main__` guard
  check kept, failing job never raises, atomic CSV writes.
- Do not loosen or skip existing tests; keep the TEST-1 per-worker trace files.
- Tests use the fake `runner` only (no SWAT exe, no real data). Runtime messages in English.
- Timing tests assert on recorded start/end timestamps (overlap), not on wall-clock totals.

## Acceptance criteria
- [ ] RED first: new tests fail on `main` (record the failure lines in the log).
- [ ] 2 bases x 2 parameter sets, `n_parallel=4`: all 4 jobs overlap in time.
- [ ] No barrier: `n_parallel=2`, one job 3x longer than three others: the short jobs all
      run on the other slot while the long one is still running.
- [ ] Reseed: a slot switching from base A to base B sees only B's files (marker file per
      base checked by the runner); `r`/`a` changes never compound.
- [ ] Bad base: its jobs `failed` with the setup message, other base's jobs `ok`.
- [ ] Existing `tests/test_scenarios.py` unchanged in its assertions and green 3 runs in a row.
- [ ] `python -m pytest tests/ -q`: 0 failed (baseline on main: 336 passed, 11 skipped;
      record counts). `git diff --check main...HEAD` exits 0.
- [ ] Product diff under ~400 lines (tests excluded); log lists every file changed.

## Report format
`agm send` to the CEO terminal: 1-3 lines pointing to `.agents/log/PAR-1.md` (files changed,
commands with counts, open questions). Then stop.
