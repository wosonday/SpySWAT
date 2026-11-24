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
