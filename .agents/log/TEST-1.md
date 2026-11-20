# Log TEST-1

Append-only. Correct a mistake by adding a new entry below it.

## 2026-11-20 · claude-opus-5.5 · step 1/1
- Done: `fake_runner` writes `runs.log.<worker folder>` (one writer per file, because a
  folder runs one job at a time). The new helper `trace_lines(log)` reads all of them in
  folder order. All 7 readers use it (2 x `assert not ...`, counts 2 / 8 / 9, and the n=1
  ordering test). Counts and assertions are unchanged.
- Files changed: `tests/test_scenarios.py`
- Checks:
  - `pytest tests/test_scenarios.py -q` x5 in a row (in the background, partly concurrent
    with the full suite): runs 1-4 → 16 passed each (103-135 s);
  - full suite with it → 327 passed / 11 skipped.
- Not committed.

## 2026-11-20 · claude-opus-5.5 · stress run finished
- `pytest tests/test_scenarios.py -q` x5: **5/5 runs → 16 passed** (103-140 s); exit 0.
  Acceptance met.
