# API standardisation 0.3.0 — final report (BOT-CEO, 2026-11-25)

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md`. All tasks merged on `main` (c207e6c):
`721 passed, 15 skipped` (also with `-W error::DeprecationWarning:spyswat`), harness lint 0 errors.

| Task | Content | Review rounds (model) |
|---|---|---|
| API-1 | pure `evaluate()` (periods, warm-up, monthly aggregation of the simulation) | 3 (Hydrogen) |
| API-2a | `SessionStore` (session folder, exact floats, torn tail, locked files) | 2 (Hydrogen) |
| API-2b/2c/2d | multi-site core in `CalibrationManager`; fail-fast; hotfix raw params in the store | 2 / 1 / 1 |
| API-3a | regression sensitivity from calibration runs | 1 + minor rework |
| API-3b/3c | algorithms + legacy facades on the vocabulary; reported metrics, GLUE rng | 1 / 1 |
| API-4 | `SWATProject.calibration/evaluate/sensitivity/scenarios/apply`, `CalibrationResult` | 3 (Hydrogen, Neon, Neon) |
| API-5a/5b | resume by replay (cursor, manager, algorithms, facade) | 1 / 1 + minor rework (Neon) |
| API-6 | README/README_VI, samples, CHANGELOG 0.3.0 + migration, AGENTS.md | 2 (Neon) |

Routing used: OpenCode workers (Flash fast/mid, Pro strong) → CEO audit (full pytest) → agy Hydrogen High review
(Neon for high-risk tasks and for code written by Hydrogen) → copilot-git merge briefs MERGE-8..19.
Neon also did the design builder check and the API-5 pre-review (found the formatted-params bug → API-2d).
When OpenCode Go hit its 5 h limit, agy Hydrogen (accept-edits, no shell) finished API-4 rework and API-6 docs.
Log summaries: NVIDIA Mistral Large 4 (Nemotron/Kimi timed out on long prompts).

## Not done / for the user
- Push (local only), release tag, and a run on a real SWAT project (tests use fake runners only).
- The three uncommitted files in the main checkout (`swat_base/parameters.py`, `core/__init__.py`,
  `core/hru_manager.py`) are not from this batch and were never staged.
- Worktrees `.wt/api-*`, `.wt/docs-5`, `.wt/harn-2` can be removed.
