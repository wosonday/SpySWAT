# SpySWAT — Agent Guide

> Version: 0.2.5 | Updated: 2026-06-18

This document provides orientation for AI agents (and developers) working inside the SpySWAT codebase.

---

## Project Overview

SpySWAT is a Python library for automated calibration, validation, and sensitivity analysis of SWAT hydrological models. It wraps the SWAT executable and TxtInOut file format with a clean Python API.

**Package root:** `spyswat/`
**Main entry point:** `SWATProject` in `spyswat/swat_project.py`
**CLI entry point:** `spyswat/__main__.py`

---

## Quick orientation

```
spyswat/
├── swat_project.py                 ← SWATProject: top-level facade
└── swat_calib/
    ├── core/
    │   ├── txinout.py              ← TxInOut: path management for TxtInOut/
    │   ├── hru_manager.py          ← HRUManager: read/write SWAT parameters
    │   ├── output_manager.py       ← OutputFileManager: read output.rch/hru/sub/sed
    │   └── workingFolder_manager.py← WorkingFolderManager: parallel worker dirs
    ├── io/
    │   ├── parameters.py           ← SWATParam, SWATParamInfo
    │   ├── readers.py              ← Fixed-width file readers
    │   ├── writers.py              ← HRUWriter: fixed-width column writes
    │   ├── mapping_file.py         ← Maps ext → file type
    │   └── file_cio.py             ← FileCIO: parse file.cio (sim dates)
    ├── calibration/
    │   ├── calib_manager.py        ← CalibrationManager: run_iteration, run_batch
    │   └── validation_runner.py    ← ValidationRunner, PeriodConfig
    ├── analysis/
    │   ├── statistics.py           ← SWATAnalysis: NSE, KGE, R², RMSE, ...
    │   ├── calibration.py          ← SWATCalibration: facade (optimize, analyze)
    │   ├── sensitivity.py          ← SWATSensitivity: OAT, Morris, SALib
    │   └── algorithms/
    │       ├── dds.py              ← DDS (standalone) + DDSCalibration
    │       ├── glue.py             ← GLUE + 95PPU
    │       ├── parallel_de.py      ← ParallelDE (Differential Evolution)
    │       └── pso.py              ← PSO (standalone) + PSOCalibration
    ├── run/
    │   └── swat_run.py             ← SWATRun: subprocess wrapper for SWAT exe
    ├── visualization/
    │   └── fig_viewer.py           ← FigViewer: fig.fig → interactive HTML
    └── utils/
        └── data_info.py            ← DATAParameter dataclass
```

---

## Key design rules (v0.2.5)

**1. Parameter keys must use `name.ext` format.**
`CN2.mgt`, `ALPHA_BF.gw`, `ESCO.hru` — never bare `CN2`. This disambiguates parameters that appear in multiple file types.

**2. No shared mutable state for methods/subbasins.**
`CalibrationManager` does not store `_methods` or `_subbasins` as instance fields. They are always passed as local arguments through `run_iteration(..., methods=None, subbasins=None)` and `_format_params(raw, methods, subbasins)`. Algorithms (GLUE, DE, DDS, PSO) parse `param_ranges` at the start of `run()` and pass locals down.

**3. param_ranges accepts a unified format (since v0.2.2).**
```python
param_ranges = {
    "ESCO.hru":    (0.01, 1.0),                        # bounds only → method defaults to "v"
    "CN2.mgt":     ((35, 98),   "r"),                  # bounds + method
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),   # bounds + method + subbasins
}
```
`_parse_spec()` raises `ValueError` if old-format tuple `(min, max)` has > 2 elements (catches misuse).

**4. Backup/restore in run_iteration.**
`_backup_state()` copies TxtInOut to a temp dir before each iteration. `_restore_state()` is called in `finally` — always runs even on exception. If a backup already exists when `_backup_state()` is called, it first restores the previous backup (no temp dir leak).

**5. _align_series infers frequency from obs.**
`pd.infer_freq(obs.index)` → `'MS'` (monthly) or `'D'` (daily). Assigns a DatetimeIndex to sim, then intersects with obs. This is the single authoritative alignment used by both `run_iteration` and `run_batch`.

**6. Parallel execution via ProcessPoolExecutor.**
`WorkingFolderManager.setup()` creates N isolated TxtInOut copies under `working_dir/TxInOut{1..N}`. `run_batch` chunks param_sets by `n_parallel`, calls `wf.run_parallel()` per chunk, then reads outputs from each worker.

**7. All runtime messages are in English.**
Log messages, `ValueError`, `RuntimeError`, `ImportError` strings — all English as of v0.2.5.

---

## Common tasks for agents

### Read a parameter value
```python
project.read_params_values(["CN2.mgt", "ALPHA_BF.gw"])
```

### Run a single SWAT iteration
```python
from spyswat.swat_calib.calibration import CalibrationManager
manager = CalibrationManager(project)
score = manager.run_iteration(
    {"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.5},
    observed_series, metric="nse"
)
```

### Run GLUE calibration
```python
from spyswat.swat_calib.analysis import SWATCalibration
calib = SWATCalibration(project)
calib.manager.setup_parallel(overwrite=True)
result = calib.glue.run(param_ranges, obs, n_samples=500, threshold=0.5, seed=42)
```

### Run PSO calibration
```python
result = calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50, seed=42)
print(result["best_params"])   # {name: [(val, method, ...)]}
print(result["best_score"])    # float
print(result["history"])       # iteration, best_score, mean_score, std_score
```

### Add a new calibration algorithm
1. Create `spyswat/swat_calib/analysis/algorithms/myalgo.py` — class with `__init__(self, manager)` and `run(param_ranges, observed_series, ...) -> dict` returning `{"best_params", "best_score", "history"}`
2. Use `self._manager.run_batch()` for population-based parallel evaluation (see `pso.py` as template)
3. Export from `algorithms/__init__.py`
4. Register in `SWATCalibration.__init__` as `self.myalgo = MyAlgoCalibration(self.manager)`
5. Add tests in `tests/test_myalgo.py` (mock `manager.run_batch`)

---

## Commands

```bash
# Install
pip install -e .

# Run tests
pytest tests/ -v
# Expected: 73 passed in ~5s

# CLI
python -m spyswat --help
```

---

## Important notes for agents

- **Do not restore swat_toolkit/** — the package was renamed to `spyswat/` and all imports use `spyswat.*`.
- **Test files** in `tests/` are proper pytest tests, not manual scripts. Do not delete or overwrite them without running the suite.
- **Windows paths** appear in some test fixtures — this is expected; SWAT runs on Windows.
- **ProcessPoolExecutor** means worker code must be picklable. Do not capture lambdas or local closures in worker functions.
- **TxtInOut mutation** — `run_iteration` modifies TxtInOut files and always restores them. Never call `project.HRU.update_params()` outside of CalibrationManager without manual backup/restore.
