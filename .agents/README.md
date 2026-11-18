# .agents/ — per-task notebook

Committed together with the code on the working branch. Git records *what* changed; these
files record *why* and *what was checked*. Rules: `AGENTS.md` → "Agent team workflow";
full guide: `docs/agents/AGENTS-TUTORIAL.md` (section 3.3).

| Folder | File | Writer | Content |
|---|---|---|---|
| `tasks/` | `<ID>.md` | Manager | Goal, files in scope, constraints, acceptance criteria, `tier:`, `skills:` |
| `log/` | `<ID>.md` | Worker | Append-only entries, one per step / commit |
| `reviews/` | `<ID>-<n>.md` | Reviewer | Review round n: PASS / FAIL, findings |
| `decisions/` | `<ID>.md` | Architect / Manager | Decisions, risks, reasons |
| `reports/` | `<ID>.md` | Manager | Final branch report |
| `templates/` | — | — | Copy a template to start a file |

Not committed (see `.gitignore`): `.agents/.runtime/` (bot scratch, message logs) and
`.wt/` (worktrees).

Task IDs: short, upper-case, `<AREA>-<n>`, e.g. `DOCS-1`, `CAL-12`. Branch: `feat/<ID>` or
`fix/<ID>`. Commit messages start with `<ID>:`.

This repository is public: never write secrets, real watershed data or personal paths here.
