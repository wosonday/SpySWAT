---
id: test-1
branch: fix/phase1-correctness
tier: mid
skills: verification-before-completion
docs_impact: no
gitnexus: none
---

# TEST-1: per-worker trace files in the scenario test fixture

## Goal
`tests/test_scenarios.py::fake_runner` appended from several worker processes to one
`runs.log`; on Windows append is seek + write, so lines were lost (7 of 8 seen in coord-1).
Write one trace file per worker folder and aggregate in the readers.

## Files in scope
- `tests/test_scenarios.py`, `.agents/log/TEST-1.md`

## Constraints
- Test-only. Do not loosen counts (8 -> 9, 7 skipped), skip, or retry tests.
- Keep the single-worker ordering test (`n=1`, one file, in call order).

## Acceptance criteria
- [x] Every `E5_RUNLOG` reader uses the aggregated trace
- [x] `pytest tests/test_scenarios.py -q` passes 5 times in a row (counts in the log)
