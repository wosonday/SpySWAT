---
id: merge-8
branch: feat/api-5b
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-19: merge `feat/api-5b` at `72712a8` into `main` (local only)

Owner: `copilot-git`. Gate: review round 2 PASS (agy); worker suite 625 passed / 11 skipped.

## Steps
1. `git status --short` in the main checkout. Allowed entries ONLY: `?? .agents/tasks/MERGE-19.md` and the three
   user files ` M spyswat/swat_base/parameters.py`, ` M spyswat/swat_calib/core/__init__.py`,
   ` M spyswat/swat_calib/core/hru_manager.py` (someone else's work in progress: never stage, commit,
   restore or stash them). Branch must be `main`.
2. `git rev-parse --short feat/api-5b` is `72712a8`.
3. `git merge --no-ff 72712a8 -m "Merge feat/api-5b: resume through the facade; replay follow-ups"`.
   On any conflict or refusal: `git merge --abort`, stop, report. CRLF warnings are normal.
4. `python -m pytest tests/ -q -p no:cacheprovider` → expected **721 passed, 15 skipped**, 0 failed
   (the three user files are part of the working tree; report any failure verbatim). Report the real summary line.
5. No push, tag, rebase, reset, checkout, stash, branch/worktree deletion or file edits. Print `git log --oneline -3`.
