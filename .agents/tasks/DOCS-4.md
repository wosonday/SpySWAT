---
id: docs-4
branch: fix/phase1-correctness
tier: mid
skills: verification-before-completion
docs_impact: yes
gitnexus: none
---

# DOCS-4: adopt team workflow v3.6 (user-updated guides)

## Goal
The user dropped the v3.6 guides at the repo root and in `docs/`. Put them where SpySWAT
keeps the team workflow (`docs/agents/`), fix links, apply the public-repo rules, and bring
`AGENTS.md`, `CLAUDE.md`, `.agents/` and `SETUP-WINDOWS.md` up to the v3.6 routing.

## Files in scope
- `docs/agents/**` (tutorial, BOT-CEO, HERDR-CORE-BOT, new `models/`, `superpowers/`)
- `AGENTS.md`, `CLAUDE.md`, `.agents/README.md`, `.agents/templates/task.md`
- `.agents/log/DOCS-4.md`

## Constraints
- No personal machine paths (public repo).
- The agent-tutorial lint tooling stays out of SpySWAT (user decision 2026-11-20).

## Acceptance criteria
- [x] Every relative link and anchor under `docs/agents/`, `AGENTS.md`, `CLAUDE.md`, READMEs resolves
- [x] No `/mnt/...` or user paths in new files
- [x] `pytest tests/ -q` collects no harness tests
