---
id: merge-2
branch: feat/ARCH-1
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-2: merge `feat/ARCH-1` into `main`

Owner: `copilot-git` (GitHub Copilot CLI, terminal `t4q`). The user requested it on
2026-11-20 ("hoàn thiện và nhờ copilot merge branch").

## Gate status (read first)

- The Architect reviewed every ARCH-1 commit and re-ran the suite on the final branch
  head. The counts are in `.agents/log/ARCH-1.md`, in the entry "Architect review".
- The Auditor gate and a formal Reviewer pass were **not** run. The user authorized the
  merge with this status. Record that in the merge commit body.

## Steps

1. Run `git status --short` on `feat/ARCH-1`. It must be empty; anything else → stop and report.
2. Run `python -m pytest tests/ -q` on the branch head. Expect the count recorded in the
   Architect review entry, with 0 failed. Then run `git diff --check main..feat/ARCH-1`,
   which must exit 0. On any failure, stop and report. Never edit code or tests.
3. `git switch main`.
4. `git merge --no-ff feat/ARCH-1`, with the message
   `Merge feat/ARCH-1: run_once/sandbox primitive and calib_manager module split`.
   Put the gate status in the body.
5. Post-merge audit on `main`: `python -m pytest tests/ -q` must give the same counts.
6. **Do not push, tag, release or delete the branch.** Ask the user with
   `agm send user --type HỎI --task merge-2 "Merged locally at <sha>; push main + delete branch?"`.
7. Report to the Architect with
   `hc send t16 "[BÁO CÁO merge-2] merged <sha>; pytest <counts>; push pending user"`.

Shell commands need the user's approval in the Copilot terminal (do not use Autopilot
mode with auto-deny).
