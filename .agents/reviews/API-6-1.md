# API-6 review round 1 — agy gemini-4-neon-high (plan, sandbox, real signatures + docs diff)

Verdict: FAIL

### Blocking Mismatches (Signatures & Defaults)
1. **README.md:1036 & README_VI.md:974** — `CalibrationManager.run_once(param_dict, *, outputs={"FLOW_OUTcms": [1]})`
   - Wrong parameter name: `param_dict` → `params`
   - Wrong default: `outputs={"FLOW_OUTcms": [1]}` → `outputs=None`
   - Also omits `methods=None, subbasins=None` (real: `run_once(self, params, *, outputs=None, reach_id=_SENTINEL, output_variable=_SENTINEL, methods=None, subbasins=None)`).
2. **README.md:1037-1039 & README_VI.md:975-978** — `CalibrationManager.run_iteration(param_dict, observed, metric="nse", *, ..., methods=None, subbasins=None, ...)`
   - Wrong default: `metric="nse"` → `metric=None`
   - Wrong placement: `methods=None, subbasins=None` are positional-or-keyword (before `*`), not keyword-only (after `*`).
3. **README.md:1040-1042 & README_VI.md:979-982** — `CalibrationManager.run_batch(param_sets, observed, metrics=("nse",), *, ..., methods=None, subbasins=None, store=None, is_initial=False)`
   - Wrong default: `metrics=("nse",)` → `metrics=None`
   - Wrong placement: `methods=None, subbasins=None` are before `*`, not after `*`.
   - Omits keyword-only parameter `run_ids=None`.
4. **README.md:1043 & README_VI.md:983** — `CalibrationManager.record_run(params, scores, status="ok", ...)`
   - Missing `*` before `status="ok"` (`status` and subsequent args are keyword-only in code; pre-existing line).

### Broken Example Values
5. **README.md:147, README_VI.md:147, docs/sample_run_parallel.py:30** — `"CN2.mgt": ((35.0, 98.0), "r")`
   - Relative method `"r"` computes `val * (1 + x)`, so `(35.0, 98.0)` multiplies `CN2` by 36x–99x. Use absolute bounds with default `"v"` (`(35.0, 98.0)`) or relative bounds like `((-0.2, 0.2), "r")`.
   - Similarly, **README.md:151, README_VI.md:151, docs/sample_run_parallel.py:34** pair old absolute bounds `(0.01, 0.5)` with `"r"` for `SOL_AWC.sol` (prefer `((-0.25, 0.25), "r")` or `(0.01, 0.5)`).

### Minor Notes (Non-blocking)
- **README.md:742 & README_VI.md:728**: prose refers to `sens.last_samples` / `sens.last_scores` after `sens = SWATSensitivity(project)` was removed from the example above.
- **AGENTS.md:214**: unused `ParamSet` import in the scenarios example.
- **CHANGELOG.md:27**: repeats the "Planned in 0.3.0 (API-5)" `resume=True` note outside the calibration section (API-5 will need to update it too).

### Verified OK
- `SWATProject` facade (`calibration`, `evaluate`, `sensitivity`, `scenarios`, `apply`), `CalibrationResult`, `evaluate`, `regression_sensitivity`, `GLUE`, `DDSCalibration`, `ParallelDE`, `PSOCalibration`, `SWATCalibration`, `ScenarioBatch` / `ParamSet`: all names, args, and defaults match code.
- `README.md` and `README_VI.md` are in sync across all changed sections.
- `CHANGELOG.md` `[0.3.0] – 2026-11-25` and "Migration from 0.2.x" table are accurate; `pyproject.toml` is `0.3.0`.
- `docs/sample_run_*.py`: valid imports, call order, `if __name__ == "__main__":` guards; placeholder `D:/SWAT/...` paths only; no personal paths or secrets.

## CEO triage → rework (agy Hydrogen Medium): fix items 1-5 and all three minor notes; keep the resume note in ONE place (calibration section) and make CHANGELOG point to it.
