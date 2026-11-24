## 2026-11-25 — Docs Updater (API-6)

Updated 0.3.0 documentation, samples, changelog, metadata, and agent guide.

Files edited:
- `README.md`
- `README_VI.md`
- `docs/sample_run_single.py`
- `docs/sample_run_parallel.py`
- `docs/sample_run_scenarios.py`
- `CHANGELOG.md`
- `pyproject.toml`
- `AGENTS.md`
- `.agents/log/API-6.md`


## 2026-11-25 — Docs Updater (API-6 rework)

Fixed all items from `.agents/reviews/API-6-1.md`:
- `README.md`, `README_VI.md`: synced `CalibrationManager` signatures (`run_once`, `run_iteration`, `run_batch`, `record_run`) with `calib_manager.py`; updated `CN2.mgt` and `SOL_AWC.sol` relative bounds; defined `sens = SWATSensitivity(project)` before `sens.last_samples`/`sens.last_scores`.
- `docs/sample_run_parallel.py`: updated `CN2.mgt` (`((-0.2, 0.2), "r")`) and `SOL_AWC.sol` (`((-0.25, 0.25), "r")`) relative bounds.
- `AGENTS.md`: removed unused `ParamSet` import in the scenarios example.
- `CHANGELOG.md`: pointed `resume=True` note to `README.md#calibration` so the status note lives in one place.
