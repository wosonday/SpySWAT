---
id: <ID>
branch: feat/<ID>
tier: fast | mid | strong
skills: <at most 2 for a worker, comma-separated>
gitnexus: none | main | worktree
---

# <ID>: <short title>

## Goal
One or two sentences.

## Files in scope
- `spyswat/...`
- `tests/...`
- `.agents/log/<ID>.md`

Anything else is out of scope: propose it in the log instead.

## Constraints
- Follow the key design rules in `AGENTS.md`.
- Runtime messages in English.

## Acceptance criteria
- [ ] `pytest tests/ -q`: all pass (record the counts)
- [ ] ...

## Report format
Files changed, checks run with counts, open questions.
