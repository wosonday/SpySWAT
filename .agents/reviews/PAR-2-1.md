# Review PAR-2 round 1 — Architect pre-review (before the formal Reviewer)

- Reviewer: Architect / BOT-CEO (Claude Opus 5.5), pre-review of `feat/PAR-2` at 25731a8.
- Read: `git diff main...HEAD`, `.agents/tasks/PAR-2.md`, `.agents/log/PAR-2.md`.
- Scope check: 5 files, all in scope; `batch.py` touched only in the 4 allowed places;
  `git diff --check main...HEAD` exit 0.

## Verdict: FAIL (1 Major)

### Major 1 — a missing scenario base now aborts the whole batch

- Location: `spyswat/swat_calib/scenarios/signature.py:19` (`os.scandir`), called from
  `scenarios/batch.py:378` while building `new_sig`, before any job runs.
- Evidence: `txinout_fingerprint(<missing dir>)` raises `FileNotFoundError` (probe run by the
  Architect). On `main`, a scenario whose `txinout_dir` is missing only fails **its own** jobs
  with `setup of <base> failed: ...` and the other scenarios run (design rule 5: failures stay
  per job). `feat/PAR-1` adds `test_bad_base_fails_its_jobs_others_ok`, which will fail once
  both branches are merged.
- Fix:
  1. `txinout_fingerprint` never raises for an unreadable directory: on `OSError` return a
     sentinel such as `"unreadable:<ExceptionName>"` (stable, so resume compares it like any
     other value).
  2. Add a test: a batch with one good scenario and one scenario whose `txinout_dir` was
     deleted runs, the good jobs are `ok`, the bad jobs are `failed` with `setup of` in the
     error (same as `main`).
  3. Add a unit test for the sentinel.

No other findings. Commit this file unchanged with the fix (`par-2:` prefix).
