---
id: merge-8
branch: feat/api-1
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-9: merge `feat/api-1` at `bb2ff2f` into `main` (local only)

Owner: `copilot-git`. Gate: review round 1 PASS (agy), minor rework done; worker suite 515 passed / 11 skipped.

## Steps
1. `git status --short` in the main checkout. Allowed entries ONLY: `?? .agents/tasks/MERGE-9.md` and the three
   user files ` M spyswat/swat_base/parameters.py`, ` M spyswat/swat_calib/core/__init__.py`,
   ` M spyswat/swat_calib/core/hru_manager.py` (someone else's work in progress: never stage, commit,
   restore or stash them). Branch must be `main`.
2. `git rev-parse --short feat/api-1` is `bb2ff2f`.
3. `git merge --no-ff bb2ff2f -m "Merge feat/api-1: pure evaluate() with periods, warm-up guard and monthly aggregation"`.
   On any conflict or refusal: `git merge --abort`, stop, report. CRLF warnings are normal.
4. `python -m pytest tests/ -q -p no:cacheprovider` → expected **515 passed, 11 skipped**, 0 failed
   (the three user files are part of the working tree; report any failure verbatim). Report the real summary line.
5. No push, tag, rebase, reset, checkout, stash, branch/worktree deletion or file edits. Print `git log --oneline -3`.
