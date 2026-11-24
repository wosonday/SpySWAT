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
