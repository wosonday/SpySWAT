# SpySWAT Agent Guide

## Project Overview

SpySWAT is a Python toolkit for SWAT (Soil and Water Assessment Tool) model calibration and manipulation. It interfaces with the SWAT model executable to run simulations and analyze outputs.

## Package Structure

- **Main package**: `swat_toolkit/`
- **Entry point**: `SWATProject` class in `swat_toolkit/swat_project.py`
- **CLI command**: `spyswat` (via `swat_toolkit.__main__:main`)
- **Core submodules** under `swat_toolkit/swat_calib/`: `analysis/`, `calibration/`, `core/`, `io/`, `run/`, `utils/`, `visualization/`

## Commands

```bash
# Install dependencies (requires Python 3.12+)
uv sync

# Run CLI
spyswat --txinout <path> --workingF <path> --exe <path> --params <path> --observed <path> --n_parallel <n>

# Build package
uv build
```

## Important Notes

- **Windows-only data paths**: Test files (`test/*.py`, `main_test.py`, `main.py`) contain hardcoded Windows absolute paths to SWAT data directories. These are manual test scripts, not automated tests.
- **Python 3.12 required**: Project specifies `requires-python = ">=3.12"`
- **Dependency quirks**: `pyodbc` requires ODBC drivers; Dockerfile handles this with `unixodbc-dev` and `libodbc.so.2`
- **No pytest framework**: Test directory contains exploratory scripts, not a formal test suite
- **matplotlib logging**: `swat_toolkit/__init__.py` suppresses matplotlib logging by setting `logging.getLogger('matplotlib').setLevel(logging.WARNING)`

## Architecture Notes

- `SWATProject` is the main facade class providing:
  - `HRU` property: HRU parameter management
  - `Output` property: output file reading (`read_rch`, `read_sed`, etc.)
  - `WorkingFolder` property: parallel worker setup
  - `Statistic` property: statistical analysis
  - `FileCIO` property: file I/O operations
- Worker pattern: `project.WorkingFolder.setup()` creates parallel TxInOut copies, then `project.worker(n)` returns a sub-project for worker `n`