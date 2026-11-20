# Review coord-1 — round 1

- Reviewer: Claude Opus 5.5 High (requested by the user via coord-1)
- Sparring pre-review: agy / Gemini 4 Argon High, rounds 1-2 (see `log/coord-1.md`)
- Diff: **working tree** on `fix/phase1-correctness` at `fb49870` (uncommitted REV-1,
  DOCS-2, DOCS-3 work). This is a read-only pre-review, **not** a clean-commit handoff.
- Inputs read: `tasks/coord-1.md`, `log/coord-1.md`, `reports/coord-1.md`, `tasks/REV-1.md`,
  plus source context: `analysis/statistics.py`, `analysis/calibration.py:70-155`,
  `algorithms/parallel_de.py:140-270`, `algorithms/pso.py:400-495`,
  `tests/test_scenarios.py:95-290`, `.opencode/agents/reviewer.md`.

## Verdict: FAIL (branch not ready); coord-1 report: ACCURATE

The coord-1 report is accurate. Every claim I re-checked held up, and its approval
boundaries are correct. The branch stays blocked on two items: the user-reserved
decision for finding 1, and a separate test-only task for the scenario trace race.

## Independent verification (this session)

| Claim | Check | Result |
|---|---|---|
| 6 metric failures on the unpatched source | `python -m pytest tests/test_metrics.py tests/test_calibration.py -q` | **6 failed, 80 passed**, same cases as the report |
| `worst_score` is the only penalty source | grep `worst_score\|sanitize_scores` in `spyswat/` | DE `parallel_de.py:156`, PSO `pso.py:413,472`, optimize `calibration.py:130`; nothing else |
| DE and PSO stay correct with ±inf | read the selection code | DE `trial_obj <= obj`: `inf <= finite` is False, and `inf <= inf` only swaps one failed member for another. PSO `obj < pbest_obj` is strict. The convergence spread `obj.max()-obj.min()` is `inf` while a failed member remains, so `< tol` never fires early (no behaviour change: the spread was already ≥ 1e6). Means and stds go through `finite_stats` |
| SciPy DE (default `optimize` path) accepts inf | read `_differentialevolution.py` (explicit `isinf` handling at 1169-1213); probe with 70% of the domain returning `inf` | Converged to the valid optimum: 47 calls, 32 valid, **0 warnings** |
| The non-DE branch ignores `method` | `calibration.py:137` `minimize(objective, x0, bounds=bounds)` | Confirmed: `method` is never forwarded, so the call is always L-BFGS-B. The docstring ("Nelder-Mead/SLSQP") is wrong |
| The scenario failure is a pre-existing flake | `git diff --stat -- tests/test_scenarios.py` is empty; last changed in `b1931b7` | Confirmed: not a REV-1 regression. `fake_runner` appends from several processes to one `runs.log` (`test_scenarios.py:100-103`) |
| Reviewer role sees only committed diffs | `.opencode/agents/reviewer.md:22` | Confirmed |

## Findings

| # | Severity | Location | Problem | Fix |
|---|---|---|---|---|
| 1 | Critical | `analysis/statistics.py:51-59` | A failed run (±1e6) outranks real scores beyond 1e6, so DE and PSO can return `best_score=NaN` | **User decision (REV-1).** Recommendation: signed infinity, `-inf` for maximize metrics, `+inf` otherwise (`pbias` goes through `abs()`, and `abs(±inf)=inf`). Keep the signature. Drop `_WORST_MAGNITUDE` and its stale comment. Keep raw NaN in history. Do **not** change DE's `<=` rule |
| 2 | Major | `analysis/calibration.py:134-137` | The `minimize` branch never forwards `method` and always runs L-BFGS-B. Its finite differences turn `inf - inf` into NaN, and with ±1e6 it falsely reports convergence on a failed plateau (coord-1 probe) | New task, not REV-1: forward `method=` and fix the docstring. Under `on_failure="penalize"`, default to or allow only derivative-free methods (`Nelder-Mead`, `Powell`, `COBYLA`), which only compare values, so `inf` is safe. Add a test that the returned params match the best finite history row |
| 3 | Major (test reliability) | `tests/test_scenarios.py:100-103, 253-275` | On Windows, text-mode `"a"` is a CRT seek-then-write, not atomic across processes, so concurrent workers lose trace lines (7 of 8 seen) | New test-only task: one trace file per worker (named by worker dir or pid) outside the worker folders, aggregated in the parent by every `E5_RUNLOG` reader. Keep the counts 8 → 9 and 7 skipped, and the `n=1` ordering test. `os.open(O_APPEND)` is not a fix on Windows (same CRT emulation). Do not loosen the assertion or skip |
| 4 | Minor (harness) | `.opencode/agents/reviewer.md:22` | The formal Reviewer reads only `git diff main...HEAD`, so uncommitted work is invisible and the "ONLY" rule bans source context | Separate harness task (Gemini Argon owner): allow a labelled *pre-review* mode (`git status`, `git diff`, `git diff --cached`, source context). Keep the formal gate on clean committed diffs |
| 5 | Minor (tooling) | `agm 0.1.0` vs tutorial `0.2.0` | `agm send` refuses recipients in state `done` (`status_mismatch`). The `hc send` fallback worked: this review was triggered by it | Record in `docs/agents/SETUP-WINDOWS.md` (DOCS task): send to a `done` Claude session with `hc send` without `--force`. Quote multi-word `--type` values |
| 6 | Minor (docs) | `AGENTS.md` Commands section | "expected: 308 passed" is stale. The real gate must be re-measured after finding 1 and finding 3 are fixed | Update the count in the same commit that turns the suite green |

## Recommended order (for the Manager)

1. **User:** implement or approve finding 1 (signed infinity). Then run
   `pytest tests/test_metrics.py tests/test_calibration.py -q`, which should give 86 passed.
   Commit as `REV-1:` with the existing REV-1 changes and their log.
2. Commit DOCS-2 / DOCS-3 separately (`<ID>: docs: ...`). Do not mix them into REV-1.
3. `TEST-1` (worker tier mid): per-worker scenario traces (finding 3). Run a stress
   loop, e.g. `pytest tests/test_scenarios.py -q --count=20` or a shell loop, and record
   the counts.
4. `OPT-1` (strong, needs approval): `optimize` method dispatch and derivative-free
   policy under penalize (finding 2).
5. Full suite, then Auditor `PASS ALL`, then formal Reviewer on clean commits, then
   `copilot-git`.
6. ARCH-1 stays **proposed** until the user approves. It must not be bundled with
   steps 1-4.

## Scope check

- coord-1 changed only its own notebook files (`tasks/`, `log/`, `reports/coord-1.md`).
  I found no product, test or permission edits attributable to coord-1.
- This review changed only `.agents/reviews/coord-1-1.md`. No source edits, commits or merges.
- The worktree is still mixed (REV-1 + DOCS-2 + DOCS-3 + harness). It is not a clean final SHA.

## Correction (2026-11-20, same reviewer)

Finding 2 above recommended allowing only derivative-free methods under `penalize`
because they "only compare values, so `inf` is safe". A probe disproves this. The probe
used a 2-parameter bounded problem, with failures at `x0 > 0.6 or x1 > 0.7`.

When the search starts **inside** the failed region:

| Method | Outcome |
|---|---|
| Nelder-Mead | 799 calls, 0 valid |
| COBYLA | 7 calls, 0 valid |
| SLSQP | ends at `inf` |
| L-BFGS-B | returns `nan` |
| Powell, COBYQA | recover |

When the search starts **valid but near** the failed region, every method finds the
optimum with `inf`. With the old `1e6` penalty, local methods instead *prefer* failed
points.

OPT-1 therefore makes these changes:

- It forwards `method` and `max_iter`.
- It documents that a local method needs a valid start point, and that DE should be used
  when parts of the space crash SWAT.
- It adds **no** method whitelist.
