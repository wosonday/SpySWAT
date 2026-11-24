# DOCS-5 — work log

## 2026-11-24 — steps 1–2 (CEO, commit `d313316`)

Copied the shared harness (`D:\.harnessing\agent-tutorial`) into the repository-root layout:
`AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md`, `AGM-UPGRADE-SPEC.md` at the root;
`docs/*.md` and `docs/superpowers/**`; `scripts/*.py`; `tests/*.py`. `git mv`ed
`docs/agents/SETUP-WINDOWS.md` to `docs/SETUP-WINDOWS.md` and `git rm -r docs/agents`.
Measured lint state after this step: 14 errors = 6 LINK007 (AGENTS.md x5, README_VI.md x1)
+ 8 MD001 (trailing whitespace in `docs/SYSTEM_DESIGN_EN.md` and `_VI.md`).

## 2026-11-24 — steps 3–8 (worker, tier mid)

Skill note: the task lists `skills: verification-before-completion`; no skill with that id is
installed in this worktree, so the intent (re-run every check, compare the copies, record
evidence, never report an unrun check as passed) was applied manually.

### Files changed (all inside the task scope)

- `AGENTS.md` — every `docs/agents/...` link/reference remapped (`AGENTS-TUTORIAL.md`,
  `HERDR-CORE-BOT.md`, `BOT-CEO.md`, `docs/README.md`, `docs/SETUP-WINDOWS.md`; background
  role row now points at `docs/NVIDIA-BACKGROUND.md`); the `docs/` part of the Quick
  orientation tree rewritten for the new layout (root rule docs listed after `docs/`); the
  "harness lint tests" sentence no longer mentions `docs/agents/`; Commands counts updated
  (see below).
- `CLAUDE.md` — `docs/agents/BOT-CEO.md` -> `BOT-CEO.md`,
  `docs/agents/models/CLAUDE-ARCHITECT-CEO.md` -> `docs/CLAUDE-ARCHITECT-CEO.md`.
- `README_VI.md` — quick-link row: `docs/agents/AGENTS-TUTORIAL.md` -> `AGENTS-TUTORIAL.md`.
- `CHANGELOG.md` — one new bullet under `[Unreleased]` > `Changed` describing the single
  harness copy and the removal of `docs/agents/`; no old entry rewritten.
- `.agents/README.md` — pointer lines now name `AGENTS-TUTORIAL.md` / `HERDR-CORE-BOT.md` /
  `BOT-CEO.md` at the root and the per-model guides in `docs/`.
- `.gitignore` — comment for the agent-workflow block no longer says `docs/agents/`.
- `docs/SETUP-WINDOWS.md` — only the path references: `../AGENTS-TUTORIAL.md`,
  `../HERDR-CORE-BOT.md` (x3), `OPENCODE-WORKERS-REVIEWER.md`, `NVIDIA-BACKGROUND.md`.
- `docs/SYSTEM_DESIGN_EN.md`, `docs/SYSTEM_DESIGN_VI.md` — trailing whitespace removed from
  the 4 header lines of each file (the 8 MD001 errors); no other edit.
- `pyproject.toml` — sdist `exclude` gains `/tests/test_skill_routing.py`.
- `.agents/log/DOCS-5.md` — this file.

### Commands and recorded output

Mapping check (step 1 acceptance, `diff -rq` equivalent via `git diff --no-index`, which is
the only comparable command this shell allows; no output for a pair = identical):

- `git diff --no-index --stat D:/.harnessing/agent-tutorial/docs docs` -> only files that have
  no harness counterpart are listed: `docs/SETUP-WINDOWS.md`, `docs/SYSTEM_DESIGN_EN.md`,
  `docs/SYSTEM_DESIGN_VI.md`, `docs/sample_run_parallel.py`, `docs/sample_run_scenarios.py`,
  `docs/sample_run_single.py`. Every harness doc and every `docs/superpowers/**` file is
  byte-identical.
- `git diff --no-index --stat D:/.harnessing/agent-tutorial/{BOT-CEO.md,HERDR-CORE-BOT.md,AGM-UPGRADE-SPEC.md}` vs the repo copies, and the same for `AGENTS-TUTORIAL.md` -> no output
  (identical).
- `git diff --no-index --stat D:/.harnessing/agent-tutorial/scripts scripts` -> only
  `scripts/__pycache__/*.pyc` differ (binary, excluded by the acceptance criterion).
- `git diff --no-index --stat` for `tests/test_harness_markdown.py`,
  `tests/test_harness_routing.py`, `tests/test_guardrail_examples.py`,
  `tests/test_skill_routing.py` -> no output (identical).

Full suite:

- `pytest tests/ -q` -> `464 passed, 11 skipped, 5 warnings, 28 subtests passed in 222.34s (0:03:42)`
  (baseline before the sync: 454 passed, 11 skipped; the extra 10 come from
  `tests/test_skill_routing.py` and the newer harness test files).
- `pytest tests/test_harness_markdown.py tests/test_harness_routing.py tests/test_guardrail_examples.py tests/test_skill_routing.py -q`
  -> `97 passed, 28 subtests passed in 8.61s` (was 87 harness tests).
- `git diff --check` -> no output.
- `git status --short` before the commit -> only the ten modified files above.
- `pytest tests/test_harness_routing.py -q -k "complete_fixture_passes or cli_json_and_exit_codes"`
  -> `2 passed, 35 deselected in 0.29s`: the lint functions and the `lint_harness.py` CLI
  (exit codes + JSON) used by the copied docs are proven on the harness fixture; the
  repository-level run is the only part left to the Auditor.

`AGENTS.md` Commands now read `# measured on feat/docs-5 (harness sync): 464 passed, 11 skipped
(~4 min on Windows)` and the paragraph below it now says `Of the 464 passing tests, 97 are
harness lint tests (tests/test_harness_*.py, tests/test_guardrail_examples.py,
tests/test_skill_routing.py)`.

- **Step 6 (lint) could not be run by this worker.** `python scripts/lint_harness.py`,
  `python -B scripts/lint_harness.py`, `python --version`, `python -c ...`, `py --version` and
  `diff --version` are all rejected by the worker shell permission (`permission.rejected`,
  non-interactive: no allow rule, and the run cannot ask). Only `pytest*` and
  `git status|diff|log|add|commit` execute. So `0 errors` is **not** claimed as a measured
  result. Evidence gathered instead:
  - the copied harness docs/scripts/tests are byte-identical to the shared harness, which is
    lint-clean (and the CEO measured only the 14 known errors after the copy);
  - all 6 LINK007 targets fixed and every new/changed link target exists
    (`AGENTS-TUTORIAL.md`, `HERDR-CORE-BOT.md`, `BOT-CEO.md`, `docs/README.md`,
    `docs/SETUP-WINDOWS.md`, `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`);
  - the 8 MD001 lines fixed; `grep '[ \t]+\r?$'` finds no trailing whitespace in any edited
    Markdown file; no new heading, table or fence was added to a checked document;
  - `docs/HARNESS-LINT.md` required documents are present (`docs/README.md`,
    `docs/HARNESS-LINT.md`, `AGENTS-TUTORIAL.md`, `BOT-CEO.md`, `HERDR-CORE-BOT.md`).
  Auditor/Reviewer should run `python -B scripts/lint_harness.py` (expected final line:
  `Harness lint: <n> documents, 0 errors.`) and record the line.

### Step 5 — personal machine paths / other projects in the copied harness text (reported, not edited)

- `docs/AGM-0.4.0-GUIDE.md:5` and `docs/superpowers/plans/2026-11-22-agm-mcp-branch-phase1.md:11`
  contain `D:\.harnessing\agent-tutorial\AGM-UPGRADE-SPEC.md` (the harness author's local path).
- `docs/AGM-0.4.0-GUIDE.md` also uses `D:\Project\agmag` and `D:\Project\shop\...` as generic
  example paths for another project.
- `docs/SETUP-WINDOWS.md` (SpySWAT-only, not copied harness text) keeps `D:\SWAT-model\SpySWAT`
  (lines 29, 100) and `~\.claude\projects\D--SWAT-model-SpySWAT\*.jsonl` (line 175).
- No secrets, watershed data or observation files found; the only other drive-letter paths in
  checked Markdown are the sanctioned `D:/SWAT/...` placeholders in the READMEs and the
  `D:\MyProject\...` samples in `docs/SYSTEM_DESIGN_*.md`.

### Step 8 — `docs/agents` search

`docs/agents/` is gone (`git` removal in `d313316`; no files under it). Remaining
`docs/agents` matches outside the harness documents:

- `.agents/tasks|log|reviews|decisions|reports` — history files, deliberately not edited;
- `CHANGELOG.md:124` — the historical 0.1.0 entry ("team workflow in `docs/agents/`");
- `CHANGELOG.md:15-16` — the new `[Unreleased]` bullet that says the path was removed.

No live link or path reference to `docs/agents/...` remains in `AGENTS.md`, `CLAUDE.md`,
`README_VI.md`, `.agents/README.md`, `.gitignore`, `docs/SETUP-WINDOWS.md`, `scripts/` or the
copied harness docs.

### Open questions

- `python` is not allowed by the worker shell, so the lint gate is unverified (see Step 6);
  the task brief said `python` would be allowed — the worker role permission may need the
  `python *` allow rule added.
- `AGENTS.md` Commands use `measured on feat/docs-5 (harness sync)` instead of
  `measured on main <sha>` because the sync is not merged yet; re-word after the merge if the
  team prefers a main SHA.
- Public-repository rule check: `docs/SETUP-WINDOWS.md` still names the local project path
  (`D:\SWAT-model\SpySWAT`) and the CLI project-folder name `D--SWAT-model-SpySWAT`. Left as
  is (only reported here); say if it should be generalised.
