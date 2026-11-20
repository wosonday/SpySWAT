---
id: <ID>                    # lowercase a-z0-9_- (<= 27 chars) when spawning via agm/hc
branch: feat/<ID>
tier: fast | mid | strong   # v3.6: fast/mid -> deepseek-v4.1-flash (Go), strong -> deepseek-v4-pro
skills: <at most 2 for a worker, comma-separated>
docs_impact: yes | no       # yes -> call Gemini 4 Hydrogen Medium after Reviewer PASS
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
