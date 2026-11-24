# DOCS-5 review round 1 — agy gemini-4-hydrogen-high (plan, sandbox; worker+audit diff inlined, verbatim copies excluded)

Verdict: PASS

## Findings

### Critical
None.

### Major
None.

### Minor
- `AGENTS.md:223` — Records `# measured on feat/docs-5 (harness sync): 464 passed, 11 skipped`, whereas step 7 requested keeping the `"measured on main <sha>: N passed, M skipped"` wording style. Fix (optional): keep as an accurate pre-merge branch measurement, or update `feat/docs-5 (harness sync)` to `main <sha>` once merged.
- `CHANGELOG.md:16` — The new `[Unreleased]` bullet writes ``so old `docs/agents/...` paths no longer exist``, which introduces a literal `docs/agents` match outside historical entries. Fix (optional): rephrase without the literal path prefix if step 8 expects zero hits in new text.

## Checklist
- **Link remapping:** `.agents/README.md:5-6`, `AGENTS.md:7,238-246,265`, `CLAUDE.md:13,27`, `README_VI.md:10`, and `docs/SETUP-WINDOWS.md:3,83,87,181,194,197` remap root harness docs (`AGENTS-TUTORIAL.md`, `HERDR-CORE-BOT.md`, `BOT-CEO.md`, `../...` from `docs/`) and `docs/` guides (`docs/README.md`, `docs/SETUP-WINDOWS.md`, `docs/NVIDIA-BACKGROUND.md`, `docs/CLAUDE-ARCHITECT-CEO.md`, `OPENCODE-WORKERS-REVIEWER.md`, `NVIDIA-BACKGROUND.md`) consistently.
- **Orientation & counts:** `AGENTS.md:72-81` reflects the synced `docs/` guides, `docs/SETUP-WINDOWS.md`, `docs/superpowers/`, and root `*.md` harness files; `AGENTS.md:223,230-232` consistently report `464 passed, 11 skipped` and `97` harness lint tests.
- **Changelog & sdist:** `CHANGELOG.md:12-16` appends under `[Unreleased]` without altering prior history; `pyproject.toml:51-54` excludes `/tests/test_harness_markdown.py`, `/tests/test_harness_routing.py`, `/tests/test_guardrail_examples.py`, and `/tests/test_skill_routing.py`.
- **Hygiene & scope:** No secrets, personal paths, or other projects' names added (`docs/SETUP-WINDOWS.md:175` replaces a local path slug with `<project-folder-slug>`); `docs/SYSTEM_DESIGN_EN.md:3-6` and `docs/SYSTEM_DESIGN_VI.md:3-6` remove only MD001 trailing whitespace; all changed files are in scope.

## CEO triage
- Minor 1: the 'measured on' line is updated to a main SHA after the merge (CEO chore).
- Minor 2: the CHANGELOG bullet names the removed path on purpose (users need it); kept.
