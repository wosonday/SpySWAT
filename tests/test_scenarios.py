"""
Tests for spyswat.swat_calib.scenarios (no SWAT executable: a fake runner writes a
synthetic daily output.rch whose values depend on the worker's CURRENT input files).

Value model (per reach r, day d):  CN2 * PCP / 100 * r + d * 0.01
where CN2 is read from the first .mgt file and PCP from pcp1.pcp of the worker folder.
"""
import logging
import multiprocessing
import os
import queue
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat import SWATProject
from spyswat.logger import Logger
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.io import SWATParam
from spyswat.swat_calib.scenarios import ParamSet, Scenario, ScenarioBatch
from spyswat.swat_calib.scenarios.batch import WORK_SUBDIR

HRU_HEADER = ("Watershed HRU:{h} Subbasin:{s} HRU:{h} Luse:AGRL Soil: Ao90-2-3c-4284 "
              "Slope: 10-20 9/30/2025 12:00:00 AM ArcSWAT 2012.10_4.21")
HRUS = [("000010001", 1, 1), ("000010002", 1, 2), ("000020001", 2, 3)]
PARAM_TXT = """\
!Parameter(SWAT) AtLine StartPosition EndPosition RoundUp AbsoluteMin AbsoluteMax
HRU_FR.hru        2   1   16   7    0.0     1.0
CN2.mgt          11   1   16   2   35.0    98.0
ALPHA_BF.gw       5   1   16   4    0.0     1.0
"""
RCH_COLS = {"RCH": (6, 11), "MON": (21, 26), "FLOW_OUTcms": (51, 62), "SED_OUTtons": (99, 110)}
REACHES = [1, 2, 3]


# ── synthetic project ────────────────────────────────────────────────

def _line(value: str, label: str) -> str:
    return f"{value:>16s}    | {label}\n"


def build_txinout(root: Path, name="TxtInOut", cn2="35.00", pcp="10.0") -> Path:
    d = root / name
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
                _line(cn2, "CN2"), _line("1.00", "USLE_P"), "tail\n"]
        (d / f"{stem}.mgt").write_text("".join(mgt))
    cio = [f"cio line {i}\n" for i in range(70)]
    for idx, val, label in [(7, 2, "NBYR"), (8, 2000, "IYR"), (9, 1, "IDAF"), (10, 366, "IDAL"),
                            (58, 1, "IPRINT"), (59, 0, "NYSKIP")]:
        cio[idx] = f"{'':12s}{val:4d}    | {label}\n"
    (d / "file.cio").write_text("".join(cio))
    (d / "pcp1.pcp").write_text(f"{pcp}\n")
    return d


def make_weather(root: Path, name: str, pcp: str, extra=False) -> Path:
    d = root / name
    d.mkdir()
    (d / "pcp1.pcp").write_text(f"{pcp}\n")
    if extra:
        (d / "extra1.tmp").write_text("x\n")
    return d


def _rch_line(width=200, **vals) -> str:
    buf = [" "] * width
    buf[0:5] = "REACH"
    for key, v in vals.items():
        a, b = RCH_COLS[key]
        txt = f"{v:{b - a}.3f}" if isinstance(v, float) else f"{v:{b - a}d}"
        buf[a:b] = txt
    return "".join(buf) + "\n"


def read_cn2(wd: str) -> float:
    first = sorted(Path(wd).glob("0*.mgt"))[0]
    return float(first.read_text().splitlines()[10][:16])


def read_pcp(wd: str) -> float:
    p = Path(wd, "pcp1.pcp")
    return float(p.read_text().split()[0]) if p.exists() else 1.0


def expected(cn2, pcp, reach, ndays):
    return cn2 * pcp / 100.0 * reach + np.arange(ndays) * 0.01


def fake_runner(worker_dir: str) -> None:
    cio = Path(worker_dir, "file.cio").read_text().splitlines()
    nbyr, iyr, skip = (int(cio[i][12:16]) for i in (7, 8, 59))
    cn2, pcp = read_cn2(worker_dir), read_pcp(worker_dir)
    extra = Path(worker_dir, "extra1.tmp").exists()
    log = os.environ.get("E5_RUNLOG")
    if log:
        # One trace file per worker folder: worker processes appending to ONE shared
        # file lose lines on Windows (append = seek + write, not atomic across processes).
        # A folder runs one job at a time, so each file has a single writer.
        with open(f"{log}.{Path(worker_dir).name}", "a") as fh:
            fh.write(f"{Path(worker_dir).name}|{cn2}|{pcp}|{int(extra)}|{nbyr}\n")
    if cn2 == 77.0 and pcp > 20 and not os.environ.get("E5_ALLOW_FAIL"):
        raise RuntimeError("injected failure")
    lines = ["header\n"] * 9
    if int(cio[58][12:16]) == 0:      # monthly: 12 months + annual block per year, then avg
        for y in range(iyr + skip, iyr + nbyr):
            for mon in list(range(1, 13)) + [y]:
                for r in REACHES:
                    flow = cn2 * pcp / 100.0 * r + (mon if mon <= 12 else 0) * 0.01
                    lines.append(_rch_line(RCH=r, MON=mon, FLOW_OUTcms=flow,
                                           SED_OUTtons=flow * 2))
        for r in REACHES:
            lines.append(_rch_line(RCH=r, MON=nbyr, FLOW_OUTcms=1.0, SED_OUTtons=1.0))
        Path(worker_dir, "output.rch").write_text("".join(lines))
        return
    dates = pd.date_range(f"{iyr + skip}-01-01", f"{iyr + nbyr - 1}-12-31", freq="D")
    for d, date in enumerate(dates):
        for r in REACHES:
            flow = cn2 * pcp / 100.0 * r + d * 0.01
            lines.append(_rch_line(RCH=r, MON=date.dayofyear, FLOW_OUTcms=flow,
                                   SED_OUTtons=flow * 2))
    Path(worker_dir, "output.rch").write_text("".join(lines))


# CN2 value → sleep duration for the timing runner (long job vs short jobs).
_TIMING_SLEEP = {35.0: 0.6, 40.0: 2.4, 50.0: 0.6, 60.0: 0.6, 70.0: 0.6}


def timing_runner(worker_dir: str) -> None:
    """fake_runner that sleeps by CN2 and records per-job start/end timestamps.

    Timestamps are wall-clock (``time.time()``) and therefore comparable across
    worker processes; the trace line is ``<folder>|<start>|<end>|<cn2>``.
    """
    cn2 = read_cn2(worker_dir)
    start = time.time()
    time.sleep(_TIMING_SLEEP.get(cn2, 0.6))
    fake_runner(worker_dir)
    end = time.time()
    log = os.environ.get("E5_TIMING")
    if log:
        with open(f"{log}.{Path(worker_dir).name}", "a") as fh:
            fh.write(f"{Path(worker_dir).name}|{start:.6f}|{end:.6f}|{cn2:.1f}\n")


def marker_runner(worker_dir: str) -> None:
    """fake_runner that records which base marker files the worker folder holds.

    Each base TxtInOut carries a unique ``base_<name>.marker`` file; after a slot
    is reseeded for a new base, the previous base's marker must be gone.
    """
    wd = Path(worker_dir)
    a = int((wd / "base_A.marker").exists())
    b = int((wd / "base_B.marker").exists())
    fake_runner(worker_dir)
    log = os.environ.get("E5_MARKER")
    if log:
        with open(f"{log}.{wd.name}", "a") as fh:
            fh.write(f"{wd.name}|A={a}|B={b}\n")


# CN2 → sleep for completion_runner: a later-plan job finishes before an earlier one.
_COMPLETION_SLEEPS = {35.0: 2.0, 40.0: 0.5}


def completion_runner(worker_dir: str) -> None:
    """fake_runner with per-CN2 sleeps so a later-plan job finishes before an earlier one."""
    cn2 = read_cn2(worker_dir)
    time.sleep(_COMPLETION_SLEEPS.get(cn2, 0.5))
    fake_runner(worker_dir)


def leftover_runner(worker_dir: str) -> None:
    """The failing job (CN2=77) leaves ``leftover.tmp``; the next job must not see it."""
    wd = Path(worker_dir)
    leftover = wd / "leftover.tmp"
    if read_cn2(worker_dir) == 77.0:
        leftover.write_text("junk")
        raise RuntimeError("injected failure")
    if leftover.exists():
        raise RuntimeError("leftover leaked into the next job")
    fake_runner(worker_dir)


# open handles (worker process only) keep output.rch locked so a reseed cannot remove the slot.
_LOCKED_HANDLES = []


def lock_runner(worker_dir: str) -> None:
    """fake_runner that keeps output.rch open so a later reseed cannot remove the slot."""
    fake_runner(worker_dir)
    _LOCKED_HANDLES.append(open(Path(worker_dir) / "output.rch", "rb"))


def trace_lines(log: Path) -> list:
    """Every fake_runner call traced under ``log`` (all worker files, in folder order)."""
    return [ln for f in sorted(log.parent.glob(log.name + ".*"))
            for ln in f.read_text().splitlines()]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = build_txinout(tmp_path)
    param = tmp_path / "swatParam.txt"
    param.write_text(PARAM_TXT)
    exe = tmp_path / "swat.exe"
    exe.write_text("")
    return tmp_path, base, param, exe


def make_project(env, n=2):
    tmp, base, param, exe = env
    return SWATProject(base, tmp / "workers", exe, param, n_parallel=n)


PARAMS = [ParamSet("p_none"),
          ParamSet("p_v60", {"CN2.mgt": [(60, "v")]}),
          ParamSet("p_rel", {"CN2.mgt": [(0.1, "r")]})]
CN2_OF = {"p_none": 35.0, "p_v60": 60.0, "p_rel": 38.5}
OUTS = {"FLOW_OUTcms": [1, 2, 3]}


# ── model ─────────────────────────────────────────────────────────────

def test_scenario_validation(tmp_path):
    with pytest.raises(ValueError):
        Scenario("")
    with pytest.raises(ValueError):
        Scenario("a/b")
    with pytest.raises(FileNotFoundError):
        Scenario("x", txinout_dir=tmp_path / "nope")
    with pytest.raises(ValueError):
        Scenario("x", cio={"BOGUS": 1})
    with pytest.raises(ValueError):
        Scenario("x", cio={"NBYR": 1.5})
    with pytest.raises(ValueError):
        ParamSet("p", {"CN2": [(1, "v")]})
    assert ParamSet.from_dict("p", {"CN2.mgt": 60}).updates == {"CN2.mgt": [(60.0, "v")]}


def test_duplicate_names_rejected(env):
    b = ScenarioBatch(make_project(env), env[0] / "res")
    with pytest.raises(ValueError, match="Duplicate"):
        b.run([Scenario("a"), Scenario("a")], PARAMS, outputs=OUTS, runner=fake_runner)


def test_from_dataframe_matches_update_by_df(env, tmp_path):
    df = pd.DataFrame({
        "PARAM": ["CN2.mgt", "CN2.mgt", "ALPHA_BF.gw", None, "CN2.mgt"],
        "method": ["v", "r", "v", "v", "a"],
        "MIN": [60.0, 0.1, 0.3, 9.0, 2.0],
        "SUBBASIN": ["All", "1,2", None, "All", "2"],
    })
    ps = ParamSet.from_dataframe(df, "p", param="PARAM", method="method", value="MIN",
                                 sub="SUBBASIN")
    assert ps.updates == {"CN2.mgt": [(60.0, "v"), (0.1, "r", [1, 2]), (2.0, "a", [2])],
                          "ALPHA_BF.gw": [(0.3, "v")]}
    with pytest.raises(ValueError, match="extension"):
        ParamSet.from_dataframe(pd.DataFrame({"param": ["CN2"], "method": ["v"],
                                              "value": [1.0]}), "q")

    _, base, param, _ = env
    import shutil
    a, b = tmp_path / "A", tmp_path / "B"
    shutil.copytree(base, a)
    shutil.copytree(base, b)
    sp = SWATParam(param)
    HRUManager(TxInOut(str(a)), sp).update_by_df(
        df, param_name="PARAM", method="method", value="MIN", sub="SUBBASIN")
    HRUManager(TxInOut(str(b)), sp).update_params(ps.updates)
    for f in sorted(a.iterdir()):
        assert f.read_bytes() == (b / f.name).read_bytes(), f.name
    assert (a / "000010001.mgt").read_bytes() != (base / "000010001.mgt").read_bytes()


# ── runs ──────────────────────────────────────────────────────────────

def test_full_product_values_and_no_compounding(env, tmp_path):
    wet = make_weather(tmp_path, "wet", "30.0")
    scen = [Scenario("base"), Scenario("wet", weather_dir=wet)]
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        scen, PARAMS, outputs=OUTS, runner=fake_runner)
    assert len(out.summary) == 6 and set(out.summary["status"]) == {"ok"}
    assert len(list((res_dir / "series").glob("*.csv"))) == 6
    assert len(pd.read_csv(res_dir / "summary.csv")) == 6
    for r in out.results:
        df = pd.read_csv(r.series_path, index_col="date", parse_dates=True)
        pcp = 30.0 if r.scenario == "wet" else 10.0
        assert len(df) == 731 and df.index[0] == pd.Timestamp("2000-01-01")
        assert df.index[-1] == pd.Timestamp("2001-12-31")
        for reach in REACHES:
            np.testing.assert_allclose(df[f"FLOW_OUTcms@{reach}"],
                                       expected(CN2_OF[r.param_set], pcp, reach, 731),
                                       atol=2e-3)
    wide = out.series("FLOW_OUTcms")
    assert list(wide.columns.names) == ["scenario", "param_set", "reach"]
    assert wide.shape == (731, 18)
    # scenario effect and parameter effect are both visible
    assert wide[("wet", "p_none", 1)].iloc[100] > wide[("base", "p_none", 1)].iloc[100]
    assert wide[("base", "p_v60", 1)].iloc[100] > wide[("base", "p_none", 1)].iloc[100]
    flat = out.to_csv("FLOW_OUTcms", tmp_path / "flow.csv")
    assert "base|p_rel|3" in pd.read_csv(flat, index_col="date").columns


def test_pairs_and_unknown_names(env, tmp_path, monkeypatch):
    log = tmp_path / "runs.log"
    monkeypatch.setenv("E5_RUNLOG", str(log))
    scen = [Scenario("base"), Scenario("luc", txinout_dir=build_txinout(
        tmp_path, "LUC", cn2="50.00"))]
    batch = ScenarioBatch(make_project(env), tmp_path / "res")
    with pytest.raises(ValueError, match="Unknown pair"):
        batch.run(scen, PARAMS, pairs=[("base", "p_none"), ("nope", "p_v60")],
                  outputs=OUTS, runner=fake_runner)
    assert not trace_lines(log)
    out = batch.run(scen, PARAMS, pairs=[("luc", "p_rel"), ("base", "p_v60")],
                    outputs=OUTS, runner=fake_runner)
    assert [r.job_id for r in out.results] == ["luc__p_rel", "base__p_v60"]
    assert len(trace_lines(log)) == 2
    wide = out.series("FLOW_OUTcms")
    np.testing.assert_allclose(wide[("luc", "p_rel", 2)], expected(55.0, 10.0, 2, 731), atol=2e-3)
    np.testing.assert_allclose(wide[("base", "p_v60", 2)], expected(60.0, 10.0, 2, 731),
                               atol=2e-3)


def test_failure_isolation_and_resume(env, tmp_path, monkeypatch):
    log = tmp_path / "runs.log"
    monkeypatch.setenv("E5_RUNLOG", str(log))
    wet = make_weather(tmp_path, "wet", "30.0")
    scen = [Scenario("base"), Scenario("wet", weather_dir=wet)]
    params = PARAMS + [ParamSet("p_bad", {"CN2.mgt": [(77, "v")]})]
    res_dir = tmp_path / "res"
    batch = ScenarioBatch(make_project(env), res_dir)
    out = batch.run(scen, params, outputs=OUTS, runner=fake_runner)
    assert [r.status for r in out.results].count("ok") == 7
    assert [r.job_id for r in out.failed] == ["wet__p_bad"]
    assert "injected failure" in out.failed[0].error
    assert not (res_dir / "series" / "wet__p_bad.csv").exists()
    assert len(list((res_dir / "series").glob("*.csv"))) == 7
    assert len(trace_lines(log)) == 8

    monkeypatch.setenv("E5_ALLOW_FAIL", "1")
    out2 = batch.run(scen, params, outputs=OUTS, runner=fake_runner)
    assert len(trace_lines(log)) == 9          # only the failed job re-ran
    assert [r.status for r in out2.results].count("skipped") == 7
    assert out2.results[-1].status == "ok" and not out2.failed
    assert (res_dir / "series" / "wet__p_bad.csv").exists()
    assert set(pd.read_csv(res_dir / "summary.csv")["status"]) == {"ok"}
    assert out2.series("FLOW_OUTcms").shape[1] == 24


def test_weather_overlay_gone_for_next_job_and_cio_override(env, tmp_path, monkeypatch):
    log = tmp_path / "runs.log"
    monkeypatch.setenv("E5_RUNLOG", str(log))
    wet = make_weather(tmp_path, "wet", "30.0", extra=True)
    short = Scenario("short", cio={"NBYR": 1, "IYR": 2001})
    scen = [Scenario("wet", weather_dir=wet), short, Scenario("base")]
    out = ScenarioBatch(make_project(env, n=1), tmp_path / "res").run(
        scen, [ParamSet("p_none")], outputs=OUTS, runner=fake_runner)   # one folder, in order
    rows = [ln.split("|") for ln in trace_lines(log)]
    assert [r[0] for r in rows] == ["TxInOut1"] * 3
    assert [(r[2], r[3], r[4]) for r in rows] == [("30.0", "1", "2"), ("10.0", "0", "1"),
                                                  ("10.0", "0", "2")]
    wide = out.series("FLOW_OUTcms")
    assert wide[("short", "p_none", 1)].dropna().index.min() == pd.Timestamp("2001-01-01")
    assert wide[("short", "p_none", 1)].count() == 365
    assert wide[("base", "p_none", 1)].count() == 731
    assert wide[("base", "p_none", 1)].index.min() == pd.Timestamp("2000-01-01")


def test_reach_labels_metrics_and_two_variables(env, tmp_path):
    obs_idx = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    obs = pd.Series(expected(35.0, 10.0, 3, 731), index=obs_idx)
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        [Scenario("base")], PARAMS[:2],
        outputs={"FLOW_OUTcms": [3, 1], "SED_OUTtons": [2]},
        observed={("FLOW_OUTcms", 3): obs}, metrics=("nse", "pbias"), runner=fake_runner)
    df = pd.read_csv(res_dir / "series" / "base__p_none.csv", index_col="date")
    assert list(df.columns) == ["FLOW_OUTcms@3", "FLOW_OUTcms@1", "SED_OUTtons@2"]
    np.testing.assert_allclose(df["FLOW_OUTcms@3"], expected(35.0, 10.0, 3, 731), atol=2e-3)
    np.testing.assert_allclose(df["FLOW_OUTcms@1"], expected(35.0, 10.0, 1, 731), atol=2e-3)
    np.testing.assert_allclose(df["SED_OUTtons@2"], 2 * expected(35.0, 10.0, 2, 731), atol=4e-3)
    m = pd.read_csv(res_dir / "metrics.csv")
    assert list(m.columns) == ["job_id", "scenario", "param_set", "variable", "reach",
                               "metric", "value"]
    assert len(m) == 4 and set(m["metric"]) == {"nse", "pbias"} and set(m["reach"]) == {3}
    best = m[(m.job_id == "base__p_none") & (m.metric == "nse")]["value"].iloc[0]
    worse = m[(m.job_id == "base__p_v60") & (m.metric == "nse")]["value"].iloc[0]
    assert best > 0.99 and worse < best
    assert len(out.metrics) == 4


def test_mixed_historical_and_future_batch(env, tmp_path, monkeypatch):
    obs = pd.Series(expected(35.0, 10.0, 1, 731),
                    index=pd.date_range("2000-01-01", periods=731, freq="D"))
    wet = make_weather(tmp_path, "wet", "30.0")
    scen = [Scenario("h1"), Scenario("h2", weather_dir=wet),
            Scenario("future", weather_dir=wet, evaluate=False,
                     cio={"IPRINT": 0, "IYR": 2030, "NBYR": 2}),
            Scenario("late", cio={"IYR": 2050})]            # evaluated, but no overlap
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        scen, PARAMS[:1], outputs=OUTS, observed={("FLOW_OUTcms", 1): obs},
        metrics=("nse", "pbias"), runner=fake_runner)
    assert not out.failed
    m = pd.read_csv(res_dir / "metrics.csv")
    assert set(m["scenario"]) == {"h1", "h2"} and len(m) == 4
    assert set(out.metrics["scenario"]) == {"h1", "h2"}
    s = pd.read_csv(res_dir / "summary.csv").set_index("scenario")
    assert list(s["status"]) == ["ok"] * 4
    assert list(s["evaluated"]) == [True, True, False, False]
    assert s.loc["future", "eval_note"] == "evaluate=False"
    assert s.loc["late", "eval_note"] == "no overlap with observations"
    assert pd.isna(s.loc["h1", "eval_note"])
    fut = pd.read_csv(res_dir / "series" / "future__p_none.csv", index_col="date",
                      parse_dates=True)
    assert len(fut) == 24 and fut.index[0] == pd.Timestamp("2030-01-01")
    assert (res_dir / "series" / "late__p_none.csv").exists()
    assert [r.evaluated for r in out.results] == [True, True, False, False]
    # resume keeps the flags
    out2 = ScenarioBatch(make_project(env), res_dir).run(
        scen, PARAMS[:1], outputs=OUTS, observed={("FLOW_OUTcms", 1): obs},
        metrics=("nse", "pbias"), runner=fake_runner)
    assert [r.status for r in out2.results] == ["skipped"] * 4
    assert [r.evaluated for r in out2.results] == [True, True, False, False]


def test_evaluate_flag_is_part_of_resume_signature(env, tmp_path):
    res_dir = tmp_path / "res"
    batch = ScenarioBatch(make_project(env), res_dir)
    batch.run([Scenario("base")], PARAMS[:1], outputs=OUTS, runner=fake_runner)
    with pytest.raises(ValueError, match="base"):
        batch.run([Scenario("base", evaluate=False)], PARAMS[:1], outputs=OUTS,
                  runner=fake_runner)


def test_names_with_double_underscore_rejected():
    with pytest.raises(ValueError, match="__"):
        Scenario("a__x")
    with pytest.raises(ValueError, match="__"):
        ParamSet("x__y")


def test_observation_step_mismatch_fails_before_any_run(env, tmp_path, monkeypatch):
    log = tmp_path / "runs.log"
    monkeypatch.setenv("E5_RUNLOG", str(log))
    obs = pd.Series(np.arange(731.0), index=pd.date_range("2000-01-01", periods=731, freq="D"))
    scen = [Scenario("base"), Scenario("monthly", cio={"IPRINT": 0})]
    with pytest.raises(ValueError, match="monthly"):
        ScenarioBatch(make_project(env), tmp_path / "res").run(
            scen, PARAMS[:1], outputs=OUTS, observed={("FLOW_OUTcms", 1): obs},
            runner=fake_runner)
    assert not trace_lines(log)


def test_resume_with_changed_outputs_or_params_raises(env, tmp_path):
    res_dir = tmp_path / "res"
    batch = ScenarioBatch(make_project(env), res_dir)
    batch.run([Scenario("base")], PARAMS[:2], outputs=OUTS, runner=fake_runner)
    with pytest.raises(ValueError, match="new results_dir"):
        batch.run([Scenario("base")], PARAMS[:2], outputs={"FLOW_OUTcms": [1, 2]},
                  runner=fake_runner)
    changed = [PARAMS[0], ParamSet("p_v60", {"CN2.mgt": [(61, "v")]})]
    with pytest.raises(ValueError, match="p_v60"):
        batch.run([Scenario("base")], changed, outputs=OUTS, runner=fake_runner)
    # a new name is fine, and resume=False accepts the change
    out = batch.run([Scenario("base")], PARAMS[:2] + PARAMS[2:], outputs=OUTS,
                    runner=fake_runner)
    assert [r.status for r in out.results] == ["skipped", "skipped", "ok"]
    out = batch.run([Scenario("base")], PARAMS[:2], outputs={"FLOW_OUTcms": [1, 2]},
                    resume=False, runner=fake_runner)
    assert [r.status for r in out.results] == ["ok", "ok"]
    assert out.series("FLOW_OUTcms").shape[1] == 4


def test_summary_locked_is_retried_then_written(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    monkeypatch.setattr(bmod, "_RETRY_SLEEP", 0.0)
    real = os.replace
    state = {"fails": 8}

    def flaky(src, dst):
        if str(dst).endswith("summary.csv") and state["fails"] > 0:
            state["fails"] -= 1
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(bmod.os, "replace", flaky)
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        [Scenario("base")], PARAMS, outputs=OUTS, runner=fake_runner)
    assert not out.failed
    assert len(pd.read_csv(res_dir / "summary.csv")) == 3


def test_summary_always_locked_falls_back_to_other_file(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    monkeypatch.setattr(bmod, "_RETRY_SLEEP", 0.0)
    real = os.replace

    def locked(src, dst):
        if Path(dst).name == "summary.csv":
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(bmod.os, "replace", locked)
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        [Scenario("base")], PARAMS, outputs=OUTS, runner=fake_runner)
    assert len(out.results) == 3 and not out.failed
    assert len(out.warnings) == 1 and "summary_" in out.warnings[0]
    alt = list(res_dir.glob("summary_*.csv"))
    assert len(alt) == 1 and len(pd.read_csv(alt[0])) == 3
    assert not (res_dir / "summary.csv").exists()
    assert len(list((res_dir / "series").glob("*.csv"))) == 3
    assert (res_dir / "metrics.csv").exists()


def test_fallback_write_failing_too_raises(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    monkeypatch.setattr(bmod, "_RETRY_SLEEP", 0.0)
    real = os.replace

    def locked(src, dst):
        if Path(dst).name.startswith("summary"):
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(bmod.os, "replace", locked)
    with pytest.raises(PermissionError):
        ScenarioBatch(make_project(env), tmp_path / "res").run(
            [Scenario("base")], PARAMS, outputs=OUTS, runner=fake_runner)


# ── scheduling: one pool, a job queue, no barrier between base groups ──

def test_all_jobs_overlap_across_two_bases(env, tmp_path, monkeypatch):
    log = tmp_path / "timing.log"
    monkeypatch.setenv("E5_TIMING", str(log))
    base_a = build_txinout(tmp_path, "A")
    base_b = build_txinout(tmp_path, "B")
    scen = [Scenario("a", txinout_dir=base_a), Scenario("b", txinout_dir=base_b)]
    params = [ParamSet("p1", {"CN2.mgt": [(50, "v")]}),
              ParamSet("p2", {"CN2.mgt": [(60, "v")]})]
    out = ScenarioBatch(make_project(env, n=4), tmp_path / "res").run(
        scen, params, outputs=OUTS, runner=timing_runner)
    assert [r.status for r in out.results] == ["ok"] * 4
    rows = [ln.split("|") for ln in trace_lines(log)]
    assert len(rows) == 4
    starts = [float(r[1]) for r in rows]
    ends = [float(r[2]) for r in rows]
    assert max(starts) < min(ends)          # all 4 jobs overlap in time


def test_no_barrier_short_jobs_flow_while_long_runs(env, tmp_path, monkeypatch):
    log = tmp_path / "timing.log"
    monkeypatch.setenv("E5_TIMING", str(log))
    params = [ParamSet("long", {"CN2.mgt": [(40, "v")]}),
              ParamSet("s1", {"CN2.mgt": [(50, "v")]}),
              ParamSet("s2", {"CN2.mgt": [(60, "v")]}),
              ParamSet("s3", {"CN2.mgt": [(70, "v")]})]
    out = ScenarioBatch(make_project(env, n=2), tmp_path / "res").run(
        [Scenario("base")], params, outputs=OUTS, runner=timing_runner)
    assert [r.status for r in out.results] == ["ok"] * 4
    rows = [ln.split("|") for ln in trace_lines(log)]
    assert len(rows) == 4
    long_row = next(r for r in rows if float(r[3]) == 40.0)
    shorts = [r for r in rows if float(r[3]) != 40.0]
    long_start, long_end = float(long_row[1]), float(long_row[2])
    # short jobs run on the other slot while the long one is still running
    for r in shorts:
        assert float(r[1]) < long_end, "short job must start before the long job ends"
        assert float(r[2]) > long_start


def test_reseed_on_base_switch_sees_only_that_bases_files(env, tmp_path, monkeypatch):
    log = tmp_path / "marker.log"
    monkeypatch.setenv("E5_MARKER", str(log))
    base_a = build_txinout(tmp_path, "A")
    base_b = build_txinout(tmp_path, "B")
    (base_a / "base_A.marker").write_text("A")
    (base_b / "base_B.marker").write_text("B")
    scen = [Scenario("a1", txinout_dir=base_a), Scenario("a2", txinout_dir=base_a),
            Scenario("b1", txinout_dir=base_b), Scenario("b2", txinout_dir=base_b)]
    out = ScenarioBatch(make_project(env, n=2), tmp_path / "res").run(
        scen, [ParamSet("p")], outputs=OUTS, runner=marker_runner)
    assert [r.status for r in out.results] == ["ok"] * 4
    rows = [ln.split("|") for ln in trace_lines(log)]
    assert len(rows) == 4
    for r in rows:
        a, b = r[1].split("=")[1], r[2].split("=")[1]
        assert (a, b) in (("1", "0"), ("0", "1"))      # exactly one base, never both
    seen = {(r[1], r[2]) for r in rows}
    assert ("A=1", "B=0") in seen and ("A=0", "B=1") in seen


def test_bad_base_fails_its_jobs_others_ok(env, tmp_path):
    import shutil
    good = build_txinout(tmp_path, "GOOD")
    bad = build_txinout(tmp_path, "BAD")
    scen = [Scenario("good", txinout_dir=good), Scenario("bad", txinout_dir=bad)]
    shutil.rmtree(bad)
    out = ScenarioBatch(make_project(env), tmp_path / "res").run(
        scen, PARAMS[:2], outputs=OUTS, runner=fake_runner)
    ok = [r.job_id for r in out.results if r.status == "ok"]
    failed = [r for r in out.results if r.status == "failed"]
    assert ok == ["good__p_none", "good__p_v60"]
    assert [r.job_id for r in failed] == ["bad__p_none", "bad__p_v60"]
    assert all("setup of" in r.error and "BAD" in r.error for r in failed)


# ── rework round 1: exit-path saving, reseed isolation, locked slots ──

def test_exception_mid_batch_saves_finished_rows_and_resume_skips(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    obs_idx = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    obs = pd.Series(expected(35.0, 10.0, 1, 731), index=obs_idx)
    params = [ParamSet("p0", {"CN2.mgt": [(35, "v")]}),   # slow (2.0 s)
              ParamSet("p1", {"CN2.mgt": [(40, "v")]})]    # fast (0.5 s): finishes first
    res_dir = tmp_path / "res"
    batch = ScenarioBatch(make_project(env, n=2), res_dir)

    real = bmod._atomic_csv
    state = {"raised": False}

    def boom(df, path):
        if not state["raised"] and Path(path).name == "metrics.csv":
            state["raised"] = True
            raise RuntimeError("boom")
        return real(df, path)

    monkeypatch.setattr(bmod, "_atomic_csv", boom)
    with pytest.raises(RuntimeError, match="boom"):
        batch.run([Scenario("base")], params,
                  outputs={"FLOW_OUTcms": [1]},
                  observed={("FLOW_OUTcms", 1): obs}, metrics=("nse",),
                  runner=completion_runner)
    s = pd.read_csv(res_dir / "summary.csv")
    assert list(s["job_id"]) == ["base__p0", "base__p1"]
    assert list(s["status"]) == ["ok", "ok"]
    m = pd.read_csv(res_dir / "metrics.csv")
    assert list(m["job_id"]) == ["base__p0", "base__p1"]      # plan order, not completion order
    out2 = batch.run([Scenario("base")], params,
                     outputs={"FLOW_OUTcms": [1]},
                     observed={("FLOW_OUTcms", 1): obs}, metrics=("nse",),
                     runner=completion_runner)
    assert [r.status for r in out2.results] == ["skipped", "skipped"]


def test_no_pool_when_everything_resumed(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    res_dir = tmp_path / "res"
    batch = ScenarioBatch(make_project(env), res_dir)
    batch.run([Scenario("base")], PARAMS[:1], outputs=OUTS, runner=fake_runner)

    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("pool must not start when nothing to run")

    monkeypatch.setattr(bmod.concurrent.futures, "ProcessPoolExecutor", boom)
    out = batch.run([Scenario("base")], PARAMS[:1], outputs=OUTS, runner=fake_runner)
    assert calls == []
    assert [r.status for r in out.results] == ["skipped"]


def test_failed_job_reseeds_slot_before_next_job(env, tmp_path):
    wet = make_weather(tmp_path, "wet", "30.0")
    scen = [Scenario("wet", weather_dir=wet)]
    params = [ParamSet("p_bad", {"CN2.mgt": [(77, "v")]}),
              ParamSet("p_ok")]
    out = ScenarioBatch(make_project(env, n=1), tmp_path / "res").run(
        scen, params, outputs=OUTS, runner=leftover_runner)
    assert [r.status for r in out.results] == ["failed", "ok"]
    assert "injected failure" in out.results[0].error


@pytest.mark.skipif(os.name != "nt", reason="relies on Windows open-file locking")
def test_locked_slot_unusable_then_remaining_fail_with_message(env, tmp_path):
    base_a = build_txinout(tmp_path, "A")
    base_b = build_txinout(tmp_path, "B")
    base_c = build_txinout(tmp_path, "C")
    scen = [Scenario("a", txinout_dir=base_a),
            Scenario("b", txinout_dir=base_b),
            Scenario("c", txinout_dir=base_c)]
    out = ScenarioBatch(make_project(env, n=1), tmp_path / "res").run(
        scen, [ParamSet("p")], outputs=OUTS, runner=lock_runner)
    assert [r.job_id for r in out.results] == ["a__p", "b__p", "c__p"]
    assert out.results[0].status == "ok"
    assert out.results[1].status == "failed"
    assert "slot locked" in out.results[1].error
    assert out.results[2].status == "failed"
    assert "no usable worker folder" in out.results[2].error


# ── rework round 2: broken pool, interrupt-save isolation, unreadable overlay ──

def break_runner(worker_dir: str) -> None:
    """CN2=35 job finishes fast and drops a marker; CN2=50 waits for that marker, then
    kills its worker via ``os._exit``; CN2=60/70 jobs stay slow so they are still
    running (or pending) when the pool breaks."""
    cn2 = read_cn2(worker_dir)
    marker = os.environ.get("E5_BREAK_MARKER")
    if cn2 == 35.0:
        fake_runner(worker_dir)
        if marker:
            Path(marker).write_text("done")
        return
    if cn2 == 50.0:
        deadline = time.time() + 60
        while marker and not Path(marker).exists() and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.5)          # let the parent harvest job 1 before we kill the worker
        os._exit(1)
    time.sleep(2.0)              # jobs 3, 4: still running when the pool breaks
    fake_runner(worker_dir)


def test_broken_process_pool_fails_remaining_jobs(env, tmp_path, monkeypatch):
    marker = tmp_path / "break.marker"
    monkeypatch.setenv("E5_BREAK_MARKER", str(marker))
    params = [ParamSet("p1", {"CN2.mgt": [(35, "v")]}),
              ParamSet("p2", {"CN2.mgt": [(50, "v")]}),
              ParamSet("p3", {"CN2.mgt": [(60, "v")]}),
              ParamSet("p4", {"CN2.mgt": [(70, "v")]})]
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env, n=2), res_dir).run(
        [Scenario("base")], params, outputs=OUTS, runner=break_runner)
    assert [r.status for r in out.results] == ["ok", "failed", "failed", "failed"]
    assert "BrokenProcessPool" in out.results[1].error
    for r in out.results[2:]:
        assert "BrokenProcessPool" in r.error or "pool broke" in r.error
    # a second run with a normal runner runs only the not-ok jobs
    out2 = ScenarioBatch(make_project(env), res_dir).run(
        [Scenario("base")], params, outputs=OUTS, runner=fake_runner)
    assert [r.status for r in out2.results] == ["skipped", "ok", "ok", "ok"]


def test_keyboardinterrupt_not_masked_by_save_failure(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    monkeypatch.setattr(bmod, "_RETRY_SLEEP", 0.0)
    params = [ParamSet("p0", {"CN2.mgt": [(35, "v")]}),
              ParamSet("p1", {"CN2.mgt": [(40, "v")]}),
              ParamSet("p2", {"CN2.mgt": [(60, "v")]}),
              ParamSet("p3", {"CN2.mgt": [(70, "v")]})]
    res_dir = tmp_path / "res"

    real_wait = bmod.concurrent.futures.wait
    calls = {"n": 0}

    def interrupt_wait(futures, return_when):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real_wait(futures, return_when=return_when)

    def atomic_boom(df, path):
        raise OSError("disk full")

    monkeypatch.setattr(bmod.concurrent.futures, "wait", interrupt_wait)
    monkeypatch.setattr(bmod, "_atomic_csv", atomic_boom)
    with pytest.raises(KeyboardInterrupt):
        ScenarioBatch(make_project(env, n=2), res_dir).run(
            [Scenario("base")], params, outputs=OUTS, runner=fake_runner)


def test_unreadable_weather_dir_fails_its_jobs_others_ok(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    wet = make_weather(tmp_path, "wet", "30.0")
    scen = [Scenario("wet", weather_dir=wet), Scenario("base")]
    import shutil
    shutil.rmtree(wet)                        # deleted after the Scenario objects are built
    monkeypatch.setattr(bmod, "_scenario_sig", lambda s: "fixed")
    out = ScenarioBatch(make_project(env), tmp_path / "res").run(
        scen, PARAMS[:2], outputs=OUTS, runner=fake_runner)
    failed = [r for r in out.results if r.status == "failed"]
    ok = [r for r in out.results if r.status == "ok"]
    assert [r.job_id for r in failed] == ["wet__p_none", "wet__p_v60"]
    assert [r.job_id for r in ok] == ["base__p_none", "base__p_v60"]
    assert all("weather_dir unreadable" in r.error for r in failed)


# ── rework round 3: broken-pool drain keeps an already-finished sibling job ──

def drain_break_runner(worker_dir: str) -> None:
    """p1 (CN2=35) finishes fast and ok; p2 (CN2=50) waits for p1's marker, then
    kills its worker via ``os._exit(1)`` so the pool breaks."""
    cn2 = read_cn2(worker_dir)
    marker = os.environ.get("E5_DRAIN_MARKER")
    if cn2 == 35.0:
        fake_runner(worker_dir)
        if marker:
            Path(marker).write_text("done")
        return
    if cn2 == 50.0:
        deadline = time.time() + 60
        while marker and not Path(marker).exists() and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.5)          # let p1 finish its series write before we kill the worker
        os._exit(1)
    fake_runner(worker_dir)


def test_broken_pool_drain_keeps_finished_sibling_job(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    marker = tmp_path / "drain.marker"
    monkeypatch.setenv("E5_DRAIN_MARKER", str(marker))
    params = [ParamSet("p1", {"CN2.mgt": [(35, "v")]}),
              ParamSet("p2", {"CN2.mgt": [(50, "v")]})]
    res_dir = tmp_path / "res"

    real_wait = bmod.concurrent.futures.wait

    def fake_wait(fs, return_when=None):
        # Wait until every future has a result (or the pool broke), then report only
        # the futures whose result raises as "done"; the finished p1 future stays in
        # not_done (still in `futures`), so the drain loop must read its real result.
        real_wait(fs, return_when=bmod.concurrent.futures.ALL_COMPLETED)
        done, not_done = set(), set()
        for fut in fs:
            try:
                fut.result()
            except Exception:  # noqa: BLE001 - BrokenProcessPool for the crashed worker
                done.add(fut)
            else:
                not_done.add(fut)
        return done, not_done

    monkeypatch.setattr(bmod.concurrent.futures, "wait", fake_wait)
    out = ScenarioBatch(make_project(env, n=2), res_dir).run(
        [Scenario("base")], params, outputs=OUTS, runner=drain_break_runner)
    assert [r.status for r in out.results] == ["ok", "failed"]
    assert "BrokenProcessPool" in out.results[1].error
    assert (res_dir / "series" / "base__p1.csv").exists()
    assert not (res_dir / "series" / "base__p2.csv").exists()


# ── FIX-1: worker log queue (F5) and a per-batch work dir (F6) ────────

WORKER_LOG_MARKER = "worker log "


def logging_runner(worker_dir: str) -> None:
    """fake_runner that also emits one log record from inside the worker process."""
    logging.getLogger("spyswat.tests.worker").info(WORKER_LOG_MARKER + Path(worker_dir).name)
    fake_runner(worker_dir)


def queued_messages(q) -> list:
    """Every record currently in a (listener-less) queue, as rendered messages."""
    out = []
    while True:
        try:
            out.append(q.get(timeout=1.0).getMessage())
        except queue.Empty:
            return out


def _work_root(env) -> Path:
    return Path(make_project(env).working_folder) / WORK_SUBDIR


def _batch_dirs(work_root: Path) -> list:
    return sorted(p.name for p in work_root.iterdir() if p.is_dir()) \
        if work_root.is_dir() else []


def test_run_passes_log_queue_to_every_job(env, tmp_path):
    with multiprocessing.get_context("spawn").Manager() as mgr:
        q = mgr.Queue(-1)
        out = ScenarioBatch(make_project(env, n=1), tmp_path / "res").run(
            [Scenario("base")], PARAMS, outputs=OUTS, runner=logging_runner, log_queue=q)
        assert set(out.summary["status"]) == {"ok"}
        msgs = queued_messages(q)
    assert sum(m.startswith(WORKER_LOG_MARKER) for m in msgs) == len(PARAMS)


def test_run_defaults_to_the_logger_queue_and_starts_no_listener(env, tmp_path, monkeypatch):
    with multiprocessing.get_context("spawn").Manager() as mgr:
        q = mgr.Queue(-1)
        monkeypatch.setattr(Logger, "_log_queue", q)
        monkeypatch.setattr(Logger, "_listener", None)
        out = ScenarioBatch(make_project(env, n=1), tmp_path / "res").run(
            [Scenario("base")], PARAMS[:1], outputs=OUTS, runner=logging_runner)
        assert out.results[0].status == "ok"
        assert Logger._listener is None          # run() must never start a listener
        msgs = queued_messages(q)
    assert any(m.startswith(WORKER_LOG_MARKER) for m in msgs)


def test_work_dir_is_keyed_by_results_dir(env, tmp_path):
    proj = make_project(env, n=1)
    work_root = _work_root(env)
    res_a, res_b = tmp_path / "res_a", tmp_path / "res_b"

    ScenarioBatch(proj, res_a).run([Scenario("base")], PARAMS[:1], outputs=OUTS,
                                   runner=fake_runner)
    dirs_a = _batch_dirs(work_root)
    assert len(dirs_a) == 1
    assert re.fullmatch(r"[0-9a-f]{10}", dirs_a[0])       # key: 10 lowercase hex chars
    assert (work_root / dirs_a[0] / "TxInOut1").is_dir()

    ScenarioBatch(proj, res_b).run([Scenario("base")], PARAMS[1:2], outputs=OUTS,
                                   runner=fake_runner)
    dirs_b = _batch_dirs(work_root)
    assert len(dirs_b) == 2                                # own work dir, nothing shared
    assert len(set(dirs_b) - set(dirs_a)) == 1             # the second dir is a new name

    # the same results_dir keeps its work dir: running more jobs adds no new one
    ScenarioBatch(proj, res_a).run([Scenario("base")], PARAMS[2:3], outputs=OUTS,
                                   runner=fake_runner)
    assert _batch_dirs(work_root) == dirs_b
