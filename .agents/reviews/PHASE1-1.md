# Review PHASE1 — round 1

- Reviewer: `/code-review high` (multi-agent, Claude Opus 5.5), then each finding re-checked
  against the code by the session (Claude Opus 5.5)
- Diff: `git diff main...fix/phase1-correctness` at fb49870 (+ uncommitted DOCS-2)

## Verdict: FAIL (5 correctness findings confirmed)

## Findings

| # | Severity | Location | Problem | Verified | Fix (task) |
|---|---|---|---|---|---|
| 1 | Critical | `analysis/statistics.py:29` | Failed runs scored ±1e6; real scores can be worse (sediment RMSE, very negative NSE), so DE/PSO/optimize can keep a failed run as best | Yes: `parallel_de.py:221` `trial_obj <= obj`, `:259` argmin; `pso.py:482` | REV-1 (design choice left to the user) |
| 2 | Major | `analysis/sensitivity.py:38` | `_sequential_mean` has no fresh-output check; stale `output.rch` recorded as ok | Yes: no `_stamp_output_rch` / `_check_fresh_output_rch` in the function | REV-1 |
| 3 | Major | `calibration/validation_runner.py:126` | `';'.join(subs)` crashes on scalar subbasin after calibration; `"All"` written `A;l;l` | Yes | REV-1 |
| 4 | Minor | `calibration/calib_manager.py:469` | `observed.index` evaluated outside the try, before `_restore_state()` | Yes (needs a non-Series `observed`) | REV-1 |
| 5 | Major | `calibration/calib_manager.py:692` | `_sim_freq` uses the project's cached `FileCIO`; `read_rch` re-reads `file.cio` → disagree after a hand edit or another `FileCIO` instance | Yes; `project.FileCIO.set()` itself stays consistent | REV-1 |
| 6 | Minor (perf) | `calibration/calib_manager.py:503` | Sequential backup copies every extension in the parameter file each iteration | Yes | REV-1 |
| 7 | Minor (perf) | `core/workingFolder_manager.py:174` | Each worker job builds TxInOut twice, parses SWATParam several times | Plausible, not measured | ARCH-1 |
| 8 | Major (design) | 4 call sites | backup → run → fresh check → read → restore copied four times; already drifted (#2) | Yes | ARCH-1 |
| 9 | Minor (rule) | `calibration/calib_manager.py:695` | `_sim_freq` infers frequency from obs for mocks; breaks design rule 6 | Yes | REV-1 |
| 10 | Minor | `scenarios/batch.py:33`, `scenarios/model.py:11`, pso/de | IPRINT table, cio keys, finite-stats helper duplicated | Yes | REV-1 |

## Scope check
- Findings outside the branch: none.
