# API-2A review round 1 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Critical
None.

## Major
None.

## Minor
- **Stale `_partK.csv` files on re-open or torn tail** (`spyswat/swat_calib/calibration/session_store.py:145-160`, `spyswat/swat_calib/calibration/session_store.py:280-296`): `open()` does not restore `max_columns` (it defaults to `16000`), so re-opening a session created with a smaller `max_columns` and flushing writes all runs into `<variable>.csv` without removing existing `_part2.csv`+ files; `series()` (`pd.concat(frames, axis=1)`) then returns duplicate `run_<id>` columns. Stale `_partK.csv` files from a torn tail also remain on disk.
  - **Fix:** Persist `max_columns` in `session.json` and restore it in `open()`, and unlink any `_part<k>.csv` beyond the chunks written in `_write_series_files()`.
- **Locked `best.csv` / `sensitivity.csv` not retried on `close()`** (`spyswat/swat_calib/calibration/session_store.py:252-276`): `write_best()` and `write_sensitivity()` call `_commit_file()` without buffering their inputs, so if either file hits `PermissionError`, `flush()` inside `close()` does not retry it and `close()` raises `OSError` even if unlocked. Additionally, a lock encountered for the first time during `close()` is only tried once.
  - **Fix:** Cache pending `best`/`sensitivity` payloads to write inside `flush()`, and in `close()` call `self.flush()` once more when `self._locked_files` is non-empty before raising `OSError`.
- **Signature canonicalisation asymmetry** (`spyswat/swat_calib/calibration/session_store.py:75-80`, `spyswat/swat_calib/calibration/session_store.py:411-420`): `_write_session_json()` serialises with `default=str`, while `_canon()` omits `default=str`, causing `Path` or `Timestamp` signature values to mismatch after `open()`.
  - **Fix:** Pass `default=str` to `json.dumps` in `_canon()`.
- **Torn-tail rewrite on flush untested** (`tests/test_session_store.py:135-158`): `test_torn_tail_ignored_by_open` checks that `open()` ignores `run_999`, but does not verify that a subsequent `add_run` + `flush()` clears `run_999` from the CSV files on disk.
  - **Fix:** Add an `add_run` + `close()` step and assert `run_999` is absent from the CSV files.

## Checks
- **Spec & Design:** Exact layout, method signatures, `repr()` float round-trip, `runs.csv`-last commit order, `max_columns` splitting, `PermissionError` buffering/warning-once/retry-on-close, `FileExistsError`/`FileNotFoundError`, and `check_signature` error match the spec.
- **Numeric hand-check:** `0.1 + 0.2` (`0.30000000000000004`) and `1e-17` round-trip bit-identically via `repr()` + `float()`; `-0.0` normalises to `0.0` (`'0.0'`); `NaN`/`None` write as `""` and parse back as `float('nan')`.
- **Tests & Rules:** 13 synthetic `tmp_path` tests exercise the core behaviours without `swat.exe` or `TxtInOut` mutation; English messages, explicit failures, scope limited to the three spec files, and no secrets. (Commands were not executed per review instructions; `.agents/log/API-2A.md` reports `13 passed` and `488 passed, 11 skipped`.)

## CEO triage → rework round (worker-mid)
Fix all four Minor findings exactly as proposed, test-first (persist/restore max_columns + unlink stale parts; buffer best/sensitivity and retry in close(); default=str in _canon; torn-tail rewrite test). Auditor: full suite on 28a21a7 = 488 passed, 11 skipped (CEO run).
