---
id: fix-1
branch: feat/fix-1
tier: fast
skills: test-driven-development
docs_impact: yes
gitnexus: none
---

# FIX-1: ScenarioBatch worker logging (F5) and per-batch work dir (F6)

Findings F5/F6 in `.agents/decisions/PAR-1.md`. Written by the CEO (Codex Manager unavailable).

## Goal
1. **F5** — `ScenarioBatch.run()` submits jobs with `log_queue=None`, so worker log records are lost
   on Windows (spawned children have no handler). Add a keyword argument `log_queue=None` to
   `ScenarioBatch.run()`. When it is `None`, use `Logger._log_queue` (the queue of an already
   running listener, may also be `None`). Pass it to every `executor.submit(...)` of `_run_job`
   (currently the literal `None` near `batch.py:622-625`).
   Do **not** start a listener inside `run()`.
2. **F6** — the work dir is fixed: `Path(proj.working_folder) / WORK_SUBDIR`. Two batches on the
   same project with different `results_dir` overwrite each other's slot folders. Make it
   `Path(proj.working_folder) / WORK_SUBDIR / <key>`, where `<key>` = first 10 hex chars of
   `sha1(str(Path(results_dir).resolve()).lower())`. Same `results_dir` → same work dir
   (resume keeps working). Update the class docstring (around `batch.py:260`) accordingly.

## Files in scope
- `spyswat/swat_calib/scenarios/batch.py`
- `tests/test_scenarios.py` (add tests; do not weaken existing ones)
- `.agents/log/FIX-1.md` (append-only)

Anything else is out of scope: propose it in the log.

## Constraints
- AGENTS.md key design rules (11: picklable, module-level callables; 12: English messages).
- No new dependencies. Keep `WORK_SUBDIR` constant name.

## Acceptance criteria
- [ ] Test: `run(..., log_queue=q)` passes `q` to every submitted job (fake/mocked executor or
      runner is fine; tests must not need a SWAT exe).
- [ ] Test: with `log_queue` omitted and `Logger._log_queue` set, that queue is passed.
- [ ] Test: two `ScenarioBatch` objects with different `results_dir` on the same project get
      different work dirs; the same `results_dir` gets the same one.
- [ ] `python -m pytest tests/test_scenarios.py tests/test_scenario_scheduler.py -q` passes, then
      `python -m pytest tests/ -q` passes (record counts; baseline 451 passed, 11 skipped).
- [ ] `git diff --check` clean.

## Report format
Append to `.agents/log/FIX-1.md`: files changed, commands run with counts, open questions.
Commit messages start with `fix-1:`.
