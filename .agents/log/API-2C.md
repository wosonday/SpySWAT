# API-2C — work log

## 2026-11-25 — worker-fast (deepseek-v4.1-flash)

Task: two follow-ups from review API-2B-2 (Minor 1 and Minor 3).

### Files changed
- `spyswat/swat_calib/calibration/calib_manager.py`
  - `_run_iteration_multi`: `_resolve_metrics(metric, metrics)` is now called right after
    `_validate_config`, so an unknown `metric` / `metrics` entry raises `ValueError` before
    any SWAT run (previously it ran SWAT and surfaced as `RuntimeError("Iteration failed")`).
  - `_new_path`: new optional `metrics=None` parameter, included in the routing expression
    and docstring, so `run_iteration(..., metrics=(...))` alone takes the multi-site path.
  - `run_iteration`: passes `metrics=metrics` into the `_new_path` check.
- `tests/test_calib_multisite.py`
  - `test_preflight_runs_before_any_swat_run` now records `proj.run_impl` calls and asserts
    none happened (Minor 3).
  - New `test_run_iteration_unknown_metric_fails_before_run`: `metric="no_such_metric"` with
    `outputs=` raises `ValueError("Unknown metric ...")` and `run_impl` was never called.
  - New `test_run_iteration_unknown_reported_metric_fails_before_run`: same for
    `metrics=("no_such_metric",)` alone (proves the metrics-only route + fail-fast).
  - New `test_run_iteration_metrics_alone_uses_new_path`: bare obs Series +
    `metrics=("nse",)` returns the real NSE from `evaluate` (`1 - 105/82.5 = -0.2727...`),
    not the old single-site stub value, proving the new path is taken.

### TDD sequence
1. Tests written first (red): 3 failures, all for the expected reasons —
   unknown metric ran SWAT and ended in `RuntimeError: Iteration failed: SWAT ended without
   writing a fresh output.rch`; `metrics=` alone returned the old-path stub score `3.0`.
2. Implementation added (green): `27 passed` in `tests/test_calib_multisite.py`.

### Commands + results
```
python -m pytest tests/test_calib_multisite.py -q -p no:cacheprovider
  (red)  3 failed, 24 passed
  (green) 27 passed in 4.63s

python -m pytest tests/ -q -p no:cacheprovider
  595 passed, 11 skipped, 47 warnings, 28 subtests passed in 212.10s (0:03:32)

git diff --check
  (no output — clean)
```

Baseline note: 24 tests in `tests/test_calib_multisite.py` before this task (574 passed +
11 skipped recorded for main at API-2B-2 review); this branch already carries other merged
work, so the total is 595 passed + 11 skipped with +3 tests from this task. The 11 skips are
the known POSIX-only `tests/test_run.py` / missing-SALib tests.

Scope: only the two in-scope files above changed. No rebase/merge/push. `ruff` is not
installed in this environment, so no lint run was possible; `git diff --check` is clean.
