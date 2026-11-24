"""End-to-end tests for the 0.3.0 facade on ``SWATProject`` (API-4).

A real ``SWATProject`` is built on a synthetic TxtInOut, but the SWAT execution
layer is faked in-process (no ``swat.exe``, no worker subprocesses): the batch
path replaces ``WorkingFolderManager.run_parallel`` and the sequential path
replaces ``swat_exe.run`` + output reading. The session layout, best-run metrics,
regression sensitivity and TxtInOut restore are all exercised for real.
"""
import json
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat import SWATProject
from spyswat.logger import Logger
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.calibration.result import CalibrationResult
from spyswat.swat_calib.core.workingFolder_manager import WorkerResult
from spyswat.swat_calib.scenarios.model import ParamSet, Scenario

from test_working_folder import build_param_file, build_txinout, read_cn2, snapshot

DATES = pd.date_range("2000-01-01", periods=10, freq="D")
PARAM_RANGES = {"CN2.mgt": (35.0, 98.0), "ALPHA_BF.gw": (0.0, 1.0)}
CALIB = ("2000-01-01", "2000-01-10")
VALID = ("2000-01-06", "2000-01-10")


def _obs():
    return {
        ("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES),
        ("SED_OUTtons", 51): pd.Series(np.arange(10, dtype=float) * 2 + 1, index=DATES),
    }


class FakeOutputFileManager:
    """Reads a plain-number ``output.rch`` (one value per line)."""

    def __init__(self, txinout):
        self.directory = Path(getattr(txinout, "directory", txinout))

    def read_rch(self, columns=None, reach_id=None, freq=None):
        vals = [float(x) for x in (self.directory / "output.rch").read_text().split()]
        return pd.DataFrame({columns[-1]: vals})


class FakeOutputManager(FakeOutputFileManager):
    def invalidate(self):
        pass


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logger, "init_queue_listener", classmethod(lambda cls, **k: None))
    monkeypatch.setattr(Logger, "stop_listener", classmethod(lambda cls: None))
    monkeypatch.setattr(cm, "OutputFileManager", FakeOutputFileManager)

    base = build_txinout(tmp_path)
    param = build_param_file(tmp_path)
    exe = tmp_path / "swat.exe"
    exe.write_text("")
    p = SWATProject(base, tmp_path / "work", exe, param_file=param, n_parallel=2)
    p.WorkingFolder.setup()
    p.get_date_range = lambda freq="D": DATES   # 10-value output matches 10 dates

    wf = p.WorkingFolder

    def fake_run_parallel(swat_exe, param_sets=None, log_queue=None, *,
                          extract=None, runner=None, prepare=None, overlays=None,
                          timeout_s=None):
        results = []
        for i, ps in enumerate(param_sets):
            wdir = wf.worker_dirs[i]
            cn2 = float(ps["CN2.mgt"][0][0])
            if cn2 == 77.0:
                results.append(WorkerResult(False, "RuntimeError: boom", 0.0,
                                            str(wdir), None))
                continue
            n_vals = len(p.get_date_range("D"))
            (wdir / "output.rch").write_text("\n".join([repr(cn2)] * n_vals) + "\n")
            extractor = pickle.loads(pickle.dumps(extract))
            payload = extractor(str(wdir))
            results.append(WorkerResult(True, None, 0.0, str(wdir), payload))
        return results

    wf.run_parallel = fake_run_parallel

    def fake_swat_run(directory):
        cn2 = read_cn2(directory)
        n_vals = len(p.get_date_range("D"))
        (Path(directory) / "output.rch").write_text(
            "\n".join([repr(cn2)] * n_vals) + "\n")

    p.swat_exe.run = fake_swat_run
    p._output_manager = FakeOutputManager(base)
    return p


def _layout(session_dir):
    return sorted(rp.relative_to(session_dir).as_posix()
                  for rp in Path(session_dir).rglob("*"))


def test_calibration_glue_end_to_end(proj):
    before = snapshot(proj.txinout.directory)
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, VALID,
                           algorithm="glue", n_samples=8, seed=1)

    assert isinstance(res, CalibrationResult)
    assert res.algorithm == "glue" and res.seed == 1 and res.metric == "nse"

    # exact session layout
    rel = _layout(res.session_dir)
    for expected in ("session.json", "runs.csv", "best.csv", "sensitivity.csv",
                     "reach_1/FLOW_OUTcms.csv", "reach_1/FLOW_OUTcms_metrics.csv",
                     "reach_51/SED_OUTtons.csv", "reach_51/SED_OUTtons_metrics.csv"):
        assert expected in rel, f"missing {expected} in {rel}"

    # best by score: the aggregate score matches the best run's score
    assert res["best_score"] == pytest.approx(res.runs["score"].max())
    assert np.isfinite(res.best_score)

    # metrics has calib + valid rows for both sites
    idx = res.metrics.index
    assert ("FLOW_OUTcms", 1, "calib") in idx and ("FLOW_OUTcms", 1, "valid") in idx
    assert ("SED_OUTtons", 51, "calib") in idx and ("SED_OUTtons", 51, "valid") in idx

    # sensitivity produced a DataFrame (8 samples > k+2 for 2 parameters)
    assert isinstance(res.sensitivity, pd.DataFrame)
    assert "parameter" in res.sensitivity.columns
    assert res.sensitivity_status == "ok"

    # session.json signature records options, observed_hash and numpy_version
    sig = json.loads((res.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]
    assert sig["options"] == {"n_samples": 8}
    assert sig["numpy_version"] == np.__version__
    assert isinstance(sig["observed_hash"], str) and len(sig["observed_hash"]) == 64

    # TxtInOut input files are byte-identical afterwards
    assert snapshot(proj.txinout.directory) == before


@pytest.mark.parametrize("algorithm,kwargs", [
    ("pso", dict(n_particles=4, max_iterations=1)),
    ("de", dict(pop_size=4, max_generations=1)),
    ("dds", dict(n_iterations=5)),
])
def test_calibration_other_algorithms(proj, algorithm, kwargs):
    before = snapshot(proj.txinout.directory)
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, VALID,
                           algorithm=algorithm, seed=1, **kwargs)
    assert res.algorithm == algorithm
    assert np.isfinite(res.best_score)
    assert list(res.runs["run_id"]) == sorted(res.runs["run_id"])
    if algorithm == "dds":
        assert res.sensitivity is None
        assert res.sensitivity_status == "insufficient runs"
    else:
        assert res.sensitivity is not None or res.sensitivity_status
    assert snapshot(proj.txinout.directory) == before


def test_calibration_param_methods_and_subbasins(proj):
    wf = proj.WorkingFolder
    orig_run_parallel = wf.run_parallel
    seen_param_sets = []

    def spy_run_parallel(swat_exe, param_sets=None, **kwargs):
        seen_param_sets.extend(param_sets)
        return orig_run_parallel(swat_exe, param_sets=param_sets, **kwargs)

    wf.run_parallel = spy_run_parallel
    res = proj.calibration(
        PARAM_RANGES, _obs(), CALIB,
        algorithm="glue", n_samples=4, seed=1, sensitivity=False,
        param_methods={"CN2.mgt": "r"},
        param_subbasins={"CN2.mgt": [1]},
    )

    assert len(seen_param_sets) == 4
    assert all(ps["CN2.mgt"][0][1:] == ("r", [1]) for ps in seen_param_sets)
    assert res.methods == {"CN2.mgt": "r"}
    assert res.subbasins == {"CN2.mgt": [1]}
    assert res.best_params["CN2.mgt"][0][1:] == ("r", [1])
    sig = json.loads((res.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]
    assert sig["methods"] == {"CN2.mgt": "r"}
    assert sig["subbasins"] == {"CN2.mgt": [1]}


def test_calibration_monthly_step_and_bare_series_observed(proj):
    daily_dates = pd.date_range("2000-01-01", periods=91, freq="D")   # Jan-Mar 2000
    proj.get_date_range = lambda freq="D": daily_dates
    obs_monthly = pd.Series(
        [40.0, 50.0, 60.0],
        index=pd.date_range("2000-01-01", periods=3, freq="MS"),
    )
    res = proj.calibration(
        PARAM_RANGES, obs_monthly, ("2000-01-01", "2000-03-31"),
        algorithm="glue", n_samples=4, step="M", seed=1, sensitivity=False,
    )
    assert np.isfinite(res.best_score)
    assert res.metrics.loc[("FLOW_OUTcms", 1, "calib"), "n"] == 3


def test_calibration_timestamp_periods_and_on_failure_signature(proj):
    res = proj.calibration(
        PARAM_RANGES, _obs(),
        (pd.Timestamp("2000-01-01"), pd.Timestamp("2000-01-10")),
        (pd.Timestamp("2000-01-06"), pd.Timestamp("2000-01-10")),
        algorithm="dds", n_iterations=3, seed=1, sensitivity=False,
        on_failure="penalize",
    )
    sig = json.loads((res.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]
    assert sig["calib_period"] == ["2000-01-01T00:00:00", "2000-01-10T00:00:00"]
    assert sig["valid_period"] == ["2000-01-06T00:00:00", "2000-01-10T00:00:00"]
    assert sig["on_failure"] == "penalize"
    assert sig["options"] == {"n_iterations": 3, "on_failure": "penalize"}
    assert sig["numpy_version"] == np.__version__


def test_calibration_observed_hash_order_and_data_sensitivity(proj):
    obs1 = _obs()
    obs2 = {k: obs1[k] for k in reversed(list(obs1))}
    obs3 = {
        ("FLOW_OUTcms", 1): obs1[("FLOW_OUTcms", 1)] + 1.0,
        ("SED_OUTtons", 51): obs1[("SED_OUTtons", 51)],
    }
    r1 = proj.calibration(PARAM_RANGES, obs1, CALIB, algorithm="glue",
                          n_samples=3, seed=1, sensitivity=False)
    r2 = proj.calibration(PARAM_RANGES, obs2, CALIB, algorithm="glue",
                          n_samples=3, seed=1, sensitivity=False)
    r3 = proj.calibration(PARAM_RANGES, obs3, CALIB, algorithm="glue",
                          n_samples=3, seed=1, sensitivity=False)
    h1 = json.loads((r1.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]["observed_hash"]
    h2 = json.loads((r2.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]["observed_hash"]
    h3 = json.loads((r3.session_dir / "session.json").read_text(encoding="utf-8"))["signature"]["observed_hash"]
    assert h1 == h2
    assert h1 != h3


def test_observed_hash_normalises_minus_zero(proj):
    from spyswat.swat_project import _hash_observed
    idx = pd.DatetimeIndex(["2000-01-01", "2000-01-02"])
    a = {("FLOW_OUTcms", 1): pd.Series([0.0, -0.0], index=idx)}
    b = {("FLOW_OUTcms", 1): pd.Series([-0.0, 0.0], index=idx)}
    c = {("FLOW_OUTcms", 1): pd.Series([0.0, 0.0], index=idx)}
    # -0.0 normalises to 0.0, so all three hash identically (API-4-3).
    assert _hash_observed(a) == _hash_observed(b) == _hash_observed(c)


def test_calibration_constant_and_collinear_parameter_sensitivity(proj, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = proj.calibration(
            {"CN2.mgt": (35.0, 98.0), "ALPHA_BF.gw": (0.5, 0.5)},
            _obs(), CALIB, algorithm="glue", n_samples=6, seed=1,
        )
    assert res.sensitivity_status == "ok"
    row = res.sensitivity[res.sensitivity["parameter"] == "ALPHA_BF.gw"].iloc[0]
    assert row["coef"] == 0.0
    assert row["t_stat"] == 0.0
    assert np.isnan(row["p_value"])
    assert res.sensitivity.attrs.get("n_used") == 6

    from spyswat.swat_calib.calibration.session_store import SessionStore
    store = SessionStore(
        tmp_path / "collinear_session",
        signature={}, param_names=["K1.mgt", "K2.mgt"], sites=[],
    )
    try:
        noise = [0.01, -0.02, 0.01, -0.01, 0.02, -0.01, 0.0, 0.0]
        for i, eps in enumerate(noise, start=1):
            k1 = i * 0.1
            store.add_run(
                i, params={"K1.mgt": k1, "K2.mgt": 2.0 * k1 + 1.0},
                status="ok", error=None, score=3.0 * k1 + eps,
                is_initial=True, series={}, site_metrics={},
            )
        store.flush()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sens, status = SWATProject._regression_sensitivity(
                store,
                {"K1.mgt": (0.0, 1.0), "K2.mgt": (1.0, 3.0)},
                ["K1.mgt", "K2.mgt"],
                True,
            )
    finally:
        store.close()
    assert status == "ok"
    k2_row = sens[sens["parameter"] == "K2.mgt"].iloc[0]
    assert k2_row["coef"] == 0.0
    assert k2_row["t_stat"] == 0.0
    assert np.isnan(k2_row["p_value"])
    assert sens.attrs.get("n_used") == 8


def test_calibration_load_roundtrip(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, VALID,
                           algorithm="glue", n_samples=8, seed=1)
    loaded = CalibrationResult.load(res.session_dir)
    assert loaded.best_score == pytest.approx(res.best_score)
    assert loaded.best_run_id == res.best_run_id
    assert loaded.best_params == res.best_params
    assert loaded.metric == res.metric
    assert loaded.sensitivity_status == "ok"
    assert isinstance(loaded.sensitivity, pd.DataFrame)
    pd.testing.assert_frame_equal(loaded.runs, res.runs)

    res_no_sens = proj.calibration(PARAM_RANGES, _obs(), CALIB,
                                   algorithm="glue", n_samples=3, seed=1,
                                   sensitivity=False)
    loaded_no_sens = CalibrationResult.load(res_no_sens.session_dir)
    assert loaded_no_sens.sensitivity is None
    assert loaded_no_sens.sensitivity_status == ""


def test_select_unknown_metric_raises(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=4, metrics=("nse",), seed=1, sensitivity=False)
    with pytest.raises(ValueError, match="metric"):
        res.select(bogus__gt=0.5)


def test_select_drops_failed_even_with_finite_score():
    # API-4-3: select() must filter status == "ok", not rely on a failed run's
    # NaN score. Here the failed run carries a finite score that would otherwise
    # satisfy the condition.
    runs = pd.DataFrame({
        "run_id": [1, 2],
        "time": ["t", "t"],
        "status": ["ok", "failed"],
        "error": ["", "boom"],
        "is_initial": [True, True],
        "CN2.mgt": [50.0, 60.0],
        "ALPHA_BF.gw": [0.5, 0.6],
        "score": [0.8, 0.95],
    })
    res = CalibrationResult(
        best_params={}, best_score=0.8, best_run_id=1, metric="nse", runs=runs,
        session_dir=Path("s"),
    )
    picked = res.select(score__gt=0.7)
    assert [p.name for p in picked] == ["run_1"]


def test_calibration_existing_session_resume_false_raises(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    name = res.session_dir.name
    with pytest.raises(FileExistsError):
        proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                         n_samples=3, seed=1, session=name, resume=False,
                         sensitivity=False)


def test_calibration_existing_session_resume_true_replays(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    name = res.session_dir.name
    resumed = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                               n_samples=3, seed=1, session=name, resume=True,
                               sensitivity=False)
    assert resumed.best_score == pytest.approx(res.best_score)
    assert resumed.best_run_id == res.best_run_id
    assert resumed.best_params == res.best_params
    pd.testing.assert_frame_equal(
        resumed.runs.drop(columns=["time"]), res.runs.drop(columns=["time"]))


# ── evaluate facade ──────────────────────────────────────────────────────────

def test_evaluate_fills_print_step_and_warmup(proj):
    from spyswat.swat_calib.analysis import EvaluationResult
    sim = pd.Series([1.0, 2.0, 3.0, 5.0], index=DATES[:4])
    obs = pd.Series([1.0, 2.0, 3.0, 4.0], index=DATES[:4])
    res = proj.evaluate(sim, obs, metrics=("nse",))
    assert isinstance(res, EvaluationResult)
    assert res.table.loc[(None, None, "all"), "n"] == 4
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(0.8)


# ── sensitivity facade ───────────────────────────────────────────────────────

def test_sensitivity_from_session(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=8, seed=1, sensitivity=False)
    sens = proj.sensitivity(from_session=res.session_dir)
    assert isinstance(sens, pd.DataFrame)
    assert list(sens.columns) == ["parameter", "coef", "t_stat", "p_value", "rank"]


def test_sensitivity_regression_runs_glue_first(proj):
    sens = proj.sensitivity(PARAM_RANGES, _obs(), method="regression",
                            n_samples=8, seed=1)
    assert isinstance(sens, pd.DataFrame)
    assert "parameter" in sens.columns


def test_sensitivity_regression_accepts_calib_period(proj):
    sens = proj.sensitivity(PARAM_RANGES, _obs(), method="regression",
                            calib_period=CALIB, n_samples=8, seed=1)
    assert isinstance(sens, pd.DataFrame)
    assert "parameter" in sens.columns


# ── scenarios facade ─────────────────────────────────────────────────────────

def test_scenarios_accepts_result_and_top(proj, monkeypatch):
    from spyswat.swat_calib.scenarios import ScenarioBatch
    captured = {}

    def fake_run(self, scenarios, param_sets, *, outputs=None, observed=None, **kw):
        captured["param_sets"] = param_sets
        captured["outputs"] = outputs
        return "batch-result"

    monkeypatch.setattr(ScenarioBatch, "run", fake_run)
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=4, seed=1, sensitivity=False)
    top = res.top(2)
    out = proj.scenarios([Scenario("s1")], [res, top],
                         outputs={"FLOW_OUTcms": [1]})
    assert out == "batch-result"
    assert captured["outputs"] == {"FLOW_OUTcms": [1]}
    names = [ps.name for ps in captured["param_sets"]]
    assert names == [f"run_{res.best_run_id}"] + [p.name for p in top]
    assert all(isinstance(ps, ParamSet) for ps in captured["param_sets"])


def test_scenarios_accepts_bare_result_and_param_set(proj, monkeypatch):
    from spyswat.swat_calib.scenarios import ScenarioBatch
    captured = {}

    def fake_run(self, scenarios, param_sets, *, outputs=None, observed=None, **kw):
        captured["param_sets"] = param_sets
        return "batch-result"

    monkeypatch.setattr(ScenarioBatch, "run", fake_run)
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=4, seed=1, sensitivity=False)

    assert proj.scenarios([Scenario("s1")], res, outputs={"FLOW_OUTcms": [1]}) == "batch-result"
    assert [ps.name for ps in captured["param_sets"]] == [f"run_{res.best_run_id}"]

    ps = ParamSet("p1", {"CN2.mgt": [(60.0, "v")]})
    assert proj.scenarios([Scenario("s1")], ps, outputs={"FLOW_OUTcms": [1]}) == "batch-result"
    assert captured["param_sets"] == [ps]


# ── apply facade ─────────────────────────────────────────────────────────────

def test_apply_dict_writes_and_warns(proj, caplog):
    with caplog.at_level("WARNING", logger="spyswat.swat_project"):
        proj.apply({"CN2.mgt": 50.0})
    assert "modified TxtInOut" in caplog.text
    assert read_cn2(str(proj.txinout.directory)) == 50.0


def test_apply_dict_non_v_methods_without_methods_raises(proj):
    with pytest.raises(ValueError, match="non-'v'"):
        proj.apply({"CN2.mgt": [(50.0, "r")]})


def test_apply_dict_non_v_with_subbasins_without_methods_raises(proj):
    with pytest.raises(ValueError, match="non-'v'"):
        proj.apply({"CN2.mgt": [(0.1, "r")]}, subbasins={"CN2.mgt": [1]})


def test_apply_param_set_and_result(proj, caplog):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    best_cn2 = res.best_params["CN2.mgt"][0][0]
    proj.apply(res)
    assert read_cn2(str(proj.txinout.directory)) == pytest.approx(best_cn2, abs=0.01)

    proj.apply(ParamSet("p1", {"CN2.mgt": [(60.0, "v")]}))
    assert read_cn2(str(proj.txinout.directory)) == 60.0


def test_apply_formatted_dict_with_methods_and_subbasins(proj):
    updates = proj.apply(
        {"CN2.mgt": [(0.1, "v")]},
        methods={"CN2.mgt": "r"},
        subbasins={"CN2.mgt": [1]},
    )
    assert updates == {"CN2.mgt": [(0.1, "r", [1])]}
    assert read_cn2(str(proj.txinout.directory)) == pytest.approx(35.0 * 1.1)
    sub2_cn2 = float((proj.txinout.directory / "000020001.mgt").read_text().splitlines()[10][:16])
    assert sub2_cn2 == pytest.approx(35.0)
