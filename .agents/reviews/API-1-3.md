# API-1 review round 3 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

No Critical, Major, or Minor findings. All round-1 and round-2 review fixes are implemented and verified against the design excerpt and API-1 task spec.

### Verified
- **API & Spec Compliance** (`spyswat/swat_calib/analysis/__init__.py:393-397`, `spyswat/swat_calib/analysis/evaluate.py:454-580`):
  - `EvaluationResult(table, to_csv)` and `evaluate(sim, observed, periods=None, *, metrics=("nse", "kge", "pbias", "r2"), freq=None, step=None, agg=None, warmup_end=None)` are exported from `analysis` and produce a `(variable, reach, period)` MultiIndex DataFrame with columns `[<metrics>, "n"]`.
  - Series pairs map to `(None, None)`; dict inputs validate `(variable, reach)` keys, reject missing observed keys with a `ValueError` naming the key, and drop unobserved `sim` sites before frequency inference, aggregation, and bound checks (`_normalise_sites`, `spyswat/swat_calib/analysis/evaluate.py:584-618`).
  - Reuses `check_observation_step` (`spyswat/swat_calib/analysis/evaluate.py:429,715-724`) and the `METRIC_DIRECTIONS` / `known_metrics()` / `SWATAnalysis` metric methods (`430,436-445,654-667,828-837`).
  - `step="M"` aggregates daily simulations to `"MS"` using `"sum"` (`min_count=1`) for `SED_*`, `*tons`, `*kg` or explicit `agg` overrides and `"mean"` otherwise, is a no-op on monthly simulations, and validates observations against `"MS"` without resampling them (`528-532,718,727-743`).
  - Round-2 fixes verified: `raw_max` preserves the last real simulated day for `sim_max` while `sim_min` uses post-aggregation start (`527-538`), `pd.isna` guards reject `None`/`NaT` in period bounds and `warmup_end` (`543-546,781-785`), and `_sorted_keys` sorts numeric reaches before `None` (`649-651`).
- **Hand-Checked Numerics** (`tests/test_evaluate.py`):
  - `test_series_pair_returns_hand_computed_nse` (`870-886`): `obs=[1,2,3,4]` (`mean=2.5`, `SS_tot=5.0`), `sim=[1,2,3,5]` (`SS_res=1.0`) -> `NSE = 1 - 1/5 = 0.8`.
  - `test_step_m_sum_aggregation_is_explicit` (`1038-1060`): daily `[2,4,6,8]` -> `20` and `[10,20,30,40]` -> `100` vs `obs=[5,25]` -> `PBIAS = 100 * ((5-20) + (25-100)) / 30 = -300.0`.
  - `test_step_m_period_may_end_mid_the_last_simulated_month` (`1214-1226`): daily `2000-01-01..2000-02-04` (`5.0` in Jan, `25.0` in Feb) vs monthly `obs=[5,25]` with period ending `2000-02-04` -> `n=2`, `NSE=1.0`.
- **Tests, Rules & Scope**:
  - `tests/test_evaluate.py` exercises Series/dict inputs, unobserved sites, multi-period scoring, NaN/empty overlaps, warm-up and bound errors, `NaT`/`None` guards, duplicate metrics, `step="M"` mean/sum/all-NaN/no-op/mid-month-start/last-day-end cases, and reach ordering.
  - `.agents/log/API-1.md:303-307` reports `tests/test_evaluate.py`: 40 passed; full suite `tests/`: 504 passed, 11 skipped, 0 failed; `git diff --check` clean (diff inspection only; no commands run here).
  - Top-level picklable callables, English error messages, no `TxtInOut` mutation, no secrets, and scope limited to `evaluate.py`, `analysis/__init__.py`, `tests/test_evaluate.py`, `.agents/log/API-1.md`, and prior `.agents/reviews/API-1-{1,2}.md`.

## CEO: round 3 PASS; full suite on eec7fe5: 504 passed, 11 skipped. Trailing blank line removed from the log (diff --check).
