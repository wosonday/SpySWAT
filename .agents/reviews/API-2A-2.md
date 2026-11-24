# API-2A review round 2 — agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

## Critical
None.

## Major
None.

## Minor
- **`write_best` / `write_sensitivity` do not guard `_closed`** (`spyswat/swat_calib/calibration/session_store.py:281-288`): Unlike `add_run()`, calling `write_best()` or `write_sensitivity()` after `close()` does not raise `RuntimeError`; if the target file hits `PermissionError`, the payload stays in `_pending_best` / `_pending_sensitivity` while `flush()` returns early because `self._closed` is `True`.
  - **Fix:** Add `if self._closed: raise RuntimeError("SessionStore is closed")` at the start of `write_best()` and `write_sensitivity()`.

## Checks
- **Spec & Design:** All four round-1 Minor findings were resolved (`max_columns` persisted/restored and stale `_partK.csv` files unlinked; `_pending_best`/`_pending_sensitivity` buffered and retried on `close()`; `default=str` in `_canon()`; torn-tail rewrite verified on disk). Layout, signatures, `runs.csv`-last commit order, `PermissionError` buffering/warning-once/retry-on-close, `FileExistsError`/`FileNotFoundError`, and `check_signature` diff reporting match the spec.
- **Numeric hand-check:** `_fmt_float` writes `0.1 + 0.2` via `repr()` as `0.30000000000000004` and `1e-17` as `'1e-17'`, which `float()` parses back bit-identically; `-0.0` normalises via `if f == 0.0: f = 0.0` to `'0.0'` (`+0.0`); `NaN`/`None` write as `""` and `_parse_float("")` returns `float("nan")`.
- **Tests & Rules:** `tests/test_session_store.py` (17 synthetic `tmp_path` tests) exercises layout, float round-trip, batching (`flush_every` and `flush_seconds`), torn-tail filtering and disk rewrite, `max_columns` splitting/reopen/stale cleanup, locked-file buffering and `close()` retry/error, signature canonicalisation, and error paths without `swat.exe` or `TxtInOut` mutation. English messages, module-level picklable definitions, explicit errors, scope (spec files plus `.agents/reviews/API-2A-1.md`), and no secrets all hold. (Commands were not executed per review instructions; `.agents/log/API-2A.md` reports `17 passed` for `test_session_store.py`, `492 passed, 11 skipped` for `tests/`, and clean `git diff --check`.)
