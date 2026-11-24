# Log HARN-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-24 · worker-fast · step 1/4
- Done: committed the six coordination files the Architect placed in this worktree, unchanged.
- Files changed: `.agents/decisions/BG-1.md`, `.agents/decisions/HARN-1.md`, `.agents/tasks/HARN-1.md`, `.agents/tasks/MERGE-3.md`, `.agents/tasks/MERGE-4A.md`, `.agents/tasks/MERGE-4.md`, `.agents/log/HARN-1.md` (new)
- Checks: `git status --porcelain` before commit → only these six untracked files (no product code touched)
- Decision: content committed verbatim; no edits to coordination files (one writer per file).
- Previous commit: 301cecb

## 2026-11-24 · worker-fast · step 2/4
- Done: excluded the harness-only lint tests from the sdist (change 1); `__pycache__` still excluded, includes untouched.
- Files changed: `pyproject.toml` (sdist `exclude` list only), `.agents/log/HARN-1.md`
- Checks: not run yet in this step; full suite run before the final entry (task forbids `uv build`/`python -m build` here — the Architect verifies the sdist).
- Decision: keep `exclude` a multi-line list so every pattern is on its own line.
- Previous commit: c0498a8

## 2026-11-24 · worker-fast · step 3/4
- Done: changes 2-4 — `AGENTS.md` Commands line now `measured on main 301cecb: 451 passed, 11 skipped (~4 min on Windows)` plus the sentence about the 87 harness lint tests left in the repo but excluded from the sdist; `execute: deny` added under `permission:` in `.opencode/agents/explore.md`, `reviewer.md`, `auditor.md` (auditor keeps its allowed bash commands); one bullet in `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md` §3 that `bash: deny` does not cover the `execute` tool.
- Files changed: `AGENTS.md`, `.opencode/agents/explore.md`, `.opencode/agents/reviewer.md`, `.opencode/agents/auditor.md`, `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`, `.agents/log/HARN-1.md`
- Checks: `python -m pytest tests/ -q` → 451 passed / 11 skipped / 0 failed (5 warnings, 24 subtests) in 188.86s — unchanged from baseline.
- Decision: counts re-measured after the docs edits; no source code touched, so the suite is unaffected.
- Blocked / question: none. The sdist itself is not built here (not permitted); the Architect verifies the exclusion.
- Previous commit: af9ee53

## 2026-11-24 · worker-fast · step 4/4 — done
- Done: all of changes 1-6 complete; nothing outside the task scope was touched, nothing merged or pushed.
- Files changed (whole branch): `.agents/decisions/BG-1.md`, `.agents/decisions/HARN-1.md`, `.agents/tasks/HARN-1.md`, `.agents/tasks/MERGE-3.md`, `.agents/tasks/MERGE-4A.md`, `.agents/tasks/MERGE-4.md` (committed unchanged), `.agents/log/HARN-1.md`, `pyproject.toml`, `AGENTS.md`, `.opencode/agents/explore.md`, `.opencode/agents/reviewer.md`, `.opencode/agents/auditor.md`, `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`
- Checks: `python -m pytest tests/ -q` → 451 passed / 11 skipped / 0 failed, 5 warnings, 24 subtests passed, 188.86s (matches the 451/11 baseline). `git diff --stat main...HEAD` → the 13 files above and nothing else.
- Decision: sdist not built (task forbids `uv build`/`python -m build`); the exclusion is verified by the Architect.
- Blocked / question: none.
- Previous commit: 7946614

## 2026-11-24 · worker-fast · rework 1/3 — decision correction
- Done: committed the Architect's `Correction after Architect probes` section in `.agents/decisions/HARN-1.md` verbatim (item 3 was insufficient: `execute: deny` alone exposes plugin tools such as `browse_*` and the worktree tools).
- Files changed: `.agents/decisions/HARN-1.md` (committed unchanged, no edits)
- Checks: `git status --porcelain` before commit → only ` M .agents/decisions/HARN-1.md`
- Decision: no coordination file edited (one writer per file).
- Previous commit: a80f5ea

## 2026-11-24 · worker-fast · rework 2/3 — corrected permissions, docs bullet, AGENTS.md paragraph
- Done: corrected change 3 per the decision — `"*": deny`, `read: allow`, `glob: allow`, `grep: allow` inserted as the first keys under `permission:` (2-space indent) in `.opencode/agents/explore.md`, `reviewer.md`, `auditor.md`; every existing key kept (incl. `edit`, `bash`, `webfetch: deny`, `execute: deny`, `task: deny`). Rewrote the added bullet in `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md` §3: read-only agents need a default `"*": deny` with explicit allows because `execute` is a code-mode wrapper around plugin/MCP tools (`browse_*`, worktree tools) that appear when it alone is denied. In `AGENTS.md` the 87-harness-tests sentence is now its own paragraph starting `Of the 451 passing tests, 87 are harness lint tests`.
- Files changed: `.opencode/agents/explore.md`, `.opencode/agents/reviewer.md`, `.opencode/agents/auditor.md`, `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`, `AGENTS.md`, `.agents/log/HARN-1.md`
- Checks: `python -m pytest tests/ -q` → 451 passed / 11 skipped / 0 failed (5 warnings, 24 subtests) in 222.45s — unchanged baseline. `git diff` reviewed: only the keys/paragraph/bullet above, nothing else.
- Decision: task-file items 1 (`pyproject.toml` sdist exclude) untouched and still in place from step 2; no `uv build`/`python -m build` here (not permitted) — the Architect verifies the sdist.
- Blocked / question: none. Nothing merged or pushed.
- Previous commit: a80f5ea

## 2026-11-24 · worker-fast · rework 3/3 — done
- Done: rework complete exactly as instructed: decision file committed unchanged (`a80f5ea`), then the corrected permissions + docs bullet + `AGENTS.md` paragraph in `788b00d`. No source code, tests, `pyproject.toml` or coordination files touched in the rework.
- Files changed (whole branch): unchanged from step 4, i.e. the six coordination files, `pyproject.toml`, `AGENTS.md`, `.opencode/agents/{explore,reviewer,auditor}.md`, `docs/agents/models/OPENCODE-WORKERS-REVIEWER.md`, `.agents/log/HARN-1.md`.
- Checks: `python -m pytest tests/ -q` → 451 passed / 11 skipped / 0 failed (5 warnings, 24 subtests) in 222.45s; `git status --porcelain` → clean after the log commit.
- Decision: `"*": deny` with `read`/`glob`/`grep` allows kept the auditors' allowed `bash` commands and `execute: deny`; workers are HARN-2 scope.
- Blocked / question: none.
- Previous commit: 788b00d
