---
id: par-2
branch: feat/PAR-2
tier: mid
skills: tdd
docs_impact: yes
gitnexus: none
---

# PAR-2: `resume=True` detects edited scenario TxtInOut inputs (finding F4)

Evidence: `.agents/decisions/PAR-1.md` finding F4 (in the main checkout / branch `feat/PAR-1`).
Model: `opencode-go/deepseek-v4.1-flash` (worker-mid). Runs in parallel with PAR-1, which
rewrites the dispatch loop of `scenarios/batch.py`: **touch only the lines listed below** so
the two branches merge cleanly (PAR-1 merges first; PAR-2 rebases after).
Budget: `agm budget task:par-2` soft 2M / hard 4M tokens; one rework round reserved.

## Goal
`ScenarioBatch.run(resume=True)` raises the existing "differs from the one stored" ValueError
when an input file of a scenario's base TxtInOut (its `txinout_dir`, or the project TxtInOut
when `txinout_dir` is None) was added, removed, resized or re-written since the stored run.
Results directories written by 0.2.6 (no fingerprint stored) keep resuming.

## Design (decided by the Architect)
1. New module `spyswat/swat_calib/scenarios/signature.py` with a pure function
   `txinout_fingerprint(directory) -> str`: SHA-1 hex digest of the sorted list of
   `(file name, size, st_mtime_ns)` for regular files directly in `directory`, **excluding**
   output files with the same patterns as `workingFolder_manager._OUTPUT_IGNORE`
   (`output.*`, `watout.dat`, the manifest name). Import those names; do not edit
   `workingFolder_manager.py`. Stats only, never file contents (TxtInOut can be GBs).
2. In `batch.py`, the stored signature gets one new key `"scenario_inputs": {scenario name:
   fingerprint}` built next to `"scenarios"` in `new_sig`.
3. `_signature_diff(old, new)`: compare `scenario_inputs[name]` only for names present in
   **both** old and new `scenario_inputs`; report `scenario 'X' inputs changed`. If the old
   signature has no `scenario_inputs` key (0.2.6 results), do not report a difference; log one
   INFO line: `cannot verify that scenario TxtInOut inputs are unchanged (results written by
   an older version)`.
4. Keep the "keep definitions of names not in this call" merge (`merged[...]`) working for the
   new key the same way as for `scenarios`.

Allowed edits in `batch.py`: the import block, `_signature_diff`, the `new_sig` dict and the
`merged` block. Nothing in the job loop.

## Files in scope
- `spyswat/swat_calib/scenarios/signature.py` (new)
- `spyswat/swat_calib/scenarios/batch.py` (only the parts named above)
- `tests/test_scenario_signature.py` (new)
- `.agents/log/PAR-2.md`; commit `.agents/tasks/PAR-2.md` unchanged in the first commit.

## Constraints
- Design rules in `AGENTS.md`; runtime messages in English; synthetic fixtures only
  (`tmp_path`, fake runner from `tests/test_scenarios.py` may be imported).
- Do not change existing tests in `tests/test_scenarios.py`.
- mtime tests: set times explicitly with `os.utime(..., ns=...)`, never sleep.

## Acceptance criteria
- [ ] RED first: new tests fail on `main` (failure lines in the log).
- [ ] Fingerprint changes on: new input file, deleted input file, size change, mtime change.
- [ ] Fingerprint unchanged when only `output.rch` / `output.std` / `watout.dat` change.
- [ ] `resume=True` after editing a file in a scenario's `txinout_dir` → ValueError naming
      the scenario; `resume=False` runs it again.
- [ ] Old `.signature.json` without `scenario_inputs` → resume works, INFO line logged.
- [ ] `python -m pytest tests/ -q`: 0 failed (record counts). `git diff --check main...HEAD`
      exits 0.

## Report format
`agm send t81 --type "BÁO CÁO" --task par-2 "see .agents/log/PAR-2.md"` (1-3 lines), then stop.

## Docs step (Architect, 2026-11-24, after review PAR-2-2 PASS and rebase onto main 10203f2)

Docs Updater: `gemini-4-hydrogen-medium` (agy, edits only); a short Flash session commits
(`par-2: docs: ...`). Describe only behaviour present in the code. Edit only:
- `CHANGELOG.md` `[Unreleased]` → `### Changed` (keep the PAR-1 entry): `resume=True` also raises when
  an input file of a scenario's base TxtInOut was added, removed, resized or re-written (file
  stats, not contents; outputs ignored); results written by 0.2.6 still resume (one INFO line);
  an unreadable base does not abort the batch. New module `scenarios/signature.py`.
- `README.md` / `README_VI.md`: the `resume=True` table row (~line 566 / 543): add "or a scenario's
  TxtInOut input files changed" (Vietnamese equivalent).
- `ARCHITECTURE.md` §3.7 (Vietnamese): the signature line (~418) mentions the per-scenario
  TxtInOut fingerprint (`scenario_inputs`).
- `AGENTS.md` quick-orientation tree: add `scenarios/signature.py`. Do not touch test counts.
- `.agents/log/PAR-2.md`: append one docs entry.
