"""Tests for the public entry points: SWATProject, package version and the CLI."""
import pytest

import spyswat
import spyswat.__main__ as cli
from spyswat import SWATProject


HRU_HEADER = (
    " .hru file Watershed HRU:{hru} Subbasin:{sub} HRU:{hru} Luse:AGRL "
    "Soil: Ao90-2-3c-4284 Slope: 10-20 9/30/2025 12:00:00 AM ArcSWAT 2012.10_4.21\n"
)


def _cio_lines():
    lines = [
        "Master Watershed File: file.cio",
        "Project Description:",
        "General Input/Output section (file.cio):",
        "9/30/2025 12:00:00 AM ARCGIS-SWAT interface AV",
        "",
        "General Information/Watershed Configuration:",
        "fig.fig",
        f"{22:16d}    | NBYR : Number of years simulated",
        f"{1998:16d}    | IYR : Beginning year of simulation",
        f"{1:16d}    | IDAF : Beginning julian day of simulation",
        f"{365:16d}    | IDAL : Ending julian day of simulation",
    ]
    while len(lines) < 57:
        lines.append(f"{0:16d}    | FILLER{len(lines)} : unused in tests")
    lines.append("Output Information:")
    lines.append(f"{1:16d}    | IPRINT: print code (month, day, year)")
    lines.append(f"{2:16d}    | NYSKIP: number of years to skip output printing/summarization")
    while len(lines) < 70:
        lines.append(f"{0:16d}    | FILLER{len(lines)} : unused in tests")
    return lines


@pytest.fixture
def txinout(tmp_path):
    d = tmp_path / "TxtInOut"
    d.mkdir()
    for sub, hru in ((1, 1), (1, 2), (2, 3)):
        (d / f"{sub:05d}{hru:04d}.hru").write_text(
            HRU_HEADER.format(hru=hru, sub=sub), encoding="utf-8")
    (d / "file.cio").write_text("\r\n".join(_cio_lines()) + "\r\n", encoding="utf-8")
    return d


@pytest.fixture
def project(txinout, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Logger.init(log_dir="logs") is relative to the CWD
    exe = tmp_path / "swat.exe"
    exe.write_text("")
    return SWATProject(txinout, tmp_path / "workers", exe)


def test_constructs_without_param_file(project):
    assert project.param_file is None
    assert project.txinout.number_hru == 3
    assert project.txinout.number_sub == 2
    repr(project)
    project.info()


def test_param_functions_need_param_file(project):
    with pytest.raises(RuntimeError, match="param_file"):
        project.HRU
    with pytest.raises(RuntimeError, match="param_file"):
        project.read_params_values(["CN2"])


def test_worker_works_without_param_file(project):
    project.WorkingFolder.setup(overwrite=True)
    w = project.worker(1)
    assert w.param_file is None


@pytest.mark.parametrize("value, expected", [(1, 1), (4, 4), ("4", 4), (" 3 ", 3)])
def test_n_parallel_accepted(txinout, tmp_path, monkeypatch, value, expected):
    monkeypatch.chdir(tmp_path)
    p = SWATProject(txinout, tmp_path / "w", tmp_path / "swat.exe", n_parallel=value)
    assert p.WorkingFolder.n_parallel == expected
    assert isinstance(p.WorkingFolder.n_parallel, int)


@pytest.mark.parametrize("value", [0, -2, "abc", "", 2.5, None, True, [2]])
def test_n_parallel_rejected(txinout, tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        SWATProject(txinout, tmp_path / "w", tmp_path / "swat.exe", n_parallel=value)


def test_run_invalidates_output_cache(project, monkeypatch):
    calls = []
    monkeypatch.setattr(project.swat_exe, "run", lambda path, *a, **k: calls.append("run") or "done")

    class StubOutput:
        def invalidate(self):
            calls.append("invalidate")

    monkeypatch.setattr(project, "_output_manager", StubOutput())
    assert project.run() == "done"
    assert calls == ["run", "invalidate"]


def test_version_is_string():
    assert isinstance(spyswat.__version__, str) and spyswat.__version__


def test_cli_parses_n_parallel_as_int_and_optional_args():
    args = cli.build_parser().parse_args(
        ["--txinout", "t", "--workingF", "w", "--exe", "e", "--n_parallel", "4"])
    assert args.n_parallel == 4 and isinstance(args.n_parallel, int)
    assert args.params is None and args.observed is None and args.reach == 1
    assert cli.build_parser().parse_args(
        ["--txinout", "t", "--workingF", "w", "--exe", "e"]).n_parallel == 1


def test_cli_main_runs_project_once(monkeypatch):
    created, ran = [], []

    class FakeProject:
        def __init__(self, *args):
            created.append(args)

        def run(self):
            ran.append(True)

    monkeypatch.setattr(spyswat, "SWATProject", FakeProject)
    cli.main(["--txinout", "t", "--workingF", "w", "--exe", "e", "--n_parallel", "4"])
    assert created == [("t", "w", "e", None, 4)]
    assert ran == [True]
