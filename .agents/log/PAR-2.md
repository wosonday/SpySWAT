# PAR-2 — work log (append-only)

Task: `resume=True` must notice edited scenario TxtInOut inputs (finding F4).
Branch `feat/PAR-2`, worker-mid, `opencode-go/deepseek-v4.1-flash`, skill: tdd.

## 2026-11-23 — task brief

- Read `AGENTS.md`, `.agents/tasks/PAR-2.md` and the touched code
  (`spyswat/swat_calib/scenarios/batch.py`, `core/workingFolder_manager.py`,
  `tests/test_scenarios.py`).
- Committed the task brief unchanged so the work starts from a clean tree.
- Plan (one vertical slice per cycle, RED before GREEN):
  1. `signature.py::txinout_fingerprint` — changes on add/remove/size/mtime, ignores
     `output.*` / `watout.dat` / manifest.
  2. `batch.py` `new_sig["scenario_inputs"]` + `_signature_diff` reporting
     `scenario 'X' inputs changed` only for names in both maps.
  3. 0.2.6 signature without `scenario_inputs` → resume works + one INFO line.
  4. `merged` keeps definitions of scenario names absent from the current call.
- No files changed in this commit besides this log and the task brief.

Files changed: `.agents/tasks/PAR-2.md` (new, as given), `.agents/log/PAR-2.md` (new).
Checks: none yet (no code change).
