---
id: merge-4a
branch: feat/PAR-2
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-4A: rebase `feat/PAR-2` onto `main` 10203f2 (local only, unpushed branch)

Owner: `copilot-git`, run in the worktree `.wt/par-2`. Written by the Architect, 2026-11-24.
Why: PAR-2 (review PASS, `.agents/reviews/PAR-2-2.md`) must sit on top of the merged PAR-1 before
its docs step, because both touch the same CHANGELOG/README sections.

## Expected conflict and its only allowed resolution

Exactly one conflict, in `spyswat/swat_calib/scenarios/batch.py`, in the import block:

    <<<<<<< ...
    from .scheduler import Scheduler
    =======
    from .signature import txinout_fingerprint
    >>>>>>> ...

Resolve by keeping both lines, in this order, and nothing else:

    from .scheduler import Scheduler
    from .signature import txinout_fingerprint

This is the resolution already verified by the Architect's trial merge (443 passed earlier).

## Steps

1. `git status --short` in `.wt/par-2` must be empty; `git rev-parse HEAD` must start with `1ca47c0`,
   except for the untracked `.agents/reviews/PAR-2-2.md`, which is allowed.
2. `git rebase main`.
3. On a conflict: `git diff --name-only --diff-filter=U` must list only that file and the
   conflict must be exactly the block above. Apply the resolution, `git add` the file,
   `git -c core.editor=true rebase --continue`. Any other conflict → `git rebase --abort`, stop, report.
4. Print `git log --oneline main..HEAD` and `git diff --stat main...HEAD`. Stop.
Never push, merge, tag, reset, delete branches/worktrees, or edit any other file.
