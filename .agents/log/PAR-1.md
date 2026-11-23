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
