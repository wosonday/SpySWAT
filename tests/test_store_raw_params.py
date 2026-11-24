"""
API-2d: ``CalibrationManager`` must hand the session store raw ``{name: float}``
parameters, never the formatted ``{name: [(value, method[, subs])]}`` dict.

A real ``SessionStore`` is written to ``tmp_path`` and re-opened: ``runs()`` has
to return the exact float values for raw and for pre-formatted parameter sets,
with a method and with subbasins. Fake runner / plain-number ``output.rch`` — no
SWAT executable (helpers reused from ``test_calib_multisite``).
"""
import numpy as np
import pandas as pd
import pytest

from spyswat.logger import Logger
from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.calibration.session_store import SessionStore

from test_calib_multisite import (
    DATES, FakeOutputFileManager, StubProject, _install_fake_run_parallel,
    _run_writes_rch, _two_site_obs,
)
from test_working_folder import build_param_file, build_txinout

OUTPUTS = {"FLOW_OUTcms": [1], "SED_OUTtons": [51]}
SITES = [("FLOW_OUTcms", 1), ("SED_OUTtons", 51)]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logger, "init_queue_listener", classmethod(lambda cls, **k: None))
    monkeypatch.setattr(Logger, "stop_listener", classmethod(lambda cls: None))
    monkeypatch.setattr(cm, "OutputFileManager", FakeOutputFileManager)
    base = build_txinout(tmp_path)
    param = build_param_file(tmp_path)
    return StubProject(base, param, tmp_path / "work")


def _new_store(tmp_path, param_names=("CN2.mgt",)):
    return SessionStore(
        tmp_path / "session",
        signature={"fixture": "api-2d"},
        param_names=list(param_names),
        sites=SITES,
    )


def _stored_params(tmp_path, name="CN2.mgt"):
    runs = SessionStore.open(tmp_path / "session").runs()
    return runs[name].tolist()


# ── run_batch ───────────────────────────────────────────────────────────────

def test_run_batch_stores_raw_float_params_from_raw_input(proj, tmp_path):
    _install_fake_run_parallel(proj)
    store = _new_store(tmp_path)
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 50.0}, {"CN2.mgt": 60.5}], _two_site_obs(),
        metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=("2000-01-01", "2000-01-10"), store=store,
    )
    store.close()
    assert _stored_params(tmp_path) == [50.0, 60.5]


def test_run_batch_stores_raw_float_params_from_formatted_input(proj, tmp_path):
    _install_fake_run_parallel(proj)
    store = _new_store(tmp_path)
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": [(55.25, "r")]}, {"CN2.mgt": [(70.75, "r", [1, 2])]}],
        _two_site_obs(), metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=("2000-01-01", "2000-01-10"), store=store,
    )
    store.close()
    assert _stored_params(tmp_path) == [55.25, 70.75]


def test_run_batch_stores_raw_float_params_with_methods_kwargs(proj, tmp_path):
    _install_fake_run_parallel(proj)
    store = _new_store(tmp_path)
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 42.125}], _two_site_obs(), metrics=("nse",), metric="nse",
        outputs=OUTPUTS, calib_period=("2000-01-01", "2000-01-10"), store=store,
        methods={"CN2.mgt": "r"}, subbasins={"CN2.mgt": [1]},
    )
    store.close()
    assert _stored_params(tmp_path) == [42.125]


# ── run_iteration ───────────────────────────────────────────────────────────

def _one_site_obs():
    return {("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES)}


def test_run_iteration_stores_raw_float_params_from_raw_input(proj, tmp_path):
    proj.run_impl = _run_writes_rch
    store = _new_store(tmp_path)
    CalibrationManager(proj).run_iteration(
        {"CN2.mgt": 48.5}, _one_site_obs(), metric="nse",
        outputs={"FLOW_OUTcms": [1]}, calib_period=("2000-01-01", "2000-01-10"),
        store=store,
    )
    store.close()
    assert _stored_params(tmp_path) == [48.5]


def test_run_iteration_stores_raw_float_params_from_formatted_input(proj, tmp_path):
    proj.run_impl = _run_writes_rch
    store = _new_store(tmp_path)
    CalibrationManager(proj).run_iteration(
        {"CN2.mgt": [(61.75, "r", [1, 2])]}, _one_site_obs(), metric="nse",
        outputs={"FLOW_OUTcms": [1]}, calib_period=("2000-01-01", "2000-01-10"),
        store=store,
    )
    store.close()
    assert _stored_params(tmp_path) == [61.75]
