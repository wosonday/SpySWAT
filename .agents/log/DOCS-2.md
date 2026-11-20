# Log DOCS-2

Request (user, 2026-11-18): practical guide to set up the multi-model team in this repo: how
to open the agents and follow their conversations. One Claude Code session (Opus 5.5).
Scope: `docs/agents/SETUP-WINDOWS.md` (new), one link in `AGENTS.md`, this log.

## 2026-11-18 · claude-opus-5.5 · step 1/1 — guide
- Checked on the machine: claude 2.1.327, codex 0.169.0, opencode 2.3.2, herdr 0.9.5 (Windows
  build), hc 0.1.21 (server running, 2 live terminals, no templates), ollama 0.40.16 (no
  models), herdr-mesh / gitnexus / jq not installed; herdr server not running; no herdr
  integration installed; `opencode models` providers: anthropic, openai, openrouter,
  huggingface, opencode.
- Sources read: `herdr --help` and `agent|worktree|integration|session --help`, `hc --help`,
  `hc run --help`, `opencode --help`, `opencode run|session --help`, `codex resume --help`,
  https://herdr.dev/agent-guide.md, https://github.com/runchr-works/herdr-mesh.
- Finding: `herdr-mesh` is not on the npm registry (`npm view` → 404); install from the GitHub
  tarball.
- Decision: start with the whole team inside herdr TUI; herdr-core bot is phase 2 (bash +
  systemd samples need Git Bash + Task Scheduler on Windows).
- Not done (the user runs them; they write into each agent's own config): `herdr integration
  install ...`, `herdr-mesh install`, `.opencode/agents/*.md` (model choice is the user's).
- Files changed: `docs/agents/SETUP-WINDOWS.md`, `AGENTS.md`, `.agents/log/DOCS-2.md`.
- Not committed.
