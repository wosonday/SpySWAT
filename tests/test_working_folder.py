"""
Tests for WorkingFolderManager / worker jobs (no SWAT executable needed: fake runners).

The helpers defined here (synthetic TxtInOut, fake runners, parameter file) are
reused by tests/test_run.py and tests/test_calib_manager.py.
"""
import multiprocessing
import os
import stat
import sys
from pathlib import Path

import pytest

from spyswat.swat_calib.core import TxInOut
from spyswat.swat_calib.core import workingFolder_manager as wfm
from spyswat.swat_calib.core.workingFolder_manager import (
    WorkerResult, WorkingFolderManager, _worker_job, MANIFEST_NAME,
)

HRU_HEADER = ("Watershed HRU:{h} Subbasin:{s} HRU:{h} Luse:AGRL Soil: Ao90-2-3c-4284 "
              "Slope: 10-20 9/30/2025 12:00:00 AM ArcSWAT 2012.10_4.21")
HRUS = [("000010001", 1, 1), ("000010002", 1, 2), ("000020001", 2, 3)]

PARAM_TXT = """\
!Parameter(SWAT) AtLine StartPosition EndPosition RoundUp AbsoluteMin AbsoluteMax
HRU_FR.hru        2   1   16   7    0.0     1.0
CN2.mgt          11   1   16   2   35.0    98.0
ALPHA_BF.gw       5   1   16   4    0.0     1.0
"""

FAIL_CN2 = 77.0
NOOP_CN2 = 66.0


def _line(value: str, label: str) -> str:
    return f"{value:>16s}    | {label}\n"


def build_txinout(root: Path, with_outputs: bool = True) -> Path:
    """Create a small synthetic TxtInOut with 3 HRUs and a 60+ line file.cio."""
    d = root / "TxtInOut"
    d.mkdir(parents=True)
    for stem, sub, hru in HRUS:
        hdr = HRU_HEADER.format(h=hru, s=sub)
        (d / f"{stem}.hru").write_text(
            f".hru file {hdr}\n" + _line("0.0594563", "HRU_FR") + _line("1.0", "x"))
        gw = [f".gw file {hdr}\n", _line("1000.0000", "SHALLST"), _line("2000.0000", "DEEPST"),
              _line("436.9050", "GW_DELAY"), _line("0.5060", "ALPHA_BF"), _line("3744.0", "GWQMN")]
        (d / f"{stem}.gw").write_text("".join(gw))
        mgt = [f".mgt file {hdr}\n"] + [f"filler line {i}\n" for i in range(2, 9)]
        mgt += ["General Management Parameters\n", _line("0.20", "BIOMIX"),
                _line("35.00", "CN2"), _line("1.00", "USLE_P"), "tail\n"]
        (d / f"{stem}.mgt").write_text("".join(mgt))
    cio = [f"cio line {i}\n" for i in range(70)]
    cio[7] = f"{'':12s}{3:4d}    | NBYR\n"
    cio[8] = f"{'':12s}{2000:4d}    | IYR\n"
    cio[58] = f"{'':12s}{1:4d}    | IPRINT\n"
    cio[59] = f"{'':12s}{0:4d}    | NYSKIP\n"
    (d / "file.cio").write_text("".join(cio))
    if with_outputs:
        (d / "output.rch").write_text("OLD RCH\n" * 1000)
        (d / "output.std").write_text("old std\n")
        (d / "watout.dat").write_text("old watout\n")
    return d


def build_param_file(root: Path) -> Path:
    p = root / "swatParam.txt"
    p.write_text(PARAM_TXT)
    return p


def read_cn2(worker_dir: str) -> float:
    first = sorted(Path(worker_dir).glob("0*.mgt"))[0]
    return float(first.read_text().splitlines()[10][:16])


def read_gw_alpha(worker_dir: str) -> float:
    first = sorted(Path(worker_dir).glob("0*.gw"))[0]
    return float(first.read_text().splitlines()[4][:16])


def fake_runner(worker_dir: str) -> None:
    """Writes a 10-line output.rch holding CN2; CN2==77 raises, CN2==66 writes nothing."""
    cn2 = read_cn2(worker_dir)
    if cn2 == FAIL_CN2:
        raise RuntimeError("boom")
    if cn2 == NOOP_CN2:
        return
    Path(worker_dir, "output.rch").write_text("\n".join([repr(cn2)] * 10) + "\n")


def snapshot(directory: Path, skip_prefix=("output.", "watout")) -> dict:
    return {p.name: p.read_bytes() for p in Path(directory).iterdir()
            if p.is_file() and not p.name.startswith(skip_prefix)}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = build_txinout(tmp_path)
    param = build_param_file(tmp_path)
    return tmp_path, base, param


def make_wf(env, n=2):
    tmp, base, param = env
    wf = WorkingFolderManager(TxInOut(str(base)), tmp / "work", n_parallel=n, param_path=param)
    wf.setup()
    return wf


REL = {"CN2.mgt": [(0.1, "r")]}
ADD = {"CN2.mgt": [(5.0, "a")]}


# ── setup ─────────────────────────────────────────────────────────────

def test_setup_does_not_copy_outputs(env):
    wf = make_wf(env)
    for d in wf.worker_dirs:
        names = {p.name for p in d.iterdir()}
        assert "file.cio" in names and "000010001.mgt" in names
        assert not any(n.startswith("output.") for n in names)
        assert "watout.dat" not in names


def test_setup_raises_when_worker_dir_cannot_be_removed(env, monkeypatch):
    wf = make_wf(env)
    monkeypatch.setattr(wfm, "_rmtree", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="TxInOut1"):
        wf.setup(overwrite=True)


def test_setup_and_run_parallel_refuse_in_child_process(env, monkeypatch):
    wf = make_wf(env)
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: object())
    with pytest.raises(RuntimeError, match="__main__"):
        wf.setup()
    with pytest.raises(RuntimeError, match="__main__"):
        wf.run_parallel("exe", runner=fake_runner)


# ── no compounding / restore ──────────────────────────────────────────

@pytest.mark.parametrize("params, expected", [(REL, 35.0 * 1.1), (ADD, 40.0)])
def test_three_consecutive_runs_do_not_compound(env, params, expected):
    wf = make_wf(env)
    before = snapshot(env[1])
    for _ in range(3):
        res = wf.run_parallel("exe", param_sets=[params, params],
                              runner=fake_runner, extract=read_cn2)
        assert [r.ok for r in res] == [True, True], [r.error for r in res]
        assert [r.payload for r in res] == pytest.approx([expected, expected])
    assert snapshot(env[1]) == before  # baseline never modified


def test_results_aligned_with_param_sets_and_failures_isolated(env):
    wf = make_wf(env, n=3)
    sets = [{"CN2.mgt": [(50.0, "v")]}, {"CN2.mgt": [(FAIL_CN2, "v")]},
            {"CN2.mgt": [(NOOP_CN2, "v")]}]
    res = wf.run_parallel("exe", param_sets=sets, runner=fake_runner, extract=read_cn2)
    assert len(res) == 3
    assert res[0].ok and res[0].payload == 50.0
    assert not res[1].ok and "boom" in res[1].error
    assert not res[2].ok and "fresh output.rch" in res[2].error
    assert all(isinstance(r, WorkerResult) for r in res)
    assert [Path(r.worker_dir).name for r in res] == ["TxInOut1", "TxInOut2", "TxInOut3"]


def test_dir_without_manifest_is_fully_restored(env):
    wf = make_wf(env)
    w = wf.worker_dirs[0]
    # emulate a dir compounded by the old code: modified .gw/.mgt, no manifest
    for f in w.glob("0*.mgt"):
        f.write_text(f.read_text().replace("35.00", "99.00"))
    for f in w.glob("0*.gw"):
        f.write_text(f.read_text().replace("0.5060", "0.9999"))
    assert not (w / MANIFEST_NAME).exists()
    res = _worker_job(str(w), str(env[1]), "exe", REL, str(env[2]), None,
                      None, read_cn2, fake_runner, None)
    assert res.ok, res.error
    assert res.payload == pytest.approx(38.5)
    assert read_gw_alpha(str(w)) == pytest.approx(0.506)
    for f in w.glob("0*.gw"):
        assert (env[1] / f.name).read_bytes() == f.read_bytes()
    assert (w / MANIFEST_NAME).exists()


def test_restore_over_read_only_files_and_no_outputs_copied(env):
    wf = make_wf(env)
    w = wf.worker_dirs[0]
    for f in list(w.glob("0*")) + [w / "file.cio"]:
        os.chmod(f, stat.S_IREAD)
    res = _worker_job(str(w), str(env[1]), "exe", ADD, str(env[2]), None,
                      None, read_cn2, fake_runner, None)
    assert res.ok, res.error
    assert res.payload == pytest.approx(40.0)
    res = _worker_job(str(w), str(env[1]), "exe", ADD, str(env[2]), None,
                      None, read_cn2, fake_runner, None)
    assert res.payload == pytest.approx(40.0)
    assert not (w / "output.std").exists()
    assert not (w / "watout.dat").exists()
    assert (w / "output.rch").read_text() != "OLD RCH\n" * 1000


def test_overlay_files_are_copied_and_removed_next_time(env):
    wf = make_wf(env)
    w = wf.worker_dirs[0]
    src = env[0] / "cio_alt.txt"
    src.write_text("".join(f"alt {i}\n" for i in range(70)))
    res = _worker_job(str(w), str(env[1]), "exe", None, str(env[2]), {"extra.dat": str(src)},
                      None, None, fake_runner_always, None)
    assert res.ok, res.error
    assert (w / "extra.dat").exists()
    res = _worker_job(str(w), str(env[1]), "exe", None, str(env[2]), None,
                      None, None, fake_runner_always, None)
    assert res.ok, res.error
    assert not (w / "extra.dat").exists()


def fake_runner_always(worker_dir: str) -> None:
    Path(worker_dir, "output.rch").write_text("1\n" * 10)


def test_prepare_runs_before_params_and_failure_is_reported(env):
    wf = make_wf(env)
    w = wf.worker_dirs[0]
    res = _worker_job(str(w), str(env[1]), "exe", None, str(env[2]), None,
                      prepare_raises, None, fake_runner_always, None)
    assert not res.ok and "prep failed" in res.error


def prepare_raises(worker_dir: str) -> None:
    raise ValueError("prep failed")


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX script as fake exe")
def test_timeout_kills_child_and_gives_failed_result(env):
    wf = make_wf(env, n=1)
    exe = env[0] / "sleeper"
    exe.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    exe.chmod(0o755)
    res = wf.run_parallel(str(exe), param_sets=[None], timeout_s=1)
    assert len(res) == 1 and not res[0].ok
    assert "Timeout" in res[0].error
    assert res[0].duration_s < 20


# ── per-job prepare / extract ─────────────────────────────────────────

def prep_marker_a(worker_dir: str) -> None:
    Path(worker_dir, "marker.txt").write_text("A:" + Path(worker_dir).name)


def prep_marker_b(worker_dir: str) -> None:
    Path(worker_dir, "marker.txt").write_text("B:" + Path(worker_dir).name)


def extract_marker(worker_dir: str):
    return Path(worker_dir, "marker.txt").read_text()


def extract_name(worker_dir: str):
    return "job-" + Path(worker_dir).name


def extract_raises(worker_dir: str):
    raise ValueError("extract failed")


def test_per_job_prepare_and_extract_are_index_aligned(env):
    wf = make_wf(env, n=3)
    res = wf.run_parallel("exe", param_sets=[None, None, None], runner=fake_runner_always,
                          prepare=[prep_marker_a, prep_marker_b, None],
                          extract=[extract_marker, extract_name, None])
    assert all(r.ok for r in res), [r.error for r in res]
    assert res[0].payload == "A:TxInOut1"
    assert res[1].payload == "job-TxInOut2"
    assert res[2].payload is None
    assert not (wf.worker_dirs[2] / "marker.txt").exists()
    assert (wf.worker_dirs[1] / "marker.txt").read_text() == "B:TxInOut2"


def test_single_callable_still_applies_to_every_job(env):
    wf = make_wf(env, n=2)
    res = wf.run_parallel("exe", param_sets=[None, None], runner=fake_runner_always,
                          prepare=prep_marker_a, extract=extract_marker)
    assert [r.payload for r in res] == ["A:TxInOut1", "A:TxInOut2"]


def test_wrong_length_prepare_or_extract_raises(env):
    wf = make_wf(env, n=2)
    with pytest.raises(ValueError, match="prepare"):
        wf.run_parallel("exe", param_sets=[None, None], runner=fake_runner_always,
                        prepare=[prep_marker_a])
    with pytest.raises(ValueError, match="extract"):
        wf.run_parallel("exe", param_sets=[None, None], runner=fake_runner_always,
                        extract=(extract_name, extract_name, extract_name))


def test_failing_extract_marks_job_failed(env):
    wf = make_wf(env, n=2)
    res = wf.run_parallel("exe", param_sets=[None, None], runner=fake_runner_always,
                          extract=[extract_raises, extract_name])
    assert not res[0].ok and "extract failed" in res[0].error
    assert res[1].ok and res[1].payload == "job-TxInOut2"


# ── busy probe ────────────────────────────────────────────────────────

def test_busy_probe_fails_only_the_locked_worker(env, monkeypatch):
    import builtins
    wf = make_wf(env, n=2)
    for w in wf.worker_dirs:
        (w / "output.rch").write_text("old\n")
    real_open = builtins.open

    def fake_open(file, mode="r", *a, **k):
        p = Path(str(file))
        if mode == "ab" and p.name == "output.rch" and p.parent.name == "TxInOut1":
            raise PermissionError("locked")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(wfm, "open", fake_open, raising=False)
    calls = []

    def recording_runner(worker_dir: str) -> None:
        calls.append(Path(worker_dir).name)
        fake_runner_always(worker_dir)

    results = [
        _worker_job(str(w), str(env[1]), "exe", None, str(env[2]), None,
                    None, None, recording_runner, None)
        for w in wf.worker_dirs
    ]
    assert not results[0].ok and "still using this folder" in results[0].error
    assert results[1].ok, results[1].error
    assert calls == ["TxInOut2"]
