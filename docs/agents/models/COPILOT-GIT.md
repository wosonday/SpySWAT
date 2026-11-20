# GitHub Copilot CLI (`copilot`) Guide — Git Version Manager

GitHub Copilot CLI (`copilot-git`) is the **only agent** permitted to integrate (merge), manage history (`git revert`), and clean up merged worktrees/branches on the shared branch (`main`). It runs on your GitHub Copilot account and does not consume Claude or ChatGPT/Codex quotas.

## 1. Startup & Scope

- Run **exactly 1 `copilot-git` session** in the **main checkout** (on `main`) so integrations are strictly **sequential**—one branch/feature per merge.
- Launch command:
  ```powershell
  copilot
  # Opening prompt: Read AGENTS.md (and BOT-CEO.md / GIT_BOT.md if present). You are copilot-git; process the queue strictly by verified SHA.
  ```
- **Verified (2026-11-18):** Copilot CLI 1.0.113 passed 3/3 Git smoke tests on an isolated fixture (halted on dirty checkout, rejected mismatched SHA, merged exact SHA—see `COPILOT_GIT_SMOKE.md` in `MATHY-AI`).

---

## 2. Handoff Prerequisites (Before Merging)

Depending on project mode, `copilot-git` receives work from:
- **Multi-lane (`BOT-CEO.md`):** read entries with **`status: ready`** in `BRANCHES.md` (under lock `.agents/.runtime/locks/branches`, inside `.gitignore` so the main checkout stays clean), checking that all `depends_on` branches are `merged`/`deployed`.
- **Single-lane (`AGENTS-TUTORIAL.md`):** receive a handoff packet from `codex-mgr` / Architect (branch name, full `head` SHA, test commands + real counts, Audit + Review reports, and Hydrogen Medium docs confirmation).

**Immediately reject and return `needs-rebase` / `failed` if:**
1. The main checkout is dirty (`git status --short` has uncommitted files).
2. The branch's `head` SHA does not match the approved SHA from Review/Docs (extra commits added after `ready`).
3. Audit/Review results or required doc updates are missing.
4. Any branch in `depends_on` has not been merged into `main`.

---

## 3. Six-Step Integration Workflow

1. **Mark `merging`** in `BRANCHES.md` (holding the `mkdir` lock) so all BOT-CEOs see it is in progress.
2. **Verify exact SHA and merge sequentially** into `main` at the main checkout.
   - On merge conflicts, business logic conflicts, or >1 migration head: **stop immediately—never edit feature code to force a pass**; set `status: needs-rebase` in `BRANCHES.md` and notify the lane's BOT-CEO via `agm send <lane> --type LỖI --task <ID> "..."`.
3. **Re-run post-merge Audit/CI gates** on `main` (ESLint `--max-warnings 0`, typecheck, tests, build). If any check fails: log the failure, set `failed` (or `git revert` if already pushed further), and return to the manager/BOT-CEO.
4. **Trigger GitNexus refresh:** after a clean merge, invoke **`gitnexus-sync`** (`gitnexus analyze --index-only` in the main checkout) or rely on the `post-merge` hook so BOT-CEOs never query a stale graph (`staleness: behind`).
5. **Update final status & clean up:**
   - Update `BRANCHES.md` to `merged` (or `deployed` if deployment is enabled and authorized).
   - Remove the worktree and merged branch (`cleanup-wt.sh`) only after verifying the worktree is clean and `agm ps` shows no live session inside that directory.
6. **Report completion** via `agm send` and move to the next `ready` entry in the queue.

---

## 4. Actions Requiring Explicit User Approval

`copilot-git` must **never** perform these actions without explicit user authorization:
- `git push` to remote, `git tag`, or cutting a `release`.
- Deploying to production/live environments (when `MATHY_DEPLOY` or equivalent flag is off).
- Rewriting or destroying history on `main` (`git reset --hard`, force-push). To roll back on `main`, use **`git revert`** and append a correction note.
