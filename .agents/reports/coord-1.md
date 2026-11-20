# coord-1: engineering evidence and handoff to Opus

- Date: 2026-11-19
- Branch: `fix/phase1-correctness`
- Inspected HEAD: `fb49870c33ff981cd0aa4b515e31ec3106f3d01b`
- Engineering: OpenCode / GPT-6.1 Sol
- Technical consultation: agy / Gemini 4 Argon High, read-only
- Requested reviewer: the existing SpySWAT Claude Opus 5.5 session
- Status: **BLOCKED for integration/release; read-only diagnostic handoff**
- Delivery: **verified** through direct `hc send` after the AGM guard failed;
  Opus responded in `.agents/reviews/coord-1-1.md`.
- Reviewer outcome: **coord-1 report ACCURATE; branch FAIL / not ready**.

## Outcome

Current source is not ready: the full suite reports **7 failed, 315 passed,
11 skipped**. Six failures reproduce the reserved REV-1 penalty decision.
The seventh exposes an intermittently failing shared trace in the scenario
test fixture. This coordination task changed no product code, tests or agent
permissions, and did not commit another agent's work.

## Findings and proposed disposition

### 1. Critical: failed population members can become the best result

- Locations: `spyswat/swat_calib/analysis/statistics.py:28-59`,
  `analysis/algorithms/parallel_de.py:154-162,216-223,255-261`,
  `analysis/algorithms/pso.py:411-420,471-483`.
- `worst_score` uses finite magnitude `1e6`; legitimate finite scores can be worse.
- Existing tests fail for large RMSE, MAE, signed PBIAS, NSE and KGE.
- A synthetic fixed population `[NaN, 3e6, NaN, 7e6]`, RMSE, seed 0, makes
  **both DE and PSO return NaN** with the current source.
- Process-local signed-infinity replacement makes both return `3e6`.
- The same in-memory replacement changes the targeted suite from
  **6 failed / 80 passed** to **86 passed**, with an additional SciPy warning.
  This is diagnostic evidence, not an implemented fix.

**Recommendation for approval:** retain the metric registry and current function
signature; return `-inf` for maximizing metrics and `+inf` for minimizing and
absolute-minimizing metrics. Remove/update the stale finite-penalty constant and
comment if this is implemented. Preserve raw NaN scores in run history.

Do not automatically change DE's `<=` replacement rule: with infinity,
`inf <= finite` is false, so failed candidates cannot replace valid candidates.
Changing equal-fitness replacement adds behavior not required by this finding.

**Approval boundary:** `.agents/tasks/REV-1.md:25` explicitly reserves this
implementation/design choice to the user. Opus should record a recommendation
or obtain an updated authorization; this report does not override that constraint.

### 2. Optimizer caveat: neither penalty guarantees local-search recovery

- Location: `spyswat/swat_calib/analysis/calibration.py:102-142`.
- The non-DE branch calls bounded `minimize` without forwarding the requested
  method, so its current default is L-BFGS-B. This report does not change that API.
- Infinity can cause invalid subtraction in numerical derivatives.
- A synthetic failed-plateau probe produced:
  - finite `1e6`: reported convergence after 2 calls, **0 valid evaluations**;
  - infinity: `ABNORMAL` after 42 calls, **0 valid evaluations**.
- Therefore finite adaptive penalties are not automatically a safer solution.
- `optimize` already returns the best **raw finite history score**, not
  `scipy_result.fun`, and raises when its history contains no finite scores.
  Do not incorrectly describe its final-selection path as identical to DE/PSO.

**Recommendation:** document the local-search limitation and add tests for
partial failures, all failures and agreement between returned parameters/score
and the best valid history row. Any change to optimizer method dispatch or
retry/recovery policy needs separately approved scope.

### 3. Test reliability: scenario fixture loses concurrent trace writes

- Locations: `tests/test_scenarios.py:100-103,253-275`.
- Full-suite failure: `test_failure_isolation_and_resume`, line 267, expected
  8 trace lines but observed 7.
- Prior assertions passed: 7 successful jobs, the correct injected failed job,
  and 7 output CSVs. There is no current evidence of missing production jobs.
- Isolated rerun: **1 passed** in 22.47 seconds, confirming intermittent behavior.
- Windows concurrent buffered-append probe: **946 / 1000** trace lines.
- Stress probe through the real `fake_runner`, synchronizing buffered closes:
  **369 / 400** trace lines. Using separate trace files per worker and aggregating
  in the parent produced **400 / 400**.

**Recommendation:** a test-only follow-up in `tests/test_scenarios.py`:
use per-worker trace files outside worker folders, aggregate in the parent, and
adapt every `E5_RUNLOG` reader. Preserve the single-worker test's ordering and
the resume assertions (8 initial invocations, 9 after retry, 7 skipped).
Do not use a thread-only lock as a cross-process solution. Do not weaken the
assertion to accept 7 lines, skip the test, or treat a lucky rerun as a fix.

The shared trace path is demonstrably racy; attribution of this particular
full-suite failure to that race is strongly supported by the evidence, rather
than a claim that production job execution has been proven faulty.

### 4. Review coverage: committed-only diff omits the pending fixes

- Location: `.opencode/agents/reviewer.md:22`, mirrored by the repository's
  committed-only formal review instructions.
- `git diff main...HEAD` excludes the existing uncommitted REV-1 and DOCS-3 work.
- The role also says to read ONLY the task/log/diff, precluding source context.

**Recommendation:** distinguish this read-only working-tree pre-review from a
formal clean-commit handoff. For preliminary diagnosis inspect `git status`,
`git diff`, `git diff --cached`, and relevant source context; use
`git diff main...HEAD` for committed branch history. Formal review still needs
scoped, logged commits and the clean-worktree gate. Update the harness in a
separate approved task rather than silently treating this branch as ready.

### 5. Tooling: compatibility is not the same as verified enforcement

- Runtime `agm --version`: **0.1.0**; tutorial assumptions target **0.2.0**.
  Working `ask`, `send --help`, `ps` and `inbox` commands do not prove every
  documented rotation/daemon behavior on this version.
- Official OpenCode V2 documentation confirms `.opencode/agents/` is correct and
  legacy `permission` / `bash` / `task` frontmatter remains translated.
  Do **not** label those permissions broken solely because the syntax is V1.
- Native V2 conversion is optional; if undertaken, convert each complete
  frontmatter block, avoiding partial V1/V2 mixing, and verify effective rules.
- Quote multiword CLI message kinds, e.g. `--type "BÁO CÁO"` and
  `--type "CHƯA ĐẠT"`.
- Actual handoff exposed a concrete transport problem: `agm send` passes an
  idle-only guard but the completed Claude session reports `done`. It failed
  with `status_mismatch` and `nothing was typed` (AGM message 1).
  Direct, non-forced `hc send` succeeded and Opus was observed reading the task.
  No daemon or installed CLI was modified.

Sources: https://opencode.ai/docs/agents and
https://opencode.ai/docs/migrate-v1 (checked 2026-11-19).

## agy discussion

Round 1 succeeded using `gemini-4-argon-high`, conversation
`65ca977b-1d77-46db-b999-5dfb6af4db0d`.
Argon recommends directed infinity, explicitly retains the user's reserved
decision, keeps ARCH-1 separate, and identifies missing PSO/optimizer-history
regression coverage. It did not execute tests.

Engineering challenged its unnecessary suggestion to change DE's tie rule and
sent a follow-up with the additional flaky-test and optimizer probes. Round 2
succeeded, conversation `25c65021-4351-4db8-a21a-64f1d6a2495e`: Argon accepted
keeping DE's tie rule unchanged and endorsed test-only per-worker traces.
Both rounds retain the user approval boundary and report no implemented fix.
See `.agents/log/coord-1.md` for the evidence and qualified conclusions.

## Opus response

Read `.agents/reviews/coord-1-1.md` for the independent review. Opus reproduced
**6 failed, 80 passed** in the targeted suite and confirmed the report's findings.
Its separate SciPy DE probe tolerated infinity and converged to a valid optimum
(47 evaluations, 32 valid, 0 warnings).

Requested next steps remain conditional:
- User implements or authorizes signed infinity for REV-1.
- Separate `TEST-1` repairs the pre-existing scenario trace fixture.
- Separate, approved `OPT-1` addresses dropped optimizer method dispatch and
  chooses a failure-handling policy; derivative-free methods do not guarantee
  recovery from every invalid initial region.
- Preserve separate DOCS-2/DOCS-3 work and the unapproved ARCH-1 proposal.
- Re-run the full suite and obtain clean-commit audit/review before integration.

## Acceptance checks after an authorized fix

1. Add or retain regressions for large finite scores, both signed PBIAS cases,
   and non-finite inputs over all registry directions.
2. Test DE **and PSO** with a mixed large-score/failed population and a wholly
   failed initial population; results must be finite when valid runs exist.
3. Test raw-score/history/parameter consistency for partial and all-failed
   `optimize(on_failure="penalize")` evaluations.
4. Stress the corrected scenario trace; retain isolation and resume assertions.
5. Run:

   ```text
   python -m pytest tests/test_metrics.py tests/test_calibration.py -q
   python -m pytest tests/test_scenarios.py -q
   python -m pytest tests/ -q
   git diff --check
   git status --short
   ```

6. Record actual counts; do not reuse the historical 316-pass claim as the
   current gate. Reconcile every changed file with its task and log.
7. Commit only authorized scoped work; do not stage unrelated pre-existing
   changes. Auditor and formal Reviewer gates remain pending.

## Deferred and unverified

- ARCH-1 remains **proposed**; no structural refactor performed.
- No runtime permission-enforcement test or full agm 0.2.0 feature validation.
- No real SWAT project, real watershed data, release, merge, push or tag used.
- GitNexus: task policy `none`; no index refresh requested or performed.
- Dirty mixed worktree: **not a clean final-SHA handoff**.
- Auditor: **FAIL** on the recorded unpatched tests.
- Opus verdict: **FAIL for branch readiness; report ACCURATE**, independently
  verified from the review file rather than inferred from report delivery.

## Files authored by this coordination task

- `.agents/tasks/coord-1.md`
- `.agents/log/coord-1.md`
- `.agents/reports/coord-1.md`

An Opus response, if produced, belongs in `.agents/reviews/coord-1-1.md`.
