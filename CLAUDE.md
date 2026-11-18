# CLAUDE.md

Claude Code reads this file; Codex and OpenCode read `AGENTS.md`. The project rules and the
binding team-workflow summary live in `AGENTS.md`, imported here so both stay in one place:

@AGENTS.md

## Claude Code specifics

- **Roles for Claude:** Architect (Opus 5.5 extra effort, or Fable 5.2) and Reviewer
  (Opus 5.5 high effort). Both are read-only on source code; the Architect writes
  `.agents/decisions/`, the Reviewer writes `.agents/reviews/`.
- **Skills per session:** 1 to 3 at start (Architect: e.g. `brainstorming`, then
  `architecture`/`system-design`; Reviewer: `code-review`, `verification-before-completion`).
  Swap a skill instead of stacking more.
- **When one Claude session plays every role** (no Codex/OpenCode available), follow the
  roles in order: write `tasks/<ID>.md`, implement, log, run the audit commands, review the
  diff against the task, then write `reports/<ID>.md`. Say so in the report.
- **Commits and pushes** only when the user asks. The repository is public: apply the
  public repository rules in `AGENTS.md` before every commit.
