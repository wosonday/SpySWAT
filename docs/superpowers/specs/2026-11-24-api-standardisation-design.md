# API standardisation (0.3.0) — design

Date: 2026-11-24. Status: agreed with the user in discussion; execution authorised ("run until all 7 are done").
Owner: BOT-CEO. Routing: OpenCode workers implement, agy Hydrogen reviews, Neon for hard analysis, Opus last.

## Intent

The user runs calibration/validation ("HCKD") and future scenarios. They want:

- **short calls** for the everyday workflow, and
- **the same building blocks callable one by one** for testing and checking, with **the same parameter
  names**, so any result of a short call can be reproduced by hand.

Validation is not a separate operation: it is computing metrics of a simulated series on a chosen period.

## Goals

1. One parameter vocabulary for calibration, evaluation, sensitivity and scenarios.
2. Facade on `SWATProject`: `calibration`, `evaluate`, `sensitivity`, `scenarios`, `apply`.
3. Multi-station / multi-variable calibration (R-SWAT style): per-site metrics for every run + one
   aggregated score (mean, or user weights); runs sorted by score.
4. Warm-up guard; monthly evaluation of a daily simulation by aggregating the **simulation** only.
5. Storage of every run (run number, parameters, metrics, simulated series) in a per-session folder,
   one folder per station, one file per variable, one column per run.
6. Resume after interruption for **all** algorithms by replaying from the run log.
7. Several parameter sets out of a calibration (`top(n)`, `select(...)`) fed straight into scenarios.
8. Backward compatibility: old names keep working with `DeprecationWarning` until 0.4.0; migration notes.

Also: sensitivity computed from the calibration runs themselves (regression, SWAT-CUP style), so
sensitivity does not have to be re-run.

## Non-goals

- No renaming of modules or of the low-level primitives beyond what the vocabulary needs
  (`workingFolder_manager.py`, `one_at_a_time`/`morris_method` names stay; aliases may come later).
- No change to the strict file I/O, sandbox/backup rules, the metric registry, `name.ext` keys.
- No resampling or interpolation of observations, ever.
- No change of the simulation period during calibration (see Decisions).

## Anti-goals

- A short call that computes anything the building blocks cannot reproduce with the same arguments.
- A calibration or evaluation that silently leaves modified parameters in the user's TxtInOut.
- Metrics computed on warm-up years or on dates outside the simulation without an error.

## Vocabulary (binding)

| Name | Type | Meaning |
|---|---|---|
| `param_ranges` | dict | unchanged format (`AGENTS.md` rule 3) |
| `outputs` | `{variable: [reach, ...]}` | what is extracted from `output.rch`; if omitted and `observed` is a dict, derived from its keys |
| `observed` | `pd.Series` or `{(variable, reach): pd.Series}` | a bare Series means one site and needs exactly one `(variable, reach)` in `outputs` (default `{"FLOW_OUTcms": [1]}`) |
| `metric` | str | objective (one registry metric) |
| `metrics` | tuple[str] | reported metrics, default `("nse", "kge", "pbias", "r2")`; `metric` is always included |
| `weights` | `{(variable, reach): float}` | site weights for the aggregated score; default equal |
| `calib_period`, `valid_period` | `(start, end)` strings or Timestamps | `valid_period` optional |
| `periods` | `{name: (start, end)}` | used by `evaluate`; `None` = whole overlap |
| `step` | `None` or `"M"` | `"M"` aggregates the simulation to months before scoring |
| `agg` | `{variable: "mean" \| "sum"}` | aggregation per variable for `step="M"`; default mean (sum for `SED_*`, `*tons`, `*kg`) |
| `n_parallel`, `seed`, `results_dir`, `session`, `resume` | as today | `n_parallel` defaults to the project's |

Deprecated (accepted, mapped, `DeprecationWarning`, removed in 0.4.0): `observed_series` → `observed`;
`reach_id` + `output_variable` → `outputs={output_variable: [reach_id]}`.
`param_methods`/`param_subbasins` stay as they are.

## Aggregated score

Per site and period, every metric in `metrics` is computed with the registry. The objective per site is
`metric`; the aggregated `score` is the weighted mean of the per-site objective values, using `|pbias|`
for pbias (registry direction is respected: `score` has the direction of `metric`). Sampling algorithms
(GLUE/LHS) rank all runs by `score` after the batch; search algorithms (PSO/DE/DDS) use `score` during the
search. NaN for a site makes `score` NaN (failed run ranks worst, rule 7).

## API (facade on `SWATProject`)

```python
res = project.calibration(param_ranges, observed, calib_period, valid_period=None, *,
                          algorithm="glue", metric="nse", metrics=..., weights=None, outputs=None,
                          step=None, agg=None, n_parallel=None, seed=None, results_dir=None,
                          session=None, resume=True, sensitivity=True, **algorithm_options)
ev  = project.evaluate(sim, observed, periods=None, *, metrics=..., step=None, agg=None)
sens = project.sensitivity(param_ranges, observed, method="morris", *, from_session=None, ...)
batch = project.scenarios(scenarios, param_sets, outputs, observed=None, **options)  # ScenarioBatch.run
project.apply(params)   # the only facade call that writes parameters into TxtInOut (explicit)
```

- `evaluate` is **pure**: two series (or dicts of series keyed `(variable, reach)`), no SWAT run, no
  parameters. It checks the print step (rule 6), the warm-up and the period bounds, aligns with the
  existing `_align_series` logic and returns `EvaluationResult(table)`: rows `(variable, reach, period)`,
  columns metrics. A module-level `evaluate()` exists in `analysis/evaluate.py`; `project.evaluate` adds the
  project's print step and warm-up end (from `file.cio`: `IYR + NYSKIP`).
- `calibration` simulates the **whole `file.cio` period on every run** (user decision: the simulation is
  the slow part, so no extra validation run). The objective uses `calib_period`; calib **and** valid
  metrics are computed and stored for every run. The best run's series is evaluated with the same
  `evaluate` (calib + valid). TxtInOut is never modified (workers / sandbox).
- `calibration(sensitivity=True)` returns `res.sensitivity`: OLS regression of `score` on the
  parameters scaled to [0, 1], t-stat, p-value, rank by |t|, failed runs dropped. GLUE/LHS: all runs.
  PSO/DE/DDS: only the initial random population (noted in the result). `project.sensitivity(...,
  from_session=...)` recomputes it from a saved session without running SWAT; other methods
  (morris/sobol/oat) run as today.
- `CalibrationResult`: `best_params`, `best_score`, `best_run_id`, `runs` (DataFrame), `metrics`
  (best run, per site and period), `sensitivity`, `session_dir`; `top(n)` and `select(**conditions)`
  (e.g. `select(nse__gt=0.5)`, metric on calib period unless `period=` given) return
  `ParamSet` objects named `run_<id>`; `CalibrationResult.load(session_dir)`; dict-style access to
  `best_params`, `best_score`, `history` keeps old callers working.
- `project.scenarios` accepts `ParamSet`s, a `CalibrationResult` (its best) and lists from `top/select`.

## Storage layout (per calibration session)

```
<results_dir>/<session>/          default session: <YYYYMMDD_HHMMSS>_<algorithm>_<metric>
  session.json                    signature: algorithm, options, param_ranges, seed, metric(s), weights,
                                  periods, step, observed hashes, library version
  runs.csv                        one row per run: run_id, time, status, error, parameters..., score
  best.csv                        best parameters
  sensitivity.csv
  reach_<id>/
    <variable>.csv                rows = dates, columns = run_<n> (simulated series)
    metrics.csv                   one row per run: run_id, <metric>_calib, <metric>_valid, ...
```

Written in batches (every `n_parallel` runs or ~10 s, and on any exit), as `ScenarioBatch` does;
locked files are buffered and warned once (rule 10). More than 16 000 run columns → `<variable>_part2.csv`.
`RunLog` keeps `record_run()` for custom callers; its old flat `<session>_metrics.csv`/`_outputs.csv`
remain for the low-level primitives, the facade uses the session layout.

## Resume by replay

With the same `session` and `resume=True`, `session.json` must match (else `ValueError`, like scenarios).
The manager keeps a cache `parameter vector → stored result` loaded from `runs.csv` + the series files;
algorithms run again from the start with the same seed and propose the same parameter sets, which are
answered from the cache without running SWAT until the first missing run. Requirements: algorithms draw
randomness only from `np.random.default_rng(seed)`; parameters are logged with `repr`-exact floats; batch
results are consumed in submission order. Cache misses on a vector that should exist are an error, not a
silent re-run.

## Constraints

- AGENTS.md key design rules 1–12 stay binding (picklable workers, English messages, strict I/O,
  explicit failures, one metric registry).
- Windows spawn; tests never need `swat.exe` (fake runners / mocked `run_batch`).
- Public repo: synthetic fixtures only.

## Approaches

1. One big 0.3.0 branch — one migration, but a huge diff that is hard to review.
2. **Three phases in dependency order (chosen by the user)** — each phase usable on its own.
3. Facade only, translating to the old names — rejected: the building blocks would keep different names,
   which defeats the "reproduce by hand" need, and multi-site storage needs `RunLog` changes anyway.

## Phases and tasks

| Phase | Task | Content | Depends on |
|---|---|---|---|
| 1 | API-1 | `analysis/evaluate.py`: pure `evaluate`, periods, warm-up guard, `step="M"` + `agg` | — |
| 1 | API-2 | vocabulary + multi-site core in `CalibrationManager` (`run_once/run_iteration/run_batch` take `outputs`/`observed`/`weights`, per-site metrics, `score`) and the session storage writer | — |
| 2 | API-3a | `analysis/regression_sensitivity.py`: pure OLS sensitivity on a runs DataFrame | — |
| 2 | API-3b | algorithms (GLUE, PSO, DE, DDS), `SWATSensitivity`, `SWATCalibration`, `ValidationRunner` adopt the vocabulary; deprecated kwargs | API-2 |
| 2 | API-4 | facade on `SWATProject` + `CalibrationResult` (`load`, `top`, `select`) + `scenarios` accepting results | API-1, API-3a, API-3b |
| 3 | API-5 | resume by replay | API-4 |
| 3 | API-6 | docs, samples, CHANGELOG migration section, version 0.3.0 | API-5 |

## Left to the builder

Internal helper names, exact module split inside the files listed per task, test layout, the CSV
float formatting used to make replay exact (must be `repr`-round-trippable).

## Decisions after the builder check (Neon, 2026-11-24; CEO calls, within what the user agreed)

1. **Per-variable metric files:** `reach_<id>/<variable>_metrics.csv` (one row per run) next to
   `reach_<id>/<variable>.csv`; no shared `metrics.csv` per reach.
2. **One metric implementation:** `CalibrationManager` computes every per-site/period metric by calling
   `analysis.evaluate.evaluate()`; API-2 therefore depends on API-1.
3. **Primitive return types:** `run_iteration` → `float` (`score`), `run_batch` → `list[float]`;
   per-site results go to the session store. `run_once(outputs=...)` → `{(variable, reach): Series}`;
   the deprecated `reach_id`/`output_variable` path keeps returning a `Series`.
4. **`apply`:** `project.apply(x, methods=None, subbasins=None)` takes a `ParamSet`, a
   `CalibrationResult` (its best) or a dict. Methods and subbasins are stored in `session.json` and in
   `ParamSet`s from `top/select`; a dict whose calibration used non-`"v"` methods without `methods=` raises.
5. **Warm-up and months:** warm-up end = `Timestamp(IYR + NYSKIP, 1, 1)`. `step="M"` resamples the
   simulation with `"MS"`; default `agg` by `fnmatch` (`SED_*`, `*tons`, `*kg` → sum, else mean);
   user `agg` wins.
6. **`select`/`top`:** `select(score__gt=0.5)` or `select(nse__gt=0.5, site=(var, reach), period="calib",
   how="all"|"any")` with operators `gt/gte/lt/lte`; default `how="all"` over calibrated sites, period
   `calib`. `top(n)` drops failed/NaN runs, best first.
7. **Sessions:** `results_dir` default `<working_dir>/calibration_results`; `session=None` creates a new
   timestamped folder; an existing session with `resume=False` raises `FileExistsError`. `outputs` may be a
   superset of `observed` (ungauged sites stored without metrics); observed keys missing from `outputs` are
   added. `project.sensitivity(from_session=...)` needs no `param_ranges`/`observed`.
8. **Hashing / loading:** observed hash = SHA-256 over sorted `(variable, reach)` + ISO index + float64
   bytes. `CalibrationResult.load` reads metadata eagerly, series lazily.
9. **Replay (API-5):** `seed=None` is resolved to a concrete integer before run 1 and stored. Replay uses an
   **ordered cursor** (run k of the new execution must equal stored row k exactly, else
   `ResumeMismatchError`), not a dict lookup. Floats written with `repr`, read with stdlib `csv` +
   `float()`; `-0.0` normalised to `0.0`. Batch results are collected in submission order; series and
   metric files are committed before the batch's rows are appended to `runs.csv` (temp + `os.replace`);
   an uncommitted tail is discarded on resume. Failed runs are replayed as failed (never silently retried).
   `session.json` stores seed, `on_failure`, `n_parallel`, parameter order, numpy version.
10. **Score:** per-site metric files keep **signed** pbias; `|pbias|` only inside `score`. `score` uses the
    calib period and sites with weight > 0 only. Weights must be positive, known sites, normalised to sum 1.
    Warn when `rmse`/`mae` are aggregated across different variables without explicit weights. Before any
    SWAT run, each observed site must overlap `calib_period` and have non-zero variance (fail fast).
11. **Regression sensitivity:** `runs.csv` has `is_initial` (True for GLUE/LHS rows and the initial random
    population of PSO/DE/DDS). The result also reports `r2`, `n_used`, `n_dropped`; collinear or constant
    parameters get `t=0, p=NaN` instead of an error inside `calibration()`; when `n_used < k + 2` the
    facade stores a status "insufficient runs" instead of failing; warn when `n_used < max(20, 3k)` or
    `r2 < 0.3`. (API-3a raises on these cases; API-4 turns the error into the status.)
12. **Exports:** `analysis/__init__.py` re-exports are allowed in API-1/API-3a (one line each); a trivial
    merge conflict there is resolved at merge time.
