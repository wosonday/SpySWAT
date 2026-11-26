# SCEN-CLEANUP-1 log

## 2026-11-26 — Gemini 4 Hydrogen (Antigravity session, at the user's request)

- Implemented in the main checkout: `ScenarioBatch.run(cleanup=False)`, removal of `output.*` / `watout.dat`
  in each worker slot after extraction, `_rmtree` retries, `_param_exts` skips extension-less entries,
  `src/swatParam.txt` `GDRAIN_BSN` -> `GDRAIN_BSN.bsn`; tests in `tests/test_scenarios.py` and
  `tests/test_working_folder.py`. Decision: `.agents/decisions/SCEN-CLEANUP-1.md`.

## 2026-11-26 — Claude Opus 5.5 (Architect)

- Audit: `python -m pytest tests/ -q -p no:cacheprovider` → `723 passed, 15 skipped, 14 warnings,
  28 subtests passed in 266.11s` (721 before + 2 new tests).
- Architect read of the diff (no independent review: the user chose the quick path, commit as is).
- Open for a follow-up task (user decision: defer):
  1. `output.*` is removed even with `cleanup=False`: document it (docstring + CHANGELOG) or make it an option,
     since users lose `output.std`/`output.hru` for debugging.
  2. Silent failures: `unlink` errors are ignored and `_rmtree` returns silently when the folder survives
     all retries; log a warning (AGENTS.md rule 8).
  3. The decision proposes `cleanup=True` while the code defaults to `False`; align the decision text.
  Also missing: CHANGELOG entry for 0.3.1.
