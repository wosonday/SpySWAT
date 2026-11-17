"""
Tests for spyswat.swat_calib.scenarios (no SWAT executable: a fake runner writes a
synthetic daily output.rch whose values depend on the worker's CURRENT input files).

Value model (per reach r, day d):  CN2 * PCP / 100 * r + d * 0.01
where CN2 is read from the first .mgt file and PCP from pcp1.pcp of the worker folder.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat import SWATProject
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.io import SWATParam
from spyswat.swat_calib.scenarios import ParamSet, Scenario, ScenarioBatch

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
        with open(log, "a") as fh:
            fh.write(f"{Path(worker_dir).name}|{cn2}|{pcp}|{int(extra)}|{nbyr}\n")
    if cn2 == 77.0 and pcp > 20 and not os.environ.get("E5_ALLOW_FAIL"):
        raise RuntimeError("injected failure")
    dates = pd.date_range(f"{iyr + skip}-01-01", f"{iyr + nbyr - 1}-12-31", freq="D")
    lines = ["header\n"] * 9
    for d, date in enumerate(dates):
        for r in REACHES:
            flow = cn2 * pcp / 100.0 * r + d * 0.01
            lines.append(_rch_line(RCH=r, MON=date.dayofyear, FLOW_OUTcms=flow,
                                   SED_OUTtons=flow * 2))
    Path(worker_dir, "output.rch").write_text("".join(lines))


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
    assert not log.exists()
    out = batch.run(scen, PARAMS, pairs=[("luc", "p_rel"), ("base", "p_v60")],
                    outputs=OUTS, runner=fake_runner)
    assert [r.job_id for r in out.results] == ["luc__p_rel", "base__p_v60"]
    assert len(log.read_text().splitlines()) == 2
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
    assert len(log.read_text().splitlines()) == 8

    monkeypatch.setenv("E5_ALLOW_FAIL", "1")
    out2 = batch.run(scen, params, outputs=OUTS, runner=fake_runner)
    assert len(log.read_text().splitlines()) == 9          # only the failed job re-ran
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
    rows = [ln.split("|") for ln in log.read_text().splitlines()]
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


def test_no_common_dates_keeps_series_with_nan_metrics(env, tmp_path):
    obs = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("1990-01-01", periods=3))
    res_dir = tmp_path / "res"
    out = ScenarioBatch(make_project(env), res_dir).run(
        [Scenario("base")], PARAMS[:1], outputs=OUTS, observed={("FLOW_OUTcms", 1): obs},
        metrics=("nse", "kge"), runner=fake_runner)
    assert not out.failed and out.results[0].status == "ok"
    assert (res_dir / "series" / "base__p_none.csv").exists()
    m = pd.read_csv(res_dir / "metrics.csv")
    assert set(m["metric"]) == {"nse", "kge"} and m["value"].isna().all()


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
    assert not log.exists()


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


def test_summary_always_locked_raises_after_all_jobs(env, tmp_path, monkeypatch):
    from spyswat.swat_calib.scenarios import batch as bmod
    monkeypatch.setattr(bmod, "_RETRY_SLEEP", 0.0)
    real = os.replace

    def locked(src, dst):
        if str(dst).endswith("summary.csv"):
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(bmod.os, "replace", locked)
    res_dir = tmp_path / "res"
    with pytest.raises(PermissionError):
        ScenarioBatch(make_project(env), res_dir).run(
            [Scenario("base")], PARAMS, outputs=OUTS, runner=fake_runner)
    assert len(list((res_dir / "series").glob("*.csv"))) == 3
    assert (res_dir / "metrics.csv").exists()
