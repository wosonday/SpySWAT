"""
Tests for the multi-site CalibrationManager path (API-2b): run_once(outputs=...),
run_batch multi-site columns/order/store, DeprecationWarning, warmup_end and
TxtInOut restore. Fake runner / fake output.rch — no SWAT executable.
"""
import types
import warnings
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat.logger import Logger
from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.core.workingFolder_manager import WorkingFolderManager, WorkerResult
from spyswat.swat_calib.io import SWATParam

from test_working_folder import build_txinout, build_param_file, snapshot

DATES = pd.date_range("2000-01-01", periods=10, freq="D")


class StubStats:
    def calculate_statistics(self, obs, sim, metrics=None):
        return {m: float(np.asarray(sim).mean()) for m in (metrics or ["nse"])}


class StubOutput:
    def __init__(self, directory):
        self.directory = Path(directory)

    def read_rch(self, columns=None, reach_id=None, freq=None):
        vals = [float(x) for x in (self.directory / "output.rch").read_text().split()]
        return pd.DataFrame({columns[-1]: vals})


class StubWorker:
    def __init__(self, directory):
        self.Output = StubOutput(directory)
        self.Statistic = StubStats()


class StubProject:
    def __init__(self, base, param, work, n_parallel=2, iprint="D", dates=DATES,
                 year_start=2000):
        self.txinout = TxInOut(str(base))
        self.working_folder = Path(work)
        self.param_file = SWATParam(str(param))
        self.HRU = HRUManager(self.txinout, self.param_file)
        self.WorkingFolder = WorkingFolderManager(self.txinout, work, n_parallel, param)
        self.WorkingFolder.setup()
        self.swat_exe = types.SimpleNamespace(swat_exe_path="fake_exe")
        self.FileCIO = types.SimpleNamespace(get_iprint=lambda: iprint,
                                             year_start=year_start)
        self.Output = StubOutput(base)
        self.Statistic = StubStats()
        self._dates = dates
        self.run_impl = None

    def worker(self, i):
        return StubWorker(self.WorkingFolder.worker_dirs[i - 1])

    def get_date_range(self, freq="D"):
        return self._dates

    def run(self):
        self.run_impl(self)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logger, "init_queue_listener", classmethod(lambda cls, **k: None))
    monkeypatch.setattr(Logger, "stop_listener", classmethod(lambda cls: None))
    base = build_txinout(tmp_path)
    param = build_param_file(tmp_path)
    return StubProject(base, param, tmp_path / "work")


class FakeStore:
    """Duck-typed session store: records ``add_run`` calls in order."""

    def __init__(self):
        self.runs = []

    def add_run(self, run_id, *, params, status, error, score, is_initial,
                series, site_metrics, time=None):
        self.runs.append({
            "run_id": run_id, "params": params, "status": status, "error": error,
            "score": score, "is_initial": is_initial, "series": series,
            "site_metrics": site_metrics,
        })


def _run_writes_rch(p):
    (p.txinout.directory / "output.rch").write_text("\n".join(["3.0"] * 10) + "\n")


# ── run_once(outputs=...) ───────────────────────────────────────────────────

def test_run_once_outputs_returns_dated_dict(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    sim = mgr.run_once({"CN2.mgt": 50.0}, outputs={"FLOW_OUTcms": [1, 2]})
    assert set(sim) == {("FLOW_OUTcms", 1), ("FLOW_OUTcms", 2)}
    for series in sim.values():
        assert isinstance(series.index, pd.DatetimeIndex)
        assert list(series.index) == list(DATES)
        assert series.tolist() == [3.0] * 10


def test_run_once_without_outputs_keeps_series_and_no_warning(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        sim = mgr.run_once({"CN2.mgt": 50.0})
    assert isinstance(sim, pd.Series)
    assert sim.tolist() == [3.0] * 10


def test_run_once_explicit_old_kwargs_warn(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    with pytest.warns(DeprecationWarning, match="deprecated"):
        mgr.run_once({"CN2.mgt": 50.0}, reach_id=1, output_variable="FLOW_OUTcms")


# ── warmup_end ──────────────────────────────────────────────────────────────

def test_warmup_end_is_first_day_after_skip(proj):
    mgr = CalibrationManager(proj)
    assert mgr.warmup_end() == pd.Timestamp(2000, 1, 1)


def test_warmup_end_none_when_filecio_has_no_year_start(proj):
    proj.FileCIO = types.SimpleNamespace(get_iprint=lambda: "D")
    assert CalibrationManager(proj).warmup_end() is None


# ── multi-site run_batch ────────────────────────────────────────────────────

def _install_fake_run_parallel(proj, outputs):
    """Replace run_parallel with an in-process fake writing plain-number output.rch."""
    wf = proj.WorkingFolder

    def fake_run_parallel(swat_exe, param_sets=None, log_queue=None, *,
                          extract=None, runner=None, prepare=None, overlays=None,
                          timeout_s=None):
        results = []
        for i, ps in enumerate(param_sets):
            wdir = wf.worker_dirs[i]
            try:
                cn2 = float(ps["CN2.mgt"][0][0])
                (wdir / "output.rch").write_text("\n".join([repr(cn2)] * 10) + "\n")
                vals = [float(x) for x in (wdir / "output.rch").read_text().split()]
                payload = {(var, reach): pd.Series(vals)
                           for var, reaches in outputs.items() for reach in reaches}
                results.append(WorkerResult(True, None, 0.0, str(wdir), payload))
            except Exception as e:
                results.append(WorkerResult(False, f"{type(e).__name__}: {e}",
                                             0.0, str(wdir), None))
        return results

    wf.run_parallel = fake_run_parallel


def _two_site_obs():
    obs = {
        ("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES),
        ("SED_OUTtons", 51): pd.Series(np.arange(10, dtype=float) * 2 + 1, index=DATES),
    }
    return obs


def test_run_batch_multisite_columns_and_submission_order(proj):
    outputs = {"FLOW_OUTcms": [1], "SED_OUTtons": [51]}
    _install_fake_run_parallel(proj, outputs)
    mgr = CalibrationManager(proj)
    df = mgr.run_batch(
        [{"CN2.mgt": 50.0}, {"CN2.mgt": 60.0}, {"CN2.mgt": 70.0}],
        _two_site_obs(), metrics=("nse",), metric="nse", outputs=outputs,
        calib_period=("2000-01-01", "2000-01-10"),
    )
    assert list(df.columns) == ["score", "nse@FLOW_OUTcms@1", "nse@SED_OUTtons@51"]
    assert len(df) == 3
    # each site's nse depends only on the sim (constant CN2), so the score is
    # deterministic per run and rows stay in submission (param) order.
    assert df["nse@FLOW_OUTcms@1"].notna().all()
    assert df["score"].tolist() == pytest.approx(
        (df["nse@FLOW_OUTcms@1"] + df["nse@SED_OUTtons@51"]) / 2
    )
    # distinct runs -> distinct scores, in increasing CN2 order (constant sim
    # diverges further from the observations, so NSE falls monotonically)
    assert df["score"].is_monotonic_decreasing


def test_run_batch_multisite_fake_store_receives_runs_in_order(proj):
    outputs = {"FLOW_OUTcms": [1], "SED_OUTtons": [51]}
    _install_fake_run_parallel(proj, outputs)
    mgr = CalibrationManager(proj)
    store = FakeStore()
    df = mgr.run_batch(
        [{"CN2.mgt": 50.0}, {"CN2.mgt": 60.0}, {"CN2.mgt": 70.0}],
        _two_site_obs(), metrics=("nse",), metric="nse", outputs=outputs,
        calib_period=("2000-01-01", "2000-01-10"), store=store, is_initial=True,
    )
    assert [r["run_id"] for r in store.runs] == [1, 2, 3]
    assert [r["status"] for r in store.runs] == ["ok", "ok", "ok"]
    assert all(r["is_initial"] for r in store.runs)
    assert [r["params"] for r in store.runs] == [
        {"CN2.mgt": [(50.0, "v")]}, {"CN2.mgt": [(60.0, "v")]},
        {"CN2.mgt": [(70.0, "v")]},
    ]
    assert [r["score"] for r in store.runs] == pytest.approx(df["score"].tolist())
    # the store is the log: no flat RunLog files were written
    assert not (proj.working_folder / "calibration_results").exists()


def test_run_batch_multisite_explicit_run_ids(proj):
    outputs = {"FLOW_OUTcms": [1]}
    _install_fake_run_parallel(proj, outputs)
    mgr = CalibrationManager(proj)
    store = FakeStore()
    mgr.run_batch(
        [{"CN2.mgt": 50.0}, {"CN2.mgt": 60.0}],
        {("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES)},
        metrics=("nse",), metric="nse", outputs=outputs,
        calib_period=("2000-01-01", "2000-01-10"), store=store,
        run_ids=[10, 11],
    )
    assert [r["run_id"] for r in store.runs] == [10, 11]


def test_run_batch_multisite_run_ids_continue_counter(proj):
    outputs = {"FLOW_OUTcms": [1]}
    _install_fake_run_parallel(proj, outputs)
    mgr = CalibrationManager(proj)
    obs = {("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES)}
    store1, store2 = FakeStore(), FakeStore()
    mgr.run_batch([{"CN2.mgt": 50.0}], obs, metrics=("nse",), metric="nse",
                  outputs=outputs, calib_period=("2000-01-01", "2000-01-10"),
                  store=store1)
    mgr.run_batch([{"CN2.mgt": 60.0}], obs, metrics=("nse",), metric="nse",
                  outputs=outputs, calib_period=("2000-01-01", "2000-01-10"),
                  store=store2)
    assert [r["run_id"] for r in store1.runs] == [1]
    assert [r["run_id"] for r in store2.runs] == [2]


# ── multi-site run_iteration ────────────────────────────────────────────────

def test_run_iteration_multisite_restores_txinout(proj):
    proj.run_impl = _run_writes_rch
    base = proj.txinout.directory
    before = snapshot(base)
    mgr = CalibrationManager(proj)
    obs = {("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES)}
    score = mgr.run_iteration(
        {"CN2.mgt": 50.0}, obs, metric="nse", outputs={"FLOW_OUTcms": [1]},
        calib_period=("2000-01-01", "2000-01-10"), methods={"CN2.mgt": "r"},
    )
    assert np.isfinite(score)
    assert snapshot(base) == before
    assert mgr._backup_dir is None


def test_run_iteration_multisite_uses_store_after_restore(proj):
    proj.run_impl = _run_writes_rch
    base = proj.txinout.directory
    before = snapshot(base)
    mgr = CalibrationManager(proj)
    store = FakeStore()
    obs = {("FLOW_OUTcms", 1): pd.Series(np.arange(10, dtype=float), index=DATES)}
    score = mgr.run_iteration(
        {"CN2.mgt": 50.0}, obs, metric="nse", outputs={"FLOW_OUTcms": [1]},
        calib_period=("2000-01-01", "2000-01-10"), store=store,
    )
    assert len(store.runs) == 1
    assert store.runs[0]["run_id"] == 1
    assert store.runs[0]["status"] == "ok"
    assert store.runs[0]["score"] == pytest.approx(score)
    assert snapshot(base) == before


# ── deprecation warnings at the manager entry points ────────────────────────

def test_run_iteration_explicit_old_kwargs_warn(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    obs = pd.Series(np.arange(10, dtype=float), index=DATES)
    with pytest.warns(DeprecationWarning, match="deprecated"):
        mgr.run_iteration({"CN2.mgt": 50.0}, obs, metric="nse",
                          reach_id=1, output_variable="FLOW_OUTcms")


def test_run_iteration_no_old_kwargs_does_not_warn(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    obs = pd.Series(np.arange(10, dtype=float), index=DATES)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        mgr.run_iteration({"CN2.mgt": 50.0}, obs, metric="nse")


def test_preflight_runs_before_any_swat_run(proj):
    proj.run_impl = _run_writes_rch
    mgr = CalibrationManager(proj)
    obs = {("FLOW_OUTcms", 1): pd.Series([5.0] * 10, index=DATES)}  # zero variance
    with pytest.raises(ValueError, match="zero variance"):
        mgr.run_iteration(
            {"CN2.mgt": 50.0}, obs, metric="nse", outputs={"FLOW_OUTcms": [1]},
            calib_period=("2000-01-01", "2000-01-10"),
        )
