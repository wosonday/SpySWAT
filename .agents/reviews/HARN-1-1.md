# Review HARN-1 round 1 — PASS (0 Critical, 0 Major, 0 Minor)

- Reviewer: Architect / Claude Opus 5.5 — escalation reviewer, because the change touches agent
  permissions (security). Branch `feat/HARN-1` at 0eacfa1 (base main 301cecb).
- Read: `git diff main...HEAD`, `.agents/tasks/HARN-1.md`, `.agents/decisions/HARN-1.md` (incl.
  the correction), `.agents/log/HARN-1.md`.

## Scope

13 files, all listed in the task: 6 coordination files committed unchanged, `pyproject.toml`
(sdist exclude only), `AGENTS.md` (Commands section), three `.opencode/agents/*.md` permission
blocks, one bullet in `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`, the log.
`git diff --check main...HEAD`: exit 0.

## Behavioural evidence (not just reading the config)

1. **sdist** (`uv build --sdist`, listed with Python `tarfile`): 78 files; the 14 library test
   modules are shipped; `test_harness_markdown.py`, `test_harness_routing.py`,
   `test_guardrail_examples.py` are absent.
2. **Tool lists of the committed agent files** (OpenCode 2.4, `opencode run`, the agent asked to
   list its tools without calling any):
   - `explore`: `glob, grep, read, shell, skill`
   - `reviewer`: `edit, glob, grep, opencode_worktree_remove, read, shell, skill, write`
   - `auditor`: `edit, glob, grep, opencode_worktree_remove, read, shell, skill, write`
   Before the correction the reviewer also exposed `browse_*` (incl. `browse_eval`,
   `browse_upload`), `opencode_worktree_create`, `opencode_session_move` and others.
3. `edit`/`write`/`opencode_worktree_remove` remain but are gated by the `edit` patterns: a real
   call of `opencode_worktree_remove` on `.wt/victim` inside a scratch repo returned
   `permission.rejected — Permission denied: edit` and the worktree survived.
4. `shell` remains and is limited by each agent's existing `bash` allowlist (unchanged).

## Notes (no change required here)

- Worker agents (`worker-*`) and the global `hc`/`agy` templates were not audited: follow-up HARN-2.
- The test count line was re-measured on main 301cecb (451 passed, 11 skipped).
