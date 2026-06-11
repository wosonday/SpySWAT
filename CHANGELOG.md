# CHANGELOG

All notable changes to SpySWAT are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
# Elementary Effects computed in post-processing from all_scores
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

```python
# Before — crashed with AttributeError
calib = SWATCalibration(project)
calib.optimize(...)  # AttributeError: 'NoneType' has no attribute 'run_iteration'

# After — works without any code change
calib = SWATCalibration(project)
calib.optimize(...)  # OK
```

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

```python
# Before — crashed with AttributeError (3 methods did not exist on project)
sens = SWATSensitivity(project)
oat_df, idx = sens.one_at_a_time(param_ranges, observed_series=obs)  # AttributeError

# After — works and runs in parallel
sens = SWATSensitivity(project)
oat_df, idx = sens.one_at_a_time(param_ranges, observed_series=obs)  # OK
```

No user code change required — the bug is fixed internally.

#### 5. Sensitivity from GLUE results — new API, no extra SWAT runs

```python
# Before — no way to do this
# (had to run separate OAT/Morris = M additional SWAT runs)

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
best_idx = glue_result["all_results"]["nse"].idxmax()
best_params = ...
sensitivity = project.Statistic.sensitivity_from_results(glue_result["all_results"])
rating = project.Statistic.evaluate_performance(obs_aligned, sim_aligned)

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

*See also: [README_VI.md](README_VI.md) · [README_EN.md](README_EN.md)*
