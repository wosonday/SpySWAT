---
id: docs-5
branch: feat/docs-5
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# DOCS-5: one harness copy at the repo root, synced with the shared harness

Written by the CEO. User decision (2026-11-24): keep ONE copy of the team-workflow harness, laid out
exactly like the shared harness, at the repository root; delete `docs/agents/`.

Shared harness source (read-only, outside the repo): `D:/.harnessing/agent-tutorial`
(`*.md` at its root, `docs/`, `docs/superpowers/`, `scripts/`, `tests/`). Mapping into this repo:

| Source (harness) | Destination (repo) |
|---|---|
| `<H>/AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md`, `AGM-UPGRADE-SPEC.md` | repo root, same names (overwrite) |
| `<H>/docs/*.md` (incl. new `WINDOWS-AGENT-RUNTIME.md`, `CONTEXT-ROTATION.md`, `SKILL-ROUTING.md`) | `docs/*.md` (overwrite/add) |
| `<H>/docs/superpowers/**` | `docs/superpowers/**` (overwrite/add; keep existing extra files) |
| `<H>/scripts/*.py` | `scripts/*.py` (overwrite; never copy `__pycache__`) |
| `<H>/tests/*.py` (incl. new `test_skill_routing.py`) | `tests/` (overwrite/add) |

Never touch SpySWAT library docs: `docs/SYSTEM_DESIGN_*.md`, `docs/sample_run_*.py`.

## Steps
1. Copy per the table (use `cp`, not hand edits).
2. `docs/agents/SETUP-WINDOWS.md` is SpySWAT-only: `git mv` it to `docs/SETUP-WINDOWS.md`.
   Files in `docs/agents/superpowers/**` that do not exist in `docs/superpowers/` are `git mv`ed there.
   Then `git rm -r docs/agents`.
3. Fix every reference to `docs/agents/...` in: `AGENTS.md`, `CLAUDE.md`, `README_VI.md`,
   `CHANGELOG.md` (add a new bullet under `[Unreleased]` instead of rewriting old entries),
   `.agents/README.md`, `.gitignore`, `docs/SETUP-WINDOWS.md`. Mapping: `docs/agents/X.md` → `X.md`
   (root), `docs/agents/models/Y.md` → `docs/Y.md`, `docs/agents/SETUP-WINDOWS.md` →
   `docs/SETUP-WINDOWS.md`, `docs/agents/superpowers/` → `docs/superpowers/`. Do NOT edit old
   `.agents/tasks|decisions|reviews|reports|log` files (history).
   In `AGENTS.md` also update the `docs/` part of the Quick orientation tree.
4. `pyproject.toml` sdist `exclude`: add `/tests/test_skill_routing.py` next to the other harness tests.
5. The copied harness docs must not contain personal machine paths or other projects' names beyond
   what the harness already has; report any you see (do not edit harness text).
6. Run `python scripts/lint_harness.py` → must end with `0 errors` (record the line). If errors remain
   that come from the harness text itself, list them in the log and stop; do not edit harness text.
7. `python -m pytest tests/ -q` → all pass; record counts (baseline 454 passed, 11 skipped; harness
   test count changes). Update the counts sentence(s) in `AGENTS.md` "Commands" to the new numbers
   (keep the wording style: "measured on main <sha>: N passed, M skipped").
8. `git grep -n "docs/agents"` outside `.agents/` history files → no hits (record).

## Files in scope
Repo-root harness `*.md`, `docs/*.md` (harness ones), `docs/superpowers/**`, `docs/agents/**` (removal),
`scripts/*.py`, `tests/test_harness_*.py`, `tests/test_guardrail_examples.py`, `tests/test_skill_routing.py`,
`AGENTS.md`, `CLAUDE.md`, `README_VI.md`, `CHANGELOG.md`, `.agents/README.md`, `.gitignore`,
`pyproject.toml`, `.agents/log/DOCS-5.md`.

## Acceptance criteria
- [ ] `diff -rq` of each mapped pair shows no differences (except `__pycache__`).
- [ ] `docs/agents/` gone; no stale `docs/agents` references (step 8).
- [ ] lint `0 errors`; full pytest green with recorded counts; `git diff --check` clean.

## Report format
Append to `.agents/log/DOCS-5.md`: files changed (summary), commands with output lines, open questions.
Commits start with `docs-5:`. LF→CRLF warnings are normal.
