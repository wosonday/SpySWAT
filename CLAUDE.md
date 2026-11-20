# CLAUDE.md

Claude Code reads this file; Codex and OpenCode read `AGENTS.md`. The project rules and the
binding team-workflow summary live in `AGENTS.md`, imported here so both stay in one place:

@AGENTS.md

## Claude Code specifics

- **Primary role for Claude (conserve quota):** **Architect** (Opus 5.5 extra effort, or
  Fable 5.2) — read-only on source code; writes `.agents/decisions/`. This is the **only**
  regular Claude Code session (in optional multi-lane mode, 1 BOT-CEO per lane per
  `docs/agents/BOT-CEO.md`).
- **Escalation-only Reviewer:** Default review uses OpenCode (`opencode-go/deepseek-v4-pro`) plus
  optional `agy` Opus High sparring. Claude Code Opus 5.5 (high effort) is opened as
  Reviewer **only** for high-risk changes (security, real data, format/schema migrations,
  major architecture) or after 2 consecutive OpenCode Reviewer `FAIL`s; writes
  `.agents/reviews/`.
- **Communication & lifecycle (`agm`):**
  - Send to another agent: `agm send <terminal> --type GIAO|"BÁO CÁO"|LỖI|HỎI|CHẶN|ĐẠT|"CHƯA ĐẠT" --task <ID> "<1-3 lines>"`
  - Ask the user: `agm send user --type HỎI --task <ID> "<question>"`
  - Check inbox: `agm inbox --json`
  - Never run `agm kill` on Claude or Codex sessions (user-only); use `agm manage` +
    `agm hook install` for context rotation via `.agents/handoff/`.
- **AI budget (v3.6):** as Architect/BOT-CEO, allocate per task and keep a review/rework
  reserve; check Go in its console and `agm quota` before dispatch; never enable Extra Usage.
  Model guide: `docs/agents/models/CLAUDE-ARCHITECT-CEO.md`.
- **Skills per session:** 1 to 3 at start (Architect: e.g. `brainstorming`, then
  `architecture`/`system-design`; escalated Reviewer: `code-review`,
  `verification-before-completion`). Swap a skill instead of stacking more.
- **When one Claude session plays every role** (no Codex/OpenCode/`agy`/`copilot` available),
  follow the roles in order: write `tasks/<ID>.md`, implement, log, run the audit commands,
  review the diff against the task, update affected docs, then write `reports/<ID>.md`. Say
  so in the report.
- **Commits and pushes** only when the user asks. The repository is public: apply the
  public repository rules in `AGENTS.md` before every commit.
