# API-5A review round 1 — agy gemini-4-neon-high (plan, sandbox, diff inlined)

Verdict: PASS

### Critical
None.

### Major
None.

### Minor
1. **`spyswat/swat_calib/calibration/replay.py:144-161` — `ReplayCursor.take` advances `_pos` before validating the full batch.**
   If `param_sets[0]` matches and `param_sets[1]` mismatches, `self._pos` is already incremented before `ResumeMismatchError` is raised, violating the docstring ("without advancing the cursor").
   *Fix:* Track `pos = self._pos` locally across the loop and assign `self._pos = pos` only after all entries pass `_check`.

2. **`spyswat/swat_calib/calibration/calib_manager.py:804-809` — Explicit `run_ids` length check breaks callers when `replay` replays >= 1 run.**
   Changing `len(run_ids) != total` to `len(run_ids) != n_live` rejects a caller passing the same `run_ids` (one per `param_sets` entry) as the uninterrupted run, and fails on an all-replayed batch (`n_live == 0`).
   *Fix:* Validate `len(run_ids) != total` and slice `run_ids = run_ids[n_replayed:]` for live runs.

3. **`spyswat/swat_calib/calibration/calib_manager.py:22` — Unused import.**
   `from .replay import ReplayCursor` is never referenced in `calib_manager.py`.
   *Fix:* Remove the unused import or use it in the `replay: ReplayCursor | None = None` annotations.

4. **`tests/test_resume_replay.py:418-424` and `tests/test_resume_replay.py:253` — Weak mismatch assertion and misleading comment.**
   `test_replay_cursor_param_mismatch_names_run_and_values` only matches `"run 1"` (not the parameter name, stored value, or new value); line 253 comments `# evals 1,2 committed; 3 raised, 4 never ran`, whereas `interrupt_at=3` runs eval 3 and raises on eval 4 (leaving chunk `[3, 4]` uncommitted). Also worth adding unit checks for formatted-dict unwrapping in `ReplayCursor.take`, cursor non-advancement on batch mismatch, and `replay` with `store=None`.
   *Fix:* Assert `"CN2.mgt"`, `"50.0"`, and `"99.0"` in the mismatch message, fix the line 253 comment, and add the three edge-case checks.

### Checks
- **Hand-check (multi-site score & replay):** Two sites `("FLOW_OUTcms", 1)` (`nse_calib=0.8, kge_calib=0.75`) and `("SED_OUTtons", 51)` (`nse_calib=0.6, kge_calib=0.55`) with equal weights yield `score=0.7`. `ReplayCursor._build_runs` loads both `<var>_metrics.csv` files into `StoredRun.site_metrics[rid][(var, reach)]` and `_build_multisite_row` reconstructs `["score", "nse@FLOW_OUTcms@1", "kge@FLOW_OUTcms@1", "nse@SED_OUTtons@51", "kge@SED_OUTtons@51"] = [0.7, 0.8, 0.75, 0.6, 0.55]`; PSO/DE multi-batch `_store_counter = max(_store_counter, next_run_id - 1)` assigns contiguous live ids `7..12` after `k=6`.
- **Spec, design & rules:** All 5a build items and binding pre-review corrections are met across `replay.py`, `calib_manager.py`, and `{glue,pso,parallel_de,dds}.py`; `swat_project.py` is untouched (5b scope); English messages, picklable worker callables, no `TxtInOut` mutation on replay, and no secrets.

## CEO: PASS (Neon). Auditor full suite on 5b7d8b6 = 701 passed, 15 skipped. All four Minors go to API-5B (final task, owns replay follow-ups).
