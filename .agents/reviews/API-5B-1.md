# API-5B review round 1 — agy gemini-4-neon-high (plan, sandbox, diff inlined)

Verdict: PASS

### Critical
None.

### Major
None.

### Minor
- `spyswat/swat_project.py:353-357`: When `stored_seed is None`, the error message says `"pass seed= explicitly to continue"`, but passing an explicit `seed=` will still fail `store.check_signature(_signature())` against the missing stored seed. Fix: reword to `"cannot resume: stored session.json has no seed"` and add a unit test in `tests/test_facade_resume.py` covering a `seed: null` session.
- `spyswat/swat_calib/calibration/calib_manager.py:805-812`: The updated `run_ids` total-length check and `run_ids[n_replayed:]` slice are not exercised by any new test. Fix: add a test in `tests/test_resume_replay.py` calling `run_batch(..., run_ids=..., replay=cursor)` for both a valid partial-replay batch and a mismatched `len(run_ids)`.
- `spyswat/swat_calib/calibration/result.py:334-335`: `runs["status"].to_numpy() == "ok"` produces an object array with `pd.NA` if `status` uses a pandas nullable string dtype with missing values, causing `keep & ...` to raise `TypeError`. Fix: use `runs["status"].eq("ok").fillna(False).to_numpy(dtype=bool)`.
- `tests/test_facade_resume.py:184-201`: `test_facade_resume_seed_none_uses_stored_seed` resumes an already-completed session (`0` live runs), and all facade resume tests pass `sensitivity=False`. Fix: interrupt the `seed=None` run mid-way and compare against an uninterrupted run using `stored_seed`, and enable `sensitivity=True` on at least one resumed case to verify `sensitivity.csv` / `res.sensitivity`.

### Verification notes
- **Spec & design**: Facade resume opens `SessionStore.open` before the `try/finally` close, checks `seed`, `check_param_order`, and `check_signature` before touching any file, forwards `replay=ReplayCursor(store)`, handles missing/existing sessions (`FileNotFoundError`/`FileExistsError`), removes the `NotImplementedError`, resolves all API-4-3 and API-5A-1 Minors, updates `README.md`/`README_VI.md`/`CHANGELOG.md`, and stays strictly within scope with no secrets or `TxtInOut` mutation.
- **Numeric hand-check**:
  - `_hash_observed` (`spyswat/swat_project.py:613-614`): `0.0` (`00..00`) and `-0.0` (`00..80` in IEEE-754 `<f8`) both satisfy `vals == 0.0`, so `vals[vals == 0.0] = 0.0` canonicalises `-0.0` to `0.0` on a fresh copy without mutating the input `Series` or corrupting `NaN`.
  - Facade fixture (`tests/test_facade_resume.py:31-35`): for constant simulated `CN2=50.0` over 10 days against `FLOW_OUTcms` `[0..9]` (mean `4.5`, `SS_tot=82.5`) and `SED_OUTtons` `[1,3..19]` (mean `10.0`, `SS_tot=330.0`), `NSE_flow = 1 - (10*45.5^2 + 82.5)/82.5 = -250.9394`, `NSE_sed = 1 - (10*40^2 + 330)/330 = -48.4848`, equal-weighted `score = -149.7121` (monotone in `CN2` on `[35, 98]`, giving PSO/DE/DDS real search gradients).
- **Tests & rules**: 717 passed, 15 skipped (+16 new tests over 701 baseline), `-W error::DeprecationWarning:spyswat` clean, `fake_run_parallel` verifies `extract` picklability, harness lint 0 errors, `git diff --check` clean.

## CEO triage → rework (worker-mid)
PASS, but fix all four Minors exactly as proposed before the final merge (resume must be proven on an interrupted seed=None run, with sensitivity=True on one resumed case). Auditor: full suite on def096c = 717 passed, 15 skipped; lint 0 errors.

## CEO: rework done. Auditor on 2bc58b6: 721 passed, 15 skipped (-W error::DeprecationWarning:spyswat), lint 0 errors. Minor-only rework: no further review round.
