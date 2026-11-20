---
id: REV-1
branch: fix/phase1-correctness
tier: strong
skills: test-driven-development, verification-before-completion
gitnexus: none
---

# REV-1: fix the verified findings of review PHASE1-1

## Goal
Fix findings 1-6, 9, 10 of `.agents/reviews/PHASE1-1.md`, each with a test that fails before
the fix. Findings 7 and 8 belong to `.agents/decisions/ARCH-1.md`.

## Files in scope
- `spyswat/swat_calib/analysis/statistics.py`, `analysis/sensitivity.py`,
  `analysis/algorithms/pso.py`, `analysis/algorithms/parallel_de.py`
- `spyswat/swat_calib/calibration/calib_manager.py`, `calibration/validation_runner.py`
- `spyswat/swat_project.py` (FileCIO freshness)
- `spyswat/swat_calib/scenarios/batch.py`, `scenarios/model.py`
- `tests/**`, `.agents/log/REV-1.md`

## Constraints
- No behaviour change beyond the findings. Design rules in AGENTS.md.
- Finding 1 (worst score) is a design decision: the user implements it.

## Acceptance criteria
- [ ] One failing-then-passing test per finding
- [ ] `pytest tests/ -q`: 0 failed (record counts)
