# SpySWAT 🌊

**Python library for SWAT model calibration, validation, and sensitivity analysis**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-73%20passed-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.2.1-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

> Vietnamese version: [README_VI.md](README_VI.md) · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Changelog: [CHANGELOG.md](CHANGELOG.md)

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Project Setup](#project-setup)
- [Parameter Key Format](#parameter-key-format)
- [Quick Start](#quick-start)
- [Calibration](#calibration)
- [Validation](#validation)
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
- Automated calibration: **GLUE** (parallel Monte Carlo), **DDS**, **Parallel DE**
- Uncertainty quantification: 95PPU band, p-factor, r-factor
- Sensitivity analysis from GLUE results — **zero extra SWAT runs**
- Performance evaluation following Moriasi et al. (2007)
- Parallel execution via `ProcessPoolExecutor` with isolated worker copies

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
| `param_file` | — | Parameter definition file `.txt` |
| `n_parallel` | — | Number of parallel workers (default: 1) |

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

From v0.2.1, algorithms are standalone classes accessed via `calib.glue`, `calib.de`, `calib.dds`.

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

### Scipy DE / Nelder-Mead (sequential)

```python
result = calib.optimize(
    param_ranges    = param_ranges,
    observed_series = obs,
    method          = "differential_evolution",  # or "minimize"
    metric          = "nse",
    max_iter        = 100,
)
print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

### param_methods — per-parameter update control

All algorithms accept `param_methods` to specify how each parameter value is applied:

```python
methods = {
    "CN2.mgt":     "r",   # relative: new = old × (1 + val)
    "ALPHA_BF.gw": "v",   # replace:  new = val
    "ESCO.hru":    "a",   # add:      new = old + val
}
result = calib.glue.run(param_ranges, obs, param_methods=methods)
result = calib.de.run(param_ranges, obs, param_methods=methods)
result = calib.dds.run(param_ranges, obs, param_methods=methods)
result = calib.analyze(param_ranges, obs, param_methods=methods)
```

| Code | Formula | Meaning |
|------|---------|---------|
| `v` (default) | `new = val` | Direct assignment |
| `r` | `new = old × (1 + val)` | Relative change |
| `a` | `new = old + val` | Additive change |

---

## Validation

```python
# Apply best params from calibration
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
r = runner.run(metric="nse")
print("Calib NSE:", r["calibration"]["nse"])
print("Valid NSE:", r["validation"]["nse"])
```

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
```

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

---

## Performance Statistics

```python
stats  = project.Statistic.calculate_statistics(obs, sim,
    metrics=["nse", "kge", "r2", "rmse", "pbias", "rsr"])
rating = project.Statistic.evaluate_performance(obs, sim)
```

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
print(results)   # DataFrame: nse
```

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
project.FileCIO.get_date_range_sim(freq)
project.WorkingFolder.setup(overwrite)
project.info()
```

### SWATCalibration

```
calib = SWATCalibration(project)

# Standalone algorithm instances
calib.glue    → GLUE(manager, analysis)
calib.de      → ParallelDE(manager)
calib.dds     → DDSCalibration(manager)
calib.manager → CalibrationManager

# Algorithm methods
calib.glue.run(param_ranges, obs, n_samples, threshold, metric, seed,
               compute_uncertainty, param_methods) → dict
calib.glue.uncertainty_band(behavioral_df, obs, metric, param_methods) → dict
calib.de.run(param_ranges, obs, pop_size, max_generations, F, CR,
             strategy, seed, tol, patience, param_methods) → dict
calib.dds.run(param_ranges, obs, n_iterations, r, seed, metric,
              output_variable, reach_id, maximize) → dict

# Orchestrated workflows
calib.analyze(param_ranges, obs, n_samples, threshold, metric,
              sensitivity_method, seed, param_methods) → dict
calib.optimize(param_ranges, obs, method, metric, max_iter) → dict
```

### Standalone Algorithm Classes

```python
from spyswat.swat_calib.analysis.algorithms import DDS, DDSCalibration, GLUE, ParallelDE

DDS(param_ranges, objective, n_iterations=200, r=0.2, seed=None, maximize=True)
  .run() → {"best_params", "best_score", "history"}

DDSCalibration(manager)
  .run(param_ranges, obs, ...) → dict

GLUE(manager, analysis=None)
  .run(param_ranges, obs, ...) → dict
  .uncertainty_band(behavioral_df, obs, ...) → dict

ParallelDE(manager)
  .run(param_ranges, obs, ...) → dict
```

### CalibrationManager

```
CalibrationManager(project)
  .setup_parallel(overwrite=False)
  .run_iteration(param_dict, obs, metric, reach_id, output_variable) → float
  .run_batch(param_sets, observed, metrics, reach_id, output_variable) → DataFrame
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
│       ├── calibration/ CalibrationManager, ValidationRunner
│       └── analysis/   SWATAnalysis, SWATCalibration (facade), SWATSensitivity
│                       └── algorithms/  dds.py, glue.py, parallel_de.py
├── tests/              73 tests (pytest)
├── ARCHITECTURE.md     Architecture + connection diagrams
└── pyproject.toml
```

---

## References

- Beven, K. & Binley, A. (1992). The future of distributed models. *Hydrological Processes*, 6(3), 279–298.
- Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality. *Journal of Hydrology*, 333, 554–570.
- Tolson, B.A. & Shoemaker, C.A. (2007). Dynamically dimensioned search. *Water Resources Research*, 43(1), W01413.
- Storn, R. & Price, K. (1997). Differential evolution. *Journal of Global Optimization*, 11(4), 341–359.
- Moriasi, D.N. et al. (2007). Model evaluation guidelines. *Trans. ASABE*, 50(3), 885–900.
- Helton, J.C. & Davis, F.J. (2003). Latin hypercube sampling. *Reliability Engineering & System Safety*, 81(1), 23–69.

---

*SpySWAT v0.2.1 · [CHANGELOG](CHANGELOG.md) · [Vietnamese](README_VI.md) · [Architecture](ARCHITECTURE.md)*
