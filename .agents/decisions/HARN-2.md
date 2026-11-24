# HARN-2: default-deny worker and gitnexus-sync OpenCode agents

Date: 2026-11-24. Owner: BOT-CEO. Analysis: agy `gemini-4-neon-high` (plan, sandbox, inputs inlined),
following HARN-1 (read-only agents). Routing per user: agy reviews, Neon for hard analysis, Opus last.

## Findings (Neon, accepted)
| Agent file | Issue | Severity |
|---|---|---|
| `worker-fast/mid/strong.md` | no `"*": deny`, no `execute: deny`: ~30 plugin tools exposed (`browse_*`, `opencode_worktree_*`, `opencode_session_move`) | Critical |
| `worker-*.md` | `edit: allow` without exclusions: workers could edit `.agents/tasks/`, `.opencode/`, other worktrees | Critical |
| `worker-*.md` | bash `"*": ask`: headless runs auto-reject anything not listed (e.g. `python scripts/...`), so workers stall; destructive git commands were only implicitly blocked | Critical |
| `gitnexus-sync.md` | missed by HARN-1: same plugin-tool exposure | Critical |
| `gitnexus-sync.md` | `gitnexus clean*` allowed though the role only runs `status` / `analyze --index-only` | Minor |

## Decision
- All four start with `"*": deny`, then `read/glob/grep` (+ `skill` for workers) allow,
  `external_directory: deny`, `webfetch/websearch/execute/task: deny`.
- Workers: `edit` allowed except `.agents/tasks|reviews|locks/*`, `.opencode/*`, `.wt/*`, paths outside the
  worktree. Bash default deny; allow `python *` (CEO change to Neon's draft: workers must run repo scripts such
  as `scripts/lint_harness.py`; review is the gate for what they run), pytest, `uv pip|sync|run pytest`, pip,
  `git status|diff|log|add|commit` (not `git add .agents/tasks*`), `agm send*`.
- gitnexus-sync: edit only `.agents/log/*`; bash only `git status`, `gitnexus status`,
  `gitnexus analyze --index-only`, `opencode mcp list`, `git add .agents/log/*`, `git commit`, `agm send`.

## Evidence (probes on 91b0e5c, OpenCode, deepseek-v4.1-flash)
- Tool list, all four agents: `edit, glob, grep, opencode_worktree_remove, read, shell, skill, write`
  (same as HARN-1 reviewer; no `execute`, `browse_*`, `opencode_worktree_create`, `task`, `web*`).
- worker-fast denied: write `.agents/tasks/probe.md` (`Permission denied: edit`), write `../outside-probe.txt`
  (`external_directory`), `git rebase HEAD`, `git branch -D x`, `git add .agents/tasks/probe.md` (`shell`).
- worker-fast allowed: `git status --short`, `python -c "print(1)"`, write `.agents/log/probe.md`,
  write `spyswat/probe_tmp.txt`, edit `.agents/log/probe.md` (probe files removed afterwards).
- Observed in DOCS-5 (old config): `python --version` → "non-interactive run cannot ask ... rejected".

## Not done here (needs user OK)
Global `hc` templates in `%APPDATA%\herdr-core\templates\` carry another project's routing (personal paths,
project names, Rust/PowerShell scripts, internal decision IDs) and lack `worker-strong.md`. They are shared by
other projects, so replacing them is the user's call. Generic replacements drafted by Neon are kept outside
the repo (CEO scratch) and summarised to the user.
