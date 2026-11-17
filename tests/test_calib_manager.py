"""Tests for CalibrationManager: run_batch NaN handling, sequential backup/restore, alignment."""
import types
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat.logger import Logger
from spyswat.swat_calib.calibration import CalibrationManager
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


def test_align_series_coarser_obs_and_empty_intersection(proj):
    mgr = CalibrationManager(proj)
    monthly = pd.Series(np.arange(5.0), index=pd.date_range("2000-01-01", periods=5, freq="MS"))
    with pytest.raises(ValueError, match="coarser"):
        mgr._align_series(monthly, pd.Series(np.zeros(10)))
    other = pd.Series(np.arange(10.0), index=pd.date_range("1990-01-01", periods=10, freq="D"))
    with pytest.raises(ValueError, match="No common dates"):
        mgr._align_series(other, pd.Series(np.zeros(10)))
