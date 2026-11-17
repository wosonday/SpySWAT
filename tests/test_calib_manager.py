"""Tests for CalibrationManager: run_batch NaN handling, sequential backup/restore, alignment."""
import types
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat.logger import Logger
from spyswat.swat_calib.calibration import CalibrationManager, ValidationRunner
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.calibration.calib_manager import check_observation_step
from spyswat.swat_calib.calibration.validation_runner import PeriodConfig
from spyswat.swat_calib.core import TxInOut, HRUManager
from spyswat.swat_calib.core.workingFolder_manager import WorkingFolderManager
from spyswat.swat_calib.io import SWATParam

from test_working_folder import (
    build_txinout, build_param_file, fake_runner, read_cn2, snapshot, FAIL_CN2, NOOP_CN2,
)

DATES = pd.date_range("2000-01-01", periods=10, freq="D")
METRICS = ["nse", "rmse"]


class StubStats:
    def calculate_statistics(self, obs, sim, metrics=None):
        return {m: float(sim.mean()) for m in (metrics or ["nse"])}


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
    def __init__(self, base, param, work, n_parallel=2, iprint="D", dates=DATES):
        self.txinout = TxInOut(str(base))
        self.param_file = SWATParam(str(param))
        self.HRU = HRUManager(self.txinout, self.param_file)
        self.WorkingFolder = WorkingFolderManager(self.txinout, work, n_parallel, param)
        self.WorkingFolder.setup()
        self.swat_exe = types.SimpleNamespace(swat_exe_path="fake_exe")
        self.FileCIO = types.SimpleNamespace(get_iprint=lambda: iprint)
        self.Output = StubOutput(base)
        self.Statistic = StubStats()
        self._dates = dates
        self.run_impl = None
        # inject the fake runner into run_parallel (swat.exe is not available)
        orig = self.WorkingFolder.run_parallel
        self.WorkingFolder.run_parallel = partial(orig, runner=fake_runner)

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


@pytest.fixture
def obs():
    return pd.Series(np.arange(10, dtype=float), index=DATES)


def _v(x):
    return {"CN2.mgt": x}


# ── run_batch ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("n_parallel", [1, 2, 4])
def test_run_batch_nan_rows_for_failed_runs_and_order_kept(proj, obs, n_parallel):
    proj.WorkingFolder.n_parallel = n_parallel
    proj.WorkingFolder.setup(overwrite=True)
    mgr = CalibrationManager(proj)
    sets = [_v(50.0), _v(FAIL_CN2), _v(60.0), _v(NOOP_CN2), _v(70.0)]
    df = mgr.run_batch(sets, obs, metrics=METRICS)
    assert len(df) == 5 and list(df.columns) == METRICS
    assert df["nse"].isna().tolist() == [False, True, False, True, False]
    assert df["rmse"].isna().tolist() == [False, True, False, True, False]
    assert df["nse"].dropna().tolist() == [50.0, 60.0, 70.0]
    assert not np.isinf(df.to_numpy(dtype=float)).any()


def test_run_batch_unreadable_output_is_nan(proj, obs):
    class Broken(StubProject):
        def worker(self, i):
            raise OSError("cannot read")
    proj.__class__ = Broken
    df = CalibrationManager(proj).run_batch([_v(50.0), _v(55.0)], obs, metrics=METRICS)
    assert len(df) == 2 and df.isna().all().all()


# ── sequential run_iteration ─────────────────────────────────────────

def _run_writes_rch(p):
    (p.txinout.directory / "output.rch").write_text("\n".join(["3.0"] * 10) + "\n")


def _setup_iteration(proj, run_impl):
    proj.run_impl = run_impl
    base = proj.txinout.directory
    (base / "keep.txt").write_text("user file")
    return base, snapshot(base)


def test_run_iteration_restores_inputs_keeps_dir_and_outputs(proj, obs):
    base, before = _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    score = mgr.run_iteration({"CN2.mgt": 0.1}, obs, metric="nse", methods={"CN2.mgt": "r"})
    assert score == pytest.approx(3.0)
    assert base.is_dir() and snapshot(base) == before
    assert (base / "output.rch").read_text().startswith("3.0")   # outputs left as produced
    assert (base / "output.std").exists()
    assert mgr._backup_dir is None
    # repeated iterations do not compound
    for _ in range(2):
        mgr.run_iteration({"CN2.mgt": 0.1}, obs, metric="nse", methods={"CN2.mgt": "r"})
    assert snapshot(base) == before


def test_run_iteration_restores_when_run_raises(proj, obs):
    def boom(p):
        raise OSError("swat crashed")
    base, before = _setup_iteration(proj, boom)
    with pytest.raises(RuntimeError, match="swat crashed"):
        CalibrationManager(proj).run_iteration({"CN2.mgt": 0.1}, obs, metric="nse",
                                               methods={"CN2.mgt": "r"})
    assert base.is_dir() and snapshot(base) == before


def test_run_iteration_stale_output_is_an_error(proj, obs):
    base, before = _setup_iteration(proj, lambda p: None)   # SWAT "runs" but writes nothing
    with pytest.raises(RuntimeError, match="fresh output.rch"):
        CalibrationManager(proj).run_iteration({"CN2.mgt": 50.0}, obs, metric="nse")
    assert snapshot(base) == before


def test_backup_restore_zero_arg_and_readonly(proj):
    import os, stat
    mgr = CalibrationManager(proj)
    base = proj.txinout.directory
    before = snapshot(base)
    mgr._backup_state()
    for f in base.glob("0*.mgt"):
        f.write_text("changed")
        os.chmod(f, stat.S_IREAD)
    mgr._restore_state()
    assert snapshot(base) == before
    mgr._restore_state()   # no-op when nothing is backed up


# ── _align_series ────────────────────────────────────────────────────

def test_align_series_ok_gives_datetime_index(proj, obs):
    mgr = CalibrationManager(proj)
    o, s = mgr._align_series(obs, pd.Series(np.arange(10.0) + 100))
    assert isinstance(s.index, pd.DatetimeIndex) and len(o) == len(s) == 10


def test_align_series_length_mismatch_raises(proj, obs):
    mgr = CalibrationManager(proj)
    with pytest.raises(ValueError, match=r"10.*7|7.*10") as ei:
        mgr._align_series(obs, pd.Series(np.arange(7.0)))
    assert "IDAF" in str(ei.value)


def test_align_series_never_returns_range_index(proj, obs):
    mgr = CalibrationManager(proj)
    for n in (0, 5, 11, 100):
        try:
            _, s = mgr._align_series(obs, pd.Series(np.zeros(n)))
        except ValueError:
            continue
        assert not isinstance(s.index, pd.RangeIndex)


def test_align_series_step_mismatch_and_empty_intersection(proj):
    mgr = CalibrationManager(proj)
    monthly = pd.Series(np.arange(5.0), index=pd.date_range("2000-01-01", periods=5, freq="MS"))
    with pytest.raises(ValueError, match="monthly but the simulation prints daily"):
        mgr._align_series(monthly, pd.Series(np.zeros(10)))
    other = pd.Series(np.arange(10.0), index=pd.date_range("1990-01-01", periods=10, freq="D"))
    with pytest.raises(ValueError, match="No common dates"):
        mgr._align_series(other, pd.Series(np.zeros(10)))


def test_align_series_daily_obs_with_monthly_sim_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = build_txinout(tmp_path)
    p = StubProject(base, build_param_file(tmp_path), tmp_path / "work", iprint="MS",
                    dates=pd.date_range("2000-01-01", periods=3, freq="MS"))
    daily = pd.Series(np.arange(10.0), index=DATES)
    with pytest.raises(ValueError, match="daily but the simulation prints monthly"):
        CalibrationManager(p)._align_series(daily, pd.Series(np.zeros(3)))
    monthly = pd.Series([1.0, 2.0, 3.0], index=p._dates)
    o, s_ = CalibrationManager(p)._align_series(monthly, pd.Series([1.0, 2.0, 3.0]))
    assert len(o) == 3 and isinstance(s_.index, pd.DatetimeIndex)


# ── check_observation_step ───────────────────────────────────────────

def _idx(*dates):
    return pd.DatetimeIndex(pd.to_datetime(list(dates)))


@pytest.mark.parametrize("dates, freq, ok", [
    (["2000-01-01", "2000-02-01", "2000-05-01"], "MS", True),      # monthly with gaps
    (["2000-01-01", "2000-02-01", "2000-05-01"], "D", False),
    (["2000-01-01", "2000-01-02", "2000-01-04"], "D", True),       # daily with gap
    (["2000-01-01", "2000-01-02", "2000-01-04"], "MS", False),
    (["2000-01-15", "2000-02-15"], "MS", False),                   # not first of month -> daily
    (["2000-01-15", "2000-02-15"], "D", True),
    (["2000-01-01", "2000-01-01 12:00"], "MS", False),             # same month twice -> daily
    (["2000-01-01 06:00", "2000-02-01 06:00"], "D", True),         # not midnight -> daily
    (["2000-03-01"], "D", True),                                   # single observation
    (["2000-03-01"], "MS", True),
    ([], "D", True),
])
def test_check_observation_step(dates, freq, ok):
    idx = pd.DatetimeIndex(pd.to_datetime(dates, format="mixed"))
    if ok:
        check_observation_step(idx, freq)
    else:
        with pytest.raises(ValueError):
            check_observation_step(idx, freq)


@pytest.mark.parametrize("freq", ["YS", "M", "H", None])
def test_check_observation_step_unsupported_freq(freq):
    with pytest.raises(ValueError, match="Unsupported"):
        check_observation_step(_idx("2000-01-01", "2000-01-02"), freq)


# ── restore failure handling ─────────────────────────────────────────

def _flaky_copy(monkeypatch, fail_times):
    state = {"n": 0}
    real = cm._copy_over

    def flaky(src, dst, *a, **k):
        if Path(dst).suffix == ".mgt" and state["n"] < fail_times:
            state["n"] += 1
            raise PermissionError("locked by antivirus")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(cm, "_copy_over", flaky)
    return state


def test_failed_restore_keeps_backup_and_never_compounds(proj, obs, monkeypatch):
    seen = []

    def run_impl(p):
        seen.append(read_cn2(str(p.txinout.directory)))
        _run_writes_rch(p)

    base, before = _setup_iteration(proj, run_impl)
    mgr = CalibrationManager(proj)
    _flaky_copy(monkeypatch, fail_times=1)

    with pytest.raises(RuntimeError, match="Could not restore"):
        mgr.run_iteration({"CN2.mgt": 0.5}, obs, metric="nse", methods={"CN2.mgt": "r"})
    kept = mgr._backup_dir
    assert kept is not None and kept.is_dir()
    assert snapshot(base) != before                    # user files still hold calibrated values

    # next iteration finishes the pending restore first, so relative changes start from 35
    mgr.run_iteration({"CN2.mgt": 0.5}, obs, metric="nse", methods={"CN2.mgt": "r"})
    assert seen == [pytest.approx(52.5), pytest.approx(52.5)]
    assert snapshot(base) == before
    assert mgr._backup_dir is None and not kept.exists()


def test_backup_refused_while_unrestored_backup_exists(proj, monkeypatch):
    mgr = CalibrationManager(proj)
    base = proj.txinout.directory
    before = snapshot(base)
    mgr._backup_state()
    kept = mgr._backup_dir
    for f in base.glob("0*.mgt"):
        f.write_text("changed")
    _flaky_copy(monkeypatch, fail_times=10 ** 6)
    with pytest.raises(RuntimeError, match=kept.name):
        mgr._backup_state()
    assert mgr._backup_dir == kept and kept.is_dir()
    monkeypatch.undo()
    mgr._restore_state()
    assert snapshot(base) == before and mgr._backup_dir is None


def test_run_error_and_restore_error_are_both_reported(proj, obs, monkeypatch):
    def boom(p):
        raise OSError("swat crashed")
    _setup_iteration(proj, boom)
    mgr = CalibrationManager(proj)
    _flaky_copy(monkeypatch, fail_times=10 ** 6)
    with pytest.raises(RuntimeError) as ei:
        mgr.run_iteration({"CN2.mgt": 0.5}, obs, metric="nse", methods={"CN2.mgt": "r"})
    msg = str(ei.value)
    assert "swat crashed" in msg and "could not be restored" in msg
    assert isinstance(ei.value.__cause__, OSError)
    monkeypatch.undo()
    mgr._restore_state()


# ── ValidationRunner ─────────────────────────────────────────────────

def test_validation_runner_leaves_inputs_unchanged(proj, obs, monkeypatch):
    seen = []

    def run_impl(p):
        seen.append(read_cn2(str(p.txinout.directory)))
        _run_writes_rch(p)

    base, before = _setup_iteration(proj, run_impl)
    monkeypatch.setattr(ValidationRunner, "_calibrate",
                        lambda self, *a: ({"CN2.mgt": 0.1}, 0.5))
    period = PeriodConfig("2000-01-01", "2000-01-05", "2000-01-06", "2000-01-10")
    runner = ValidationRunner(proj, {"CN2.mgt": ((-0.2, 0.2), "r")}, obs, period)
    out = runner.run()
    out2 = runner.run()
    assert seen == [pytest.approx(38.5), pytest.approx(38.5)]
    assert out["validation"]["nse"] == pytest.approx(3.0) and out2 == out
    assert snapshot(base) == before
    assert (base / "output.rch").read_text().startswith("3.0")
