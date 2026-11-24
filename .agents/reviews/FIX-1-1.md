# FIX-1 review round 1 — Reviewer: agy gemini-4-hydrogen-high (plan, sandbox, diff inlined)

Verdict: PASS

Implementation satisfies F5 and F6 against the spec: `log_queue` defaults to `Logger._log_queue` without starting a listener and is passed to every `_seed_and_run` submission; `work_dir` uses `WORK_SUBDIR / _work_dir_key(res_dir)` with the required 10-char lowercase resolved-path SHA-1; class/method docstrings are updated in English; workers/runners remain picklable for Windows `spawn`; new tests exercise real spawned execution; and no out-of-scope files were modified.

### Critical
None.

### Major
None.

### Minor
- `tests/test_scenarios.py:914-926`: `test_work_dir_is_keyed_by_results_dir` checks `[0-9a-f]{10}`, uniqueness, and reuse, but does not assert the exact `sha1(str(Path(results_dir).resolve()).lower())[:10]` digest or path normalization.
  - **Fix**: Assert `dirs_a[0] == hashlib.sha1(str(res_a.resolve()).lower().encode("utf-8")).hexdigest()[:10]` and test an unresolved/relative path to `res_a` maps to the same directory.
- `tests/test_scenarios.py:924-926`: The second `res_a` run passes `PARAMS[2:3]` with default `resume=True`; verify `pytest` passes here in case `.signature.json` rejects a changed parameter-set list on resume.
  - **Fix**: If signature validation rejects `PARAMS[2:3]`, pass `resume=False` on that call (or keep the same `PARAMS` with an unfinished job).
- `.agents/log/FIX-1.md`: Append-only report file listed in scope is not in the diff.
  - **Fix**: Append files changed, `pytest` counts, and `git diff --check` confirmation to `.agents/log/FIX-1.md` before final commit if not already handled separately.

## CEO triage
- Minor 3 is a false positive: the snapshot diff only covered spyswat/ and tests/; the log exists (commit e5ab78d).
- Minor 2: full suite passed (454 passed, 11 skipped), so resume with PARAMS[2:3] is accepted.
- Minor 1 (exact digest assert): optional, not required by the spec; not done.
