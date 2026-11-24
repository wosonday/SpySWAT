# API-3B review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Verification Summary
- **Scope & AGENTS.md**: Only the files in scope were modified (plus `pytest.warns` wrappers in three existing test files without weakening assertions). All new messages/docstrings are English, no `TxtInOut` mutation or non-picklable callables were introduced, no secrets appear, and `-W error::DeprecationWarning:spyswat` passes (`625 passed, 11 skipped`).
- **Correctness (hand-checked)**: With 2-site `observed` and `metric="rmse"` (minimize), `GLUE`/`PSO`/`DE` pass `_reported(metric, metrics)` and `is_initial` (`True` only on GLUE samples, PSO/DE initial batch, DDS first call) to `run_batch`/`run_iteration`, extract `score` via `_batch_scores`, and rank via `to_objective`/`best_index` (lowest `rmse` wins; `NaN` excluded from behavioral mask in `GLUE.run` and ranked worst). For `pbias`, `score` carries `|pbias|` magnitude and `to_objective` preserves closest-to-zero selection. `seed=None` resolves via `SeedSequence().entropy % 2**63` before the first draw and replays identically.

## Critical
None.

## Major
None.

## Minor
- **`spyswat/swat_calib/analysis/sensitivity.py:98`** — `_batch_scores` passes `[metric] if metrics is None else list(metrics)` instead of `_reported(metric, metrics)`. Passing `metrics="kge"` splits into `['k', 'g', 'e']`, and passing `metrics=("kge",)` with `metric="nse"` omits `metric` from the reported list.
  - **Fix**: Import `_reported` from `spyswat.swat_calib.analysis.algorithms.dds` and pass `_reported(metric, metrics)`.
- **`tests/test_algorithms_vocabulary.py:316-322`** — `test_optimize_passes_new_vocabulary_through` leaves `seen = {}` unused and only asserts `call_count >= 1` (never verifying `weights`, `metric`, or `observed` reached `run_iteration`), and `SWATSensitivity` (`one_at_a_time`, `morris_method`, `morris_salib`, `sobol_method`) has no tests for the new vocabulary (`observed` dict, `weights`, `outputs`, `metrics`, old+new `TypeError`).
  - **Fix**: Assert forwarded kwargs in `test_optimize_passes_new_vocabulary_through` and add mocked `run_batch` tests for the four `SWATSensitivity` methods covering dict `observed`, `weights`, `metrics`, and old+new `TypeError`.
- **`spyswat/swat_calib/analysis/sensitivity.py:23`** — `_resolve_sens_observed` calls `_resolve_observed(..., stacklevel=3)` without passing `stacklevel=4`, so deprecation warnings from `SWATSensitivity` methods point inside `_resolve_sens_observed` rather than the caller.
  - **Fix**: Pass `stacklevel=4` to `_resolve_observed` inside `_resolve_sens_observed`.
- **`spyswat/swat_calib/analysis/algorithms/glue.py:106`** (also noted in `.agents/log/API-3B.md`) — `GLUE.run` resolves `seed` and passes it to `scipy.stats.qmc.LatinHypercube` rather than explicitly constructing `np.random.default_rng(seed)` and passing that `Generator` (`seed=rng`). Replay is deterministic for a fixed SciPy version, but passing `np.random.default_rng(seed)` aligns literally with the spec.
  - **Fix**: Pass `np.random.default_rng(seed)` into `_generate_samples` / `LatinHypercube(..., seed=rng)`.

## CEO: PASS; Auditor full suite on 1341385 = 625 passed, 11 skipped, 6 warnings. All four Minors go to follow-up API-3C (parallel with API-4, disjoint files).
