---
id: api-2b
branch: feat/api-2b
tier: strong
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-2b: vocabulary + multi-site core in `CalibrationManager`

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` — read Vocabulary, Aggregated score,
API, Storage layout and "Decisions after the builder check" (items 2, 3, 5, 7, 10). Uses
`analysis/evaluate.py::evaluate` (merged). `SessionStore` (API-2a) is merged separately; this task must NOT
depend on it: accept any `store` object with `add_run(run_id, *, params, status, error, score, is_initial,
series, site_metrics, time=None)` (duck typing) and test with a fake store.

**Correction to design decision 3:** `run_batch` keeps returning a `pd.DataFrame` (existing callers rely on it);
it gains a `score` column and per-site columns. `run_iteration` keeps returning a `float`.

## Build
1. New pure module `spyswat/swat_calib/calibration/scoring.py`:
   ```python
   def normalise_observed(observed, outputs=None) -> tuple[dict, dict]   # -> (observed_dict, outputs_dict)
   def check_weights(weights, sites) -> dict                               # positive, known sites, sum 1
   def preflight(observed_dict, calib_period) -> None                      # each site overlaps calib_period,
                                                                           # non-zero variance; ValueError
   def score_sites(sim: dict, observed: dict, *, metric, metrics, weights, calib_period,
                   valid_period=None, freq=None, step=None, agg=None, warmup_end=None)
           -> tuple[float, dict]   # (score, {(var, reach): {"<metric>_calib": x, "<metric>_valid": y, ...}})
   ```
   - `normalise_observed`: bare Series → `{(var, reach): s}` using the single `(var, reach)` of `outputs`
     (default `{"FLOW_OUTcms": [1]}`); ValueError if `outputs` has several sites. Dict observed: keys missing
     from `outputs` are added. Returns outputs as `{var: [reaches]}`.
   - `score_sites` calls `evaluate()` once per period (`calib`, and `valid` when given); per-site metrics keep
     signed pbias; `score` = weighted mean over sites with weight > 0 of the calib objective, using `|pbias|`
     for pbias; any NaN site objective → NaN score. Warn (once per call) when `metric` is rmse/mae and the
     sites span more than one variable and `weights` is None.
2. `CalibrationManager` (keep every existing behaviour and test passing):
   - `warmup_end()` → `pd.Timestamp(IYR + NYSKIP, 1, 1)` from `project.FileCIO`.
   - `run_once(params, *, outputs=None, reach_id=<sentinel>, output_variable=<sentinel>, methods, subbasins)`:
     with `outputs` → `{(var, reach): Series}` with **real model dates** (`_to_model_dates`); without → old
     behaviour (Series). `DeprecationWarning` only when `reach_id`/`output_variable` are passed explicitly.
   - `run_iteration(param_dict, observed, metric=None, *, outputs=None, weights=None, metrics=None,
     calib_period=None, valid_period=None, step=None, agg=None, store=None, run_id=None, is_initial=False,
     reach_id=<sentinel>, output_variable=<sentinel>, methods=None, subbasins=None) -> float`.
     New path when `outputs`, a dict `observed`, `weights`, `calib_period` or `store` is given; otherwise the
     old single-site path unchanged. `calib_period=None` = whole overlap. Restore guarantees unchanged.
     With `store`, call `store.add_run(...)` once per run (after restore), `status` "ok"/"failed".
   - `run_batch(param_sets, observed, metrics=None, *, metric=None, outputs=None, weights=None,
     calib_period=None, valid_period=None, step=None, agg=None, store=None, run_ids=None, is_initial=False,
     reach_id=<sentinel>, output_variable=<sentinel>, methods=None, subbasins=None) -> pd.DataFrame`.
     Multi-site extraction inside the workers (module-level picklable extract over `outputs`). Results are
     kept in **submission order**. New columns: `score` and `<metric>@<var>@<reach>` (calib period) for each
     site and reported metric; existing columns unchanged for the old path. With `store`, `add_run` per run in
     submission order; `run_ids` default to consecutive integers continuing the store's/manager's counter.
   - `preflight` runs before any SWAT run in the new path.
   - The old flat `RunLog` logging keeps working for the old path; for the new path with `store`, the store
     is the log (do not also write the flat files).

## Files in scope
`spyswat/swat_calib/calibration/scoring.py` (new), `spyswat/swat_calib/calibration/calib_manager.py`,
`spyswat/swat_calib/calibration/run_log.py` (only if needed), `tests/test_scoring.py` (new),
`tests/test_calib_multisite.py` (new), `.agents/log/API-2B.md`.

## Acceptance criteria
- [ ] All existing tests pass unchanged (no edits to existing test files).
- [ ] New tests (fake runner / fake output.rch, no SWAT): two sites, two variables; weights; |pbias| in score,
      signed in site metrics; calib/valid metrics; NaN site → NaN score; preflight errors (no overlap, zero
      variance, bad weights); run_once dict with real dates; run_batch DataFrame columns + submission order +
      fake store receives runs in order; DeprecationWarning only for explicit old kwargs; TxtInOut restored.
- [ ] `python -m pytest tests/ -q -p no:cacheprovider` pass (baseline on main: 515 passed, 11 skipped);
      `git diff --check` clean.

## Report
Append to `.agents/log/API-2B.md`: files changed, commands + result lines, open questions. Commits `api-2b:`.
