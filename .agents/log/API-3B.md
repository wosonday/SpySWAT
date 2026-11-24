# API-3B — algorithms and legacy facades adopt the vocabulary

## Report (worker-strong)

### Files changed
- `spyswat/swat_calib/analysis/algorithms/dds.py` — shared vocabulary helpers
  (`_MISSING`, `_resolve_seed`, `_resolve_observed`, `_reported`, `_batch_scores`,
  `_params_frame`, `_runs_frame`, `_single_site`); `DDSCalibration.run` renamed 2nd
  positional `observed_series` → `observed`, new keyword-only `outputs/weights/metrics/
  calib_period/valid_period/step/agg/store`, deprecated mapping, `seed` resolution,
  `is_initial` on the first evaluation, `runs` + `seed` in the result.
- `spyswat/swat_calib/analysis/algorithms/glue.py` — `GLUE.run` + `GLUE.uncertainty_band`
  adopt the vocabulary; `is_initial=True` for all samples; `runs` (params + score + per-site);
  `seed` resolved and returned.
- `spyswat/swat_calib/analysis/algorithms/pso.py` — `PSOCalibration.run` (initial swarm
  `is_initial=True`, later iterations `False`; `runs` DataFrame; `seed`).
- `spyswat/swat_calib/analysis/algorithms/parallel_de.py` — `ParallelDE.run` (initial
  population `is_initial=True`; `runs`; `seed`).
- `spyswat/swat_calib/analysis/calibration.py` — `SWATCalibration.optimize` / `analyze`
  renamed + deprecated mapping + new vocabulary passed through (fixed a local-var `step`
  shadowing the new keyword-only `step`).
- `spyswat/swat_calib/analysis/sensitivity.py` — `one_at_a_time`, `morris_method`,
  `morris_salib`, `sobol_method` renamed + deprecated mapping; `_batch_scores` /
  `_sequential_mean` use the new vocabulary (no internal DeprecationWarning).
- `spyswat/swat_calib/calibration/validation_runner.py` — `DeprecationWarning` on
  construction ("use project.calibration(...)"), and its validation run now reads via
  `run_once(outputs=...)` so the deprecated path is not exercised internally.
- `tests/test_algorithms_vocabulary.py` (new) — 33 tests (mocked `run_batch`/`run_iteration`,
  no SWAT).
- Test files changed **only** to silence expected `DeprecationWarning`s:
  `tests/test_metrics.py` (one `uncertainty_band` call), `tests/test_sensitivity.py`
  (4 `observed_series=` calls), `tests/test_calib_manager.py` (one `ValidationRunner`
  construction). No assertion weakened.

### Commands + result lines
- `python -m pytest tests/test_metrics.py tests/test_calibration.py tests/test_parallel_de.py tests/test_dds.py tests/test_sensitivity.py -q -p no:cacheprovider`
  → `133 passed, 6 skipped` (existing algorithm/sensitivity suite green after the migration).
- `python -m pytest tests/test_algorithms_vocabulary.py -q -p no:cacheprovider`
  → `33 passed`.
- `python -m pytest tests/ -q -p no:cacheprovider`
  → `625 passed, 11 skipped, 28 subtests passed` (baseline on main: 592 passed, 11 skipped;
  +33 new tests).
- `python -m pytest tests/ -q -p no:cacheprovider -W error::DeprecationWarning:spyswat`
  → `625 passed, 11 skipped` — no library code path emits a `DeprecationWarning` on its own;
  the only reported deprecation is `tests/test_run_once.py` (a pre-existing direct call to
  the manager's deprecated `run_once` path).
- `git diff --check` → clean (no output).

### Decisions / deviations (documented for the reviewer)
1. **Shared helpers live in `dds.py`.** The task's file list has no new module, so the
   vocabulary helpers (`_resolve_observed`, `_resolve_seed`, `_batch_scores`, `_runs_frame`,
   `_reported`, `_single_site`, `_MISSING`) are defined in `dds.py` (the leaf module of
   `algorithms/`, no sibling imports) and imported by `glue`, `pso`, `parallel_de`,
   `calibration` and `sensitivity`. No import cycle.
2. **`run_batch` is called with the reported metric list positionally** (3rd arg) so the
   existing single-site mocks (`batch_fn(param_sets, obs, metrics, ...)` and `make_mock`) keep
   recovering the metric name, while `metric=`/`outputs=`/`weights=`/… are passed as keywords so
   the manager routes to the multi-site path. Ranking reads the `score` column (with a legacy
   fallback to the bare `metric` column for old-style mocks), always via `best_index` /
   `to_objective` — never a hard-coded "higher is better".
3. **`seed=None`** is resolved to `int(np.random.SeedSequence().entropy % 2**63)` before the
   first draw and returned as `result["seed"]`; GLUE keeps its seeded LHS (`_generate_samples`,
   `scipy.stats.qmc`) which is deterministic for the same seed.
4. **`runs` DataFrame** = params (raw floats) + `score` + per-site columns, in submission order.
   For DDS (which evaluates via `run_iteration`, returning only a float) `runs` is derived from
   the DDS `history` (params + `score`); no per-site columns are available there.
5. **`uncertainty_band`** remains single-site: a bare `observed` Series needs exactly one site
   in `outputs`; a dict `observed` uses its first site (and ensures that site is in `outputs`).
6. **Sensitivity no-observation path** (`_sequential_mean`) reads the single series via
   `_apply_and_run` + a direct `read_rch` instead of `run_once(outputs=...)`, so it neither
   triggers the multi-site date handling (needs `FileCIO`) nor the deprecated `run_once`
   warning.

### Open questions
- None blocking. GLUE's LHS draws from `scipy.stats.qmc` (seeded) rather than strictly
  `np.random.default_rng(seed)`; replay-equivalence for a fixed seed holds either way, but if
  the reviewer wants a literal "only `np.random.default_rng`" reading for GLUE, that is a
  follow-up (would change the LHS sample values).
