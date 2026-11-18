# Log DOCS-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-18 · claude-opus-5.5 (all roles, one session) · step 1/3 — audit before writing
- Done: read `AGENTS-TUTORIAL.md`, `HERDR-CORE-BOT.md`, the 19 commit messages on
  `fix/phase1-correctness` and the public API of the changed modules.
- Checks: `pytest tests/ -q` → 300 passed / 11 skipped / 4 failed / 4 errors, all in
  `tests/test_project.py`.
- Diagnosis: the fixture writes `"\r\n"` with `Path.write_text` and no `newline=`; on
  Windows that becomes `\r\r\n`, `FileCIO` reads with `newline=""`, every line gains an
  empty line, `int('')` fails at `file_cio.py:121`. Fixture bug, not a library bug
  (real SWAT files have plain CRLF).
- Files changed: `tests/test_project.py` (`newline=""` on the `file.cio` write).
- Checks after fix: `pytest tests/test_project.py -q` → 19 passed.

## 2026-11-18 · claude-opus-5.5 · step 2/3 — agent workflow
- Files changed: `AGENTS.md` (rewritten), `CLAUDE.md` (new, imports `AGENTS.md`),
  `.gitignore` (`.wt/`, `.agents/.runtime/`), `docs/agents/AGENTS-TUTORIAL.md` and
  `docs/agents/HERDR-CORE-BOT.md` (moved from the repo root), `.agents/README.md`,
  `.agents/templates/{task,log,review,report,decision}.md`, `.agents/tasks/DOCS-1.md`.
- Decision: summarise the tutorial in `AGENTS.md` and link the full Vietnamese text,
  instead of pasting 400 lines into every session's context (the tutorial's "Cách dùng"
  note was updated to say so).
- Decision: `dispatch.sh` sample in `HERDR-CORE-BOT.md` now accepts `tier: fast|mid|strong`
  as well as `nhanh|vừa|mạnh`, matching `.agents/templates/task.md`.
- Not done: `.opencode/agents/*`, `opencode.json`, bot scripts (`.agents/bot/*.sh`). They
  depend on model names and `hc` flags still marked [KIỂM] in `HERDR-CORE-BOT.md`.
- Previous commit: 8c9535b
