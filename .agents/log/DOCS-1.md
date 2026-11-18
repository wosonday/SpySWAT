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

