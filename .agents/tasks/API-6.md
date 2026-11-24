---
id: api-6
branch: feat/api-6
tier: docs
skills: none
docs_impact: yes
gitnexus: none
---

# API-6: documentation, samples, migration notes, version 0.3.0

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md`. The new public API is on main:
`SWATProject.calibration / evaluate / sensitivity / scenarios / apply`, `CalibrationResult` (`top`, `select`,
`load`, `metrics`, `sensitivity`), the vocabulary (`observed`, `outputs`, `weights`, `metric(s)`, `calib_period`,
`valid_period`, `periods`, `step`, `agg`), multi-site scoring, the session folder layout, regression sensitivity,
deprecated names (`observed_series`, `reach_id`/`output_variable`, `ValidationRunner`) until 0.4.0.
Resume by replay (`resume=True`) is being finished in API-5: document it as "planned in 0.3.0" in ONE place
(the calibration section) so API-5 can turn that sentence into the final text.

## Do (read the code to get names and defaults exactly right; never invent parameters)
1. `README.md` and `README_VI.md` (Vietnamese; keep both in sync): new "Quick Start" based on the facade (one
   calibration with calib/valid periods, `res.metrics`, `res.sensitivity`, `res.top(10)` → `project.scenarios`,
   `project.evaluate(sim, obs, periods=...)` for checking by hand); a "Multi-site calibration" section (dict
   `observed`, `weights`, score rules incl. |pbias|); "Session folder" layout; keep the low-level sections but
   switch their examples to the new names; replace "Validation" by "Evaluation by period"; table of contents.
2. `docs/sample_run_single.py`, `docs/sample_run_parallel.py`, `docs/sample_run_scenarios.py`: use the facade and
   new names; placeholder paths only (`D:/SWAT/TxtInOut`); keep `if __name__ == "__main__":`.
3. `CHANGELOG.md`: under `[Unreleased]` → rename to `[0.3.0] – 2026-11-25`; Added / Changed / Deprecated sections
   for API-1..API-5, and a "Migration from 0.2.x" subsection with an old → new table.
4. `pyproject.toml` version `0.3.0`.
5. `AGENTS.md`: Quick orientation tree (new modules: `analysis/evaluate.py`, `analysis/regression_sensitivity.py`,
   `calibration/scoring.py`, `calibration/session_store.py`, `calibration/result.py`, `calibration/replay.py`
   (API-5)), the "Common tasks" examples switched to the facade + vocabulary, version line `0.3.0`.

## Files in scope
`README.md`, `README_VI.md`, `docs/sample_run_*.py`, `CHANGELOG.md`, `pyproject.toml`, `AGENTS.md`,
`.agents/log/API-6.md`.

## Acceptance criteria (checked by the CEO)
- [ ] `python -m py_compile docs/sample_run_*.py`; harness lint 0 errors; full pytest unchanged.
- [ ] Every function/argument named in the docs exists with that name in the code.
