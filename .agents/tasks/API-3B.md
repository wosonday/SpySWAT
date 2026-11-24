---
id: api-3b
branch: feat/api-3b
tier: strong
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-3b: algorithms and legacy facades adopt the vocabulary

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` (Vocabulary, Aggregated score,
Resume by replay, decisions 3, 9, 10, 11). Builds on API-2b (merged): `CalibrationManager.run_iteration/
run_batch(..., outputs, weights, metric, metrics, calib_period, valid_period, step, agg, store, run_ids,
is_initial)` and the `score` column.

## Build
1. `GLUE.run`, `PSOCalibration.run`, `ParallelDE.run`, `DDSCalibration.run` (and `GLUE.uncertainty_band`):
   - second positional parameter renamed `observed` (Series or `{(variable, reach): Series}`); new keyword-only
     `outputs, weights, metrics, calib_period, valid_period, step, agg, store`.
   - deprecated keywords still accepted, mapped, one `DeprecationWarning` each: `observed_series` → `observed`,
     `reach_id` + `output_variable` → `outputs={output_variable: [reach_id]}`. Passing both old and new → TypeError.
   - every model evaluation goes through `manager.run_batch` / `run_iteration` with the new vocabulary; ranking
     and best selection use the `score` column with the registry direction of `metric` (`best_index`,
     `to_objective`) — never hard-code "higher is better".
   - `is_initial=True` for: all GLUE samples; PSO initial swarm; DE initial population; DDS first evaluation.
   - randomness only from `np.random.default_rng(seed)`; `seed=None` is resolved to a concrete int before the
     first draw (`int(np.random.SeedSequence().entropy % 2**63)`) and returned as `result["seed"]`.
   - returned dict keeps every existing key; adds `"seed"`, `"runs"` (DataFrame of all evaluations in submission
     order with params, `score` and per-site columns) when available.
2. `SWATCalibration.optimize/analyze`, `SWATSensitivity.one_at_a_time/morris_method/morris_salib/sobol_method`:
   same renaming + deprecated mapping; pass the new vocabulary through.
3. `ValidationRunner`: `DeprecationWarning` on construction ("use project.calibration(...)"); behaviour unchanged.
4. Internal callers in the library must use the new names (no DeprecationWarning from library code paths).

## Files in scope
`spyswat/swat_calib/analysis/algorithms/{glue,pso,parallel_de,dds}.py`, `spyswat/swat_calib/analysis/{calibration,
sensitivity}.py`, `spyswat/swat_calib/calibration/validation_runner.py`, new tests
`tests/test_algorithms_vocabulary.py`, `.agents/log/API-3B.md`. Existing test files may only be changed to silence
expected DeprecationWarnings with `pytest.warns`/`filterwarnings` — never to weaken an assertion.

## Acceptance criteria
- [ ] New tests (mocked `manager.run_batch`, no SWAT): each algorithm with a 2-site dict `observed` + weights
      selects the best by `score` (incl. a minimise metric such as rmse); same seed → identical sequence of
      proposed parameter sets (two runs compared); `seed=None` returns a concrete int and re-running with it gives
      the same sequence; `is_initial` flags as listed; old kwargs → DeprecationWarning + same result; old+new → TypeError.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider -W error::DeprecationWarning:spyswat` passes except tests that
      deliberately exercise the deprecated path (they assert the warning) — i.e. library code emits none on its own.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider` all pass (record counts); `git diff --check` clean.

## Report
Append to `.agents/log/API-3B.md`: files changed, commands + result lines, open questions. Commits `api-3b:`.
