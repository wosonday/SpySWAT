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

## 2026-11-23 — full suite + handoff

```
$ python -m pytest tests/ -q
430 passed, 11 skipped, 5 warnings, 24 subtests passed in 276.96s (0:04:36)
```

`git diff --check main...HEAD` → exit 0 (no output).
`git diff --stat main...HEAD`:

```
.agents/log/PAR-2.md                      |  77 +++++++++++++++++++
.agents/tasks/PAR-2.md                    |  67 ++++++++++++++++
spyswat/swat_calib/scenarios/batch.py     |  14 ++++
spyswat/swat_calib/scenarios/signature.py |  37 +++++++++
tests/test_scenario_signature.py          | 124 ++++++++++++++++++++++++++++++
5 files changed, 319 insertions(+)
```

Acceptance criteria (PAR-2 §Acceptance):
- [x] RED first: failure lines above (`ModuleNotFoundError`, `DID NOT RAISE ValueError` ×2).
- [x] Fingerprint changes on new / deleted / resized / re-written input file.
- [x] Fingerprint unchanged for `output.rch` / `output.std` / `watout.dat` / manifest.
- [x] `resume=True` after editing a scenario `txinout_dir` (and the project TxtInOut for
      `txinout_dir=None`) → ValueError naming the scenario; `resume=False` runs it again.
- [x] 0.2.6 `.signature.json` without `scenario_inputs` → resume works, one INFO line.
- [x] Full suite 0 failed; `git diff --check main...HEAD` clean.

Notes for the Reviewer / Docs Updater (`docs_impact: yes`, but `README*` / `docs/**` are
outside this task's scope):
- `README.md` line ~553 (`resume = True, # skip jobs ...`) and ~566 (table row
  "`resume=True` | Skip finished jobs; raises if outputs, metrics, observations or a
  definition changed") should mention edited scenario TxtInOut *inputs*.
- `batch.py` job loop, `_prepare_dispatch`, `_extract_dispatch` and
  `workingFolder_manager.py` are untouched, so PAR-1's dispatch-loop rewrite should not
  conflict; the two added hunks in `new_sig` / `merged` are adjacent to
  `"scenarios"` / `"param_sets"` lines only.

Files changed: `.agents/log/PAR-2.md` (this entry) only.

## 2026-11-23 — report delivery

`agm send t81 --type "BÁO CÁO" --task par-2 "..."` was refused twice with
`hc status_mismatch: t81 is working, not idle` (nothing delivered). The documented fallback
`hc send t81 "<pointer>"` could not run in this non-interactive session (permission
rejected), and `--force` is forbidden, so the branch is ready but the Manager has not been
notified. Branch `feat/PAR-2`, HEAD after this commit, working tree clean.

Files changed: `.agents/log/PAR-2.md` (this entry) only.

## 2026-11-23 — rework round 1 (`.agents/reviews/PAR-2-1.md`, FAIL, 1 Major)

Finding addressed: **Major 1 — a missing scenario base aborted the whole batch**.
`txinout_fingerprint()` raised `FileNotFoundError` while `batch.py` built `new_sig`, before
any job ran; `main` only failed that scenario's own jobs (`setup of <base> failed: ...`).

RED first (two new tests in `tests/test_scenario_signature.py`, implementation unchanged):

```
$ python -m pytest ".../test_fingerprint_of_a_missing_directory_is_a_stable_sentinel" ".../test_missing_scenario_base_fails_only_its_own_jobs" -q
FF                                                                       [100%]
...
    def _input_stats(directory) -> list:
        folder = Path(directory)
>       with os.scandir(folder) as entries:
E       FileNotFoundError: [WinError 3] The system cannot find the path specified: '...\\gone'
spyswat\swat_calib\scenarios\signature.py:19: FileNotFoundError
...
spyswat\swat_calib\scenarios\batch.py:378: in run
    "scenario_inputs": {name: txinout_fingerprint(directory)
E       FileNotFoundError: [WinError 3] The system cannot find the path specified: '...\\GONE'
tests\test_scenario_signature.py::test_fingerprint_of_a_missing_directory_is_a_stable_sentinel FAILED
tests\test_scenario_signature.py::test_missing_scenario_base_fails_only_its_own_jobs FAILED
2 failed in 4.20s
```

GREEN: `spyswat/swat_calib/scenarios/signature.py` only — `txinout_fingerprint` wraps
`_input_stats` in `try/except OSError` and returns the stable sentinel
`unreadable:<ExceptionName>` (`UNREADABLE_PREFIX`); never raises, so the batch keeps going
and the broken base fails only its own jobs. `batch.py` untouched in this round.

New tests:
- `test_fingerprint_of_a_missing_directory_is_a_stable_sentinel` — `unreadable:FileNotFoundError`,
  identical across calls and for `str` / `Path`.
- `test_missing_scenario_base_fails_only_its_own_jobs` — one good + one deleted base: good
  job `ok`, bad job `failed` with `setup of` in `error`, `out.failed == ['gone__p_none']`.

```
$ python -m pytest tests/test_scenario_signature.py -q
9 passed in 62.62s (0:01:02)

$ python -m pytest tests/ -q
432 passed, 11 skipped, 5 warnings, 24 subtests passed in 194.41s (0:03:14)
```

(430 before this round + the 2 new tests.) `git diff --check main...HEAD` → exit 0.
`.agents/reviews/PAR-2-1.md` committed unchanged with this fix.

Files changed: `spyswat/swat_calib/scenarios/signature.py`, `tests/test_scenario_signature.py`,
`.agents/log/PAR-2.md`, `.agents/reviews/PAR-2-1.md` (reviewer file, unchanged).
