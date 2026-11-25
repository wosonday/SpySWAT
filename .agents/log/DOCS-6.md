# DOCS-6 log

## 2026-11-25 — Claude Opus 5.5 (Architect, playing every role)

- Measured on main b7acadf: `python -m pytest tests/ -q -p no:cacheprovider` → `721 passed, 15 skipped, 14 warnings,
  28 subtests passed in 255.90s`. Skip sources (grep of `skipif`/`importorskip`): POSIX fake-exe tests in
  `tests/test_run.py` and `tests/test_working_folder.py`, SALib tests (`tests/test_sensitivity.py`,
  `tests/test_algorithms_vocabulary.py`), one Windows-only test runs here (`tests/test_scenarios.py`).
- Files changed: `README.md` (badge, tree line, new `## Tests` section), `README_VI.md` (badge, tree line, Tests
  section), `AGENTS.md` (Commands counts and skip list), `.agents/README.md` (tutorial sections 2.3 and 3.2 instead of
  the old "v3.6, section 3.3"), plus this task/log.
- Audit: `python scripts/lint_harness.py --root .` → 0 errors; harness tests → 97 passed. No Python source changed.
