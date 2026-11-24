# Decision HARN-1: harness fixes found during PAR-1 / PAR-2 / BG-1 (2026-11-23)

- Author: Architect / BOT-CEO (Claude Opus 5.5). Status: **approved items 1-2 by the user;
  item 3 = Architect fix of a confirmed permission gap.** Runs after PAR-1 and PAR-2 merge
  (avoids conflicts with their docs step on `AGENTS.md`).

## 1. Harness lint tests stay in SpySWAT, out of the sdist (user, 2026-11-23)

Commit 628e5bb (PR #2) added `tests/test_harness_markdown.py`, `tests/test_harness_routing.py`,
`tests/test_guardrail_examples.py` (~87 tests) and `scripts/lint_harness.py`, contrary to the
DOCS-4 decision of 2026-11-20. **New decision (supersedes DOCS-4 on this point):** keep them,
because they check SpySWAT's own `docs/agents/`; exclude them from the sdist in
`pyproject.toml` (`[tool.hatch.build.targets.sdist]`).

## 2. Test counts in `AGENTS.md`

`AGENTS.md` still says 336 passed. Measured on main 12181ef: ~423 passed / 11 skipped
(336 library + ~87 harness). After PAR-1 + PAR-2: re-measure and write the library and
harness counts separately.

## 3. Read-only OpenCode agents must deny `execute`

BG-1 showed that OpenCode's `execute` tool (JavaScript with file access) is not covered by
`bash: deny` (`.agents/decisions/BG-1.md`). `.opencode/agents/explore.md`, `reviewer.md`,
`auditor.md` do not deny it. Add `execute: deny` to each (auditor: keep its allowed shell
commands), and a one-line note in `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`.

## Scope for the worker

`pyproject.toml` (sdist exclude only), `AGENTS.md` (Commands section counts),
`.opencode/agents/{explore,reviewer,auditor}.md`, `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`,
`.agents/log/HARN-1.md`. Check: `python -m pytest tests/ -q` unchanged counts; build the sdist
(`uv build --sdist` or `python -m build --sdist`) and list it to prove the exclusion.
