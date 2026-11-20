---
id: opt-1
branch: fix/phase1-correctness
tier: strong
skills: test-driven-development, verification-before-completion
docs_impact: yes
gitnexus: none
---

# OPT-1: `optimize` uses the requested local method and `max_iter`

## Goal
`SWATCalibration.optimize(method=...)` ignored `method` and `max_iter` for every non-DE
method (always L-BFGS-B, scipy default iterations). Forward both and document that a local
method cannot leave a region where every run fails (`.agents/reviews/coord-1-1.md` #2).

## Files in scope
- `spyswat/swat_calib/analysis/calibration.py`
- `tests/test_metrics.py`
- `.agents/log/OPT-1.md`

## Constraints
- No method whitelist: probes show no local scipy method recovers from a failed start
  point (Nelder-Mead: 799 calls, 0 valid), so a whitelist would promise safety it cannot give.
- Keep the final selection from the raw history (`best_index`), not `scipy_result.fun`.

## Acceptance criteria
- [x] Test: the requested method and `{"maxiter": max_iter}` reach `scipy.optimize.minimize`
- [x] Test: with partial failures, returned params/score equal the best finite history row
      (DE, Nelder-Mead, Powell)
- [x] `pytest tests/ -q`: 0 failed (counts in the log)
