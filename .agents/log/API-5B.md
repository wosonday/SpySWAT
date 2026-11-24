# API-5B — resume through the facade + replay follow-ups

Final task of 0.3.0. Implements the facade resume (`project.calibration(..., session=<existing>,
resume=True)`), the API-4-3 Minors, and the API-5A-1 Minors; finalises the resume docs.

## Files changed
- `spyswat/swat_project.py`
  - `calibration()` restructured: session resolution (fresh vs. resume), `SessionStore.open`
    **before** the `try/finally` that closes it; `seed=None` uses the stored seed (ValueError when
    the stored seed is missing); explicit different seed → ValueError via `check_signature`;
    `check_param_order(store, param_ranges)`; signature rebuilt exactly as on creation and
    `check_signature` — all before any file is rewritten; `ReplayCursor` built and `replay=`
    forwarded to the algorithm; finish (best, evaluate, regression sensitivity, `best.csv`,
    `sensitivity.csv`) identical to a fresh run.
  - `_resolve_session_dir` simplified (auto-name only); `resume=True` on a missing session →
    `FileNotFoundError`, `resume=False` on an existing one → `FileExistsError`; the API-4
    `NotImplementedError` removed.
  - `_hash_observed` uses little-endian `"<f8"` and normalises `-0.0` → `0.0` (API-4-3 Minor 2).
- `spyswat/swat_calib/calibration/result.py` — `select()` keeps only `status == "ok"` rows when a
  `status` column exists (API-4-3 Minor 1).
- `spyswat/swat_calib/calibration/replay.py` — `ReplayCursor.take` validates the whole batch before
  advancing `_pos` (API-5A-1 Minor 1).
- `spyswat/swat_calib/calibration/calib_manager.py` — removed unused `ReplayCursor` import
  (API-5A-1 Minor 3); `run_ids` length validated against `total` and sliced `[n_replayed:]` for
  live runs (API-5A-1 Minor 2).
- `tests/test_project_facade.py` — replaced `...resume_true_not_implemented` with
  `...resume_true_replays` (resume now works, no `NotImplementedError`); added
  `test_observed_hash_normalises_minus_zero` (API-4-3 Minor 2) and
  `test_select_drops_failed_even_with_finite_score` (API-4-3 Minor 1).
- `tests/test_resume_replay.py` — strengthened mismatch message assertions
  (`"CN2.mgt"` / `"50.0"` / `"99.0"`), fixed the mid-chunk comment, added three edge-case tests
  (formatted-dict unwrap in `take`, cursor non-advancement on batch mismatch, `replay` with
  `store=None`) (API-5A-1 Minor 4).
- `tests/test_facade_resume.py` (new) — facade end-to-end resume for glue/pso/de/dds, completed
  session → 0 runner calls, `seed=None` stored-seed, and the ValueError/FileNotFoundError matrix
  with session-file hash compare.
- `README.md`, `README_VI.md`, `CHANGELOG.md` — replaced the "planned in 0.3.0 (API-5)" resume note
  with the final description (how to resume, what must match, `seed=None` uses the stored seed).

## Commands + results
- `python -m pytest tests/test_facade_resume.py -q -p no:cacheprovider` → 11 passed
- `python -m pytest tests/test_resume_replay.py tests/test_project_facade.py -q -p no:cacheprovider` → 47 passed
- `python -m pytest tests/ -q -p no:cacheprovider -W error::DeprecationWarning:spyswat` → 717 passed, 15 skipped, 28 subtests
- `python -m pytest tests/test_harness_markdown.py tests/test_harness_routing.py tests/test_guardrail_examples.py tests/test_skill_routing.py -q -p no:cacheprovider` → 97 passed, 28 subtests (harness lint 0 errors)
- `git diff --check` → clean

## Open questions
- None.

## Rework round (API-5B-1 Minors)

All four review Minors fixed exactly as proposed, test-first.

### Files changed
- `spyswat/swat_project.py` — the missing-stored-seed error is now
  `"cannot resume: stored session.json has no seed"` (no misleading "pass seed= explicitly").
- `spyswat/swat_calib/calibration/result.py` — `select()` status mask is
  `runs["status"].eq("ok").fillna(False).to_numpy(dtype=bool)`, so a pandas nullable
  string `status` with `pd.NA` no longer raises `TypeError: boolean value of NA is ambiguous`.
- `tests/test_project_facade.py` — `test_select_handles_nullable_status_with_missing_values`
  (nullable `status` with a missing value).
- `tests/test_resume_replay.py` — `test_run_batch_run_ids_sliced_for_live_tail` (partial
  replay: one id per submitted set, live tail takes `run_ids[n_replayed]` → stored ids
  `[1, 2, 3]`) and `test_run_batch_run_ids_length_checked_against_total` (length mismatch →
  `ValueError`, no worker calls, nothing committed).
- `tests/test_facade_resume.py` — `test_facade_resume_seed_none_uses_stored_seed` rewritten:
  interrupt a `seed=None` run after 4 committed runs, read the stored seed, run an
  uninterrupted reference with that seed, resume with `seed=None`, compare
  `best_params`/`best_score`/`runs` and the live-call count; `sensitivity=True` on both runs
  verifies `res.sensitivity` and `sensitivity.csv` after resume. New
  `test_facade_resume_seed_none_without_stored_seed_raises` (session.json `seed: null` →
  `ValueError` matching the new message, session files unchanged).

### Commands + results (rework round)
- `python -m pytest tests/test_facade_resume.py tests/test_resume_replay.py -q` → 37 passed
- `python -m pytest tests/ -q -p no:cacheprovider` → 721 passed, 15 skipped, 28 subtests
  (+4 tests over the 717 baseline)
- `git diff --check` → clean
