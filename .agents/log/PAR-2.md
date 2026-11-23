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

## 2026-11-23 — TDD cycle 1: `signature.py::txinout_fingerprint`

RED (before the module existed):

```
tests\test_scenario_signature.py:17: ModuleNotFoundError:
No module named 'spyswat.swat_calib.scenarios.signature'
1 failed
```

GREEN: `spyswat/swat_calib/scenarios/signature.py` — `txinout_fingerprint(directory)` hashes
the sorted `(name, size, mtime_ns)` rows of the regular files directly in the folder.
Outputs are skipped with the *same* callable used by the worker copies
(`workingFolder_manager._OUTPUT_IGNORE(folder, names)`, patterns `output.*`,
`watout.dat`, manifest) plus `MANIFEST_NAME`; `workingFolder_manager.py` untouched. Stats
only, no file contents.

`python -m pytest tests/test_scenario_signature.py -q` → `3 passed`.

## 2026-11-23 — TDD cycle 2: `batch.py` resume check on scenario inputs

RED (tests written first, implementation absent):

```
>       with pytest.raises(ValueError, match="scenario 'luc' inputs changed"):
E       Failed: DID NOT RAISE ValueError
...
>       with pytest.raises(ValueError, match="scenario 'base' inputs changed"):
E       Failed: DID NOT RAISE ValueError
2 failed, 3 passed
```

GREEN, only the four spots the task allows:
- import block: `from .signature import txinout_fingerprint`.
- `_signature_diff`: adds `scenario 'X' inputs changed` for names present in **both**
  `scenario_inputs` maps; when the stored signature has no `scenario_inputs` (0.2.6) it
  reports nothing and logs one INFO line
  `cannot verify that scenario TxtInOut inputs are unchanged (results written by an older
  version)`.
- `new_sig`: new key `scenario_inputs = {scenario name: fingerprint of its base TxtInOut}`
  (`txinout_dir` or the project TxtInOut), one fingerprint per distinct name.
- `merged`: `scenario_inputs` merged like `scenarios`, so names absent from the current
  call keep their fingerprint (a later edit is still caught).
Nothing in the job loop changed.

`python -m pytest tests/test_scenario_signature.py -q` → `7 passed in 47.79s`
(covers: add/remove/resize/re-write changes; `output.rch` / `output.std` / `watout.dat` /
manifest ignored; ValueError naming the scenario for `txinout_dir` and for the project
TxtInOut; `resume=False` runs again; 0.2.6 signature resumes with the INFO line; removed
names keep their fingerprint).

Files changed: `spyswat/swat_calib/scenarios/signature.py` (new),
`spyswat/swat_calib/scenarios/batch.py`, `tests/test_scenario_signature.py` (new),
`.agents/log/PAR-2.md`.
