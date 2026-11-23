# Codex Guide — Senior Engineering & Single-Lane Management

> **Critical Quota Warning (verified in `agmag`):** OpenCode running `openai/gpt-6.1-sol` **shares the exact same ChatGPT (5h / 7d) subscription quota as Codex CLI** (quota is tracked per OpenAI provider, not per CLI). Therefore, **do not** use `gpt-6.1-sol` as the default Reviewer or for administrative report writing.

## 1. When to Use Codex (and When NOT To)

| Use Codex (`openai/gpt-6.1-sol`) | Do Not Use Codex (offload elsewhere) |
|---|---|
| **Hard engineering:** complex logic, multi-file refactors, DB migrations, performance tuning | **Mechanical 1–2 file tasks with tests:** `worker-fast` prefers `opencode-go/deepseek-v4.1-flash` within allocation |
| **Debugging after 2 failed attempts** by `worker-fast` / `worker-mid` | **Audit & lint/CI gating:** scripts/CI; approved free/local LLM only when needed |
| **Complex logic cross-reviews** (second opinion) when `agm quota` has headroom | **Routine Reviewer:** qualified `opencode-go/deepseek-v4-pro`; different family when Pro authored code, with approved `agy` fallback |
| **Orchestration in single-lane projects** (when **not** using `BOT-CEO.md`) | **Middleman orchestration under `BOT-CEO.md`:** BOT-CEO calls `agm spawn` directly; omit `codex-mgr` |
| — | **Final reports `.agents/reports/<ID>.md`:** use `gemini-3.8-flash-medium` / `hydrogen-low` |

## 2. Two Ways to Run Codex

1. **Via OpenCode v2 per task (recommended for strong workers):**
   ```powershell
   opencode run --model openai/gpt-6.1-sol ...
   ```
   Or attach to `worker-strong.md` when escalating a specific worktree (`agm spawn worker-strong --task <ID> --role worker --cwd <worktree>`).
2. **Interactive Codex CLI (`codex-mgr` in single-lane projects, or strong worker):**
   - Launch in `herdr-core` (named `codex-mgr` or `w-<ID>-<n>`).
   - For long-lived manual sessions (like `codex-mgr`), enable `agm manage codex-mgr` so `agm` prompts handoff to `.agents/handoff/` at `ctx_rotate = 70%` without killing the old session.
   - Load 1–3 skills on startup (`writing-plans`, `dispatching-parallel-agents`, `using-git-worktrees`).

## 3. Controlling ChatGPT 5h / 7d Quota

- Check quota before starting heavy Codex sessions:
  ```powershell
  agm quota
  ```
- **Recommended threshold:** if `codex 7d` has under **20–30% left** (`agm quota` shows the remaining share), reserve Codex for genuine blockers. For `worker-strong`, use a capable Go model within allocation or another approved source; never fall back to unapproved pay-as-you-go APIs.
- Fast/mid may share Flash Go; changing templates is not a capability upgrade. Pro Go needs its own coding trial for suitable strong work; use a different Reviewer family when Pro authored code. [Background NVIDIA](NVIDIA-BACKGROUND.md) supplies synthesis/proposals, not workers or review gates.
- Note in `agm`: quota consumed by OpenCode via `openai/gpt-6.1-sol` does not appear in OpenCode's own DB; it surfaces on the next `rate_limits` entry written by Codex.

## 4. Worktree & Git Discipline

- When acting as an engineering worker in a worktree: edit only files listed in `.agents/tasks/<ID>.md`, log steps in `.agents/log/<ID>.md`, prefix commits with `<ID>:`, never touch `BRANCHES.md`, and never merge/push.
- When acting as manager (single-lane): do not edit worker code directly; check `agm inbox --json`, escalate worker models after 2 failures, verify `git status` / `git diff --stat`, update `BRANCHES.md` via `agm branch set` (when used), and hand off branch + final SHA to `copilot-git` via `agm send copilot-git --type ASSIGN --task <ID> ...`.
- Like Claude, interactive Codex sessions are **never auto-killed by `agm`**—only the user (TTY + `y`) can stop them.
