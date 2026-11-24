"""Tests for ``CalibrationResult``: dict-style access, top/select, best_param_set,
load round-trip and the raw-params store adapter. Synthetic data only, no SWAT."""
import numpy as np
import pandas as pd
import pytest

from spyswat.swat_calib.calibration.result import (
    CalibrationResult, RawParamsStore, raw_params,
)
from spyswat.swat_calib.calibration.session_store import SessionStore
from spyswat.swat_calib.scenarios.model import ParamSet

DATES = pd.date_range("2000-01-01", periods=5, freq="D")
PARAMS = ["CN2.mgt", "ALPHA_BF.gw"]
SITES = [("FLOW_OUTcms", 1), ("SED_OUTtons", 51)]


def _series(v):
    return pd.Series([float(v)] * 5, index=DATES)


def _add_run(store, run_id, cn2, alpha, score, nse_calib, nse_valid):
    failed = score is None
    site_metrics = {}
    if not failed:
        site_metrics = {
            ("FLOW_OUTcms", 1): {"nse_calib": nse_calib, "nse_valid": nse_valid},
            ("SED_OUTtons", 51): {"nse_calib": nse_calib + 0.05, "nse_valid": nse_valid + 0.05},
        }
    store.add_run(
        run_id,
        params={"CN2.mgt": cn2, "ALPHA_BF.gw": alpha},
        status="failed" if failed else "ok",
        error="boom" if failed else None,
        score=np.nan if failed else score,
        is_initial=True,
        series={site: _series(run_id) for site in SITES},
        site_metrics=site_metrics,
    )


def _store(tmp_path, metric="nse", methods=None, subbasins=None, failed=True):
    store = SessionStore(
        tmp_path / "session",
        signature={
            "algorithm": "glue", "metric": metric, "seed": 1,
            "methods": methods or {}, "subbasins": subbasins or {},
            "observed_sites": [[v, r] for (v, r) in SITES],
        },
        param_names=PARAMS,
        sites=SITES,
    )
    _add_run(store, 1, 50.0, 0.5, 0.8, 0.8, 0.7)
    _add_run(store, 2, 60.0, 0.6, 0.6, 0.6, 0.5)
    if failed:
        _add_run(store, 3, 70.0, 0.7, None, np.nan, np.nan)
    _add_run(store, 4, 40.0, 0.4, 0.9, 0.9, 0.85)
    store.close()
    return store


def _result(tmp_path, metric="nse", methods=None, subbasins=None, failed=True):
    store = _store(tmp_path, metric, methods, subbasins, failed)
    runs = store.runs()
    from spyswat.swat_calib.calibration.result import best_run, raw_params_for_run, format_params
    best_id, best_score = best_run(runs, metric)
    best_params = format_params(raw_params_for_run(runs, best_id), methods or {}, subbasins or {})
    return CalibrationResult(
        best_params=best_params, best_score=best_score, best_run_id=best_id,
        metric=metric, runs=runs, session_dir=tmp_path / "session",
        algorithm="glue", methods=methods or {}, subbasins=subbasins or {},
        sites=SITES, store=store,
    )


# ── dict-style access ────────────────────────────────────────────────────────

def test_dict_style_access(tmp_path):
    res = _result(tmp_path)
    assert res["best_score"] == pytest.approx(0.9)
    assert res["best_params"]["CN2.mgt"][0][0] == pytest.approx(40.0)
    assert res["history"] is res.runs


def test_unknown_key_raises(tmp_path):
    res = _result(tmp_path)
    with pytest.raises(KeyError):
        res["nope"]


# ── top ──────────────────────────────────────────────────────────────────────

def test_top_max_metric_best_first_and_drops_failed(tmp_path):
    res = _result(tmp_path, metric="nse")
    top = res.top(2)
    assert [p.name for p in top] == ["run_4", "run_1"]
    assert all(isinstance(p, ParamSet) for p in top)
    # failed run 3 is dropped; methods default to "v"
    assert top[0].updates["CN2.mgt"] == [(40.0, "v")]


def test_top_minimize_metric(tmp_path):
    store = SessionStore(tmp_path / "s", signature={"metric": "rmse"},
                         param_names=PARAMS, sites=SITES)
    for run_id, score in ((1, 3.0), (2, 1.0), (3, 2.0)):
        store.add_run(run_id, params={"CN2.mgt": float(run_id), "ALPHA_BF.gw": 0.5},
                      status="ok", error=None, score=score, is_initial=True,
                      series={site: _series(run_id) for site in SITES},
                      site_metrics={site: {"rmse_calib": score} for site in SITES})
    store.close()
    runs = store.runs()
    from spyswat.swat_calib.calibration.result import best_run, raw_params_for_run, format_params
    best_id, best_score = best_run(runs, "rmse")
    res = CalibrationResult(
        best_params=format_params(raw_params_for_run(runs, best_id), {}, {}),
        best_score=best_score, best_run_id=best_id, metric="rmse", runs=runs,
        session_dir=tmp_path / "s", store=store, sites=SITES,
    )
    top = res.top(3)
    # rmse is minimised: 1.0 < 2.0 < 3.0
    assert [p.name for p in top] == ["run_2", "run_3", "run_1"]


def test_top_methods_and_subbasins_carried(tmp_path):
    res = _result(tmp_path, metric="nse", methods={"CN2.mgt": "r"},
                  subbasins={"CN2.mgt": [71, 45]})
    top = res.top(1)
    assert top[0].updates["CN2.mgt"] == [(40.0, "r", [71, 45])]


# ── select ───────────────────────────────────────────────────────────────────

def test_select_score_condition(tmp_path):
    res = _result(tmp_path, metric="nse")
    picked = res.select(score__gt=0.7)
    assert [p.name for p in picked] == ["run_1", "run_4"]


def test_select_site_and_period(tmp_path):
    res = _result(tmp_path, metric="nse")
    # FLOW site valid nse: run1=0.7, run2=0.5, run4=0.85
    picked = res.select(nse__gte=0.7, site=("FLOW_OUTcms", 1), period="valid")
    assert [p.name for p in picked] == ["run_1", "run_4"]


def test_select_how_any_vs_all(tmp_path):
    # Asymmetric per-site metrics: FLOW and SED disagree on which runs pass.
    store = SessionStore(tmp_path / "s", signature={"metric": "nse",
                         "observed_sites": [[v, r] for (v, r) in SITES]},
                         param_names=PARAMS, sites=SITES)
    spec = [
        (1, 0.9, 0.1),   # FLOW passes gt 0.5, SED fails
        (2, 0.1, 0.9),   # SED passes, FLOW fails
        (3, 0.9, 0.9),   # both pass
    ]
    for run_id, flow, sed in spec:
        store.add_run(run_id, params={"CN2.mgt": float(run_id), "ALPHA_BF.gw": 0.5},
                      status="ok", error=None, score=float(run_id), is_initial=True,
                      series={site: _series(run_id) for site in SITES},
                      site_metrics={
                          ("FLOW_OUTcms", 1): {"nse_calib": flow},
                          ("SED_OUTtons", 51): {"nse_calib": sed},
                      })
    store.close()
    from spyswat.swat_calib.calibration.result import best_run, raw_params_for_run, format_params
    runs = store.runs()
    best_id, best_score = best_run(runs, "nse")
    res = CalibrationResult(
        best_params=format_params(raw_params_for_run(runs, best_id), {}, {}),
        best_score=best_score, best_run_id=best_id, metric="nse", runs=runs,
        session_dir=tmp_path / "s", store=store, sites=SITES,
    )
    all_picked = res.select(nse__gt=0.5, how="all")
    any_picked = res.select(nse__gt=0.5, how="any")
    assert [p.name for p in all_picked] == ["run_3"]
    assert [p.name for p in any_picked] == ["run_1", "run_2", "run_3"]


def test_select_invalid_operator_raises(tmp_path):
    res = _result(tmp_path)
    with pytest.raises(ValueError, match="operator"):
        res.select(nse__bogus=0.5)


# ── best_param_set ───────────────────────────────────────────────────────────

def test_best_param_set_named_after_run(tmp_path):
    res = _result(tmp_path, metric="nse", methods={"CN2.mgt": "r"})
    ps = res.best_param_set()
    assert ps.name == "run_4"
    assert ps.updates["CN2.mgt"] == [(40.0, "r")]


# ── load round-trip ──────────────────────────────────────────────────────────

def test_load_equals_returned_result(tmp_path):
    res = _result(tmp_path, metric="nse", methods={"CN2.mgt": "r"})
    loaded = CalibrationResult.load(tmp_path / "session")
    assert loaded.best_score == pytest.approx(res.best_score)
    assert loaded.best_run_id == res.best_run_id
    assert loaded.best_params == res.best_params
    assert loaded.metric == res.metric
    assert loaded.algorithm == "glue"
    pd.testing.assert_frame_equal(loaded.runs, res.runs)
    # series are lazy but reachable
    ser = loaded.series("FLOW_OUTcms", 1)
    assert list(ser.columns) == ["run_1", "run_2", "run_3", "run_4"]


def test_load_top_works_on_loaded_result(tmp_path):
    _result(tmp_path, metric="nse", methods={"CN2.mgt": "r"})
    loaded = CalibrationResult.load(tmp_path / "session")
    assert [p.name for p in loaded.top(1)] == ["run_4"]
    assert loaded.top(1)[0].updates["CN2.mgt"] == [(40.0, "r")]


# ── RawParamsStore adapter ───────────────────────────────────────────────────

def test_raw_params_converts_formatted_to_raw():
    formatted = {"CN2.mgt": [(75.0, "r", [1, 2])], "ALPHA_BF.gw": [(0.5, "v")]}
    assert raw_params(formatted) == {"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.5}


def test_raw_params_store_delegates_and_converts(tmp_path):
    inner = SessionStore(tmp_path / "s", signature={}, param_names=["CN2.mgt"],
                         sites=[("FLOW_OUTcms", 1)])
    wrapped = RawParamsStore(inner)
    wrapped.add_run(1, params={"CN2.mgt": [(75.0, "r")]}, status="ok", error=None,
                    score=0.5, is_initial=True,
                    series={("FLOW_OUTcms", 1): _series(1)},
                    site_metrics={("FLOW_OUTcms", 1): {"nse_calib": 0.5}})
    inner.close()
    runs = wrapped.runs()
    assert runs["CN2.mgt"].iloc[0] == 75.0
