# CHANGELOG

All notable changes to SpySWAT are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed

- `ScenarioBatch.run()` now uses one process pool (`ProcessPoolExecutor`) for the whole
  batch via `scenarios/scheduler.py` (`Scheduler`, `Slot`): a free slot takes the next
  pending job (same base TxtInOut first, otherwise re-copied), using at most `n_parallel`
  worker folders (`TxInOut1`..`TxInOutN`). Results are saved as they arrive (every
  `n_parallel` results or 10 s) and on any exit; a broken worker pool or an unreadable
  `weather_dir` fails the affected jobs and `run()` still returns (`resume=True` re-runs
  them).
- `ScenarioBatch.run(resume=True)` now also raises `ValueError` when an input file of a
  scenario's base TxtInOut (`txinout_dir` or the project's default `TxtInOut`) was added,
  removed, resized, or re-written since the stored run (tracked via `scenario_inputs` in
  `.signature.json` using file stats, not contents; `output.*`, `watout.dat`, and the worker
  manifest are ignored). Results written by 0.2.6 (without `scenario_inputs`) still resume
  with one INFO log line, and an unreadable base directory yields an `unreadable:<Error>`
  sentinel rather than aborting the batch. New module: `spyswat/swat_calib/scenarios/signature.py`
  (`txinout_fingerprint()`).

---

## [0.2.6] – 2026-11-21

Phase-1 correctness work: SWAT runs, file I/O and metrics now fail loudly instead of
silently returning wrong numbers. This release also ships PSO (developed 2026-06-18, see
below); no package was published between 0.2.4 and 0.2.6.

### Added

- `CalibrationManager.run_once()` — the shared sequential update/run/freshness/read
  primitive; `sandbox(names=None)` restores input files on exit, including exceptions.
  Compose them when inputs must be restored; `run_once()` itself does not back up,
  compute metrics or append a run log.
- `StaleOutputError(RuntimeError)` in `core/run_state.py` identifies runs that did not
  produce a fresh `output.rch`.
- **`ScenarioBatch`** (`spyswat.swat_calib.scenarios`) — runs *scenarios × parameter sets*
  over the parallel workers. `Scenario` is a separate TxtInOut folder or a weather-file
  overlay plus an optional `file.cio` override (`cio={"IYR": 2030, ...}`); `ParamSet` comes
  from a dict or a DataFrame. Full product or explicit `pairs`, one series CSV per job,
  `summary.csv` + metrics, failure isolation, `resume=True` (refuses a changed configuration).
  `Scenario(evaluate=False)` for future/GCM runs: series written, no metrics, no
  observation-step check. Example: `docs/sample_run_scenarios.py`.
- **Per-run result log** — `CalibrationManager` appends `<session>_metrics.csv` (status,
  parameter values/methods/full spec, metrics) and `<session>_outputs.csv` (target series,
  long format) under `<working_dir>/calibration_results` after every sequential, parallel,
  validation, GLUE-uncertainty and sensitivity run. `manager.log_outputs = "all" |
  "observed" | "none"`, `manager.results_dir` (None disables), `record_run()` for custom
  algorithms, `flush_log()`, `session_files`.
- `ValidationRunner` saves `<session>_best_params.csv` and `<session>_validation.csv`.
- `check_observation_step(obs_index, sim_freq)` — rejects daily vs monthly mismatch and
  month-end dated monthly observations.
- Metric registry in `analysis/statistics.py`: `METRIC_DIRECTIONS`, `known_metrics`,
  `is_maximize`, `worst_score`, `to_objective`, `sanitize_scores`, `best_index`.
- `on_failure="raise" | "penalize"` for `SWATCalibration.optimize` and `DDSCalibration.run`.
- `HRUManager.validate_inputs()`, `FileCIO.set(**values)`, `OutputFileManager.invalidate()`
  and `check_complete()`, verified `output.sed` reader, `SWATFileFormatError`.
- `WorkingFolderManager.run_parallel(prepare=..., extract=..., overlays=..., timeout_s=...)`
  with one callable or one per job; returns `WorkerResult(ok, error, duration_s, worker_dir, payload)`.

### Changed

- Split shared copy/freshness helpers into `core/run_state.py`, pure parameter helpers
  into `calibration/param_spec.py`, and CSV/session persistence into
  `calibration/run_log.py::RunLog`. Existing private helper aliases and manager
  delegates remain available; CSV columns and formatting are unchanged.
- Sequential sensitivity and GLUE uncertainty runs now record after input restoration,
  so a restore failure is recorded as a failed run instead of an earlier successful run.
- `ValidationRunner.run()` keeps the best parameters in TxtInOut by default
  (`restore=True` puts the original files back).
- The simulation frequency comes from `IPRINT` in `file.cio`, not from the observations.
- OAT sensitivity index = parameter's metric range / largest range (`range_over_std` kept);
  parameters with < 2 successful runs get NaN. `morris_salib` passes `num_levels` to SALib.
- `SWATProject` works without `param_file`; `project.run()` invalidates the output cache.
- `spyswat.__version__` comes from package metadata. CLI parses `--n_parallel` as int.
  Dockerfile runs `python -m spyswat`. Sample scripts are `__main__`-guarded.

### Fixed

- A failed run now scores signed infinity (`worst_score`), not ±1e6: a real score beyond
  1e6 (sediment RMSE, early NSE) could rank below a failed run, so `ParallelDE`/`PSO`
  could return a NaN run as the best.
- `SWATCalibration.optimize` passes `method` and `max_iter` to `scipy.optimize.minimize`
  (it always ran L-BFGS-B with scipy's default iterations). `"minimize"` keeps scipy's default.
- Workers restore input files from the baseline before every run, so `r`/`a` changes no
  longer compound across batches; failed or stale runs score NaN instead of reading old output.
- SWAT child process: timeout, killed on interrupt (`taskkill /T` on Windows), no inherited stdin.
- Sequential backup copies only parameter input files, never removes TxtInOut, and is
  deleted only after every file was restored.
- Fixed-width writer: no silent `0.0` fallback; latin-1 with `newline=""` (byte-stable);
  one atomic write per file; unknown parameters raise; no stray temp files.
- Output cache keyed by file stamp (`mtime_ns`, size); `read_rch` honours IPRINT and splits
  monthly files structurally; parse errors name file, line and column.
- NaN scores rank worst in every optimiser; an all-failed batch raises. Fixed undefined
  `all_results` in `GLUE.run`, RSR rating, DDS history columns and `uncertainty_band`
  parameter formatting.
- Failed runs never enter sensitivity indices (Morris drops trajectories, Sobol raises, OAT skips).
- `summary.csv` locked (e.g. open in Excel) → timestamped fallback file with a warning.
- Logging never interrupts a calibration; log files are created only when a row is written.
- `tests/test_project.py`: CRLF fixture written with `newline=""` (failed on Windows).

### Docs

- `AGENTS.md` rewritten; new `CLAUDE.md`; team workflow in `docs/agents/`; `.agents/`
  notebook with templates.
- README / README_VI / ARCHITECTURE updated for the changes above.

### Packaging

- `pyproject.toml`: version 0.2.6, `description` and `readme` metadata. The sdist now
  ships only `spyswat/`, `tests/`, the sample scripts and the user docs (no IDE files,
  agent notebook, SWAT executable or local parameter files).
- `logs/run.log` (a local run log committed before `logs/` was ignored) is no longer tracked.

---

## [0.2.6] (PSO, developed 2026-06-18) – released in 0.2.6 above

### Added

#### `PSOCalibration` — Particle Swarm Optimization

New calibration algorithm following the same standalone-class pattern as `ParallelDE` and `DDSCalibration`.

**File:** `spyswat/swat_calib/analysis/algorithms/pso.py`

Two classes:

- **`PSO`** — standalone optimiser, takes an `objective: Callable[[dict], float]`, no SWAT dependency. Suitable for testing or custom objective functions.
- **`PSOCalibration`** — backed by `CalibrationManager`, evaluates the **entire swarm in parallel** each iteration via `run_batch`. Same pattern as `ParallelDE`.

Key algorithm parameters (all have sensible defaults):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_particles` | `max(10, 5*d)` | Swarm size |
| `max_iterations` | `50` | Maximum iterations |
| `w_max` / `w_min` | `0.9` / `0.4` | Inertia weight range (Shi & Eberhart 1998) |
| `c1` / `c2` | `2.0` / `2.0` | Cognitive / social coefficients |
| `v_max_ratio` | `0.2` | Max velocity as fraction of parameter range |
| `tol` / `patience` | `1e-6` / `10` | Early-stop criteria |

**Standard output contract (same as all other algorithms):**

```python
result = calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50, seed=42)
result["best_params"]      # {name: [(val, method, ...)]}
result["best_score"]       # float
result["history"]          # DataFrame: iteration, best_score, mean_score, std_score
result["all_evaluations"]  # DataFrame: all particle positions + score + iteration
```

**Registered in `SWATCalibration`:**

```python
calib = SWATCalibration(project)
calib.pso   # → PSOCalibration(manager)
calib.de    # → ParallelDE(manager)      (unchanged)
calib.dds   # → DDSCalibration(manager)  (unchanged)
calib.glue  # → GLUE(manager, analysis)  (unchanged)
```

**Exported from `algorithms/__init__.py`:** `PSO`, `PSOCalibration`

**References:**
- Kennedy, J. & Eberhart, R. (1995). Particle swarm optimization. *Proc. ICNN'95*, 4, 1942–1948.
- Shi, Y. & Eberhart, R. (1998). A modified particle swarm optimizer. *Proc. IEEE ICEC*, 69–73.

---

## [0.2.1] – 2026-06-11

### Breaking Change — Mandatory `name.ext` parameter key format

All parameter keys passed to `update_params()`, `update_by_df()`, `run_iteration()`,
`run_batch()`, `glue_analysis()`, `analyze()`, and sensitivity methods **must** now
include the file extension (e.g. `CN2.mgt`, `ALPHA_BF.gw`, `ESCO.hru`).

Bare names such as `"CN2"` are rejected with a `ValueError`.

**Why this change?** SWAT uses the same parameter names across multiple file types
(e.g. `ESCO` exists in both `.hru` and `.bsn`). Without the extension, SpySWAT
previously attempted a fuzzy lookup and silently wrote to whichever file matched first
— potentially the wrong one. Requiring `name.ext` makes the target file unambiguous.

#### Migration

```python
# Before (v0.2.0) — bare names
param_ranges = {
    "CN2":      (35, 98),
    "ALPHA_BF": (0.0, 1.0),
    "ESCO":     (0.01, 1.0),
}
project.HRU.update_params({
    "CN2":      [(75.0, "v")],
    "ALPHA_BF": [(0.05, "v")],
})

# After (v0.2.1) — name.ext required everywhere
param_ranges = {
    "CN2.mgt":      (35, 98),
    "ALPHA_BF.gw":  (0.0, 1.0),
    "ESCO.hru":     (0.01, 1.0),
}
project.HRU.update_params({
    "CN2.mgt":      [(75.0, "v")],
    "ALPHA_BF.gw":  [(0.05, "v")],
})
```

Error message when a bare name is passed:

```
ValueError: Parameter key(s) ['CN2'] missing file extension.
Use 'name.ext' format, e.g. 'CN2.mgt', 'ALPHA_BF.gw', 'ESCO.hru'.
```

When the extension is unknown, call `project.param_file.available_keys()` to list
all registered `name.ext` keys from the param definition file.

#### Changed files

| File | Change |
|------|--------|
| `swat_calib/io/parameters.py` | `SWATParam.get()` — removed fuzzy fallback; raises `KeyError` for bare names with candidate suggestions |
| `swat_calib/core/hru_manager.py` | Added `_validate_param_keys()` static method; called at the top of `update_params()` and `update_by_df()` |

---

## [0.2.0] – 2026-06-11

### Summary

This release focuses on **parallel connectivity** and a **unified workflow**:
- Calibration, sensitivity analysis, and best-parameter extraction can now run from a single call
- Eight critical bugs that prevented calibration and sensitivity from functioning are resolved
- Sensitivity analysis no longer requires additional SWAT runs — computed directly from GLUE results

---

### Added

#### `CalibrationManager`
- **`setup_parallel(overwrite=False)`** — Creates N TxtInOut copies for parallel execution. Call once before `run_batch()`.
- **`run_batch(param_sets, observed, metric, reach_id, output_variable)`** — Accepts N parameter sets, automatically chunks them by `n_parallel`, runs SWAT in parallel via `ProcessPoolExecutor`, and returns N scores. No backup/restore needed since each worker uses its own isolated directory.

#### `SWATCalibration`
- **`analyze(param_ranges, observed_series, n_samples, threshold, metric, sensitivity_method)`** — Unified workflow: generate LHS samples → parallel `run_batch` → best params → sensitivity from results → Moriasi performance rating. Uses exactly N SWAT runs with no additional runs for sensitivity.

#### `SWATAnalysis` (accessed via `project.Statistic`)
- **`sensitivity_from_results(results_df, metric, param_names, method)`** — Computes sensitivity indices from an existing Monte Carlo / GLUE results DataFrame. Supports two methods:
  - `spearman`: Spearman rank correlation — fast, no linearity assumption
  - `prcc`: Partial Rank Correlation Coefficient — removes cross-parameter effects (Helton & Davis, 2003)

#### `WorkingFolderManager`
- Added `param_path` parameter to `__init__` — propagated to `_run_single` so workers know which parameter file to use.
- `run_parallel()` now accepts `len(param_sets) < n_parallel`, enabling `run_batch()` to handle the final undersized chunk without raising an error.

---

### Fixed

| File | Bug | Effect before fix | Fix applied |
|------|-----|-------------------|-------------|
| `calibration.py` | `self._manager = None` | `optimize()` crashes immediately with `AttributeError` | Changed to `CalibrationManager(project)` |
| `calibration.py` | Dead code block after `return` in `optimize()` | Unreachable code causing confusion | Removed duplicate block |
| `calibration.py` | `glue_analysis()` called `self.analysis.batch_statistics()` which does not exist | `AttributeError` on every GLUE call | Replaced with `_generate_samples()` + `run_batch()` |
| `sensitivity.py` | `self.project.update_parameters(params)` does not exist | `AttributeError` on every OAT / Morris run | Changed to `project.HRU.update_params()` |
| `sensitivity.py` | `self.project.output.read_reach()` does not exist | `AttributeError` on every output read | Changed to `project.Output.read_rch()` |
| `sensitivity.py` | `self.project.run(clear_output_cache=True)` — unknown keyword argument | `TypeError` on every simulation run | Changed to `project.run()` |
| `workingFolder_manager.py` | `SWATParam()` called without argument in `_run_single` | Workers have no column position info → writes to wrong location | Pass `param_path` through `__init__` and `_run_single` |
| `workingFolder_manager.py` | `Logger.init()` at module level | Importing the module immediately creates a log file | Removed module-level `Logger.init()` call |
| `statistics.py` | Three `print()` debug statements in `_nse()` | Prints raw values to console on every NSE calculation | Removed all `print()` calls |
| `statistics.py` | `_generate_samples()` returned `List[Dict]` while callers expected `DataFrame` | `AttributeError: list has no attribute .to_dict()` | Changed return type to `pd.DataFrame` |
| `swat_project.py` | `WorkingFolderManager` was not receiving `param_file` | Workers could not locate the parameter definition file | Pass `param_file` into the constructor |

---

### Changed

#### `SWATSensitivity.one_at_a_time()`

**Before (v0.1.x):**
```python
# Sequential — one parameter, one value, one run at a time
for param_name in param_ranges:
    for value in np.linspace(vmin, vmax, n_steps):
        self.project.update_parameters(...)        # AttributeError
        self.project.run(clear_output_cache=True)  # TypeError
        sim_df = self.project.output.read_reach()  # AttributeError
```

**After (v0.2.0):**
```python
# Collect all configs → run all in parallel at once
all_configs = [(param_name, value, params) for ...]
scores = self._manager.run_batch(param_sets, observed_series, ...)
```

All `(parameter, value)` combinations now run in parallel. With 5 parameters × 10 steps = 50 runs and 8 cores: ~8× speedup.

#### `SWATSensitivity.morris_method()`

**Before (v0.1.x):**
```python
# Sequential — step by step through each trajectory
for traj_idx, trajectory in enumerate(trajectories):
    for step_params in trajectory:
        self.project.update_parameters(...)  # AttributeError
        self.project.run(...)                # TypeError
```

**After (v0.2.0):**
```python
# Flatten all trajectory steps → run entire batch in parallel
all_steps = [step for traj in trajectories for step in traj]
all_scores = self._manager.run_batch(all_steps, ...)
```

`n_trajectories × (n_params + 1)` steps now run fully in parallel.

#### `WorkingFolderManager.run_parallel()`

**Before:** Required `len(param_sets) == n_parallel`, raised `ValueError` otherwise.

**After:** Accepts `len(param_sets) <= n_parallel`. Only launches the required number of workers. Enables `run_batch()` to handle a final chunk smaller than `n_parallel` without error.

#### `SWATAnalysis._generate_samples()`

**Before:** Returned `List[Dict]` — each element was `{param_name: value}`.

**After:** Returns `pd.DataFrame` — each row is a sample, each column is a parameter. Internally faster due to vectorized scaling instead of a loop.

---

### Migration Guide — Upgrading from v0.1.x to v0.2.0

#### 1. Project initialization — add `param_file`

```python
# Before
project = SWATProject(
    txinout_dir="path/TxtInOut",
    working_dir="path/workers",
    swat_exe="path/swat.exe",
    n_parallel=4
)

# After — add param_file so workers write to correct columns
project = SWATProject(
    txinout_dir="path/TxtInOut",
    working_dir="path/workers",
    swat_exe="path/swat.exe",
    param_file="params.txt",   # ← add this
    n_parallel=4
)
```

#### 2. Calibration — `_manager` is no longer `None`

No user code change required — the bug is fixed internally.

#### 3. GLUE — call `setup_parallel()` before running many samples

```python
# Before — crashed with AttributeError (batch_statistics did not exist)
result = calib.glue_analysis(param_ranges, obs, n_samples=1000)

# After — set up workers first, then run
calib._manager.setup_parallel(overwrite=True)  # ← add this
result = calib.glue_analysis(param_ranges, obs, n_samples=1000)  # OK, parallel
```

#### 4. Sensitivity — broken API is fixed, no code change needed

No user code change required — the bug is fixed internally.

#### 5. Sensitivity from GLUE results — new API, no extra SWAT runs

```python
# Before — no way to do this

# After — compute sensitivity from existing GLUE results
sensitivity = project.Statistic.sensitivity_from_results(
    results_df=glue_result["all_results"],
    metric="nse",
    method="spearman"
)
```

#### 6. Unified workflow — replace multiple steps with a single call

```python
# Before — 4 separate steps
calib._manager.setup_parallel(overwrite=True)
glue_result = calib.glue_analysis(param_ranges, obs, n_samples=1000)
best_params = ...
sensitivity = project.Statistic.sensitivity_from_results(...)

# After — one call returns everything
result = calib.analyze(param_ranges, obs, n_samples=1000, metric="nse")
# result keys: best_params, best_score, sensitivity,
#              behavioral_results, behavioral_ratio, performance
```

---

## [0.1.0] – (initial release)

- Core framework: `SWATProject`, `HRUManager`, `OutputFileManager`, `FileCIO`
- Fixed-width TxtInOut read/write
- `CalibrationManager.run_iteration()` with backup/restore
- `SWATAnalysis`: NSE, KGE, R², RMSE, PBIAS, RSR
- `WorkingFolderManager`: worker copy creation and parallel execution
- `SWATParam`: parameter definition file reader
- `OutputFileReader` with `SWATReaderCache`
- `ObservedData`: CSV / Excel / TXT reader

---

*See also: [README_VI.md](README_VI.md) · [README.md](README.md)*
