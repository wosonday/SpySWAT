# SpySWAT — Agent Guide

> Version: 0.2.6 + unreleased `fix/phase1-correctness` | Updated: 2026-11-18

Orientation for AI agents (Claude Code, Codex, OpenCode) and developers working in the
SpySWAT codebase. **Project rules in this file win over the general team workflow**
(`docs/agents/AGENTS-TUTORIAL.md`). This repository is **public**: see
[Public repository rules](#public-repository-rules).

---

## Project overview

SpySWAT is a Python library for calibration, validation, sensitivity analysis and
scenario runs of SWAT hydrological models. It wraps the SWAT executable and the
TxtInOut file format with a Python API.

- **Package root:** `spyswat/`
- **Main entry point:** `SWATProject` in `spyswat/swat_project.py`
- **CLI entry point:** `spyswat/__main__.py` (runs SWAT once; `python -m spyswat --help`)

---

## Quick orientation

```
spyswat/
├── swat_project.py                 ← SWATProject: top-level facade (param_file optional)
├── logger.py                       ← Logger: file/console logging, queue listener for workers
└── swat_calib/
    ├── core/
    │   ├── txinout.py              ← TxInOut: path management for TxtInOut/
    │   ├── hru_manager.py          ← HRUManager: read/write parameters, validate_inputs()
    │   ├── output_manager.py       ← OutputFileManager: output.rch/hru/sub/sed, stamp-keyed cache
    │   └── workingFolder_manager.py← WorkingFolderManager, WorkerResult: parallel worker dirs
    ├── io/
    │   ├── parameters.py           ← SWATParam, SWATParamInfo
    │   ├── readers.py              ← Fixed-width file readers
    │   ├── writers.py              ← Strict fixed-width writer, SWATFileFormatError
    │   ├── mapping_file.py         ← Maps ext → file type
    │   ├── mapping_output.py       ← Output file layouts
    │   └── file_cio.py             ← FileCIO: sim dates, IPRINT, set(**values)
    ├── calibration/
    │   ├── calib_manager.py        ← CalibrationManager: run_iteration, run_batch, run log,
    │   │                             check_observation_step()
    │   └── validation_runner.py    ← ValidationRunner, PeriodConfig
    ├── scenarios/
    │   ├── model.py                ← Scenario, ParamSet, Job, RunResult
    │   └── batch.py                ← ScenarioBatch, BatchResult
    ├── analysis/
    │   ├── statistics.py           ← SWATAnalysis + metric registry (METRIC_DIRECTIONS, ...)
    │   ├── calibration.py          ← SWATCalibration: facade (optimize, analyze)
    │   ├── sensitivity.py          ← SWATSensitivity: OAT, Morris, SALib (Morris, Sobol)
    │   └── algorithms/
    │       ├── dds.py              ← DDS (standalone) + DDSCalibration
    │       ├── glue.py             ← GLUE + 95PPU
    │       ├── parallel_de.py      ← ParallelDE (Differential Evolution)
    │       └── pso.py              ← PSO (standalone) + PSOCalibration
    ├── run/
    │   └── run.py                  ← SWATRun: subprocess wrapper (timeout, kill on interrupt)
    ├── visualization/
    │   └── fig_viewer.py           ← FigViewer: fig.fig → interactive HTML
    └── utils/                      ← DATAParameter, output mapping info, param_loader
docs/
├── sample_run_single.py / sample_run_parallel.py / sample_run_scenarios.py
├── SYSTEM_DESIGN_EN.md / _VI.md   ← historical design audit (see banner inside)
└── agents/                         ← team workflow (Vietnamese): AGENTS-TUTORIAL.md, HERDR-CORE-BOT.md
.agents/                            ← per-task notebook committed with the code (see below)
```

---

## Key design rules

**1. Parameter keys use `name.ext`.**
`CN2.mgt`, `ALPHA_BF.gw`, `ESCO.hru`, never bare `CN2`. An unknown key raises before
any file is touched or any worker starts.

**2. No shared mutable state for methods/subbasins.**
`CalibrationManager` passes `methods` and `subbasins` as local arguments through
`run_iteration(..., methods=None, subbasins=None)` and `_format_params(raw, methods, subbasins)`.
Algorithms (GLUE, DE, DDS, PSO) parse `param_ranges` at the start of `run()`.

**3. Unified `param_ranges` format.**
```python
param_ranges = {
    "ESCO.hru":    (0.01, 1.0),                        # bounds only → method "v"
    "CN2.mgt":     ((35, 98),   "r"),                  # bounds + method
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),   # bounds + method + subbasins
}
```
`_parse_spec()` raises `ValueError` if an old-format tuple has more than 2 elements.

**4. TxtInOut is never left modified by a sequential run.**
`_backup_state()` copies only the parameter **input** files (never outputs, never the
whole folder) to a temp dir. `_restore_state()` runs in `finally`; the backup is deleted
only after every file was copied back. A failed restore keeps the backup and the next
`_backup_state()` finishes it first.

**5. Workers always start from the baseline.**
`WorkingFolderManager.run_parallel()` restores input files from the base TxtInOut before
applying parameters, so `r`/`a` changes never compound across batches. A failing job
returns `WorkerResult(ok=False, error=...)` and is scored NaN; it never raises.

**6. Observation step must match the simulation print step.**
The simulation frequency comes from `IPRINT` in `file.cio` (not from the observations).
`check_observation_step(obs.index, freq)` raises on daily vs monthly mismatch and on
month-end dated monthly observations. Observations are never resampled.
`_align_series` assigns model dates to `sim` and intersects with `obs`.

**7. One metric registry.**
`analysis/statistics.py::METRIC_DIRECTIONS` defines direction for every metric
(`nse`, `kge`, `r2`, `correlation` max; `rmse`, `mae`, `rsr` min; `pbias` min |x|).
Use `is_maximize`, `to_objective`, `best_index`, `sanitize_scores`; never hard-code
"higher is better". NaN scores rank worst; an all-failed batch raises.

**8. Failures are explicit.**
Sequential optimisers take `on_failure="raise"` (default) or `"penalize"`. Failed runs
never enter sensitivity indices (Morris drops the trajectory, Sobol raises, OAT skips).

**9. Input files are written strictly and atomically.**
Read/write TxtInOut as latin-1 with `newline=""`. Invalid slices, short lines or values
wider than the field raise `SWATFileFormatError` and leave the file untouched. Each file
is written once per update via temp file + `os.replace`.

**10. Every run is logged, and logging never breaks a calibration.**
`CalibrationManager` appends `<session>_metrics.csv` and `<session>_outputs.csv` under
`<working_dir>/calibration_results` after each run (sequential, parallel, validation,
GLUE uncertainty, sensitivity via `record_run`). Files are created only when the first row
is written. Locked files are buffered (`flush_log()`); errors are warned once.

**11. Parallel code must be picklable and `__main__`-guarded.**
`ProcessPoolExecutor` spawns workers on Windows. Worker functions, `prepare`, `extract`
and `runner` callables must be module-level. Scripts must run under
`if __name__ == "__main__":`; `setup()`, `run_parallel()` and `ScenarioBatch.run()` refuse
to run inside a spawned child.

**12. All runtime messages are in English.**
Log messages and exception strings. Some older docstrings/comments are still Vietnamese.

---

## Common tasks

### Read parameter values
```python
project.read_params_values(["CN2.mgt", "ALPHA_BF.gw"])
project.HRU.validate_inputs()          # empty DataFrame = layout matches the param file
```

### Run one SWAT iteration (backup/restore included)
```python
from spyswat.swat_calib.calibration import CalibrationManager
manager = CalibrationManager(project)
score = manager.run_iteration({"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.5}, obs, metric="nse")
```

### Run a calibration algorithm
```python
from spyswat.swat_calib.analysis import SWATCalibration
calib = SWATCalibration(project)
calib.manager.setup_parallel(overwrite=True)
result = calib.glue.run(param_ranges, obs, n_samples=500, threshold=0.5, seed=42)
result = calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50, seed=42)
# every algorithm returns {"best_params", "best_score", "history", ...}
```

### Run scenarios × parameter sets
```python
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch
batch = ScenarioBatch(project, results_dir)
res = batch.run([Scenario("LUC2000", txinout_dir=...)], [ParamSet.from_dict("p1", {...})],
                outputs={"FLOW_OUTcms": [51]}, observed={("FLOW_OUTcms", 51): obs})
```
See `docs/sample_run_scenarios.py`.

### Add a new calibration algorithm
1. Create `spyswat/swat_calib/analysis/algorithms/myalgo.py`: class with
   `__init__(self, manager)` and `run(param_ranges, observed_series, ...) -> dict` returning
   `{"best_params", "best_score", "history"}`.
2. Use `self._manager.run_batch()` for population evaluation (template: `pso.py`), and the
   metric registry for ranking (`best_index`, `to_objective`).
3. Export from `algorithms/__init__.py`; register in `SWATCalibration.__init__`.
4. Add `tests/test_myalgo.py` (mock `manager.run_batch`).

---

## Commands

```bash
pip install -e .             # or: uv sync
pytest tests/ -q             # expected: 308 passed, 11 skipped (~3 min on Windows)
python -m spyswat --help
```

On Windows the skipped tests are POSIX-only fake-executable tests (`tests/test_run.py`)
and SALib tests when SALib is not installed.

---

## Agent team workflow

Full guide (Vietnamese): [`docs/agents/AGENTS-TUTORIAL.md`](docs/agents/AGENTS-TUTORIAL.md);
background bot: [`docs/agents/HERDR-CORE-BOT.md`](docs/agents/HERDR-CORE-BOT.md).
The rules below are the binding summary for this repo.

### Roles

| Role | Model / tool | Rights | Job |
|---|---|---|---|
| Architect | Opus 5.5 (extra effort) or Fable 5.2, Claude Code | read-only | Plan, risks, acceptance criteria; hard diagnoses; READY before release |
| Reviewer | Opus 5.5 (high effort), Claude Code | read-only | PASS / FAIL with Critical / Major / Minor findings, location and fix |
| Manager | Codex CLI | coordination files only | Split work into tasks, dispatch and supervise workers, switch models, merge after audit |
| Worker | OpenCode in its own worktree (tier fast / mid / strong) | edit within task scope | Implement exactly the task; report what changed and what was checked |
| Researcher | fast model, read-only | read-only | Locations and evidence |
| Auditor | fast model | run commands, no source edits | `pytest`, git checks; PASS ALL / FAIL |

If a tool cannot spawn separate sessions, one agent plays the roles one after another, in order.
Only the Architect and the Manager spawn agents (one level deep). Workers talk only to the
Manager. Worker skill budget: at most 2 skills, listed in the task file's `skills:` field.

### The `.agents/` notebook (committed on the working branch)

```
.agents/
  tasks/<ID>.md         spec: goal, files in scope, constraints, acceptance   (Manager)
  log/<ID>.md           append-only work log, one entry per step              (Worker)
  reviews/<ID>-<n>.md   review round n: PASS/FAIL, findings                   (Reviewer)
  decisions/<ID>.md     design decisions, risks, reasons                      (Architect/Manager)
  reports/<ID>.md       final branch report                                   (Manager)
  templates/            copy these to start a file
```

- **One writer per file.** Workers never edit `tasks/`; they propose changes in `log/`.
- **Logs are append-only.** Correct by adding an entry, never by rewriting.
- **Commit early and small**, code and the matching log entry together; messages start with
  `<ID>:`. Existing history uses `FIX:` / `FEAT:` prefixes; for task work use
  `<ID>: FIX: ...`.
- **Durable content goes in files; messages are pointers** (1–3 lines, path to the file).

### Handoff check (every handoff)

1. `git status` is clean (including `.md` files).
2. `git diff --stat main...HEAD` and `git log --oneline main..HEAD` match the "Files changed"
   list in `log/<ID>.md`. A change outside the task scope, or not mentioned in the log, is a
   **Major** finding (FAIL).
3. Auditor reruns the commands recorded in the log (`pytest tests/ -q`) and gets the same result.
4. Reviewer reads only `git diff main...HEAD`, `tasks/<ID>.md` and `log/<ID>.md`.

### Release gate (in order)

Commit on the task branch → Auditor PASS ALL → Reviewer PASS → Manager merges into the shared
branch and the Auditor reruns there → Architect READY → **user approves the release** →
verify on a real SWAT project. A check that cannot run is reported with its reason, never as
passed. Bots and workers never merge or release.

### Escalation

Call the Architect for structural changes, anything touching data or security, a fix that
failed twice (after a model upgrade), and before release. If it still fails after the
Architect's diagnosis, stop and ask the user.

---

## Public repository rules

This repository is public on GitHub. In every committed file (code, docs, `.agents/`, commit
messages):

- No secrets: API keys, tokens, `auth.json`, `.env`. Model provider keys live only in the
  user's environment.
- No real watershed data, observation files or model outputs (`data/` and `logs/` are
  ignored). Test fixtures are synthetic.
- No personal machine paths or names in new docs; samples use placeholder paths such as
  `D:/SWAT/TxtInOut`.
- Tasks that touch confidential data run only on local models, or with the user's approval
  before code is sent to a cloud provider.

---

## Important notes

- **Do not restore `swat_toolkit/`**: the package is `spyswat/` and all imports use `spyswat.*`.
- **Tests** in `tests/` are real pytest tests. Do not delete or overwrite them without
  running the suite. Fixtures that write CRLF files must use `newline=""` (Windows
  translates `\n` otherwise).
- **Windows paths** appear in samples and fixtures; SWAT runs on Windows.
- **TxtInOut mutation:** never call `project.HRU.update_params()` outside
  `CalibrationManager` without your own backup/restore. `ValidationRunner.run()` keeps the
  best parameters in TxtInOut by default (`restore=True` to undo).
- **Worktrees** live in `.wt/` (ignored). Do not search or edit inside `.wt/` from the repo root.
