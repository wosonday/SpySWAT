# HARN-2 review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, full diff inlined)

Verdict: PASS

## Findings

- **Critical:** None.
- **Major:** None.
- **Minor:**
  - `.opencode/agents/worker-fast.md:19`, `.opencode/agents/worker-mid.md:18`, `.opencode/agents/worker-strong.md:19` — `"git add*": allow` only excludes `.agents/tasks*`, so `git add .` / `git add -A` or staging `.agents/reviews/` or `.opencode/` (if written via `python *`) is not blocked at the `bash` rule level. **Fix:** add `"git add .agents/reviews*": deny`, `"git add .opencode*": deny`, `"git add .": deny`, and `"git add -A*": deny` after `"git add*": allow`.
  - `.opencode/agents/worker-fast.md:19`, `.opencode/agents/worker-mid.md:18`, `.opencode/agents/worker-strong.md:19`, `.opencode/agents/gitnexus-sync.md:16` — `"git commit*": allow` also permits `git commit --amend`. **Fix:** add `"git commit *--amend*": deny` after `"git commit*": allow`.

## Checklist Summary

- **Default-deny & tool lockdown:** All four agents start with `"*": deny` and set `external_directory: deny`, `webfetch: deny`, `websearch: deny`, `execute: deny`, `task: deny`.
- **Worker scope & git safety:** Workers retain `read/glob/grep/skill`, `edit` excluding `.agents/tasks/*`, `.agents/reviews/*`, `.agents/locks/*`, `.opencode/*`, `.wt/*`, `../*`, `/*`, `[A-Za-z]:*`, plus `python *`, `pytest`/`uv`/`pip`, `git status|diff|log|add|commit`, and `agm send*`; `push`/`merge`/`rebase`/`reset`/`branch`/`worktree` remain denied.
- **Role isolation (`gitnexus-sync`):** Restricted to `read/glob/grep`, `edit` on `.agents/log/*` only, and role-specific `bash` commands (`gitnexus clean*` removed).
- **Syntax, docs & repo hygiene:** Valid YAML syntax across all four frontmatters; the deliberate `python *` CEO choice is documented in `.agents/decisions/HARN-2.md:19-20`; decision claims and `.agents/log/HARN-2.md` match the diff; nothing out of scope and no secrets or personal paths.

## CEO triage
- Applied: deny `git add .agents/reviews*`, `git add .opencode*`, `git commit *--amend*` (workers); amend deny (gitnexus-sync).
- Not applied: deny `git add .` / `-A` — workers keep `python *`, so bash-level denial adds no real boundary; review stays the gate.
