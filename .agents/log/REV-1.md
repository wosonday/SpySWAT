# Log REV-1

## 2026-11-18 · claude-opus-5.5 · step 1/2 — verify review, fix findings 2-6, 9, 10
- Review: `/code-review high fix/phase1-correctness` → 10 findings; each re-checked against
  the code, verdicts in `.agents/reviews/PHASE1-1.md`.
- Note on finding 4: a `list` has a `.index` method, so the failure needs an `ndarray`;
  the test uses `obs.to_numpy()`.
- TDD: each finding got a test that failed first (RED), then the fix (GREEN).
- Files changed:
  - `calibration/calib_manager.py`: obs index resolved before backup (4); `_backup_state(names=)`
    / `_input_files(names=)` back up only the changed extensions (6); no frequency inference
    from observations (9)
  - `calibration/validation_runner.py`: scalar / "All" subbasin in best_params (3)
  - `analysis/sensitivity.py`: fresh-output check in `_sequential_mean` (2)
  - `swat_project.py`: `FileCIO` re-read when file.cio changes on disk (5)
  - `analysis/statistics.py`: public `finite_stats`; `parallel_de.py`, `pso.py` use it;
    `scenarios/batch.py`, `scenarios/model.py` take IPRINT table / cio keys from FileCIO (10)
  - tests: `test_calib_manager.py`, `test_sensitivity.py`, `test_project.py`,
    `test_metrics.py` (new tests); mock projects now stub `FileCIO.get_iprint()` (design
    rule 6), sensitivity mock has no TxtInOut dir
- Checks: `pytest tests/ -q` → 316 passed / 11 skipped / 0 failed.

## 2026-11-18 · claude-opus-5.5 · step 2/2 — finding 1 handed to the user
- RED: `test_failed_run_ranks_below_any_real_score` (5 cases) and
  `test_parallel_de_never_returns_a_failed_member` fail; the DE run logs `best=nan` from
  generation 1, reproducing the finding end to end.
- `worst_score` in `analysis/statistics.py` carries the only TODO(human); the design choice
  (infinite vs. adaptive finite penalty) is the user's.
- Not committed.

## 2026-11-20 · claude-opus-5.5 · step 3/3 — finding 1 implemented (user asked to continue)
- Done: the user asked to continue the source fixes instead of writing the TODO(human);
  implemented the recommendation of `.agents/reviews/coord-1-1.md`: `worst_score` returns
  `-inf` for maximize metrics, `+inf` otherwise (`to_objective` -> `+inf` for every
  direction, pbias via `abs`). Removed `_WORST_MAGNITUDE` and its stale comment.
  DE `<=` / PSO `<` rules unchanged; raw NaN stays in histories.
- Tests: new `test_pso_never_returns_a_failed_member`. Both DE and PSO tests fail with the
  old ±1e6 penalty patched back in (2 failed) and pass with the fix.
- Files changed: `spyswat/swat_calib/analysis/statistics.py`, `tests/test_metrics.py`
- Checks: `pytest tests/test_metrics.py tests/test_calibration.py -q` → 86 passed (before
  the OPT-1 tests); full suite recorded in `log/OPT-1.md`.
- Not committed.
