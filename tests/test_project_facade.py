"""End-to-end tests for the 0.3.0 facade on ``SWATProject`` (API-4).

A real ``SWATProject`` is built on a synthetic TxtInOut, but the SWAT execution
layer is faked in-process (no ``swat.exe``, no worker subprocesses): the batch
path replaces ``WorkingFolderManager.run_parallel`` and the sequential path
replaces ``swat_exe.run`` + output reading. The session layout, best-run metrics,
regression sensitivity and TxtInOut restore are all exercised for real.
"""
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
            (wdir / "output.rch").write_text("\n".join([repr(cn2)] * 10) + "\n")
            extractor = pickle.loads(pickle.dumps(extract))
            payload = extractor(str(wdir))
            results.append(WorkerResult(True, None, 0.0, str(wdir), payload))
        return results

    wf.run_parallel = fake_run_parallel

    def fake_swat_run(directory):
        cn2 = read_cn2(directory)
        (Path(directory) / "output.rch").write_text(
            "\n".join([repr(cn2)] * 10) + "\n")

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

    # TxtInOut input files are byte-identical afterwards
    assert snapshot(proj.txinout.directory) == before


@pytest.mark.parametrize("algorithm,kwargs", [
    ("pso", dict(n_particles=4, max_iterations=1)),
    ("dds", dict(n_iterations=5)),
])
def test_calibration_other_algorithms(proj, algorithm, kwargs):
    before = snapshot(proj.txinout.directory)
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, VALID,
                           algorithm=algorithm, seed=1, **kwargs)
    assert res.algorithm == algorithm
    assert np.isfinite(res.best_score)
    assert list(res.runs["run_id"]) == sorted(res.runs["run_id"])
    # sensitivity is a DataFrame or a status (small populations may be insufficient)
    assert res.sensitivity is not None or res.sensitivity_status
    assert snapshot(proj.txinout.directory) == before


def test_calibration_load_roundtrip(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, VALID,
                           algorithm="glue", n_samples=8, seed=1)
    loaded = CalibrationResult.load(res.session_dir)
    assert loaded.best_score == pytest.approx(res.best_score)
    assert loaded.best_run_id == res.best_run_id
    assert loaded.best_params == res.best_params
    assert loaded.metric == res.metric
    pd.testing.assert_frame_equal(loaded.runs, res.runs)


def test_calibration_existing_session_resume_false_raises(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    name = res.session_dir.name
    with pytest.raises(FileExistsError):
        proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                         n_samples=3, seed=1, session=name, resume=False,
                         sensitivity=False)


def test_calibration_existing_session_resume_true_not_implemented(proj):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    with pytest.raises(NotImplementedError, match="API-5"):
        proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                         n_samples=3, seed=1, session=res.session_dir.name,
                         resume=True, sensitivity=False)


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


# ── apply facade ─────────────────────────────────────────────────────────────

def test_apply_dict_writes_and_warns(proj, caplog):
    with caplog.at_level("WARNING", logger="spyswat.swat_project"):
        proj.apply({"CN2.mgt": 50.0})
    assert "modified TxtInOut" in caplog.text
    assert read_cn2(str(proj.txinout.directory)) == 50.0


def test_apply_dict_non_v_methods_without_methods_raises(proj):
    with pytest.raises(ValueError, match="non-'v'"):
        proj.apply({"CN2.mgt": [(50.0, "r")]})


def test_apply_param_set_and_result(proj, caplog):
    res = proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                           n_samples=3, seed=1, sensitivity=False)
    best_cn2 = res.best_params["CN2.mgt"][0][0]
    proj.apply(res)
    assert read_cn2(str(proj.txinout.directory)) == pytest.approx(best_cn2, abs=0.01)

    proj.apply(ParamSet("p1", {"CN2.mgt": [(60.0, "v")]}))
    assert read_cn2(str(proj.txinout.directory)) == 60.0
