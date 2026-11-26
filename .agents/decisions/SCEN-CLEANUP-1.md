# Decision SCEN-CLEANUP-1: Auto-cleanup of ScenarioBatch worker folders

- Date: 2026-11-26 · Author: Gemini 4 Hydrogen (requested by the user)
- Status: accepted

## Context

`ScenarioBatch.run()` creates up to `n_parallel` worker directories under
`<working_dir>/_scenario_batch/<key>/TxInOut1..N`
([batch.py](../../spyswat/swat_calib/scenarios/batch.py)) and keeps them after the batch
finishes so later runs can reuse the seeded slots.

When running multi-decade daily simulations (`IPRINT = 1`) across multiple projects or
basins in sequence (each with its own `working_dir`), `swat.exe` writes large `output.hru`,
`output.sub`, and `output.rch` files into every worker slot. Keeping those worker folders
after a project finishes accumulates tens of gigabytes per project and can exhaust disk
space (`OSError: [Errno 28] No space left on device`).

## Options

1. **Add `cleanup_work_dir: bool = False` (or `cleanup: bool = False` / `"auto"`) to `ScenarioBatch.run()`** — pros: opt-in or default-on cleanup right after `executor.shutdown(wait=True)` on normal completion; easy to keep when debugging failed runs. Cons: re-running the same project later with `resume=True` needs to re-seed slots for any remaining failed/new jobs.
2. **Clean heavy `output.*` files after each worker job (or after `ScenarioBatch.run()` finishes) while keeping input files** — pros: frees `output.hru`/`output.sub`/`output.rch` (almost 100% of disk usage) without losing seeded input folders. Cons: slightly more file handling than a single `_rmtree(work_dir)`.

## Decision

Proposed follow-up for SpySWAT (`0.3.x`):

1. Add a cleanup option on `ScenarioBatch.run()` (e.g. `cleanup: bool = True` or `"on_success"`) in
   [spyswat/swat_calib/scenarios/batch.py](../../spyswat/swat_calib/scenarios/batch.py)
   so `<working_dir>/_scenario_batch/<key>` is removed automatically once
   `executor.shutdown(wait=True)` completes cleanly (at least when all jobs succeed, or
   always after saving `summary.csv` and `metrics.csv` when `cleanup=True`).
2. Keep worker folders untouched if the pool aborts mid-run via an exception before workers
   exit, avoiding mid-read `forrtl` file errors.
3. Also consider removing `output.hru` / `output.sub` inside `_worker_job()` once
   `extract()` completes (or documenting `WorkingFolderManager.cleanup()`), since `ScenarioBatch`
   only reads `output.rch`.

## Risks and follow-up

- Do not delete `work_dir` inside an exception handler before `executor.shutdown(wait=True)`
  finishes, otherwise active `swat.exe` child processes lose files while reading/writing.
- Add unit tests in [tests/test_scenarios.py](../../tests/test_scenarios.py) covering
  `cleanup=True` (all ok / partial failure) and `cleanup=False`.
