---
id: api-3c
branch: feat/api-3c
tier: mid
skills: test-driven-development
docs_impact: no
gitnexus: none
---

# API-3c: four follow-ups from review API-3B-1

Read `.agents/reviews/API-3B-1.md` (on main) and fix its four Minor findings exactly as proposed, test-first:
1. `analysis/sensitivity.py::_batch_scores` uses `_reported(metric, metrics)` (a bare string `metrics="kge"` must not
   split into characters; `metric` always included). Test both cases.
2. `tests/test_algorithms_vocabulary.py::test_optimize_passes_new_vocabulary_through` asserts the forwarded kwargs
   (`weights`, `metric`, `observed`); add mocked-`run_batch` tests for `one_at_a_time`, `morris_method`,
   `morris_salib` (skip if SALib missing), `sobol_method` covering dict `observed`, `weights`, `metrics`, old+new → TypeError.
3. `_resolve_sens_observed` passes `stacklevel=4`; test that the DeprecationWarning points at the caller's file.
4. GLUE builds `rng = np.random.default_rng(seed)` and passes it to `LatinHypercube(..., seed=rng)`; same-seed
   determinism test still passes.

## Files in scope
`spyswat/swat_calib/analysis/sensitivity.py`, `spyswat/swat_calib/analysis/algorithms/glue.py`,
`tests/test_algorithms_vocabulary.py`, `.agents/log/API-3C.md`.

## Acceptance criteria
- [ ] `python -m pytest tests/test_algorithms_vocabulary.py -q`, then `python -m pytest tests/ -q -p no:cacheprovider`
      and `... -W error::DeprecationWarning:spyswat` pass (record counts; main baseline 628 passed, 11 skipped);
      `git diff --check` clean.

## Report
Append to `.agents/log/API-3C.md`: files changed, commands + result lines. Commits `api-3c:`.
