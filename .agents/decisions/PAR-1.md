# Decision PAR-1: scheduling of scenarios x parameter sets over parallel workers

- Date: 2026-11-23 · Author: Architect / BOT-CEO (Claude Opus 5.5)
- Status: **proposed — on hold until the user confirms the goal** (BOT-CEO.md §5.0).
- Base: `main` / `release/0.2.6` at 628e5bb.

## Findings (read-only diagnosis, `file:line` on 628e5bb)

| # | Severity | Location | Problem | Effect |
|---|---|---|---|---|
| F1 | Major (throughput) | `scenarios/batch.py:454-547`, `core/workingFolder_manager.py:372-405` | Jobs run in fixed chunks of `k`; each chunk is one `run_parallel()` call that creates a new `ProcessPoolExecutor` and waits for **every** job (barrier). | One slow or timed-out SWAT run idles the other `k-1` workers; Windows spawn/re-import cost is paid once per chunk. |
| F2 | Major (throughput) | `scenarios/batch.py:447-466` | Jobs are grouped by base TxtInOut and groups run **one after another** with `k = min(n_parallel, len(group))`. | 4 land-use scenarios x 2 parameter sets with `n_parallel=8` use 2 cores at a time instead of 8. |
| F3 | Major (I/O) | `scenarios/batch.py:459-461`, `workingFolder_manager.py:255-289` | Every group calls `setup(overwrite=True)` in the same `_scenario_batch` dir: full `copytree` of TxtInOut `k` times, sequentially, deleting the previous group's copies. | Setup time grows with (scenarios x n_parallel x TxtInOut size). |
| F4 | Minor (correctness of resume) | `scenarios/batch.py:176-184` | `_scenario_sig` hashes the weather overlay files but not the contents of a scenario's `txinout_dir`. | `resume=True` after editing files inside a scenario TxtInOut silently reuses old results. |
| F5 | Minor (observability) | `scenarios/batch.py:492-495` | `run_parallel()` is called without `log_queue`. | Worker-side log records are lost on Windows (spawned children have no handler). |
| F6 | Minor | `scenarios/batch.py:353` | Fixed work dir `_scenario_batch`. | Two batches on the same project at once overwrite each other's workers. |

Not a finding: job isolation (baseline restore, manifest, overlays, freshness stamp) is
correct and tested; failures stay per job (design rule 5).

## Options (for F1-F3, the core)

1. **Keep the chunks, fix F2/F3 only**: one setup per distinct base, interleave groups. Small,
   but the barrier (F1) remains.
2. **Persistent pool + job queue (recommended)**: one executor for the whole batch; each free
   worker slot takes the next job; worker folders are keyed by (base, slot) and created lazily
   (copy once, reuse; restore from the job's own baseline as today). `summary.csv` is saved as
   results arrive. Keeps `_worker_job` unchanged; public API of `ScenarioBatch.run` unchanged.
3. Thread pool around `subprocess` (SWAT is an external exe, so the GIL is not the bottleneck).
   Simpler, but `prepare`/`extract` (pandas parsing) would then share one process.

## Budget snapshot (2026-11-23, `agm quota`, most rows stale ~11 h)

- `opencode-go`: 5 h 0%, week 0%, month 41% (stale — confirm in Go Console before dispatch).
- `codex` week 100% (stale) → no Codex engineering; `agy-3p` week 100% → no `agy` Opus sparring.
- `agy-argon` week 77%; `claude` 5 h 29%, week 14%.
- `[policy].max_workers = 2`.

## User answers

- 2026-11-23: the real-project problem is **slow runs with idle CPU** → goal = F1-F3
  (`serves: cost`, wall-clock time). F4-F6 deferred to a later task.
- 2026-11-23: after this batch, update the shared harness in `D:\.harnessing\agent-tutorial`
  (not a git repo) with the lessons of this session (Argon-style retro; final step).

- 2026-11-23: slot policy = **only `n_parallel` folders; a slot switching base is re-copied;
  the scheduler prefers same-base jobs** (disk over I/O).
- 2026-11-23: **user-approved exception**: `opencode-go/deepseek-v4-pro` writes PAR-1 as its
  supervised qualification task on SpySWAT (TDD + Auditor + independent review). Two failed
  rounds → stop and ask the user. Quota at dispatch (`agm quota --refresh`): Go 5 h 20%,
  week 8%, month 45%; Argon week 81%; Codex week 100%.

## Dispatch notes (harness findings for the retro)

- On this Windows host a `hc` template whose `command:` has arguments fails
  (`cannot start "sh": sh: not found on PATH`); bare `command: opencode` works but does not
  pin the model, and OpenCode 2.4 TUI has no `--model` flag. The worker was therefore started
  with `hc run` in argv form: `opencode run --agent worker-strong --model
  opencode-go/deepseek-v4-pro ...`, labels `agm.task=par-1`, `agm.role=worker`;
  `max_workers` and the task budget were checked by hand.
- The global `hc` templates (worker-fast/mid, reviewer) carry another project's routing
  (free models, "Pro Go NO GO") and there is no `worker-strong` template.

## Restated plan (confirmed 2026-11-23)

- **goal:** `ScenarioBatch.run` keeps every worker slot busy until the job list is empty;
  public API, outputs (`summary.csv`, `metrics.csv`, `series/`), resume and failure isolation
  unchanged.
- **process:** one executor for the whole batch; a free slot takes the next job; worker
  folders prepared once per (base, slot); `summary.csv` saved as results arrive; `_worker_job`
  unchanged.
- **check_work:** `pytest tests/ -q` (baseline 336 passed / 11 skipped) + new tests with a
  fake `runner` whose duration varies per job: total time ≈ longest chain, not sum of chunk
  maxima; 2 bases x 2 sets with `n_parallel=4` → 4 jobs concurrently.
- **3 examples:**
  1. 4 land-use scenarios x 2 sets, 8 slots → all 8 jobs start together.
  2. One 30-year GCM scenario among short ones → short jobs keep flowing while it runs.
  3. Failure: one base fails setup / one job times out / Ctrl+C → only those jobs `failed`,
     finished rows saved, `resume=True` skips them; a locked slot (orphan swat.exe) fails its
     job via the existing busy probe and is not reused.
- **tasks:** PAR-1 (`worker-strong`, `opencode-go/deepseek-v4-pro`, skills
  `test-driven-development, verification-before-completion`); review by a different family
  (`agy` Argon High fallback, 23% week left). Docs via Hydrogen; merge via `copilot-git`.
