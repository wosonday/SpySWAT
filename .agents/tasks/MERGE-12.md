---
id: merge-8
branch: feat/api-2c
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-12: merge `feat/api-2c` at `e00ef42` into `main` (local only)

Owner: `copilot-git`. Gate: review round 2 PASS (agy); worker suite 595 passed / 11 skipped.

## Steps
1. `git status --short` in the main checkout. Allowed entries ONLY: `?? .agents/tasks/MERGE-12.md` and the three
   user files ` M spyswat/swat_base/parameters.py`, ` M spyswat/swat_calib/core/__init__.py`,
   ` M spyswat/swat_calib/core/hru_manager.py` (someone else's work in progress: never stage, commit,
   restore or stash them). Branch must be `main`.
2. `git rev-parse --short feat/api-2c` is `e00ef42`.
3. `git merge --no-ff e00ef42 -m "Merge feat/api-2c: fail fast on metrics; preflight skips SWAT"`.
   On any conflict or refusal: `git merge --abort`, stop, report. CRLF warnings are normal.
4. `python -m pytest tests/ -q -p no:cacheprovider` → expected **595 passed, 11 skipped**, 0 failed
   (the three user files are part of the working tree; report any failure verbatim). Report the real summary line.
5. No push, tag, rebase, reset, checkout, stash, branch/worktree deletion or file edits. Print `git log --oneline -3`.
