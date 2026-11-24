---
id: api-2a
branch: feat/api-2a
tier: strong
skills: test-driven-development
docs_impact: no   # docs are API-6
gitnexus: none
---

# API-2a: `SessionStore` — the calibration session folder (write, flush, load)

Design: `docs/superpowers/specs/2026-11-24-api-standardisation-design.md` — read "Storage layout",
"Resume by replay" and "Decisions after the builder check" items 1, 7, 8, 9, 11. This task builds only the
storage module; wiring it into `CalibrationManager` is API-2b.

## Build: `spyswat/swat_calib/calibration/session_store.py`
```python
class SessionStore:
    def __init__(self, session_dir, *, signature: dict, param_names: list[str],
                 sites: list[tuple[str, int]], flush_every: int = 1, flush_seconds: float = 10.0,
                 max_columns: int = 16000, create: bool = True)
    @classmethod
    def open(cls, session_dir) -> "SessionStore"            # existing session, for resume / load
    def check_signature(self, signature: dict) -> None       # ValueError listing differing keys
    def add_run(self, run_id: int, *, params: dict, status: str, error: str | None, score: float,
                is_initial: bool, series: dict, site_metrics: dict, time: str | None = None) -> None
        # series: {(variable, reach): pd.Series with DatetimeIndex}
        # site_metrics: {(variable, reach): {"nse_calib": x, "nse_valid": y, ...}}
    def flush(self) -> None                                   # also called automatically
    def close(self) -> None                                   # flush; safe to call twice
    def write_best(self, params: dict) -> None                # best.csv
    def write_sensitivity(self, df: pd.DataFrame) -> None     # sensitivity.csv
    def runs(self) -> pd.DataFrame                            # runs.csv, exact floats (see below)
    def series(self, variable, reach) -> pd.DataFrame         # dates x run_<n> (all parts joined)
    def site_metrics(self, variable, reach) -> pd.DataFrame
    @property signature -> dict
```
Layout (exact names):
```
<session_dir>/session.json            {"signature": {...}, "param_names": [...], "sites": [[var, reach], ...],
                                       "spyswat_version": ..., "numpy_version": ...}
<session_dir>/runs.csv                run_id,time,status,error,is_initial,<param_names...>,score
<session_dir>/best.csv                parameter,value
<session_dir>/sensitivity.csv
<session_dir>/reach_<reach>/<variable>.csv           date,run_<id>,...  (rows = dates)
<session_dir>/reach_<reach>/<variable>_metrics.csv   run_id,<metric>_<period>,...
```
Rules:
- Floats in `runs.csv` and `*_metrics.csv` are written with `repr()` (`-0.0` → `0.0`, NaN → empty) and read back
  with the stdlib `csv` module + `float()` so `runs()` returns bit-identical values. Series files may use pandas.
- Buffer runs in memory; flush when `flush_every` runs are pending or `flush_seconds` passed, and in `close()`.
  Commit order per flush: series files and `*_metrics.csv` first, `runs.csv` last; every file written to a temp
  file + `os.replace`. A run counts as stored only once it is in `runs.csv`; `open()` ignores series columns /
  metric rows whose run_id is not in `runs.csv` (torn tail) and the next flush rewrites them.
- More than `max_columns` run columns in a series file → continue in `<variable>_part2.csv`, `_part3`, ...;
  `series()` joins the parts.
- A locked file (`PermissionError`) keeps the data buffered, logs one warning per file, retries on the next flush;
  `close()` retries once more and then raises a clear error naming the file.
- `create=True` on an existing `session.json` raises `FileExistsError`; `open()` on a missing one raises
  `FileNotFoundError`. `check_signature` compares the stored signature dict to the given one.
- Pure I/O: no SWAT, no metric computation, no knowledge of algorithms. English messages.

## Files in scope
`spyswat/swat_calib/calibration/session_store.py` (new), `tests/test_session_store.py` (new),
`.agents/log/API-2A.md`. Do not edit `__init__.py` files (exports come in API-4).

## Acceptance criteria
- [ ] Tests (tmp_path, synthetic): layout and exact file names; repr float round-trip incl. 0.1+0.2, 1e-17, -0.0,
      NaN; flush_every batching; torn tail ignored by `open()`; part2 split with small `max_columns`; locked file
      buffered then written (simulate with monkeypatched `os.replace` raising PermissionError once);
      FileExistsError / FileNotFoundError; check_signature diff message; best/sensitivity files.
- [ ] `python -m pytest tests/test_session_store.py -q` then `python -m pytest tests/ -q` pass
      (baseline on main: 475 passed, 11 skipped); `git diff --check` clean.

## Report
Append to `.agents/log/API-2A.md`: files changed, commands + result lines, open questions. Commits `api-2a:`.
