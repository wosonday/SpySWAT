---
id: api-1
branch: feat/api-1
tier: mid
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-1: pure `evaluate()` (periods, warm-up guard, monthly aggregation of the simulation)

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` (read sections Vocabulary, API,
Anti-goals). This task builds only the pure module; the `SWATProject.evaluate` facade is API-4.

## Build
New module `spyswat/swat_calib/analysis/evaluate.py`, exported from `spyswat/swat_calib/analysis/__init__.py`:

```python
@dataclass
class EvaluationResult:
    table: pd.DataFrame   # MultiIndex (variable, reach, period); columns = metrics + "n"
    def to_csv(self, path) -> None: ...

def evaluate(sim, observed, periods=None, *, metrics=("nse", "kge", "pbias", "r2"),
             freq=None, step=None, agg=None, warmup_end=None) -> EvaluationResult
```
- `sim` / `observed`: both `pd.Series` with a DatetimeIndex (one site: key `(None, None)`), or both
  dicts keyed `(variable, reach)`. Every observed key must exist in `sim` (else ValueError naming it).
  Sim keys without observations are ignored.
- `freq`: print step of the simulation, "daily" or "monthly" (same strings `check_observation_step`
  in `calibration/calib_manager.py` uses). `None` → infer from the sim index with the same rule that
  function applies to observations (first-of-month midnight, unique months → monthly).
- `step=None`: `check_observation_step(obs.index, freq)` must pass (reuse it; do not copy it).
  `step="M"` with a daily sim: aggregate the **simulation** to month-start timestamps with `agg`
  (`{variable: "mean"|"sum"}`; default mean, sum when the variable starts with `SED_` or ends with
  `tons` or `kg`); observations must then be monthly (check with freq "monthly"). Observations are
  never resampled. `step="M"` with a monthly sim is a no-op.
- `periods`: `{name: (start, end)}` (inclusive, strings or Timestamps). `None` → `{"all": (first, last
  common date)}`. ValueError when a period starts before `sim.index.min()`, ends after
  `sim.index.max()`, or starts before `warmup_end` (when given). Message says which period and why.
- Per site and period: intersect dates (like `CalibrationManager._align_series`, but sim already has
  real dates here), drop NaN pairs, compute each metric with the registry in
  `analysis/statistics.py` (reuse its functions; never hard-code directions). `n` = number of pairs.
  A period with no common dates → metrics NaN, n = 0 (no exception).
- Unknown metric names → ValueError before any computation.

## Files in scope
`spyswat/swat_calib/analysis/evaluate.py` (new), `spyswat/swat_calib/analysis/__init__.py` (export),
`tests/test_evaluate.py` (new), `.agents/log/API-1.md`.

## Acceptance criteria
- [ ] Tests (synthetic data, no SWAT): Series pair; dict with 2 sites; 2 periods (calib/valid) give the
      expected NSE on hand-computed data; warm-up / out-of-range period errors; daily vs monthly obs
      mismatch raises; `step="M"` mean vs sum aggregation; unknown metric raises; empty period → NaN, n=0.
- [ ] `python -m pytest tests/test_evaluate.py -q` then `python -m pytest tests/ -q` all pass
      (baseline 464 passed, 11 skipped); `git diff --check` clean.

## Report
Append to `.agents/log/API-1.md`: files changed, commands + result lines, open questions. Commits `api-1:`.
