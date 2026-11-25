# HARN-3 log

## 2026-11-25 — Claude Opus 5.5 (Architect, playing every role)

- Shared harness edited first (backup kept outside the repo), then reviewed by `agy` `gemini-4-hydrogen-high`
  (`--mode plan --sandbox`, prompt file): round 1 FAIL (3 Major, 3 Minor), round 2 FAIL (1 Major, 3 Minor),
  round 3 PASS. All findings were checked and fixed: dirty-checkout gate made consistent in COPILOT-GIT §2 and
  WINDOWS-AGENT-RUNTIME §9, README routing rows, `copilot-git` kept off feature branches, Hydrogen/Neon same-family
  note, `-d`/`-D` limits stated as brief-level, original line endings kept.
- Files changed: the 8 harness files listed in `tasks/HARN-3.md` (42 insertions, 11 deletions) + task/log files.
- Audit: `python scripts/lint_harness.py --root .` → `Harness lint: 32 documents, 0 errors`;
  `python -m pytest -q -p no:cacheprovider tests/test_harness_markdown.py tests/test_harness_routing.py
  tests/test_guardrail_examples.py tests/test_skill_routing.py` → `97 passed, 28 subtests passed`.
  Docs only: the product test suite was not re-run (no Python source changed).
- Same session: the 12 merged `feat/api-*` worktrees and branches were removed by `copilot-git` (user request);
  three formatter-only edits in the main checkout (isort/black, AST checked) were discarded at the user's word.
