# Claude Code Guide — Architect & BOT-CEO

> Open Claude Code **only** for the **Architect / BOT-CEO** role and **high-risk escalations** (security, data, DB migrations, major architecture changes, or 2 consecutive `CHƯA ĐẠT` / `FAIL` reviews). Do not use it for routine reviews, bulk coding, or mechanical tasks.

## 1. Models & Startup

```powershell
claude --model claude-opus-5-5     # Opus 5.5 (or claude-fable-5-2 for overall Architect / complex lanes)
```

- Launch Claude directly in **HERDR** with a short terminal name (≤ 32 chars `a-z 0-9 - _`, e.g., `arch`, `ceo-tap-hoa`, `ceo-platform`) for multi-turn direct conversation.
- Install the quota/context statusline hook **once per machine**:
  ```powershell
  agm hook install                 # adds statusLine (context %, 5h %, 7d %); refuses to overwrite custom statusLine
  ```
- Enable managed context rotation right after starting the session:
  ```powershell
  agm manage ceo-tap-hoa           # user-only; never auto-kills the old Claude session
  ```

## 2. Session Startup Protocol (Lauren Tan Framework: `Goal first · Process second · Then routines`)

When receiving a new request from the user (even as a messy brain dump / voice note), the Architect / BOT-CEO **owns the end goal (`you own the goal, not the steps`)** and must enforce 5 rules before spawning any worker (details in [BOT-CEO.md §5.0](../BOT-CEO.md)):

1. **Clarify the goal (`goal.first`) & value (`serves: revenue | cost`):** ask until the user confirms *"Yes, that's it"*; ask **only one question at a time** about hidden decisions (`/ask one question at a time`).
2. **Capture process & pause (`process.dump` + `hold`):** collect `steps`, `watch_outs` (hotspots), `tools`, `check_work` (`eslint --max-warnings 0` + tests), `info_from`, and `feedback_from`; `/restate` concisely and **wait for confirmation — never run `agm spawn` before the plan is approved**.
3. **Walk through 3 real examples (`/walk 3 real examples`):** must include **failure / edge cases** and specify which source wins on `conflict`.
4. **Define `done` (`"sent" is not done`):** dispatching or writing code is not done; a task is `done` only when **`saved`** (commit + `.agents/log/` + tests on branch) and **`confirmed`** (passed `auditor` ESLint/CI, `Reviewer`, `Hydrogen docs`, and `copilot-git`). Items in `waiting` (`blocked`/`depends_on`) are tracked and resumed later—never create duplicates.
5. **Output the plan summary:** end planning with `return { goal, process, rules, routine, budget, next_step }` and ask 1 final confirmation question. Record approved sources, per-task allocations and the review/rework reserve in `budget`.

## 3. What to Do vs. Offload

| Do (high-leverage Claude work) | Do Not Do (offload to other models) |
|---|---|
| Understand requirements, set the plan and budget, analyze risks, split small branches (< ~400 diff lines) | Manually grep/read dozens of files before querying `GitNexus` (`query`, `context`, `impact`) |
| Converse directly with the user for its lane (max 1 hidden-decision question per turn) | Write long code/tests instead of workers (`worker-fast` / `mid` / Codex) |
| Define acceptance criteria (`saved` + `confirmed`), write briefs / `.agents/tasks/<ID>.md` | Read raw long logs: use `explore` Flash Go within allocation; qualified NVIDIA for nonurgent synthesis |
| Reserve `wip` / mark `ready` in `BRANCHES.md` (holding `.agents/.runtime/locks/branches`) | Review routine branches: qualified Pro Go, different family when Pro authored code; `agy` Opus High for hard cases |
| Escalate diagnosis when workers + Codex fail twice | Merge into `main`, push, or deploy (handled by `copilot-git`) |

## 4. Saving Tokens & Preventing Context Bloat

**The CEO manages the AI budget.** Before dispatch, escalation or review, check the task's allocation and the applicable quota: [Go Console](https://opencode.ai/console/go) for Go and `agm quota` for sources with verified data. If quota is exhausted or unknown, use a capable approved source or mark the task blocked; never enable Extra Usage or raise limits yourself. Lanes sharing Go report allocations and usage to one existing coordinating CEO. See the [shared budget policy](../AGENTS-TUTORIAL.md#311-điều-phối-kinh-phí-ai).

Routing: `opencode-go/deepseek-v4.1-flash` for fast/mid/explore; `opencode-go/deepseek-v4-pro` for qualified review/strong tasks. [Background NVIDIA](NVIDIA-BACKGROUND.md) is read-only, at most 1 task across all aliases under manual CEO control, never a merge gate or an autonomous harness editor. Verify cloud permissions/pricing/quota first; empty pricing does not mean free.

1. **One lane = one dedicated BOT-CEO** (see [BOT-CEO.md](../BOT-CEO.md)): never deep-read another lane's code unless they share a hotspot in `BRANCHES.md`.
2. **Query GitNexus MCP first (`GITNEXUS_MCP_READ_ONLY=1`):** read `gitnexus://repo/<name>/context` → `query` → `context` → `impact` (`summaryOnly: true`), then `Read` only targeted line ranges.
3. **Load 1–3 skills per phase:** `brainstorming` during discovery, `system-design` / `architecture` during design; swap rather than stack.
4. **Use an interactive `agy` Opus High session to offload Claude directly:** when Claude's 5h/7d quota is high, open `agy --model <opus-high-slug> --mode plan --sandbox` inside the repo (keeping `conversation_id` for `cache_read_tokens`, not one-shot `agm ask`) to design, split `.agents/tasks/<ID>.md`, or arbitrate hard reviews.
5. **Rotate at 70% (`ctx_rotate`):** when `agm daemon` requests handoff, write state to `.agents/handoff/<id>-<ts>.md` with `rotation_id` and trailing `<!-- agm:handoff-done -->`, switch to the successor session, and clean up the old session manually via `agm cleanup`.

## 5. Hard Safety Rules

- Never run `git merge`, `git push`, or `nix`/deploy on the shared branch.
- `agm kill` / `agm interrupt` on Claude sessions is **blocked for all agents**—only the user (at a TTY confirming `y`) can stop a Claude session.
