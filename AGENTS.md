# SpySWAT — Agent Guide

> Version: 0.2.6 | Updated: 2026-11-21 (team workflow v3.6)

Orientation for AI agents (Claude Code, Codex, OpenCode, GitHub Copilot, Gemini via `agy`)
and developers working in the SpySWAT codebase. **Project rules in this file win over the
general team workflow** (`docs/agents/AGENTS-TUTORIAL.md`). This repository is **public**:
see [Public repository rules](#public-repository-rules).

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
    │   ├── run_state.py            ← Atomic copies, output freshness, StaleOutputError
    │   └── workingFolder_manager.py← WorkingFolderManager, WorkerResult: parallel worker dirs
    ├── io/
    │   ├── parameters.py           ← SWATParam, SWATParamInfo
    │   ├── readers.py              ← Fixed-width file readers
    │   ├── writers.py              ← Strict fixed-width writer, SWATFileFormatError
    │   ├── mapping_file.py         ← Maps ext → file type
    │   ├── mapping_output.py       ← Output file layouts
    │   └── file_cio.py             ← FileCIO: sim dates, IPRINT, set(**values)
    ├── calibration/
    │   ├── calib_manager.py        ← CalibrationManager: run_once, sandbox, run_iteration, run_batch,
    │   │                             check_observation_step()
    │   ├── param_spec.py           ← Pure parameter parsing, formatting and log columns
    │   ├── run_log.py              ← RunLog: CSV sessions, buffered writes, per-run results
    │   └── validation_runner.py    ← ValidationRunner, PeriodConfig
    ├── scenarios/
    │   ├── model.py                ← Scenario, ParamSet, Job, RunResult
    │   ├── batch.py                ← ScenarioBatch, BatchResult
    │   ├── scheduler.py            ← Scheduler, Slot: single-pool job queue & slot state
    │   └── signature.py            ← txinout_fingerprint(): per-scenario TxtInOut input stats
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
└── agents/                         ← team workflow (Vietnamese): AGENTS-TUTORIAL.md (v3.6),
    │                                  BOT-CEO.md, HERDR-CORE-BOT.md, SETUP-WINDOWS.md
    ├── models/                     ← per-model guides (English): Claude, Codex, agy, OpenCode
    │                                  workers/reviewer, NVIDIA background, Copilot, guardrails
    └── superpowers/                ← routing design + plan history (2026-11-20)
.opencode/agents/                   ← OpenCode role permissions (worker-*, auditor, reviewer,
                                       explore, gitnexus-sync)
.agents/                            ← per-task notebook & bot.env committed with the code (see below)
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
All sequential callers use `CalibrationManager.run_once()` for update → stamp → run →
freshness check → read. This primitive does not back up inputs: compose it with
`sandbox(names=...)` for restoration on any exit. `run_iteration()` keeps the equivalent
explicit backup/restore to preserve its combined run/restore error message.
`_backup_state()` copies only the parameter **input** files (never outputs, never the
whole folder) to a temp dir. `_restore_state()` runs in `finally`; the backup is deleted
only after every file was copied back. A failed restore keeps the backup and the next
`_backup_state()` finishes it first. Deliberately keeping parameters, as with
`ValidationRunner.run(restore=False)`, does not use the sandbox.

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
`CalibrationManager` delegates to `RunLog` to append `<session>_metrics.csv` and
`<session>_outputs.csv` under
`<working_dir>/calibration_results` after each run (sequential, parallel, validation,
GLUE uncertainty, sensitivity via `record_run`). Files are created only when the first row
is written. Locked files are buffered (`flush_log()`); errors are warned once.
The raw `run_once()` primitive does not log or compute metrics; custom callers use
`record_run()`. Sensitivity and GLUE uncertainty runs record after restoration, so a
restore failure is logged as a failed run.

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

For a raw simulated series with restoration (no metrics or automatic run log):
```python
with manager.sandbox(names=["CN2.mgt"]):
    sim = manager.run_once({"CN2.mgt": 75.0}, reach_id=1, output_variable="FLOW_OUTcms")
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
pytest tests/ -q             # measured: 336 passed, 11 skipped (~4-5 min on Windows)
python -m spyswat --help
```

On Windows the skipped tests are POSIX-only fake-executable tests (`tests/test_run.py`)
and SALib tests when SALib is not installed.

---

## Agent team workflow

Full guide (Vietnamese, v3.6): [`docs/agents/AGENTS-TUTORIAL.md`](docs/agents/AGENTS-TUTORIAL.md);
background orchestration (`agm` + `hc` + GitNexus sync):
[`docs/agents/HERDR-CORE-BOT.md`](docs/agents/HERDR-CORE-BOT.md);
optional multi-lane scaling (`BOT-CEO` + `BRANCHES.md` if ever split into parallel lanes):
[`docs/agents/BOT-CEO.md`](docs/agents/BOT-CEO.md);
per-model startup, permissions and quota guides:
[`docs/agents/models/README.md`](docs/agents/models/README.md);
Windows setup and session tracking:
[`docs/agents/SETUP-WINDOWS.md`](docs/agents/SETUP-WINDOWS.md).
SpySWAT currently uses the **single-lane** workflow below. The rules below are the binding
summary for this repo.

### Roles and permissions

| Role | Model / tool | Rights | Job |
|---|---|---|---|
| Architect / BOT-CEO | Opus 5.5 (extra effort) or Fable 5.2, Claude Code (`agm manage`) | read-only on source; writes `decisions/` | Plan, risks, acceptance criteria; hard diagnoses; `READY` before release. **Owns the AI budget**: per-task allocation + review/rework reserve, checks quotas before dispatch, never enables Extra Usage. **Only regular Claude Code role** |
| Sparring / Pre-review | Opus High via `agy` (`agm ask` or `--mode plan --sandbox`) | read-only | Optional plan sparring and diff pre-check before formal review to conserve Claude tokens |
| Reviewer (default) | `opencode-go/deepseek-v4-pro` (OpenCode, fresh session; a different model family when Pro wrote the code) | read-only on product code; writes `reviews/` | `PASS` / `FAIL` with Critical / Major / Minor findings, location and fix; runs GitNexus `detect_changes`/`impact` if active. **Escalate to Claude Opus 5.5 High** only for security, real data, format/schema migrations, major architecture, or 2 consecutive `FAIL`s |
| Manager | Codex CLI (`codex-mgr`) | coordination files only (`tasks/`, `reports/`, `decisions/`) | Split plan into tasks, dispatch and supervise OpenCode workers, switch models/tiers, hand off verified branch + final SHA to Copilot after Review + Docs. Never edits worker code |
| Technical Advisor & Harness Optimizer | Gemini Argon (`gemini-4-argon-medium`/`high` via `agy`, `argon-adv`) | read-only via `agm ask`; writes harness/coordination files (`AGENTS.md`, `CLAUDE.md`, `.agents/`, templates, skills) in its own worktree when tasked | Independent technical advice; analyses major/recurring session issues to update and optimize harnessing between sessions |
| Git Version Manager | GitHub Copilot CLI (`copilot-git`, 1 instance) | merge verified final SHA onto `main`, revert/rollback, clean merged/clean worktrees & branches | Serial integration of verified branches and post-merge audit re-run. Never edits business logic or fixes failing tests; push/tag/release/history-rewrite require user approval |
| Docs Updater | Gemini 4 Hydrogen Medium (`gemini-4-hydrogen-medium` via `agy`, `docs-hyd`) | docs files only (`README*`, `docs/**`) + append `log/<ID>.md` | Updates affected docs **after Reviewer passes/edits finish and before Copilot handoff**; commits `<ID>: docs: ...` on the task branch |
| Worker | OpenCode in `.wt/<ID>` (`w-<id>-<n>`); `worker-fast`/`worker-mid` → `opencode-go/deepseek-v4.1-flash`, `worker-strong` → `opencode-go/deepseek-v4-pro` after qualification; approved `:free`/local only as fallback | edit within `tasks/<ID>.md` scope; append `log/<ID>.md` | Implement scoped task + tests; escalate to `mid` / `strong` / Codex on 2 fails or complex multi-file logic. Never spawns agents or merges |
| Researcher & Log Summarizer | `agy` (`gemini-3.8-flash` / `gemini-4-argon` via `agm ask`) for web; OpenCode `explore` (`opencode-go/deepseek-v4.1-flash`) for repo & long logs | read-only | Locations and evidence (URLs or `file:line`); summarise long test/build logs. Verify web claims (versions, prices) against primary sources |
| Auditor & Pre-check | Scripts/CI first (`pytest`, `git diff --check`); approved free/local model only to interpret output | run commands, write `log/<ID>.md`, no product source edits | Run `pytest`, lint/build, check `git diff` vs `tasks/<ID>.md` scope & `log/<ID>.md` before Reviewer; `PASS ALL` / `FAIL` |
| GitNexus Sync | `gitnexus-sync` (script/CI, optional when GitNexus active) | run `gitnexus status` / `analyze --index-only` / `clean` | Refresh graph index after `copilot-git` merge; never run without `--index-only` and never modify `AGENTS.md`/`CLAUDE.md` |
| Background (optional) | NVIDIA Kimi / Mistral / Nemotron (see `docs/agents/models/NVIDIA-BACKGROUND.md`) | **read-only, writes nothing**, at most 1 task, never a merge gate | Non-urgent synthesis of code/docs/logs and proposals for Argon; CEO re-checks SHA before using the output. Never code, Audit or Review |

If a tool cannot spawn separate sessions, one agent plays the roles one after another, in order.
Only the Architect and the Manager spawn agents (one level deep). Workers talk only to the
Manager. Worker skill budget: at most 2 skills, listed in the task file's `skills:` field.

### Communication and session rules (`agm` / `hc`)

- Send to another agent: `agm send <terminal> --type GIAO|"BÁO CÁO"|LỖI|HỎI|CHẶN|ĐẠT|"CHƯA ĐẠT" --task <ID> "<1-3 lines>"`
- Ask the user for a decision: `agm send user --type HỎI --task <ID> "<question>"`
- Check inbox (Manager / user): `agm inbox --json`
- `agm` 0.1.0 refuses a recipient whose state is `done` (`status_mismatch`, nothing typed):
  fall back to `hc send <terminal> "<pointer>"` (never `--force`) and log the outcome.
- Never run `agm kill` on Codex or Claude Code sessions — only the user may stop or interrupt them.
- Terminal names (`agm` / `hc`) allow lowercase `a-z0-9_-` up to 32 chars (`arch`, `sparring`, `review`, `codex-mgr`, `argon-adv`, `docs-hyd`, `copilot-git`, `gitnexus-sync`, `w-<id>-<n>`). Use lowercase task IDs when running via `agm`/`hc`.

### The `.agents/` notebook (committed on the working branch)

```
.agents/
  tasks/<ID>.md         spec: goal, scope, tier, skills, acceptance   (Manager)
  log/<ID>.md           append-only work/audit/docs log, per commit   (Worker / Auditor / Docs Updater)
  reviews/<ID>-<n>.md   review round n: PASS/FAIL, findings           (Reviewer / Sparring)
  decisions/<ID>.md     design decisions, risks, harness tuning       (Architect / Manager / Gemini Argon)
  reports/<ID>.md       final branch report + Argon retro items       (Manager)
  templates/            copy these to start a file
```

*(Runtime-only dirs `.agents/handoff/` — auto-excluded via `git info/exclude` by `agm` — and `.agents/.runtime/` are never committed.)*

- **One writer per file.** Workers never edit `tasks/`; they propose changes in `log/`.
- **Logs are append-only.** Correct by adding an entry, never by rewriting.
- **Commit early and small**, code/docs and the matching log entry together; messages start
  with `<ID>:` (docs updates use `<ID>: docs: ...`).
- **Durable content goes in files; messages are pointers** (1–3 lines, path to the file).

### Handoff check (every handoff)

1. `git status` is clean (including `.md` files).
2. `git diff --stat main...HEAD` and `git log --oneline main..HEAD` match the "Files changed"
   list in `log/<ID>.md`. A change outside the task scope, or not mentioned in the log, is a
   **Major** finding (`FAIL`).
3. Auditor reruns the commands recorded in the log (`pytest tests/ -q`) and gets the same result.
4. Reviewer reads only `git diff main...HEAD`, `tasks/<ID>.md`, `log/<ID>.md` (and optional Sparring notes).
5. If docs changed, Docs Updater (`docs-hyd`) commits the doc edits + `log/<ID>.md` entry on the branch before Manager hands off the final SHA to `copilot-git`.

### Release gate (in order)

Commit on the task branch → Auditor `PASS ALL` (free/local model) → *(optional: Sparring `agy` Opus High)* → Reviewer `PASS` (`OpenCode` default; escalate to Claude Opus High for security/data/2× `FAIL`) → Docs Update if affected (`Gemini 4 Hydrogen Medium`, commit on branch + quick re-check if in test scope) → `copilot-git` merges exact final SHA into shared branch & reruns Auditor → `gitnexus-sync` (`analyze --index-only`, if enabled) → Architect `READY` → **user approves the release** → verify on a real SWAT project. *(Post-session: Gemini Argon reviews major recurring issues to optimize the harness.)* A check that cannot run is reported with its reason, never as passed. Bots and workers never merge or release.

### Escalation

Use Sparring (`agy` Opus High) before escalating routine reviews to Claude Code. Call the
Architect (Claude Code) for structural changes, anything touching real data or security, a
fix that failed twice (even after model-tier escalation), and before release. If it still
fails after the Architect's diagnosis, stop and ask the user (`agm send user --type HỎI`).

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
