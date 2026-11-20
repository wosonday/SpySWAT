# Log DOCS-3

Append-only. Correct a mistake by adding a new entry below it.
Request (user, 2026-11-19): update role and permission allocation for SpySWAT from the
v3.4 tutorials (`AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md`), single-lane
coordination model (keep `BOT-CEO.md` as optional scaling reference).

## 2026-11-19 · Antigravity (Gemini 4 Hydrogen) · step 1/1 — update v3.4 roles & permissions
- Done:
  - Updated `docs/agents/AGENTS-TUTORIAL.md` (v3.4) and `docs/agents/HERDR-CORE-BOT.md`
    (`agm` + `hc` + GitNexus sync, `dispatch.sh` `tier: fast|mid|strong` compatibility) and
    added `docs/agents/BOT-CEO.md` (optional multi-lane scaling).
  - Updated `AGENTS.md` (Roles and permissions table, `agm`/`hc` communication & naming
    rules, `.agents/` writers, handoff checks, release gate, escalation rules).
  - Updated `CLAUDE.md` (Claude Code reserved for Architect and high-risk Reviewer
    escalations only; `agm` communication and `agm manage` rotation rules).
  - Updated `.agents/README.md` and `.agents/templates/{task,review,decision,report}.md`.
  - Updated `.gitignore` (`.agents/locks/`, `.gitnexus/`).
  - Updated `docs/agents/SETUP-WINDOWS.md` to align with v3.4 (`agm`, `agy`, `copilot`,
    OpenCode default reviewer, `:free`/local models for `worker-fast`/`auditor`/`explore`).
- Files changed: `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.agents/README.md`,
  `.agents/templates/task.md`, `.agents/templates/review.md`,
  `.agents/templates/decision.md`, `.agents/templates/report.md`,
  `.agents/log/DOCS-3.md`, `docs/agents/AGENTS-TUTORIAL.md`,
  `docs/agents/BOT-CEO.md`, `docs/agents/HERDR-CORE-BOT.md`,
  `docs/agents/SETUP-WINDOWS.md`.
- Checks: verified CLI presence (`opencode`, `agy`, `agm` 0.1.0, `hc` 0.1.21, `copilot`,
  `gitnexus`); ran relative-link & secret/personal-path checks on edited files.
- Note: root-level `AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md` could not be
  removed from inside the terminal sandbox (`Access is denied`); delete them manually if
  they are still present at repo root.
- Not committed.

## 2026-11-19 · Antigravity (Gemini 4 Hydrogen) · step 2/2 — OpenCode role permissions & bot.env
- Done:
  - Confirmed the user removed the 3 root tutorial copies (`AGENTS-TUTORIAL.md`,
    `BOT-CEO.md`, `HERDR-CORE-BOT.md`).
  - Scaffolded `.opencode/agents/` with 7 role-permission files (`worker-fast.md`,
    `worker-mid.md`, `worker-strong.md`, `auditor.md`, `reviewer.md`, `explore.md`,
    `gitnexus-sync.md`) enforcing `edit`, `bash`, `webfetch`, and `task: deny` per v3.4
    without hardcoding unverified `model:` slugs.
  - Added `.agents/bot.env` (portable `PROJECT_DIR`, `BASE_BRANCH=main`, `WT_DIR=.wt`,
    `MANAGER=codex-mgr`, `GITNEXUS_SYNC=none`, no secrets or personal paths).
  - Updated `AGENTS.md`, `docs/agents/SETUP-WINDOWS.md`, and `.agents/README.md` to
    reference `.opencode/agents/` and `.agents/bot.env`.
- Files added/changed in step 2/2: `.opencode/agents/*.md` (7 files), `.agents/bot.env`,
  `AGENTS.md`, `docs/agents/SETUP-WINDOWS.md`, `.agents/README.md`, `.agents/log/DOCS-3.md`.
- Checks: verified YAML frontmatter & markdown links + secret/personal-path scan across all
  created/edited files.
- Not committed.
