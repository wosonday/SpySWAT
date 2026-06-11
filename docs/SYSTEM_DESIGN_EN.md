# SpySWAT System Design — Calibration, Validation & Sensitivity Analysis Extension

**Version:** 1.0  
**Date:** 2026-06-10  
**Scope:** Architecture design for extending SpySWAT with automated calibration, validation, and parameter sensitivity analysis workflows  

---

## Table of Contents

1. [Context and Objectives](#1-context-and-objectives)
2. [Current System Audit](#2-current-system-audit)
3. [Gap Analysis](#3-gap-analysis)
4. [Core Design Principle](#4-core-design-principle)
5. [Target Architecture](#5-target-architecture)
6. [Detailed Module Design](#6-detailed-module-design)
   - [6.1 CalibrationManager — The Transaction Boundary](#61-calibrationmanager--the-transaction-boundary)
   - [6.2 ValidationRunner — Two-Period Workflow](#62-validationrunner--two-period-workflow)
   - [6.3 SWATCalibration — Parameter Optimization](#63-swatcalibration--parameter-optimization)
   - [6.4 SWATSensitivity — Parallel Sensitivity Analysis](#64-swatsensitivity--parallel-sensitivity-analysis)
7. [End-to-End Data Flow](#7-end-to-end-data-flow)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Design Decisions and Trade-offs](#9-design-decisions-and-trade-offs)
10. [Scientific References](#10-scientific-references)

---

## 1. Context and Objectives

SpySWAT currently provides file read/write access to SWAT's `TxtInOut` directory and single-run execution. The goal of this extension is to integrate the full standard hydrological modelling workflow:

```
Sensitivity Analysis → Calibration → Validation → Uncertainty Estimation
```

This workflow is mandated by **Moriasi et al. (2007)** and is a prerequisite for publishing SWAT model results in peer-reviewed research.

**Specific objectives:**
- Identify which parameters most influence model outputs (sensitivity)
- Find the optimal parameter set that best matches observed data (calibration)
- Verify model generalizability on an independent time period (validation)
- Quantify prediction uncertainty from parameter equifinality (GLUE)

---

## 2. Current System Audit

### What is genuinely working

| Module | Status | Notes |
|--------|--------|-------|
| `TxInOut` | ✅ Working | Clean filesystem abstraction |
| `HRUManager.update_params()` | ✅ Working | Correct fixed-width file editing |
| `OutputFileManager` | ✅ Working | DataFrame cache keyed by filepath |
| `FileCIO` | ✅ Working | Reads/updates file.cio simulation period |
| `SWATAnalysis` | ✅ Working | NSE, KGE, PBIAS, R², RMSE, RSR |
| `WorkingFolderManager` | ✅ Working | Parallel subprocess execution |

### What has skeleton code but is non-functional

| Module | Actual Problem |
|--------|---------------|
| `CalibrationManager` | `_backup_state`, `_restore_state`, `_align_series` are all `...` (empty stubs) |
| `SWATCalibration` | `self._manager = None` → `optimize()` crashes immediately on `_manager.run_iteration()` |
| `SWATSensitivity` | Calls `project.update_parameters()` and `project.output.read_reach()` — **neither method exists** on `SWATProject` |
| `SWATRun.run()` | Receives `txinout_path: str` but applies the `/` operator (Path division) → `TypeError` on first call |

### Logic bugs identified

- `OutputFileManager.read_sed()` deduplicates columns using `_SUB_DEFAULT_COLS` instead of `_SED_DEFAULT_COLS`
- `mapping_output.py` line 112: `raise logger.exception(...)` → `raise None` (logger methods return `None`)
- `statistics.py._nse()` contains 3 leftover `print()` debug statements

---

## 3. Gap Analysis

### Functional gaps

```
REQUIRED                         CURRENT STATE
────────────────────────────     ─────────────────────────────
Backup TxtInOut before write  ←  Direct overwrite, no backup
Transaction rollback           ←  Not implemented
Time-series alignment          ←  Empty stub
Working calibration loop       ←  _manager = None
Two-period validation          ←  Does not exist
Parallel sensitivity           ←  Sequential + wrong API calls
```

### Interface mismatch

`SWATCalibration` and `SWATSensitivity` are written to call:
```python
self.project.update_parameters(params)     # DOES NOT EXIST
self.project.output.read_reach(reach_id)   # DOES NOT EXIST
self.project.run(clear_output_cache=True)  # WRONG SIGNATURE
```

The actual `SWATProject` API is:
```python
self.project.HRU.update_params(params)                            # correct
self.project.Output.read_rch(columns=[...], reach_id=reach_id)   # correct
self.project.run()                                                 # correct
```

---

## 4. Core Design Principle

> **Every write to TxtInOut is a destructive, irreversible operation. If a calibration iteration fails mid-loop, some files have been overwritten while others have not — leaving TxtInOut in an inconsistent state. The model will produce incorrect results or crash silently, with no indication of what went wrong.**

This is why `CalibrationManager` is the **single most critical component** in the extended system. It is the transaction boundary: every parameter write must either succeed completely or leave TxtInOut unchanged. Everything else — calibration algorithms, validation workflow, sensitivity analysis — builds on top of this guarantee.

**Design principles:**

1. **Atomic writes** — Every iteration must backup before writing; restore on failure
2. **Fail loudly** — Exceptions in the iteration loop must propagate; never swallow errors
3. **Parallel by default** — Sensitivity analysis is embarrassingly parallel; `WorkingFolderManager` already exists for this exact purpose
4. **No new abstractions** — The current architecture is sound; the problem is broken connections, not missing layers

---

## 5. Target Architecture

```
SWATProject  (unchanged — interface preserved)
│
├── [FIX] SWATRun.run()                → Fix type: str → Path
│
└── CalibrationManager                  [IMPLEMENT — critical]
    │  backup_state / restore_state / align_series
    │
    ├── (internal) CalibRunner          [thin wrapper]
    │     run_iteration()
    │     → backup → update_params → run → evaluate → (restore on failure)
    │
    ├── ValidationRunner                [NEW]
    │     calibrate(calib_period)
    │     validate(valid_period)
    │     → returns: calib_stats + valid_stats + best_params
    │
    ├── [FIX] SWATCalibration           → wire in real _manager
    │     optimize()                    → differential_evolution, nelder-mead
    │     glue_analysis()               → Monte Carlo + uncertainty bounds
    │
    └── [FIX] SWATSensitivity           → fix API calls + add parallel
          one_at_a_time()              → uses WorkingFolderManager
          morris_method()              → uses WorkingFolderManager
```

**Directory structure after extension:**

```
spyswat/
├── swat_project.py                    (unchanged)
├── swat_calib/
│   ├── calibration/
│   │   ├── calib_manager.py           ← IMPLEMENT
│   │   ├── validation_runner.py       ← NEW
│   │   └── __init__.py
│   ├── analysis/
│   │   ├── calibration.py             ← FIX (_manager wiring)
│   │   ├── sensitivity.py             ← FIX (API + parallel)
│   │   └── statistics.py              ← remove debug prints
│   └── run/
│       └── run.py                     ← FIX (str → Path)
```

---

## 6. Detailed Module Design

### 6.1 CalibrationManager — The Transaction Boundary

**Responsibility:** Guarantee that every calibration iteration is atomic — either fully successful or fully rolled back.

```python
# spyswat/swat_calib/calibration/calib_manager.py

import shutil, tempfile
from pathlib import Path
import pandas as pd
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)


class CalibrationManager:
    """
    Transaction boundary for all parameter-write + SWAT-run operations.

    Guarantees: if run_iteration() fails at any step,
    TxtInOut is restored to its pre-iteration state.
    """

    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None

    # ─── Public API ───────────────────────────────────────────

    def run_iteration(
        self,
        param_dict:      dict,
        observed:        pd.Series,
        metric:          str = 'nse',
        reach_id:        int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> float:
        """
        Execute one calibration iteration:
          1. Backup TxtInOut
          2. Write new parameter values
          3. Run SWAT
          4. Read output, compute metric
          5. On any failure: restore backup, re-raise

        Returns:
            Metric value (float) — higher is better for NSE, KGE, R²
        Raises:
            RuntimeError: wrapping the original exception
        """
        self._backup_state()
        try:
            self.project.HRU.update_params(param_dict)
            self.project.run()

            # Invalidate cache so we read the new output file
            self.project.Output.cache.clear()

            sim = self.project.Output.read_rch(
                columns  = ['RCH', 'MON', output_variable],
                reach_id = reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]

            logger.info(f"Iteration {metric}={score:.4f} | params={param_dict}")
            return float(score)

        except Exception as e:
            logger.warning(f"Iteration failed, restoring TxtInOut: {e}")
            self._restore_state()
            raise RuntimeError(f"Iteration failed: {e}") from e

    # ─── Transaction helpers ──────────────────────────────────

    def _backup_state(self) -> None:
        """Copy the entire TxtInOut directory to a temporary location."""
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)

        tmp = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        shutil.copytree(self.project.txinout.directory, tmp / "TxtInOut")
        self._backup_dir = tmp
        logger.debug(f"Backup created at: {self._backup_dir}")

    def _restore_state(self) -> None:
        """Restore TxtInOut from the most recent backup."""
        if self._backup_dir is None:
            logger.warning("No backup available to restore.")
            return

        src = self._backup_dir / "TxtInOut"
        dst = self.project.txinout.directory

        shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info(f"TxtInOut restored from: {src}")

    def _align_series(
        self, obs: pd.Series, sim: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """
        Align observed and simulated time series on a shared DatetimeIndex.

        Attaches the date range from FileCIO to sim, then intersects with obs.
        """
        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)

        if len(sim) != len(date_range):
            raise ValueError(
                f"Simulated length ({len(sim)}) ≠ date_range ({len(date_range)}). "
                "Check file.cio and output.rch are consistent."
            )

        sim.index = date_range
        common_idx = obs.index.intersection(sim.index)

        if len(common_idx) == 0:
            raise ValueError(
                "No overlapping dates between observed and simulated series. "
                "Verify the simulation period in file.cio."
            )

        return obs.loc[common_idx], sim.loc[common_idx]

    def cleanup(self) -> None:
        """Delete the temporary backup directory."""
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)
            self._backup_dir = None
```

**Design note — why backup the full directory:**
A typical TxtInOut folder is 20–100 MB. `shutil.copytree` completes in under one second. The simplicity and absolute consistency guarantees outweigh the disk overhead. Selective file backup (only modified files) would be more space-efficient but significantly more complex and error-prone.

---

### 6.2 ValidationRunner — Two-Period Workflow

**Responsibility:** Split observed data into calibration and validation periods, optimize on period 1, evaluate on period 2.

```python
# spyswat/swat_calib/calibration/validation_runner.py

from dataclasses import dataclass
from typing import Dict, Tuple
import pandas as pd
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)


@dataclass
class PeriodConfig:
    """
    Defines the calibration and validation time periods.

    Attributes:
        calib_start: Calibration start date (YYYY-MM-DD)
        calib_end:   Calibration end date
        valid_start: Validation start date
        valid_end:   Validation end date
    """
    calib_start: str
    calib_end:   str
    valid_start: str
    valid_end:   str


class ValidationRunner:
    """
    Executes the standard calibration → validation workflow (Moriasi et al., 2007).

    Example:
        >>> period = PeriodConfig('1990-01-01', '2004-12-31',
        ...                       '2005-01-01', '2019-12-31')
        >>> runner = ValidationRunner(project, param_ranges, observed, period)
        >>> result = runner.run(metric='nse', max_iter=150, reach_id=8)
        >>> print(result['calibration'])   # {'nse': 0.76}
        >>> print(result['validation'])    # {'nse': 0.71, 'kge': 0.73, 'pbias': -4.1}
    """

    def __init__(
        self,
        project,
        param_ranges: Dict[str, Tuple[float, float]],
        observed:     pd.Series,
        period:       PeriodConfig
    ):
        self.project      = project
        self.param_ranges = param_ranges
        self.observed     = observed
        self.period       = period

    def run(
        self,
        metric:          str = 'nse',
        method:          str = 'differential_evolution',
        max_iter:        int = 100,
        reach_id:        int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> Dict:
        """
        Execution flow:
          1. Slice observed data to calibration period
          2. Optimize parameters (SWATCalibration.optimize)
          3. Apply best parameters
          4. Slice observed data to validation period
          5. Evaluate all performance statistics

        Returns:
            {
                'best_parameters': {...},
                'calibration': {'nse': 0.76, ...},
                'validation':  {'nse': 0.71, 'kge': 0.73, ...},
                'period': PeriodConfig
            }
        """
        # ── Phase 1: Calibration ─────────────────────────────
        logger.info(f"Calibration period: {self.period.calib_start} → {self.period.calib_end}")
        obs_calib = self.observed.loc[self.period.calib_start : self.period.calib_end]

        best_params, calib_score = self._calibrate(
            obs_calib, metric, method, max_iter, reach_id, output_variable
        )
        logger.info(f"Calibration complete. {metric.upper()} = {calib_score:.4f}")
        logger.info(f"Best parameters: {best_params}")

        # ── Phase 2: Validation ──────────────────────────────
        logger.info(f"Validation period: {self.period.valid_start} → {self.period.valid_end}")
        self.project.HRU.update_params(best_params)
        self.project.run()
        self.project.Output.cache.clear()

        sim = self.project.Output.read_rch(
            columns  = ['RCH', 'MON', output_variable],
            reach_id = reach_id
        )[output_variable]

        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)
        sim.index = date_range

        obs_valid = self.observed.loc[self.period.valid_start : self.period.valid_end]
        common    = obs_valid.index.intersection(sim.index)

        valid_stats = self.project.Statistic.calculate_statistics(
            obs_valid.loc[common], sim.loc[common]
        )
        logger.info(f"Validation: NSE={valid_stats.get('nse', float('nan')):.4f}, "
                    f"KGE={valid_stats.get('kge', float('nan')):.4f}")

        return {
            'best_parameters': best_params,
            'calibration':     {metric: calib_score},
            'validation':      valid_stats,
            'period':          self.period,
        }

    def _calibrate(self, obs_calib, metric, method, max_iter, reach_id, output_variable):
        from spyswat.swat_calib.analysis.calibration import SWATCalibration
        calib  = SWATCalibration(self.project)
        result = calib.optimize(
            param_ranges    = self.param_ranges,
            observed_series = obs_calib,
            method          = method,
            metric          = metric,
            max_iter        = max_iter,
            reach_id        = reach_id,
            output_variable = output_variable,
        )
        return result['best_parameters'], result['best_objective_value']
```

---

### 6.3 SWATCalibration — Parameter Optimization

**Required fix:** Replace `self._manager = None` with a real `CalibrationManager` instance. Fix `objective()` to use the correct `HRUManager` parameter format.

```python
# Key changes in spyswat/swat_calib/analysis/calibration.py

class SWATCalibration:
    def __init__(self, project, analysis=None):
        self.project  = project
        self.analysis = analysis or SWATAnalysis(project)
        # FIX: wire in real CalibrationManager
        from spyswat.swat_calib.calibration import CalibrationManager
        self._manager = CalibrationManager(project)
        self.optimization_history = []

    def optimize(self, param_ranges, observed_series,
                 method='differential_evolution', metric='nse',
                 max_iter=100, reach_id=1,
                 output_variable='FLOW_OUTcms') -> dict:

        names  = list(param_ranges.keys())
        bounds = [param_ranges[n] for n in names]

        def objective(x: list) -> float:
            # Convert optimizer array → HRUManager.update_params() format
            param_dict = {name: [(val, 'v')] for name, val in zip(names, x)}
            score = self._manager.run_iteration(
                param_dict, observed_series, metric, reach_id, output_variable
            )
            self.optimization_history.append({
                'params': dict(zip(names, x)), 'score': score
            })
            # scipy minimizes → negate for metrics where higher = better
            return -score if metric in ('nse', 'r2', 'kge') else score

        if method == 'differential_evolution':
            from scipy.optimize import differential_evolution
            result = differential_evolution(
                objective, bounds, maxiter=max_iter, seed=42, tol=1e-4
            )
        else:
            from scipy.optimize import minimize
            x0     = [(lo + hi) / 2 for lo, hi in bounds]
            result = minimize(objective, x0, method=method, bounds=bounds)

        best_params = {name: [(val, 'v')] for name, val in zip(names, result.x)}
        return {
            'best_parameters':      best_params,
            'best_objective_value': -result.fun,
            'history':              self.optimization_history,
        }
```

---

### 6.4 SWATSensitivity — Parallel Sensitivity Analysis

**Current problem:** Sequential execution with wrong API calls. OAT with 5 parameters × 10 steps = 50 SWAT runs that could be parallelized.

**New design:** Each parameter-set evaluation is an independent worker using `WorkingFolderManager`.

```
Parallel OAT design:

param_sets = [ (CN2=60, ESCO=0.5, ...), (CN2=62, ESCO=0.5, ...),
               (CN2=64, ESCO=0.5, ...), ..., 50 parameter sets total ]
                       ↓
WorkingFolderManager.setup(n_parallel=min(cpu_count, len(param_sets)))
                       ↓
ProcessPoolExecutor → workers run simultaneously
                       ↓
Collect output from each worker → aggregate into results DataFrame
```

**Updated `one_at_a_time()` signature:**

```python
def one_at_a_time(
    self,
    param_ranges:    dict,
    n_steps:         int = 10,
    baseline_params: dict | None = None,
    observed_series: pd.Series | None = None,
    output_variable: str = 'FLOW_OUTcms',
    reach_id:        int = 1,
    metric:          str = 'nse',
    n_parallel:      int = 4,    # ← NEW
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        (results_df, sensitivity_df)
        results_df:     columns = [parameter, value, metric]
        sensitivity_df: columns = [parameter, metric_range, sensitivity_index]
                        sorted by sensitivity_index descending
    """
```

**Sensitivity indices computed:**

| Index | Formula | Interpretation |
|-------|---------|----------------|
| `metric_range` | max(metric) − min(metric) | Absolute influence range |
| `sensitivity_index` | range / std | Normalized influence |
| Morris μ* | mean(\|EE\|) | Overall importance |
| Morris σ | std(EE) | Non-linearity / interaction effects |

---

## 7. End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPLETE WORKFLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Step 1 — SENSITIVITY ANALYSIS (SWATSensitivity)                │
│     param_ranges (wide) → OAT / Morris (parallel workers)        │
│     → sensitivity_df: parameters ranked by importance            │
│     → Narrow param_ranges for calibration                        │
│                          ↓                                        │
│  Step 2 — CALIBRATION (SWATCalibration via CalibrationManager)  │
│     param_ranges (narrow) × observed_calib                       │
│     → differential_evolution / GLUE Monte Carlo                  │
│     → best_params + full optimization history                    │
│                          ↓                                        │
│  Step 3 — VALIDATION (ValidationRunner)                          │
│     best_params × observed_valid (independent period)            │
│     → calib_stats + valid_stats                                   │
│     → Performance rating (Moriasi thresholds)                    │
│                          ↓                                        │
│  Step 4 — UNCERTAINTY ESTIMATION — optional (GLUE)              │
│     behavioral_params (NSE ≥ threshold)                          │
│     → prediction uncertainty bounds (5th / 95th percentile)      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Complete usage example

```python
from spyswat import SWATProject
from spyswat.swat_calib.calibration import ValidationRunner, PeriodConfig
from spyswat.swat_calib.analysis import SWATSensitivity, SWATCalibration
import pandas as pd

# ── Initialize project ────────────────────────────────────────
project = SWATProject(
    txinout_dir = r"D:\MyProject\TxtInOut",
    working_dir = r"D:\MyProject\working",
    swat_exe    = r"D:\tools\swat_695.exe",
    param_file  = r"D:\MyProject\swatParam.txt",
    n_parallel  = 8
)

obs = pd.read_csv("Q_observed.csv", index_col='date', parse_dates=['date'])['discharge']

# ── Step 1: Sensitivity analysis ──────────────────────────────
param_ranges_wide = {
    'CN2':      (55.0, 95.0),
    'ESCO':     (0.0,  1.0),
    'ALPHA_BF': (0.0,  1.0),
    'GW_DELAY': (0.0, 500.0),
    'SOL_AWC':  (-0.5, 0.5),   # relative change
    'CH_N2':    (0.01, 0.3),
}

sensitivity = SWATSensitivity(project)
results_df, sensitivity_df = sensitivity.one_at_a_time(
    param_ranges    = param_ranges_wide,
    n_steps         = 10,
    observed_series = obs,
    metric          = 'nse',
    reach_id        = 8,
    n_parallel      = 6
)
print(sensitivity_df.head(4))
# parameter    metric_range    sensitivity_index
# CN2          0.42            3.8
# ALPHA_BF     0.31            2.7
# ESCO         0.18            1.5
# GW_DELAY     0.09            0.8

# ── Steps 2 + 3: Calibration and Validation ──────────────────
# Use only the 4 most sensitive parameters
param_ranges_narrow = {
    'CN2':      (60.0, 90.0),
    'ALPHA_BF': (0.0,  1.0),
    'ESCO':     (0.5,  1.0),
    'GW_DELAY': (0.0, 200.0),
}

period = PeriodConfig(
    calib_start = '1990-01-01', calib_end = '2004-12-31',
    valid_start = '2005-01-01', valid_end = '2019-12-31'
)

runner = ValidationRunner(project, param_ranges_narrow, obs, period)
result = runner.run(metric='nse', method='differential_evolution',
                    max_iter=150, reach_id=8)

print(result['calibration'])   # {'nse': 0.76}
print(result['validation'])    # {'nse': 0.71, 'kge': 0.73, 'pbias': -4.1}

# Qualitative rating per Moriasi et al. (2007)
# NSE 0.71 → 'Good'; PBIAS -4.1 → 'Very Good'

# ── Step 4: Uncertainty estimation (GLUE) ────────────────────
calib = SWATCalibration(project)
glue = calib.glue_analysis(
    param_ranges    = param_ranges_narrow,
    observed_series = obs.loc[period.calib_start:period.calib_end],
    n_samples       = 1000,
    threshold       = 0.65,   # behavioral: NSE ≥ 0.65
    metric          = 'nse',
    reach_id        = 8
)
print(f"Behavioral parameter sets: {glue['behavioral_ratio']:.1%}")  # e.g. 12.3%
```

---

## 8. Implementation Roadmap

```
Step 1 — Fix blocking bugs (must complete before anything else)
├── Implement CalibrationManager._backup_state / _restore_state / _align_series
│   Verify: failed iteration → TxtInOut restored to exact pre-iteration state
├── Fix SWATRun.run(): txinout_path: str → Path(txinout_path)
│   Verify: project.run() no longer raises TypeError
└── Fix raise None in mapping_output.py line 112
    Verify: reading a non-existent column raises KeyError, not TypeError

Step 2 — Wire CalibrationManager into SWATCalibration
├── Replace self._manager = None with CalibrationManager(project)
├── Fix objective() to use HRUManager.update_params() param format
│   Verify: optimize() runs 1 iteration → returns a float, no crash

Step 3 — Add ValidationRunner + PeriodConfig
├── Implement ValidationRunner.run()
│   Verify: calib_score and valid_score are both floats (not nan)
└── Verify: valid_score is reasonably close to calib_score (no severe overfit)

Step 4 — Fix SWATSensitivity
├── Replace project.update_parameters() → project.HRU.update_params()
├── Replace project.output.read_reach() → project.Output.read_rch()
└── Add n_parallel parameter, integrate WorkingFolderManager
    Verify: OAT with 50 simulations at n_parallel=4 runs ~4x faster than sequential

Step 5 — Housekeeping
├── Remove 3 debug print() calls in statistics.py._nse()
├── Remove 2 debug print() calls in mapping_output.__read_all()
└── Fix read_sed() deduplication: _SUB_DEFAULT_COLS → _SED_DEFAULT_COLS
```

---

## 9. Design Decisions and Trade-offs

### Decision 1: Full-directory backup vs. file-level backup

| Option | Pros | Cons |
|--------|------|------|
| **Full directory (chosen)** | Simple, absolute consistency | Uses more disk (~50–100 MB per backup) |
| Modified files only | Space-efficient | Complex tracking; risk of missing files |

Chosen: full directory. A typical TxtInOut is < 100 MB; `shutil.copytree` completes in under one second. The simplicity guarantee is worth the disk cost.

### Decision 2: Fix call sites rather than add aliases to SWATProject

`SWATCalibration` and `SWATSensitivity` call non-existent methods on `SWATProject`. Two ways to fix:

| Option | Approach |
|--------|---------|
| **A (chosen): Fix callers** | Change `project.update_parameters()` → `project.HRU.update_params()` in calibration/sensitivity code |
| B: Add aliases | Add `def update_parameters(self, params): return self.HRU.update_params(params)` to `SWATProject` |

Chosen: Option A. Fewer lines of code; does not expand `SWATProject`'s public surface.

### Decision 3: Sensitivity analysis must be parallel from the start

OAT and Morris methods are **embarrassingly parallel** — each simulation run is fully independent. There is no reason to run them sequentially. `WorkingFolderManager` already exists precisely for this use case. Running 50 simulations sequentially when 4–8 CPU cores are available would make sensitivity analysis impractically slow for real-world catchments.

### Decision 4: No persistence layer

Calibration results are returned as Python dicts and DataFrames. Users decide how to persist them (CSV, pickle, database). Adding persistence would introduce unnecessary dependencies and architectural complexity.

---

## 10. Scientific References

- **Moriasi, D.N., Arnold, J.G., Van Liew, M.W., Bingner, R.L., Harmel, R.D., & Veith, T.L. (2007).** Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Transactions of the ASABE*, 50(3), 885–900. — Performance rating thresholds (NSE, PBIAS, RSR).

- **Beven, K. & Binley, A. (1992).** The future of distributed models: Model calibration and uncertainty prediction. *Hydrological Processes*, 6(3), 279–298. — Generalized Likelihood Uncertainty Estimation (GLUE).

- **Morris, M.D. (1991).** Factorial sampling plans for preliminary computational experiments. *Technometrics*, 33(2), 161–174. — Morris elementary effects method.

- **van Griensven, A., Meixner, T., Grunwald, S., Bishop, T., Diluzio, M., & Srinivasan, R. (2006).** A global sensitivity analysis tool for the parameters of multi-variable catchment models. *Journal of Hydrology*, 324(1–4), 10–23. — SWAT-specific sensitivity analysis application.

- **Arnold, J.G., Srinivasan, R., Muttiah, R.S., & Williams, J.R. (1998).** Large area hydrologic modeling and assessment part I: Model development. *Journal of the American Water Resources Association*, 34(1), 73–89. — Original SWAT model publication.

- **Gupta, H.V., Kling, H., Yilmaz, K.K., & Martinez, G.F. (2009).** Decomposition of the mean squared error and NSE performance criteria: Implications for improving hydrological modelling. *Journal of Hydrology*, 377(1–2), 80–91. — Kling-Gupta Efficiency (KGE) formulation.
