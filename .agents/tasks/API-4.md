---
id: api-4
branch: feat/api-4
tier: strong
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-4: facade on `SWATProject` + `CalibrationResult`

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` — sections API, Storage layout and
decisions 4, 6, 7, 8, 10, 11. Builds on merged: `analysis.evaluate`, `analysis.regression_sensitivity`,
`calibration.session_store.SessionStore`, `calibration.scoring`, the new `CalibrationManager` vocabulary, and the
algorithms with `store`/`is_initial`/`seed` (API-3b).

## Build
1. `spyswat/swat_calib/calibration/result.py` — `CalibrationResult`:
   fields `best_params, best_score, best_run_id, metric, runs (DataFrame), metrics (EvaluationResult.table of the
   best run, calib + valid), sensitivity (DataFrame | None), sensitivity_status (str), session_dir, seed,
   algorithm, methods, subbasins`; dict-style `res["best_params"|"best_score"|"history"]` (history = runs);
   `top(n)` (drops failed/NaN, best first by registry direction) and `select(**conditions)` per decision 6 →
   `list[ParamSet]` named `run_<id>` carrying methods/subbasins; `best_param_set()`; `CalibrationResult.load(
   session_dir)` (metadata eager, series lazy via `SessionStore.series`).
2. `SWATProject` methods:
   - `calibration(param_ranges, observed, calib_period, valid_period=None, *, algorithm="glue", metric="nse",
     metrics=("nse","kge","pbias","r2"), weights=None, outputs=None, step=None, agg=None, n_parallel=None,
     seed=None, results_dir=None, session=None, resume=True, sensitivity=True, param_methods=None,
     param_subbasins=None, **algorithm_options) -> CalibrationResult`.
     algorithm ∈ {"glue","pso","de","dds"} → the existing classes. Creates the session folder (default name
     `<YYYYMMDD_HHMMSS>_<algorithm>_<metric>` under `results_dir` default `<working_dir>/calibration_results`),
     a `SessionStore` with the signature of decision 9 (seed resolved first), runs the algorithm with `store`,
     then: best run → `evaluate` of its stored series (calib + valid, using the project's print step and
     `warmup_end`) → `res.metrics`; `regression_sensitivity` on `is_initial` rows when `sensitivity=True` (errors
     become `sensitivity_status`, never an exception; warnings per decision 11) → `sensitivity.csv`;
     `best.csv`; store closed in `finally`. Existing session: `resume=False` → FileExistsError; `resume=True` →
     `NotImplementedError("resume by replay arrives in API-5")` for now. Never modifies TxtInOut.
   - `evaluate(sim, observed, periods=None, **kw)` → `analysis.evaluate` with the project's print step (IPRINT)
     and `warmup_end` filled in.
   - `sensitivity(param_ranges=None, observed=None, method="morris", *, from_session=None, **options)`:
     `from_session` → regression sensitivity from that session (no SWAT); otherwise method ∈ {"oat","morris",
     "morris_salib","sobol","regression"} dispatches to `SWATSensitivity` (regression = run a GLUE/LHS sample
     first, small helper ok).
   - `scenarios(scenarios, param_sets, outputs, observed=None, results_dir=None, **options)` →
     `ScenarioBatch(self, results_dir or <working_dir>/scenario_results).run(...)`; `param_sets` may mix
     `ParamSet`, `CalibrationResult` (its best) and lists from `top/select`.
   - `apply(x, methods=None, subbasins=None)` — the only facade call writing TxtInOut; accepts ParamSet /
     CalibrationResult / dict per decision 4; logs a warning that TxtInOut was changed.
3. Exports: `CalibrationResult` from `spyswat.swat_calib.calibration`, and from `spyswat/__init__.py` if it
   exports public names.

## Files in scope
`spyswat/swat_calib/calibration/result.py` (new), `spyswat/swat_project.py`, `spyswat/swat_calib/calibration/__init__.py`,
`spyswat/swat_calib/scenarios/{model,batch}.py` (only to accept results as param sets), `spyswat/__init__.py`
(exports only), new tests `tests/test_project_facade.py`, `tests/test_calibration_result.py`, `.agents/log/API-4.md`.

## Acceptance criteria
- [ ] End-to-end with a fake runner (no SWAT): `project.calibration(... algorithm="glue", n_samples=8, seed=1)` on a
      2-site dict creates the exact session layout, returns best by score, `res.metrics` has calib+valid rows,
      `res.sensitivity` or a status; same with "pso" (tiny) and "dds" (tiny); TxtInOut byte-identical afterwards.
- [ ] `CalibrationResult.load(session_dir)` equals the returned result (params, scores, runs); top/select incl.
      minimise metric; scenarios accepts result/top lists (mock `ScenarioBatch.run` to check the ParamSets);
      apply writes and warns; dict input with non-"v" methods and no `methods=` raises.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider` pass (record counts; main baseline 628 passed, 11 skipped); `git diff --check` clean.

## Report
Append to `.agents/log/API-4.md`: files changed, commands + result lines, open questions. Commits `api-4:`.
