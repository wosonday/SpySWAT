---
id: harn-1
branch: feat/HARN-1
tier: fast
skills: tdd
docs_impact: yes
gitnexus: none
---

# HARN-1: harness fixes from PAR-1 / PAR-2 / BG-1

Design: `.agents/decisions/HARN-1.md` (items 1-2 approved by the user 2026-11-23; item 3 is the
Architect's fix of a confirmed permission gap, `.agents/decisions/BG-1.md`).
Model: `opencode-go/deepseek-v4.1-flash`. Budget: `task:harn-1` soft 1M / hard 2M tokens.

## Changes (exactly these)

1. `pyproject.toml`, `[tool.hatch.build.targets.sdist]`: add to `exclude` the harness-only tests
   `/tests/test_harness_markdown.py`, `/tests/test_harness_routing.py`,
   `/tests/test_guardrail_examples.py`. Keep `"__pycache__"`. Change nothing else.
2. `AGENTS.md`, section "Commands": replace the measured line with
   `pytest tests/ -q             # measured on main 301cecb: 451 passed, 11 skipped (~4 min on Windows)`
   and add one sentence below the existing note: "Of these, 87 are harness lint tests
   (`tests/test_harness_*.py`, `tests/test_guardrail_examples.py`) that check `docs/agents/`;
   they stay in the repository but are excluded from the sdist."
3. `.opencode/agents/explore.md`, `reviewer.md`, `auditor.md`: add `execute: deny` under
   `permission:` (same indentation as `webfetch: deny`). Nothing else in these files.
4. `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`: add one bullet where permissions are
   described: "`bash: deny` does not cover OpenCode's `execute` tool (JavaScript with file
   access); read-only agents must also set `execute: deny` (SpySWAT BG-1, 2026-11-23)."
5. Commit, unchanged, the coordination files the Architect placed in this worktree:
   `.agents/decisions/BG-1.md`, `.agents/decisions/HARN-1.md`, `.agents/tasks/HARN-1.md`,
   `.agents/tasks/MERGE-3.md`, `.agents/tasks/MERGE-4A.md`, `.agents/tasks/MERGE-4.md`.
6. `.agents/log/HARN-1.md`: entries for each commit.

Do not run `uv build`/`python -m build` (not permitted here; the Architect checks the sdist).

## Acceptance criteria
- [ ] `python -m pytest tests/ -q`: 451 passed, 11 skipped, 0 failed (unchanged).
- [ ] `git diff --stat main...HEAD` lists only the files above.
- [ ] Commits prefixed `harn-1:`; docs/harness edits in a commit `harn-1: docs: ...`.
