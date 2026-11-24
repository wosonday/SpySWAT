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

## Correction after Architect probes (2026-11-24) — item 3 was insufficient

Tool lists printed by `opencode run` (OpenCode 2.4, same result with Flash and Nemotron):

| Agent config | Tools exposed |
|---|---|
| BG-1 `background` (`bash: "*": deny`), no `execute` rule | `... read, websearch, execute` |
| same + `execute: deny` | `execute` gone, but ~30 plugin tools appear: `browse_*` (incl. `browse_eval`, `browse_upload`), `opencode_worktree_create/remove`, `opencode_session_move`, ... |
| `reviewer` after HARN-1 (`execute: deny`) | the same plugin tools + `edit`, `write`, `shell` |
| `reviewer` + `"*": deny`, `read/glob/grep: allow` | `edit, glob, grep, opencode_worktree_remove, read, shell, skill, write` |

`execute` is a code-mode wrapper around plugin/MCP tools: denying it alone exposes them.
`opencode_worktree_remove` cannot be denied by name, but calling it on `.wt/<x>` is rejected with
`Permission denied: edit` (verified in a scratch repo; the worktree survived), so the `edit`
patterns guard it. `browse_*` are not file edits and only `"*": deny` removes them.

**Corrected item 3:** in `explore.md`, `reviewer.md`, `auditor.md` add, as the first keys under
`permission:`, `"*": deny`, `read: allow`, `glob: allow`, `grep: allow`; keep every existing key
(incl. `execute: deny`). Docs bullet: say that read-only agents need a default `"*": deny` with
explicit allows, because `execute` wraps plugin tools (`browse_*`, worktree tools) that appear
when it alone is denied. Worker agents are out of scope (follow-up HARN-2).

**AGENTS.md wording fix:** the "Of these, 87 ..." sentence follows the skipped-tests note and reads
as if 87 tests were skipped. Make it its own paragraph: "Of the 451 passing tests, 87 are harness
lint tests (...)".
