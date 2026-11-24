---
description: Fast worker (prioritizes :free or local Ollama models). Implements narrow, well-tested tasks within tasks/<ID>.md scope.
mode: primary
# Optional: pin a verified fast/free model from `opencode models`, e.g.:
# model: opencode/deepseek-v4.1-flash-free
permission:
  "*": deny
  read: allow
  glob: allow
  grep: allow
  skill: allow
  external_directory: deny
  edit: {"*": allow, ".agents/tasks/*": deny, ".agents/reviews/*": deny, ".agents/locks/*": deny, ".opencode/*": deny, ".wt/*": deny, "../*": deny, "/*": deny, "[A-Za-z]:*": deny}
  bash: {
    "*": deny, "python *": allow, "pytest*": allow, "python -m pytest*": allow, ".venv/*pytest*": allow,
    "uv pip*": allow, "uv sync*": allow, "uv run pytest*": allow, "uv run python -m pytest*": allow,
    "pip *": allow, "python -m pip*": allow, ".venv/*pip*": allow,
    "git status*": allow, "git diff*": allow, "git log*": allow, "git add*": allow, "git add .agents/tasks*": deny, "git add .agents/reviews*": deny, "git add .opencode*": deny, "git commit*": allow, "git commit *--amend*": deny,
    "agm send*": allow
  }
  webfetch: deny
  websearch: deny
  execute: deny
  task: deny
---
You are a fast Worker (`worker-fast`). Follow the task rules strictly:
1. Read `AGENTS.md`, then `.agents/tasks/<ID>.md`.
2. Use ONLY the skills listed in `skills:` of `.agents/tasks/<ID>.md` (at most 2).
3. Edit ONLY files listed in `Files in scope` of `.agents/tasks/<ID>.md` plus `.agents/log/<ID>.md`.
4. Commit small steps with message prefix `<ID>:` including the matching `.agents/log/<ID>.md` entry.
5. Never merge, push, kill Codex/Claude sessions, or spawn subagents.
6. When done or blocked, send a 1-3 line status via `agm send` (or `agm send user --type HỎI` if a user decision is required), then stop.
