---
id: DOCS-1
branch: fix/phase1-correctness
tier: mid
skills: verification-before-completion
gitnexus: none
---

# DOCS-1: Adopt the agent team workflow and bring the docs up to date

Requested by the user on 2026-11-18. One Claude Code session (Opus 5.5) plays every role in
order (AGENTS-TUTORIAL.md section 3.1, last bullet).

## Goal
1. Adopt `AGENTS-TUTORIAL.md` / `HERDR-CORE-BOT.md` in this repo: binding summary in
   `AGENTS.md`, `CLAUDE.md` for Claude Code, `.agents/` notebook with templates.
2. Update the project docs to match the 19 commits on `fix/phase1-correctness`
   (5e84162..b91512a).

## Files in scope
- `AGENTS.md`, `CLAUDE.md` (new), `.gitignore`
- `docs/agents/AGENTS-TUTORIAL.md`, `docs/agents/HERDR-CORE-BOT.md` (moved from the repo root)
- `.agents/**`
- `README.md`, `README_VI.md`, `ARCHITECTURE.md`, `CHANGELOG.md`
- `docs/SYSTEM_DESIGN_EN.md`, `docs/SYSTEM_DESIGN_VI.md` (status banner only)
- `tests/test_project.py` (Windows CRLF fixture bug found while counting tests)

Out of scope: library code, version bump in `pyproject.toml` (release is the user's decision).

## Constraints
- The repository is public: no secrets, data or personal paths.
- Describe only behaviour that exists in the code at b91512a.

## Acceptance criteria
- [ ] `pytest tests/ -q` passes; counts recorded in the log and in the docs
- [ ] Every API named in the docs exists (grep check)
- [ ] `git status` lists only files in scope
