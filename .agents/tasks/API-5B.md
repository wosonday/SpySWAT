---
id: api-5b
branch: feat/api-5b
tier: strong
skills: test-driven-development
docs_impact: yes   # README calibration sentence + CHANGELOG (small; included here)
gitnexus: none
---

# API-5b: resume through the facade + replay follow-ups (final task of 0.3.0)

Read `.agents/tasks/API-5A.md` (Build §3 and the binding corrections 3, 4 and the facade-related acceptance
criteria) — those are this task. Builds on merged `replay.py` (`ReplayCursor`, `ResumeMismatchError`,
`check_param_order`) and the facade in `spyswat/swat_project.py`.

## Build
1. `project.calibration(..., session=<existing>, resume=True)`:
   - open the store with `SessionStore.open` **before** the `try/finally` that closes it; when the caller's `seed`
     is None use the stored seed (stored seed missing → ValueError); an explicit different seed → ValueError via
     the signature check; `check_param_order(store, param_ranges)`; rebuild the signature exactly as on creation
     and `check_signature` — all of this before any file is rewritten;
   - build a `ReplayCursor` and pass `replay=` to the algorithm; then finish exactly as a fresh run
     (best, `evaluate`, regression sensitivity, `best.csv`, `sensitivity.csv`);
   - `resume=True` on a missing session folder → FileNotFoundError; `resume=False` on an existing one →
     FileExistsError (keep); remove the API-4 `NotImplementedError`.
2. Review API-4-3 Minors: `CalibrationResult.select()` keeps only `status == "ok"` rows when a `status` column
   exists; `_hash_observed` uses little-endian float64 (`"<f8"`) and normalises `-0.0` to `0.0`.
3. Review API-5A-1 Minors (all four): `ReplayCursor.take` validates the whole batch before advancing; `run_ids`
   length checked against the total and sliced for live runs; remove the unused import; strengthen the mismatch
   test message assertions, fix the misleading comment, add the three edge-case tests listed there.
4. Docs: in `README.md` and `README_VI.md` replace the "planned in 0.3.0 (API-5)" resume sentence in the
   calibration section by the final description (how to resume: same `session=`, `resume=True`; what must match;
   `seed=None` uses the stored seed); in `CHANGELOG.md` move resume from "planned" to "Added".

## Files in scope
`spyswat/swat_project.py`, `spyswat/swat_calib/calibration/{result,replay,calib_manager}.py`,
`tests/test_project_facade.py`, `tests/test_resume_replay.py`, new `tests/test_facade_resume.py`,
`README.md`, `README_VI.md`, `CHANGELOG.md`, `.agents/log/API-5B.md`.

## Acceptance criteria
- [ ] Facade end-to-end with a fake runner for glue, pso, de, dds: interrupt (fake runner raises
      `KeyboardInterrupt` at call k+1), then `project.calibration(..., session=same, resume=True)` → identical
      `best_params`, `best_score`, `runs` (excluding `time`), runner called N − k_committed times; completed session
      resumed → 0 runner calls; `seed=None` both times → identical to the stored-seed run; different explicit seed,
      changed or reordered `param_ranges`, changed observed data → ValueError and session files unchanged (hash
      compare); missing session → FileNotFoundError.
- [ ] Items 2 and 3 tested as listed.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider` and `-W error::DeprecationWarning:spyswat` pass (record
      counts; main baseline 701 passed, 15 skipped); harness lint 0 errors; `git diff --check` clean.

## Report
Append to `.agents/log/API-5B.md`: files changed, commands + result lines, open questions. Commits `api-5b:`.
