---
id: merge-1
branch: fix/phase1-correctness
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# MERGE-1: commit the verified working tree and merge `fix/phase1-correctness` into `main`

Owner: `copilot-git` (GitHub Copilot CLI, terminal `t4q`). Requested by the user on
2026-11-20 ("giao cho copilot để triển khai merge branch").

## Gate status (read first)

- Verified by the Architect on this exact working tree:
  - `pytest tests/ -q` → **327 passed, 11 skipped, 0 failed**;
  - `git diff --check` → exit 0;
  - scenario tests 5/5 green.
- **Not run**: the Auditor gate and a formal Reviewer pass on committed diffs. The working-tree
  pre-review is `.agents/reviews/coord-1-1.md`, and its blockers are now fixed. The user
  authorized the merge with this status; record it in the merge commit body.

## Steps

1. On `fix/phase1-correctness`, run `git status --short`. It must list only the paths below
   (plus nothing else). Anything unexpected → stop and report; do not commit it.
2. Create these four commits, in order, staging **exactly** these paths (no `git add -A`).
   End each message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

   **C1** `REV-1: fix PHASE1-1 findings 1-6, 9, 10 and OPT-1 optimize method/max_iter`

   This commit includes OPT-1 because `tests/test_metrics.py` holds tests for both.
   - `spyswat/swat_calib/analysis/statistics.py`
   - `spyswat/swat_calib/analysis/sensitivity.py`
   - `spyswat/swat_calib/analysis/calibration.py`
   - `spyswat/swat_calib/analysis/algorithms/parallel_de.py`
   - `spyswat/swat_calib/analysis/algorithms/pso.py`
   - `spyswat/swat_calib/calibration/calib_manager.py`
   - `spyswat/swat_calib/calibration/validation_runner.py`
   - `spyswat/swat_calib/scenarios/batch.py`
   - `spyswat/swat_calib/scenarios/model.py`
   - `spyswat/swat_project.py`
   - `tests/test_calib_manager.py`
   - `tests/test_calibration.py`
   - `tests/test_metrics.py`
   - `tests/test_project.py`
   - `tests/test_sensitivity.py`
   - `.agents/tasks/REV-1.md`
   - `.agents/tasks/OPT-1.md`
   - `.agents/log/REV-1.md`
   - `.agents/log/OPT-1.md`
   - `.agents/reviews/PHASE1-1.md`
   - `.agents/decisions/ARCH-1.md`

   **C2** `REV-1: docs: signed-infinity penalty and optimize method in README/CHANGELOG`
   - `README.md`
   - `README_VI.md`
   - `CHANGELOG.md`

   **C3** `TEST-1: per-worker trace files in the scenario test fixture`
   - `tests/test_scenarios.py`
   - `.agents/tasks/TEST-1.md`
   - `.agents/log/TEST-1.md`

   **C4** `DOCS-4: docs: adopt team workflow v3.6 (models/, routing, budget)`

   This commit also carries the DOCS-2, DOCS-3 and coord-1 notebook files.
   - `AGENTS.md`
   - `CLAUDE.md`
   - `.gitignore`
   - `.agents/README.md`
   - `.agents/templates/`
   - `.agents/bot.env` (non-secret settings, checked)
   - `.opencode/`
   - `docs/agents/`
   - `.agents/log/DOCS-2.md`
   - `.agents/log/DOCS-3.md`
   - `.agents/log/DOCS-4.md`
   - `.agents/tasks/DOCS-4.md`
   - `.agents/tasks/MERGE-1.md`
   - `.agents/tasks/coord-1.md`
   - `.agents/log/coord-1.md`
   - `.agents/reports/coord-1.md`
   - `.agents/reviews/coord-1-1.md`

3. `git status --short` must now be empty.
4. Gate on the branch head:
   - `python -m pytest tests/ -q` → expect 327 passed / 11 skipped / 0 failed (about 5 min);
   - `git diff --check main...HEAD`.

   Any failure → stop and report. Never edit code or tests to make it pass.
5. Merge locally:
   - `git fetch origin`. If local `main` is behind `origin/main`, fast-forward it first
     (`git switch main && git merge --ff-only origin/main`). If they diverged, stop and report.
   - `git switch main && git merge --no-ff fix/phase1-correctness`. Message:
     `Merge fix/phase1-correctness: phase-1 correctness, REV-1/OPT-1/TEST-1, workflow v3.6`.
     Add the gate status above to the body.
6. Post-merge audit on `main`: `python -m pytest tests/ -q` gives the same counts.
7. **Do not push, tag, release, or delete the branch.** Ask the user:
   `agm send user --type HỎI --task merge-1 "Merged locally at <sha>; push main + delete branch?"`.
8. Report to the Architect (Claude, terminal `t16`):
   `hc send t16 "[BÁO CÁO merge-1] merged <sha> on main; pytest <counts>; push pending user"`.
   Use `hc send` because `agm send` refuses recipients whose state is `done`.

## Next

After the merge SHA is reported, the Architect opens `feat/ARCH-1` from `main`
(`.agents/decisions/ARCH-1.md`, approved 2026-11-20).
