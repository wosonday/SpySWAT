# Log DOCS-4

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-20 · claude-opus-5.5 · step 1/1
- Done:
  - root `AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md` (v3.6) moved over the
    v3.4 copies in `docs/agents/`;
  - the English per-model guides (`docs/*.md`) moved to `docs/agents/models/`, and
    `docs/superpowers/` to `docs/agents/superpowers/`;
  - links rewritten: `](docs/` -> `](models/` in the three main guides, `../../` -> `../`
    in `models/`, and the language-switch lines removed because the Vietnamese twins are
    not in this repo;
  - `BOT-CEO.md`: `/mnt/d/Project/...` personal paths replaced with repo-relative names.
- `AGENTS.md`:
  - v3.6 routing: Reviewer -> `opencode-go/deepseek-v4-pro`; workers/explore -> Flash Go,
    strong -> Pro Go; Auditor/GitNexus -> script/CI;
  - new NVIDIA background row; Architect owns the AI budget;
  - quoted multi-word `--type` values; `hc send` fallback for `done` sessions
    (`.agents/reviews/coord-1-1.md` #5).
- `CLAUDE.md`: reviewer model and AI-budget bullet.
- `SETUP-WINDOWS.md`, `.agents/README.md` and `templates/task.md`: v3.6 tiers.
- User decision: the harness lint scripts and the three harness tests
  (`scripts/`, `tests/test_harness_*.py`, `tests/test_guardrail_examples.py`) were moved out
  of the repo, to the session scratchpad (not committed). They target the agent-tutorial
  layout (`docs/en/`, JS/TS ESLint examples). In SpySWAT they failed 10 tests and reported
  55 lint errors. `models/README.md` notes the SpySWAT gate (`pytest` + `git diff --check`).
- Checks: a link/anchor script over `docs/agents/**`, `AGENTS.md`, `CLAUDE.md`, the READMEs
  and `.agents/README.md` found 0 problems; `grep /mnt/` found nothing.
- Not committed.
