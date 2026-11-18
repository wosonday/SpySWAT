# Report DOCS-1

- Branch: `fix/phase1-correctness` · commits: 8c9535b (test fixture), 7fd2d69 (agent
  workflow), and the commit that adds this report (project docs). Not pushed.
- Trace of the whole session: `.agents/log/DOCS-1.md`, last entry.
- Who: one Claude Code session (Opus 5.5) playing every role in order; no independent
  Reviewer session was run.

## Changed
- Agent workflow: `AGENTS.md` rewritten (project guide + binding workflow summary + public
  repository rules), `CLAUDE.md` new (imports `AGENTS.md`), tutorial files moved to
  `docs/agents/`, `.agents/` notebook with templates, `.gitignore` entries for `.wt/` and
  `.agents/.runtime/`.
- Project docs: `CHANGELOG.md` `[Unreleased]`, `README.md`, `README_VI.md`,
  `ARCHITECTURE.md` updated for the 19 phase-1 commits; superseded-decision banners in
  `docs/SYSTEM_DESIGN_*.md`; two broken `README_EN.md` links fixed.
- Test fixture: `tests/test_project.py` CRLF bug on Windows.

## Checks
- `pytest tests/ -q` → 308 passed / 11 skipped / 0 failed (was 300 / 11 / 4 failed / 4 errors)
- Documented APIs: all exist (import + `hasattr` script)
- Relative links in edited docs: none broken; personal-data grep: clean

## Verdicts
- Reviewer: not run as a separate session (recommended before merge: Opus high effort,
  reading only the diff, `tasks/DOCS-1.md` and `log/DOCS-1.md`).
- Architect: not requested.

## Not verified
- Markdown rendering on GitHub (anchors with Vietnamese diacritics in README_VI's table of contents).
- `CLAUDE.md` `@AGENTS.md` import is a Claude Code feature; Codex/OpenCode read `AGENTS.md` directly.

## Remaining work
- Decide the release number (`pyproject.toml` 0.2.5 vs docs 0.2.6) and rename `[Unreleased]`.
- `.opencode/agents/*`, `opencode.json` and `.agents/bot/*.sh` once model names and `hc`
  flags are confirmed on the real machine (`[KIỂM]` items in `HERDR-CORE-BOT.md`).
- Push `fix/phase1-correctness` when the user decides (public repository).
