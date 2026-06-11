# SpySWAT 🌊

**Python library for SWAT model calibration, validation, and sensitivity analysis**

> Vietnamese version: [README_VI.md](README_VI.md) · Changelog: [CHANGELOG.md](CHANGELOG.md)

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Project Setup](#project-setup)
- [Quick Workflow (Recommended)](#quick-workflow-recommended)
- [Calibration](#calibration)
- [Validation](#validation)
- [Sensitivity Analysis](#sensitivity-analysis)
- [Reading and Writing TxtInOut](#reading-and-writing-txtinout)
- [Reading SWAT Output](#reading-swat-output)
- [Performance Statistics](#performance-statistics)
- [Parallel Execution](#parallel-execution)
- [Parameter File](#parameter-file)
- [API Reference](#api-reference)

---

## Overview

SpySWAT provides:

- Direct read/write access to SWAT TxtInOut files (fixed-width format)
- Automated parameter calibration: GLUE, Differential Evolution, PSO
- Parallel execution of multiple parameter sets via `ProcessPoolExecutor`
- Sensitivity analysis from existing calibration results — **no extra SWAT runs**
- Performance evaluation following Moriasi et al. (2007)

---

## Installation

```bash
pip install spyswat
# or from source
git clone https://github.com/yourname/spyswat
pip install -e .
```

Requirements: Python >= 3.12, numpy, pandas, scipy

---

## Project Setup

```python
from spyswat import SWATProject

project = SWATProject(
    txinout_dir="D:/SWAT/my_project/TxtInOut",
    working_dir="D:/SWAT/workers",
    swat_exe="D:/SWAT/swat_rev688.exe",
    param_file="params.txt",
    n_parallel=8
)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `txinout_dir` | Yes | Path to TxtInOut directory |
| `working_dir` | Yes | Directory for worker copies (auto-created) |
| `swat_exe` | Yes | Path to SWAT executable |
| `param_file` | No | Parameter definition file `.txt` |
| `n_parallel` | No | Number of parallel workers (default: 1) |

---

## Quick Workflow (Recommended)

Since v0.2.0, `SWATCalibration.analyze()` performs the complete workflow in a single call:
**parallel GLUE → best params → sensitivity → performance rating** — from N SWAT runs only.

```python
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.analysis import SWATCalibration

project = SWATProject(
    txinout_dir="path/TxtInOut",
    working_dir="path/workers",
    swat_exe="path/swat.exe",
    param_file="params.txt",
    n_parallel=8
)

obs = pd.read_csv("observed_flow.csv", index_col="date", parse_dates=True)["flow"]

param_ranges = {
    "CN2":      (35, 98),
    "ALPHA_BF": (0.0, 1.0),
    "GW_DELAY": (30, 450),
    "ESCO":     (0.01, 1.0),
    "SOL_AWC":  (0.01, 0.5),
}

calib = SWATCalibration(project)
result = calib.analyze(
    param_ranges=param_ranges,
    observed_series=obs,
    n_samples=1000,
    threshold=0.5,
    metric="nse"
)

print(f"Best NSE:  {result['best_score']:.3f}")
print(result['best_params'])
print(result['sensitivity'])
print(result['performance'])
```

What happens inside `analyze()`:

```
1000 LHS samples
      |
      v
run_batch (8 workers in parallel)
      |
      v
1000 (params, score) pairs
   /          |           \
best       sensitivity    behavioral
params     (Spearman,     (NSE >= 0.5)
           0 extra runs)
```

---

## Calibration

### GLUE – Monte Carlo (parallel)

```python
from spyswat.swat_calib.analysis import SWATCalibration

calib = SWATCalibration(project)
calib._manager.setup_parallel(overwrite=True)

result = calib.glue_analysis(
    param_ranges=param_ranges,
    observed_series=obs,
    n_samples=1000,
    threshold=0.5,
    metric="nse",
    output_variable="FLOW_OUTcms",
    reach_id=1
)

print(result["all_results"])
print(result["behavioral_results"])
print(f"Behavioral ratio: {result['behavioral_ratio']:.1%}")
```

### Differential Evolution

```python
result = calib.optimize(
    param_ranges=param_ranges,
    observed_series=obs,
    method="differential_evolution",
    metric="nse",
    max_iter=100,
    reach_id=1
)

print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

### Manual single iteration

```python
from spyswat.swat_calib.calibration import CalibrationManager

manager = CalibrationManager(project)
score = manager.run_iteration(
    param_dict={"CN2": [(75.0, "v")], "ALPHA_BF": [(0.5, "v")]},
    observed=obs,
    metric="nse",
    reach_id=1
)
print(f"NSE = {score:.4f}")
```

---

## Validation

```python
# Apply best parameters
best = result["best_params"]
project.HRU.update_params(best)
project.run()

# Read validation period output
sim = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms"],
    reach_id=1
)["FLOW_OUTcms"]

obs_val = obs["2010-01-01":"2015-12-31"]
sim_val = sim["2010-01-01":"2015-12-31"]

stats  = project.Statistic.calculate_statistics(obs_val, sim_val)
rating = project.Statistic.evaluate_performance(obs_val, sim_val)
print(stats)   # {'nse': 0.71, 'kge': 0.68, ...}
print(rating)  # {'nse': 'Good', ...}
```

---

## Sensitivity Analysis

### From GLUE results (recommended – no extra SWAT runs)

```python
sensitivity = project.Statistic.sensitivity_from_results(
    results_df=result["all_results"],
    metric="nse",
    method="spearman"   # or "prcc"
)
print(sensitivity)
# parameter  sensitivity_index  rank
# ALPHA_BF        0.83            1
# CN2             0.61            2
# GW_DELAY        0.45            3
```

Methods:

| method | Full name | Advantage |
|--------|-----------|-----------|
| `spearman` | Spearman rank correlation | Fast, no linearity assumption |
| `prcc` | Partial Rank Correlation Coefficient | Removes cross-parameter effects |

### OAT – One-At-a-Time (parallel)

```python
from spyswat.swat_calib.analysis import SWATSensitivity

sens = SWATSensitivity(project)
oat_df, indices = sens.one_at_a_time(
    param_ranges=param_ranges,
    n_steps=10,
    observed_series=obs,
    metric="nse"
)
print(indices)
```

### Morris Method (parallel)

```python
morris = sens.morris_method(
    param_ranges=param_ranges,
    n_trajectories=10,
    observed_series=obs,
    metric="nse"
)
print(morris["morris_indices"])
```

---

## Reading and Writing TxtInOut

### Update HRU parameters

```python
project.HRU.update_params({
    "CN2":      [(75.0, "v")],    # v = direct assignment
    "ALPHA_BF": [(0.5,  "v")],
    "ESCO":     [(0.1,  "r")],    # r = multiply by (1 + val)
    "SOL_AWC":  [(0.05, "add")],  # add = add to current value
})
```

Update methods:

| Code | Formula | Meaning |
|------|---------|---------|
| `v` / `replace` | `new = val` | Direct assignment |
| `r` / `relative` | `new = old × (1 + val)` | Relative change |
| `add` | `new = old + val` | Additive change |

### Read current parameter values

```python
values = project.read_params_values(["CN2", "ALPHA_BF", "ESCO"])
```

---

## Reading SWAT Output

```python
# output.rch
rch = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms", "SED_OUTtons"],
    reach_id=1
)

# output.hru
hru = project.Output.read_hru(
    columns=["LULC", "HRU", "MON", "ET", "SURQ_GEN"]
)

# output.sub
sub = project.Output.read_sub(columns=["SUB", "MON", "PRECIP", "SURQ"])

# output.sed
sed = project.Output.read_sed()

# watout.dat
wat = project.Output.read_watout()
```

Common output.rch variables:

| Variable | Unit | Description |
|----------|------|-------------|
| `FLOW_OUTcms` | m³/s | Outflow |
| `SED_OUTtons` | ton | Sediment outflow |
| `NO3_OUTkg` | kg | Nitrate |
| `ORG_N_kg` | kg | Organic nitrogen |

---

## Performance Statistics

```python
stats  = project.Statistic.calculate_statistics(obs, sim)
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

SpySWAT uses `ProcessPoolExecutor` with a worker pool model: N TxtInOut copies, each worker uses its own isolated copy.

```
1000 samples, 8 workers → 125 batches × T_swat ≈ 8× speedup

Batch 1:   [s1  s2  s3  s4  s5  s6  s7  s8]  ← simultaneous
Batch 2:   [s9  s10 s11 s12 s13 s14 s15 s16]
...
Batch 125: [s993..s1000]
```

Manual setup:

```python
project.WorkingFolder.setup(overwrite=True)

worker_dirs = project.WorkingFolder.run_parallel(
    swat_exe="path/swat.exe",
    param_sets=[
        {"CN2": [(70.0, "v")]},
        {"CN2": [(75.0, "v")]},
        {"CN2": [(80.0, "v")]},
    ]
)

for i in range(3):
    flow = project.worker(i + 1).Output.read_rch(
        columns=["RCH", "MON", "FLOW_OUTcms"], reach_id=1
    )["FLOW_OUTcms"]
    print(flow.mean())
```

---

## Parameter File

Tab-separated definition file:

```
# name    ext     line  col_start  col_end  round  vmin   vmax
CN2       .mgt    8     3          12       1      35.0   98.0
ALPHA_BF  .gw     6     3          12       3      0.0    1.0
GW_DELAY  .gw     5     3          12       1      30.0   450.0
ESCO      .hru    9     3          12       3      0.01   1.0
SOL_AWC   .sol    0     0          0        3      0.01   0.5
```

---

## API Reference

### SWATProject

```
project.HRU.update_params(param_dict)
project.HRU.update_by_df(df)
project.read_params_values(param_list)
project.run()
project.get_date_range(freq='D')
project.worker(index)
project.Output.read_rch / read_hru / read_sub / read_sed / read_watout
project.Statistic.calculate_statistics(obs, sim)
project.Statistic.evaluate_performance(obs, sim)
project.Statistic.sensitivity_from_results(df, metric, method)   # v0.2.0
project.FileCIO.get_date_range_sim(freq)
project.WorkingFolder.setup(overwrite)
project.WorkingFolder.run_parallel(exe, param_sets)
project.info()
```

### CalibrationManager

```
CalibrationManager(project)
  .setup_parallel(overwrite=False)
  .run_iteration(param_dict, obs, metric, ...)
  .run_batch(param_sets, obs, metric, ...)       # v0.2.0
```

### SWATCalibration

```
SWATCalibration(project)
  .analyze(param_ranges, obs, n_samples, ...)    # v0.2.0 – unified workflow
  .glue_analysis(param_ranges, obs, n_samples)
  .optimize(param_ranges, obs, method, ...)
```

### SWATSensitivity

```
SWATSensitivity(project)
  .one_at_a_time(param_ranges, n_steps, obs)
  .morris_method(param_ranges, n_trajectories)
```

---

## References

- Moriasi et al. (2007). *Model Evaluation Guidelines.* ASABE, 50(3), 885–900.
- Beven & Binley (1992). *GLUE.* Hydrological Processes, 6(3), 279–298.
- Saltelli et al. (2008). *Global Sensitivity Analysis: The Primer.* Wiley.
- Helton & Davis (2003). *Latin hypercube sampling.* Reliability Engineering & System Safety, 81(1), 23–69.

---

*SpySWAT v0.2.0 · [CHANGELOG](CHANGELOG.md) · [Vietnamese](README_VI.md)*
