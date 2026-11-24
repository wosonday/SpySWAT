# SpySWAT 🌊

**Python library for SWAT model calibration, validation, and sensitivity analysis**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-308%20passed-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.2.6-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

> Vietnamese version: [README_VI.md](README_VI.md) · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Changelog: [CHANGELOG.md](CHANGELOG.md) · Contributing with AI agents: [AGENTS.md](AGENTS.md)

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Project Setup](#project-setup)
- [Parameter Key Format](#parameter-key-format)
- [Quick Start](#quick-start)
- [Calibration](#calibration)
- [Fig Viewer](#fig-viewer--interactive-watershed-diagram)
- [Validation](#validation)
- [Run Log](#run-log)
- [Scenario Batch](#scenario-batch)
- [Sensitivity Analysis](#sensitivity-analysis)
- [Reading and Writing TxtInOut](#reading-and-writing-txtinout)
- [Reading SWAT Output](#reading-swat-output)
- [Performance Statistics](#performance-statistics)
- [Parallel Execution](#parallel-execution)
- [API Reference](#api-reference)
- [References](#references)

---

## Overview

SpySWAT provides:

- Direct read/write of SWAT TxtInOut files (fixed-width format)
- Automated calibration: **GLUE** (parallel Monte Carlo), **DDS**, **Parallel DE**, **PSO**
- Uncertainty quantification: 95PPU band, p-factor, r-factor
- Sensitivity analysis from GLUE results — **zero extra SWAT runs**
- Performance evaluation following Moriasi et al. (2007)
- Parallel execution via `ProcessPoolExecutor` with isolated worker copies; every worker run starts from the baseline TxtInOut
- **Scenario batches**: land-use / climate scenarios × parameter sets in parallel, with resume
- **Run log**: metrics and target series of every run appended to CSV as the calibration goes
- Fail-loud I/O: malformed files, step mismatches and failed SWAT runs raise or score NaN; nothing is silently filled with `0.0`

---

## Installation

```bash
pip install spyswat
# or from source
git clone https://github.com/wosonday/SpySWAT.git
pip install -e .
```

Requirements: Python ≥ 3.12, numpy, pandas, scipy

---

## Project Setup

```python
from spyswat import SWATProject

project = SWATProject(
    txinout_dir = "D:/SWAT/TxtInOut",
    working_dir = "D:/SWAT/workspace",
    swat_exe    = "D:/SWAT/swat_rev688.exe",
    param_file  = "D:/SWAT/params.txt",
    n_parallel  = 8
)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `txinout_dir` | ✓ | Path to TxtInOut directory |
| `working_dir` | ✓ | Directory for worker copies (auto-created) |
| `swat_exe` | ✓ | Path to SWAT executable |
| `param_file` | — | Parameter definition file `.txt` (needed only for parameter editing: `project.HRU`, `read_params_values`) |
| `n_parallel` | — | Number of parallel workers (default: 1) |

> **Windows:** parallel runs spawn new processes that re-import your script. Put the script's code under `if __name__ == "__main__":` (see `docs/sample_run_*.py`); SpySWAT raises a clear error otherwise.

Check that the parameter file matches your TxtInOut before calibrating:

```python
problems = project.HRU.validate_inputs()   # empty DataFrame = every location is valid
```

---

## Parameter Key Format

> **⚠️ Since v0.2.1, all parameter keys must use `name.ext` format.**

The `name.ext` format explicitly identifies both the parameter name and the SWAT file type to update, preventing silent errors when the same parameter exists in multiple file types.

```python
# ❌ Wrong — bare names are not accepted
{"CN2": [(75.0, "v")]}

# ✅ Correct — always include the file extension
{"CN2.mgt": [(75.0, "v")]}
```

Quick reference:

| Parameter | Key | SWAT file |
|-----------|-----|-----------|
| CN2 | `CN2.mgt` | `.mgt` (management) |
| ALPHA_BF | `ALPHA_BF.gw` | `.gw` (groundwater) |
| GW_DELAY | `GW_DELAY.gw` | `.gw` (groundwater) |
| ESCO | `ESCO.hru` | `.hru` (HRU) |
| SOL_AWC | `SOL_AWC.sol` | `.sol` (soil) |
| SURLAG | `SURLAG.bsn` | `.bsn` (basin) |

---

## Quick Start

```python
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.analysis import SWATCalibration

project = SWATProject(
    txinout_dir = "D:/SWAT/TxtInOut",
    working_dir = "D:/SWAT/workspace",
    swat_exe    = "D:/SWAT/swat.exe",
    n_parallel  = 8
)

obs = pd.read_csv("observed.csv", index_col="date", parse_dates=True)["flow"]

param_ranges = {
    "CN2.mgt":     (35.0, 98.0),
    "ALPHA_BF.gw": (0.0,  1.0),
    "GW_DELAY.gw": (30.0, 450.0),
    "ESCO.hru":    (0.01, 1.0),
    "SOL_AWC.sol": (0.01, 0.5),
}

calib = SWATCalibration(project)
calib.manager.setup_parallel(overwrite=True) #Set up in WorkingFolder
# Full workflow: GLUE → best params → sensitivity → performance
result = calib.analyze(param_ranges, obs, n_samples=1000, threshold=0.5, seed=42)

print(f"Best NSE:  {result['best_score']:.3f}")
print(result["sensitivity"])
print(result["performance"])
```

What happens inside `analyze()`:

```
1000 LHS samples (seeded for reproducibility)
         |
         ▼
 run_batch (N workers, parallel)
         |
         ▼
 1000 (params, score) rows
      /         |          \
 best        sensitivity   behavioral
 params      (Spearman,    (NSE ≥ 0.5)
             0 extra runs)
```

---

## Calibration

From v0.2.1, algorithms are standalone classes accessed via `calib.glue`, `calib.de`, `calib.dds`, `calib.pso`.

### GLUE — Parallel Monte Carlo

```python
calib = SWATCalibration(project)

result = calib.glue.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_samples       = 1000,
    threshold       = 0.5,
    metric          = "nse",
    seed            = 42,
)

print(result["all_results"])         # DataFrame: all 1000 runs
print(result["behavioral_results"])  # DataFrame: NSE ≥ threshold
print(f"Behavioral: {result['behavioral_ratio']:.1%}")
```

#### 95PPU Uncertainty Band

```python
unc = calib.glue.uncertainty_band(
    behavioral_df   = result["behavioral_results"],
    observed_series = obs,
    metric          = "nse",
)
print(f"p-factor: {unc['p_factor']:.3f}")   # ≥ 0.70 → acceptable
print(f"r-factor: {unc['r_factor']:.3f}")   # ≤ 1.50 → acceptable
unc["uncertainty_band"].plot()               # columns: lower, upper, obs
```

Criteria (Abbaspour et al., 2007):

| Metric | Target |
|--------|--------|
| p-factor | ≥ 0.70 |
| r-factor | ≤ 1.50 |

### DDS — Dynamically Dimensioned Search

DDS self-adjusts the perturbation probability: `P = 1 - ln(i)/ln(N)`. Efficient for budgets ≤ 500 SWAT runs.

```python
result = calib.dds.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_iterations    = 300,
    r               = 0.2,
    seed            = 42,
    metric          = "nse",
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["best_params"])
print(result["history"])    # DataFrame: iteration, score
```

Standalone DDS (no SWAT dependency):

```python
from spyswat.swat_calib.analysis.algorithms import DDS

dds = DDS(
    param_ranges = param_ranges,
    objective    = my_objective_fn,   # callable: dict → float
    n_iterations = 300,
    seed         = 42,
    maximize     = True
)
result = dds.run()
```

### Parallel Differential Evolution

Evaluates the entire population per generation in parallel via `run_batch`. Best when many workers are available.

```python
result = calib.de.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    pop_size        = 20,
    max_generations = 40,
    F               = 0.8,
    CR              = 0.9,
    strategy        = "rand/1/bin",   # or "best/1/bin"
    seed            = 42,
    tol             = 1e-6,
    patience        = 5,
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["history"])    # generation, best_score, mean_score, std_score
```

### PSO — Particle Swarm Optimization

Evaluates the entire swarm in parallel via `run_batch` each iteration. Inertia weight decays linearly from `w_max` to `w_min` (Shi & Eberhart, 1998), balancing exploration and exploitation automatically.

```python
result = calib.pso.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_particles     = 20,
    max_iterations  = 50,
    w_max           = 0.9,
    w_min           = 0.4,
    c1              = 2.0,
    c2              = 2.0,
    seed            = 42,
    tol             = 1e-6,
    patience        = 10,
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["best_params"])
print(result["history"])         # iteration, best_score, mean_score, std_score
print(result["all_evaluations"]) # every particle position across all iterations
```

Standalone PSO (no SWAT dependency):

```python
from spyswat.swat_calib.analysis.algorithms import PSO

pso = PSO(
    param_ranges   = param_ranges,
    objective      = my_objective_fn,   # callable: dict → float
    n_particles    = 20,
    max_iterations = 100,
    seed           = 42,
    maximize       = True
)
result = pso.run()
```

### Scipy DE / Nelder-Mead (sequential)

```python
result = calib.optimize(
    param_ranges    = param_ranges,
    observed_series = obs,
    method          = "differential_evolution",  # or "minimize" (L-BFGS-B), "Nelder-Mead", "Powell", ...
    metric          = "nse",
    max_iter        = 100,
    on_failure      = "raise",                  # or "penalize": a failed run scores the worst value
)
print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

Sequential optimisers (`calib.optimize`, `calib.dds.run`) stop on the first failed SWAT run by default (`on_failure="raise"`). Population algorithms (GLUE, DE, PSO) score a failed run as NaN, which always ranks worst; a batch where every run failed raises `RuntimeError`. A local `method` (anything but DE) starts from the middle of the bounds and cannot leave a region where every run fails: use DE when parts of the parameter space crash SWAT.

### Unified param_ranges format

From v0.2.2, bounds, method, and subbasin list can be expressed in a single dict — no need for separate `param_methods` / `param_subbasins` arguments. All formats are backward-compatible and mixable.

```python
param_ranges = {
    # Old format — bounds only (default method = "v")
    "ESCO.hru":    (0.01, 1.0),

    # bounds + method
    "CN2.mgt":     ((35, 98),   "r"),

    # bounds + method + subbasin list (per-watershed optimisation)
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),
    "GW_DELAY.gw": ((0, 450),   "v", [12, 33]),
}

# Same call — no extra kwargs needed
result = calib.glue.run(param_ranges, obs, n_samples=1000, seed=42)
result = calib.de.run(param_ranges, obs, pop_size=20, max_generations=40)
result = calib.dds.run(param_ranges, obs, n_iterations=300)
result = calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50)
result = calib.analyze(param_ranges, obs)
```

Method codes:

| Code | Formula | When to use |
|------|---------|-------------|
| `v` (default) | `new = val` | Direct assignment |
| `r` | `new = old × (1 + val)` | Relative change |
| `a` | `new = old + val` | Additive change |

You can still pass `param_methods` / `param_subbasins` as keyword arguments — they **override** values in the spec:

```python
# Override method for CN2 (spec says "r" but we want "v")
result = calib.glue.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    param_methods   = {"CN2.mgt": "v"},   # overrides spec
    param_subbasins = {"ESCO.hru": [5, 6, 7]},  # adds subbasin for ESCO
)
```

### Per-watershed independent optimisation

Assign different subbasin lists per parameter to calibrate each watershed independently:

```python
param_ranges = {
    "CN2.mgt":     ((35, 98),   "r", [71, 45, 70]),   # upper basin
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),
    "GW_DELAY.gw": ((0, 450),   "v", [12, 33, 8]),    # lower basin
    "ESCO.hru":    (0.01, 1.0),                        # all basins
}
result = calib.dds.run(param_ranges, obs, n_iterations=500)
print(result["best_params"])
# {"CN2.mgt": [(val, "r", [71,45,70])], "GW_DELAY.gw": [(val, "v", [12,33,8])], ...}
```

---

## Fig Viewer — Interactive Watershed Diagram

Visualise the SWAT routing network (`fig.fig`) as an interactive SVG graph directly in your browser.

```python
# Via SWATProject (simplest)
project.fig_viewer(
    red_reaches  = [32, 33, 37, 38],   # highlight these reach IDs in red
    output_path  = None,               # default: TxtInOut/fig_viewer.html
    open_browser = False,              # set True to auto-open
)
```

Standalone:

```python
from spyswat.swat_calib.visualization import FigViewer

viewer = FigViewer("path/to/TxtInOut")

# Parse only (returns dict)
data = viewer.parse(red_reaches=[32, 33])

# Build HTML file
path = viewer.build(
    red_reaches  = [32, 33, 37, 38],
    output_path  = "my_fig.html",
    open_browser = False,
)
```

**Interactive features:**

| Feature | Description |
|---------|-------------|
| Click node | Select and highlight connected reaches |
| Hover | Show command details (ID, type, parameters) |
| Red nodes/edges | Reaches in `red_reaches` and all related commands |
| Blue halo | Connected node highlight |
| Dashed edges | Transfer commands |
| Blue thick edges | Active (hot) edges |
| Issues panel | Validation warnings (duplicate IDs, forward references, transfer semantics) |

The viewer validates `fig.fig` on parse and reports issues per command in the sidebar.

## Validation

```python
# Apply best params from calibration.
# This edits your TxtInOut in place: keep a copy, or use ValidationRunner below.
project.HRU.update_params(result["best_params"])
project.run()

sim = project.Output.read_rch(
    columns  = ["RCH", "MON", "FLOW_OUTcms"],
    reach_id = 1
)["FLOW_OUTcms"]

obs_val = obs["2011-01-01":"2015-12-31"]
sim_val = sim["2011-01-01":"2015-12-31"]

stats  = project.Statistic.calculate_statistics(obs_val, sim_val)
rating = project.Statistic.evaluate_performance(obs_val, sim_val)
```

Automated calibration/validation split with `ValidationRunner`:

```python
from spyswat.swat_calib.calibration import ValidationRunner
from spyswat.swat_calib.calibration.validation_runner import PeriodConfig

runner = ValidationRunner(
    project, param_ranges, obs,
    PeriodConfig(
        calib_start = "2002-01-01",
        calib_end   = "2010-12-31",
        valid_start = "2011-01-01",
        valid_end   = "2015-12-31"
    )
)
r = runner.run(metric="nse", output_variable="FLOW_OUTcms")   # restore=True to undo
print("Calib NSE:", r["calibration"]["nse"])
print("Valid NSE:", r["validation"]["nse"])
print(r["best_parameters"])
```

By default the best parameters **stay in TxtInOut** after `runner.run()` (a warning is logged: applying relative `r`/`a` changes again would compound). Pass `restore=True` to get the original input files back. Best parameters and validation metrics are saved as `<session>_best_params.csv` and `<session>_validation.csv` (see [Run Log](#run-log)).

### Observation time step

Observations must have the same time step as the model's print step (`IPRINT` in `file.cio`): daily observations for daily output, monthly for monthly. SpySWAT never resamples; a mismatch raises `ValueError` before any run. Monthly observations are dated on the **1st** of the month:

```python
obs_monthly = obs_daily.resample("MS").mean()                 # flow: monthly mean
# or, if already monthly but dated at month end:
obs.index = obs.index.to_period("M").to_timestamp()

from spyswat.swat_calib.calibration.calib_manager import check_observation_step
check_observation_step(obs.index, project.FileCIO.get_iprint())   # raises on mismatch
```

---

## Run Log

Every run (sequential, parallel, validation, GLUE uncertainty band, sensitivity) is appended to CSV **right after it finishes**, so a crash or Ctrl+C never loses finished runs:

```
<working_dir>/calibration_results/
├── <session>_metrics.csv       one row per run: run_id, time, mode, status, error, reach_id,
│                               output_variable, <param>, <param>__method, <param>__spec, metrics
├── <session>_outputs.csv       target series, long format: run_id, date, variable, reach, value
├── <session>_best_params.csv   ValidationRunner
└── <session>_validation.csv    ValidationRunner
```

`<session>` is the start time (`YYYYMMDD_HHMMSS`). Files are created only when the first row is written. If the parameter or metric columns change, a new session starts.

```python
manager = calib.manager
manager.log_outputs = "observed"      # "all" (default) | "observed" (dates with obs) | "none"
manager.results_dir = "D:/SWAT/results"   # None disables the log
print(manager.session_files)          # {'metrics': Path, 'outputs': Path}

# custom algorithms that run SWAT themselves:
manager.record_run({"CN2.mgt": 75.0}, {"nse": 0.71}, sim=sim_series)
```

Logging never interrupts a calibration: if a file is locked (e.g. open in Excel), rows are kept in memory, a warning is logged once, and they are written at the next append or `manager.flush_log()`.

---

## Scenario Batch

Run several **scenarios** (land-use maps, climate inputs, simulation periods) with several **parameter sets** in parallel, and export the series and metrics.

```python
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch

if __name__ == "__main__":
    scenarios = [
        Scenario("LUC2000", txinout_dir="D:/SWAT/LUC2000/TxtInOut"),   # complete TxtInOut
        Scenario("LUC2020", txinout_dir="D:/SWAT/LUC2020/TxtInOut"),
        Scenario("GCM_ssp245", weather_dir="D:/GCM/ssp245",            # files copied over the base
                 cio={"IYR": 2030, "NBYR": 20, "NYSKIP": 0},
                 evaluate=False),                                     # future: no metrics
    ]
    param_sets = [
        ParamSet.from_dict("best", {"CN2.mgt": (-0.1, "r"), "ALPHA_BF.gw": 0.5}),
        ParamSet.from_dataframe(table, "par1", param="PARAM", method="method",
                                value="MIN", sub="SUBBASIN"),
    ]

    batch = ScenarioBatch(project, "D:/SWAT/results")
    res = batch.run(
        scenarios, param_sets,
        outputs  = {"FLOW_OUTcms": [51, 55], "SED_OUTtons": [51]},
        observed = {("FLOW_OUTcms", 51): obs},
        metrics  = ("nse", "kge", "pbias"),
        # pairs=[("LUC2000", "best")],   # default: every scenario × every parameter set
        resume   = True,                  # skip jobs already 'ok' in summary.csv
    )
    print(res.summary)      # job_id, scenario, param_set, status, error, duration_s, ...
    print(res.metrics)      # job_id, scenario, param_set, variable, reach, metric, value
    res.to_csv("FLOW_OUTcms", "D:/SWAT/results/flow_all.csv")
```

| Option | Meaning |
|--------|---------|
| `Scenario(txinout_dir=...)` | A separate, complete TxtInOut folder |
| `Scenario(weather_dir=...)` | Files copied by name over the base TxtInOut (must already be in SWAT format) |
| `Scenario(cio={...})` | `file.cio` override: `NBYR`, `IYR`, `IDAF`, `IDAL`, `IPRINT`, `NYSKIP` |
| `Scenario(evaluate=False)` | Future / GCM run: series written, no metrics, no observation-step check |
| `resume=True` | Skip finished jobs; raises if outputs, metrics, observations, a definition, or a scenario's TxtInOut input files changed |

All jobs run on a single process pool across at most `n_parallel` worker folders (`_scenario_batch/TxInOut1..N`): as soon as a slot finishes, it takes the next pending job (preferring the same base TxtInOut before re-copying another base). Results are saved to `metrics.csv` and `summary.csv` as jobs finish and on any exit (including `KeyboardInterrupt`). A failed job, unreadable `weather_dir`, bad base TxtInOut, or broken worker pool marks only the affected jobs `status="failed"` and `run()` still returns, so `resume=True` can re-run them. Names may use letters, digits, `.`, `_`, `-` but not `__`. Full example: `docs/sample_run_scenarios.py`.

---

## Sensitivity Analysis

### From GLUE results (recommended — no extra SWAT runs)

```python
sensitivity = project.Statistic.sensitivity_from_results(
    results_df  = result["all_results"],
    metric      = "nse",
    param_names = list(param_ranges.keys()),
    method      = "spearman",   # or "prcc"
)
print(sensitivity)
# parameter      sensitivity_index  rank
# ALPHA_BF.gw        0.83            1
# CN2.mgt            0.61            2
# GW_DELAY.gw        0.45            3
```

| Method | Description | Advantage |
|--------|-------------|-----------|
| `spearman` | Spearman rank correlation | Fast, no linearity assumption |
| `prcc` | Partial Rank Correlation Coefficient | Removes cross-parameter effects |

### OAT — One-At-a-Time (parallel)

```python
from spyswat.swat_calib.analysis import SWATSensitivity

sens = SWATSensitivity(project)
oat_df, indices = sens.one_at_a_time(
    param_ranges    = param_ranges,
    n_steps         = 10,
    observed_series = obs,
    metric          = "nse"
)
print(indices)
# parameter  metric_range  metric_std  range_over_std  sensitivity_index   (sorted, highest first)
```

`sensitivity_index` = the parameter's metric range divided by the largest range over all parameters (the most influential parameter gets 1.0). Failed runs are excluded; a parameter with fewer than 2 successful runs gets NaN. Without `observed_series`, OAT and Morris restore your inputs after each run.

### Morris Method (parallel)

```python
morris = sens.morris_method(
    param_ranges    = param_ranges,
    n_trajectories  = 10,
    observed_series = obs,
    metric          = "nse"
)
print(morris["morris_indices"])
```

A trajectory that contains a failed run is dropped from the Morris indices. `sens.sobol_method(...)` raises `RuntimeError` if any run failed, because Sobol indices need the complete sample; the expensive batch is not lost: `sens.last_samples` and `sens.last_scores` (NaN = failed) keep it. `morris_salib` and `sobol_method` need `pip install SALib`.

---

## Reading and Writing TxtInOut

### Update parameters

```python
project.HRU.update_params({
    "CN2.mgt":     [(75.0, "v")],
    "ALPHA_BF.gw": [(0.5,  "v")],
    "ESCO.hru":    [(0.1,  "r")],
    "SOL_AWC.sol": [(0.05, "a")],
})
```

### Update by subbasin

```python
project.HRU.update_params({
    "CN2.mgt": [
        (75.0, "v", [1, 2, 3]),   # subbasins 1-3: assign 75
        (80.0, "v", [4, 5]),      # subbasins 4-5: assign 80
    ]
})
```

### Update from DataFrame

```python
df = pd.DataFrame([
    {"param": "CN2.mgt",     "value": 75.0, "method": "v"},
    {"param": "ALPHA_BF.gw", "value": 0.5,  "method": "v"},
    {"param": "ESCO.hru",    "value": 0.1,  "method": "r"},
])
project.HRU.update_by_df(df)
```

### Read current parameter values

```python
values = project.read_params_values(["CN2.mgt", "ALPHA_BF.gw", "ESCO.hru"])
```

### Parameter file format

Tab-separated definition file:

```
# name    ext     line  col_start  col_end  round  vmin   vmax
CN2       .mgt    8     3          12       1      35.0   98.0
ALPHA_BF  .gw     6     3          12       3      0.0    1.0
GW_DELAY  .gw     5     3          12       1      30.0   450.0
ESCO      .hru    9     3          12       3      0.01   1.0
SOL_AWC   .sol    0     0          0        3      0.01   0.5
```

The code key for each entry = `name + ext`, e.g. `CN2.mgt`, `ALPHA_BF.gw`.

### Strict writes

Input files are read and written byte-for-byte (latin-1, original line endings). A value wider than its fixed-width field, a short line or a slice outside the line raises `SWATFileFormatError` and leaves the file untouched; each file is replaced atomically once per `update_params` call. An unknown parameter key raises `ValueError` before any file is changed.

Simulation settings in `file.cio`:

```python
project.FileCIO.set(IYR=2000, NBYR=16, NYSKIP=2, IPRINT=0)   # IPRINT: 0 monthly, 1 daily, 2 yearly
project.FileCIO.get_iprint()                                 # 'MS' | 'D' | 'YS'
```

---

## Reading SWAT Output

```python
# output.rch
rch = project.Output.read_rch(
    columns  = ["RCH", "MON", "FLOW_OUTcms", "SED_OUTtons"],
    reach_id = 1
)

# output.hru
hru = project.Output.read_hru(
    columns = ["LULC", "HRU", "MON", "ET", "SURQ_GEN"]
)

# output.sub
sub = project.Output.read_sub(columns=["SUB", "MON", "PRECIP", "SURQ"])

# output.sed
sed = project.Output.read_sed()
```

Common `output.rch` variables:

| Variable | Unit | Description |
|----------|------|-------------|
| `FLOW_OUTcms` | m³/s | Outflow |
| `SED_OUTtons` | ton | Sediment outflow |
| `NO3_OUTkg` | kg | Nitrate |
| `ORG_N_kg` | kg | Organic nitrogen |

`read_rch` reads the print frequency from `file.cio` and splits monthly files into their monthly blocks (annual and average-annual rows are dropped). Results are cached per file stamp (modification time and size), so a new SWAT run is always picked up; `project.run()` also clears the cache. Parse errors name the file, line and column.

```python
project.Output.check_complete(".rch")   # raises RuntimeError with the reason if output.rch is unusable
project.Output.invalidate()             # drop the cache by hand
```

---

## Performance Statistics

```python
stats  = project.Statistic.calculate_statistics(obs, sim,
    metrics=["nse", "kge", "r2", "rmse", "pbias", "rsr"])
rating = project.Statistic.evaluate_performance(obs, sim)
```

One registry (`spyswat.swat_calib.analysis.statistics.METRIC_DIRECTIONS`) tells every algorithm which way is better:

| Direction | Metrics |
|-----------|---------|
| larger is better | `nse`, `kge`, `r2`, `correlation` |
| smaller is better | `rmse`, `mae`, `rsr` |
| closest to 0 is best | `pbias` (optimised as `abs(pbias)`) |

Helpers: `known_metrics()`, `is_maximize(m)`, `to_objective(m, score)` (smaller is always better), `best_index(scores, m)` (NaN-safe). An unknown metric name raises `ValueError`.

NSE rating (Moriasi et al., 2007):

| NSE | Rating |
|-----|--------|
| > 0.75 | Very Good |
| 0.65–0.75 | Good |
| 0.50–0.65 | Satisfactory |
| 0.40–0.50 | Acceptable |
| ≤ 0.40 | Unsatisfactory |

---

## Parallel Execution

SpySWAT uses `ProcessPoolExecutor` with N isolated TxtInOut copies — one per worker.

```
1000 samples, 8 workers → 125 batches × T_swat ≈ 8× speedup

Batch 1:   [s1  s2  s3  s4  s5  s6  s7  s8]  ← simultaneous
Batch 2:   [s9  s10 s11 s12 s13 s14 s15 s16]
...
Batch 125: [s993..s1000]
```

Manual usage:

```python
from spyswat.swat_calib.calibration import CalibrationManager

manager = CalibrationManager(project)
manager.setup_parallel(overwrite=True)

results = manager.run_batch(
    param_sets = [
        {"CN2.mgt": [(70.0, "v")]},
        {"CN2.mgt": [(75.0, "v")]},
        {"CN2.mgt": [(80.0, "v")]},
    ],
    observed = obs,
    metrics  = ["nse"],
    reach_id = 1,
)
print(results)   # DataFrame: nse (NaN for a failed run)
```

Guarantees of every parallel run:

- **Baseline first:** each worker restores its input files from your TxtInOut before applying parameters, so relative (`r`) and additive (`a`) changes never compound across batches. Your TxtInOut is never modified.
- **Failure isolation:** a crashed, timed-out or stale run is reported as failed (`WorkerResult(ok=False, error=...)`) and scored NaN; old output is never read as if it were new.
- **Clean shutdown:** Ctrl+C kills the SWAT child processes (`taskkill /T` on Windows).

Low-level hooks for custom workflows: `project.WorkingFolder.run_parallel(swat_exe, param_sets, prepare=..., extract=..., overlays=..., timeout_s=...)`. `prepare`/`extract` accept one callable or a list with one entry per job; they must be module-level (picklable) functions.

---

## API Reference

### SWATProject

```
project.HRU.update_params(param_dict)
project.HRU.update_by_df(df)
project.read_params_values(param_list)
project.run()
project.get_date_range(freq="D")
project.worker(index)
project.Output.read_rch / read_hru / read_sub / read_sed / read_watout
project.Statistic.calculate_statistics(obs, sim, metrics)
project.Statistic.evaluate_performance(obs, sim)
project.Statistic.sensitivity_from_results(df, metric, param_names, method)
project.HRU.validate_inputs(params=None) → DataFrame of problems (empty = OK)
project.FileCIO.get_date_range_sim(freq)
project.FileCIO.get_iprint() → 'MS' | 'D' | 'YS'
project.FileCIO.set(NBYR=, IYR=, IDAF=, IDAL=, IPRINT=, NYSKIP=)
project.Output.check_complete(file_type=".rch") / invalidate()
project.WorkingFolder.setup(overwrite)
project.WorkingFolder.run_parallel(swat_exe, param_sets, prepare=, extract=,
                                   overlays=, timeout_s=) → [WorkerResult]
project.info()
```

### SWATCalibration

```
calib = SWATCalibration(project)

# Standalone algorithm instances
calib.glue    → GLUE(manager, analysis)
calib.de      → ParallelDE(manager)
calib.dds     → DDSCalibration(manager)
calib.pso     → PSOCalibration(manager)
calib.manager → CalibrationManager

# Algorithm methods  (param_ranges accepts unified format since v0.2.2)
calib.glue.run(param_ranges, obs, n_samples, threshold, metric, seed,
               compute_uncertainty, param_methods, param_subbasins) → dict
calib.glue.uncertainty_band(behavioral_df, obs, metric) → dict
calib.de.run(param_ranges, obs, pop_size, max_generations, F, CR,
             strategy, seed, tol, patience, param_methods, param_subbasins) → dict
calib.dds.run(param_ranges, obs, n_iterations, r, seed, metric,
              output_variable, reach_id, maximize, param_methods, param_subbasins) → dict
calib.pso.run(param_ranges, obs, n_particles, max_iterations, w_max, w_min,
              c1, c2, v_max_ratio, seed, metric, output_variable, reach_id,
              tol, patience, param_methods, param_subbasins) → dict

# Orchestrated workflows
calib.analyze(param_ranges, obs, n_samples, threshold, metric,
              sensitivity_method, seed, param_methods, param_subbasins) → dict
calib.optimize(param_ranges, obs, method, metric, max_iter,
               param_methods, param_subbasins, on_failure="raise") → dict
```

### Standalone Algorithm Classes

```python
from spyswat.swat_calib.analysis.algorithms import DDS, DDSCalibration, GLUE, ParallelDE, PSO, PSOCalibration

DDS(param_ranges, objective, n_iterations=200, r=0.2, seed=None, maximize=True)
  .run() → {"best_params", "best_score", "history"}

DDSCalibration(manager)
  .run(param_ranges, obs, ...) → dict

GLUE(manager, analysis=None)
  .run(param_ranges, obs, ...) → dict
  .uncertainty_band(behavioral_df, obs, ...) → dict

ParallelDE(manager)
  .run(param_ranges, obs, ...) → dict

PSO(param_ranges, objective, n_particles=None, max_iterations=100,
    w_max=0.9, w_min=0.4, c1=2.0, c2=2.0, seed=None, maximize=True)
  .run() → {"best_params", "best_score", "history"}

PSOCalibration(manager)
  .run(param_ranges, obs, ...) → dict
```

### CalibrationManager

```
CalibrationManager(project)
  .setup_parallel(overwrite=False)
  .run_iteration(param_dict, obs, metric, reach_id, output_variable,
                 methods=None, subbasins=None) → float
      param_dict: {name: float}  (raw)  OR  {name: [(val, method, ...)]}  (formatted)
  .run_batch(param_sets, observed, metrics, reach_id, output_variable,
             methods=None, subbasins=None) → DataFrame
      param_sets: list of raw or formatted dicts — both accepted
  .record_run(params, scores, status="ok", error=None, sim=None, mode="sequential",
              reach_id=None, output_variable=None)      append one run to the run log
  .flush_log() → bool                                    write rows buffered while a file was locked
  .results_dir        Path | None (default <working_dir>/calibration_results)
  .log_outputs        "all" | "observed" | "none"
  .session_files      {"metrics": Path, "outputs": Path}
  ._parse_spec(param_ranges) → (bounds, methods, subbasins)  [staticmethod]
      Raises ValueError if old-format tuple has > 2 elements
  ._format_params(raw_dict, methods=None, subbasins=None) → formatted_dict
  ._align_series(obs, sim) → (obs_aligned, sim_aligned)
      sim frequency from IPRINT; raises on step mismatch or no common date

check_observation_step(obs_index, sim_freq)              calibration.calib_manager
```

### ValidationRunner

```
ValidationRunner(project, param_ranges, observed, PeriodConfig(calib_start, calib_end,
                 valid_start, valid_end))
  .run(metric="nse", method="differential_evolution", max_iter=100, reach_id=1,
       output_variable="FLOW_OUTcms", restore=False)
      → {"best_parameters", "calibration": {metric: score}, "validation": {all metrics}}
```

### Scenarios

```
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch

Scenario(name, txinout_dir=None, weather_dir=None, cio=None, evaluate=True)
ParamSet(name, updates={"CN2.mgt": [(value, method[, subbasins]), ...]})
ParamSet.from_dict(name, {"CN2.mgt": 75.0, "ESCO.hru": (0.1, "r")})
ParamSet.from_dataframe(df, name, param="param", method="method", value="value", sub="subbasin")

ScenarioBatch(project, results_dir)
  .run(scenarios, param_sets, *, outputs, pairs=None, observed=None,
       metrics=("nse", "kge", "pbias"), resume=True, timeout_s=None) → BatchResult
BatchResult: .summary, .metrics, .results, .failed, .warnings,
             .series(variable) → DataFrame, .to_csv(variable, path) → Path
```

### FigViewer

```
from spyswat.swat_calib.visualization import FigViewer

FigViewer(txinout_dir)
  .parse(red_reaches=None) → dict
  .build(red_reaches=None, output_path=None, open_browser=True) → Path

# Via SWATProject
project.fig_viewer(red_reaches=None, output_path=None, open_browser=True) → Path
```

---

## Directory Structure

```
SpySWAT/
├── spyswat/
│   ├── swat_project.py               # SWATProject — main entry point
│   └── swat_calib/
│       ├── core/       TxInOut, HRUManager, OutputFileManager, WorkingFolderManager
│       ├── io/         SWATParam, readers, writers, mapping_file, FileCIO
│       ├── calibration/ CalibrationManager (+ run log), ValidationRunner
│       ├── scenarios/  Scenario, ParamSet, ScenarioBatch
│       ├── analysis/   SWATAnalysis + metric registry, SWATCalibration (facade), SWATSensitivity
│       │               └── algorithms/  dds.py, glue.py, parallel_de.py, pso.py
│       ├── run/        SWATRun (subprocess, timeout)
│       └── visualization/ FigViewer
├── docs/               sample_run_single.py, sample_run_parallel.py, sample_run_scenarios.py,
│                       agents/ (AI-agent team workflow)
├── tests/              319 tests (pytest, no SWAT executable needed)
├── .agents/            per-task notes kept with the code (see AGENTS.md)
├── AGENTS.md           guide for AI agents and contributors (CLAUDE.md imports it)
├── ARCHITECTURE.md     Architecture + connection diagrams
└── pyproject.toml
```

---

## References

- Beven, K. & Binley, A. (1992). The future of distributed models. *Hydrological Processes*, 6(3), 279–298.
- Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality. *Journal of Hydrology*, 333, 554–570.
- Tolson, B.A. & Shoemaker, C.A. (2007). Dynamically dimensioned search. *Water Resources Research*, 43(1), W01413.
- Storn, R. & Price, K. (1997). Differential evolution. *Journal of Global Optimization*, 11(4), 341–359.
- Kennedy, J. & Eberhart, R. (1995). Particle swarm optimization. *Proc. ICNN'95*, 4, 1942–1948.
- Shi, Y. & Eberhart, R. (1998). A modified particle swarm optimizer. *Proc. IEEE ICEC*, 69–73.
- Moriasi, D.N. et al. (2007). Model evaluation guidelines. *Trans. ASABE*, 50(3), 885–900.
- Helton, J.C. & Davis, F.J. (2003). Latin hypercube sampling. *Reliability Engineering & System Safety*, 81(1), 23–69.

---

*SpySWAT v0.2.6 · [CHANGELOG](CHANGELOG.md) · [Vietnamese](README_VI.md) · [Architecture](ARCHITECTURE.md) · [AGENTS](AGENTS.md)*
