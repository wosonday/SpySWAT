# .agents/ — per-task notebook

Committed together with the code on the working branch. Git records *what* changed; these
files record *why* and *what was checked*. Rules: `AGENTS.md` → "Agent team workflow";
full guide: `AGENTS-TUTORIAL.md` (sections 2.3 and 3.2) and `HERDR-CORE-BOT.md` at the repository
root, optional multi-lane scaling in `BOT-CEO.md`, per-model guides in `docs/`.

| Folder | File | Writer | Content |
|---|---|---|---|
| `tasks/` | `<ID>.md` | Manager | Goal, files in scope, constraints, acceptance criteria, `tier:`, `skills:` (max 2) |
| `log/` | `<ID>.md` | Worker / Auditor / Docs Updater | Append-only entries, one per step / commit (`<ID>: docs: ...` for docs) |
| `reviews/` | `<ID>-<n>.md` | Reviewer / Sparring | Review round n: PASS / FAIL, findings |
| `decisions/` | `<ID>.md` | Architect / Manager / Gemini Argon | Decisions, risks, reasons, harness tuning |
| `reports/` | `<ID>.md` | Manager | Final branch report + major issues for Gemini Argon retro |
| `templates/` | — | — | Copy a template to start a file |

Also kept in `.agents/`: `bot.env` (non-secret git/worktree settings for wrapper scripts).
Not committed (see `.gitignore` and `git info/exclude`): `.agents/.runtime/` (bot scratch),
`.agents/locks/` (directory locks), `.agents/handoff/` (session rotation handoffs), and
`.wt/` (worktrees).

Task IDs: short `<AREA>-<n>` (or lowercase `a-z0-9_-`, max 27 chars, when spawning via
`agm`/`hc` so `w-<id>-<n>` stays within the 32-char lowercase terminal limit). Branch:
`feat/<ID>` or `fix/<ID>`. Commit messages start with `<ID>:`.

This repository is public: never write secrets, real watershed data or personal paths here.
