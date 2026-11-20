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
from spyswat.swat_calib.calibration import run_log
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
        self.working_folder = Path(work)
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

def _validation_setup(proj, monkeypatch, obs):
    def run_impl(p):
        _run_writes_rch(p)
    base, before = _setup_iteration(proj, run_impl)
    monkeypatch.setattr(ValidationRunner, "_calibrate",
                        lambda self, *a: ({"CN2.mgt": 0.1}, 0.5))
    period = PeriodConfig("2000-01-01", "2000-01-05", "2000-01-06", "2000-01-10")
    runner = ValidationRunner(proj, {"CN2.mgt": ((-0.2, 0.2), "r", [1, 2])}, obs, period)
    return base, before, runner


def _all_cn2(base):
    return [float(f.read_text().splitlines()[10][:16]) for f in sorted(base.glob("0*.mgt"))]


def test_validation_runner_keeps_best_params_by_default_and_saves_results(
        proj, obs, monkeypatch, caplog):
    base, before, runner = _validation_setup(proj, monkeypatch, obs)
    with caplog.at_level("WARNING"):
        out = runner.run()
    assert _all_cn2(base) == pytest.approx([38.5, 38.5, 38.5])    # calibrated values stay
    assert any("CALIBRATED" in r.message for r in caplog.records)
    assert (base / "output.rch").read_text().startswith("3.0")
    assert out["validation"]["nse"] == pytest.approx(3.0)

    bp = pd.read_csv(runner.manager.session_path("best_params"))
    assert list(bp.columns) == ["name", "value", "method", "subbasins"]
    assert bp.iloc[0].tolist() == ["CN2.mgt", 0.1, "r", "1;2"]
    val = pd.read_csv(runner.manager.session_path("validation"))
    assert list(val.columns) == ["period", "metric", "value"]
    assert val.iloc[0].tolist() == ["calibration", "nse", 0.5]
    assert val.iloc[1].tolist() == ["validation", "nse", 3.0]
    runs = pd.read_csv(runner.manager.session_files["metrics"])
    assert len(runs) == 1 and runs.loc[0, "status"] == "ok"
    assert len(pd.read_csv(runner.manager.session_files["outputs"])) == 10


def test_validation_runner_restore_true_gives_original_inputs(proj, obs, monkeypatch):
    base, before, runner = _validation_setup(proj, monkeypatch, obs)
    runner.run(restore=True)
    assert snapshot(base) == before
    assert (base / "output.rch").read_text().startswith("3.0")
    assert runner.manager.session_path("best_params").exists()   # saved before the restore


# ── per-run result log ───────────────────────────────────────────────

def _metrics(mgr):
    return pd.read_csv(mgr.session_files["metrics"])


def _outputs(mgr):
    return pd.read_csv(mgr.session_files["outputs"])


def _iter(mgr, obs, cn2=0.1):
    return mgr.run_iteration({"CN2.mgt": cn2}, obs, metric="nse", methods={"CN2.mgt": "r"})


def test_sequential_runs_append_one_row_each(proj, obs):
    _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    assert mgr.results_dir == proj.working_folder / "calibration_results"
    _iter(mgr, obs, 0.1)
    assert _metrics(mgr).shape[0] == 1                 # already on disk before the next run
    _iter(mgr, obs, 0.2)
    m = _metrics(mgr)
    assert m["run_id"].tolist() == [1, 2]
    assert set(m["mode"]) == {"sequential"} and set(m["status"]) == {"ok"}
    assert m["CN2.mgt"].tolist() == [0.1, 0.2] and set(m["CN2.mgt__method"]) == {"r"}
    assert m["nse"].tolist() == [3.0, 3.0]
    assert m.loc[0, "reach_id"] == 1 and m.loc[0, "output_variable"] == "FLOW_OUTcms"
    o = _outputs(mgr)
    assert len(o) == 20 and set(o["run_id"]) == {1, 2}
    assert list(o.columns) == ["run_id", "date", "variable", "reach", "value"]
    assert o.loc[0, "date"] == "2000-01-01" and o.loc[0, "value"] == 3.0
    assert set(mgr.session_files) == {"metrics", "outputs"}


def test_parallel_runs_log_failed_job_without_output_rows(proj, obs):
    mgr = CalibrationManager(proj)
    df = mgr.run_batch([_v(50.0), _v(FAIL_CN2), _v(60.0)], obs, metrics=METRICS)
    m = _metrics(mgr)
    assert m["run_id"].tolist() == [1, 2, 3] and set(m["mode"]) == {"parallel"}
    assert m["status"].tolist() == ["ok", "failed", "ok"]
    assert "boom" in m.loc[1, "error"]
    assert m.loc[1, METRICS].isna().all() and m.loc[0, "nse"] == 50.0
    assert m["CN2.mgt"].tolist() == [50.0, FAIL_CN2, 60.0]
    assert set(_outputs(mgr)["run_id"]) == {1, 3}
    assert df["nse"].isna().tolist() == [False, True, False]   # scores/order unchanged


def test_log_survives_exception_in_later_run(proj, obs):
    base, _ = _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    _iter(mgr, obs)

    def boom(p):
        raise OSError("swat crashed")
    proj.run_impl = boom
    with pytest.raises(RuntimeError, match="swat crashed"):
        _iter(mgr, obs, 0.2)
    m = _metrics(mgr)
    assert m["status"].tolist() == ["ok", "failed"]
    assert "swat crashed" in m.loc[1, "error"] and np.isnan(m.loc[1, "nse"])
    assert set(_outputs(mgr)["run_id"]) == {1}


def test_locked_log_file_warns_once_buffers_rows_and_flushes_later(proj, obs, monkeypatch, caplog):
    _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    real_open = open
    state = {"locked": True}

    def locked_open(file, *a, **k):
        if state["locked"] and str(file).endswith("_metrics.csv"):
            raise PermissionError("open in Excel")
        return real_open(file, *a, **k)

    monkeypatch.setattr(run_log, "open", locked_open, raising=False)
    monkeypatch.setattr(run_log.time, "sleep", lambda s: None)
    with caplog.at_level("WARNING"):
        assert _iter(mgr, obs) == pytest.approx(3.0)
        assert _iter(mgr, obs) == pytest.approx(3.0)
    warns = [r for r in caplog.records if "Cannot write" in r.message and "_metrics.csv" in r.message]
    assert len(warns) == 1                                   # once per file
    assert mgr.session_files["metrics"].stat().st_size == 0  # nothing written yet
    assert len(_outputs(mgr)) == 20                          # other file unaffected
    state["locked"] = False
    assert mgr.flush_log() is True
    assert _metrics(mgr)["run_id"].tolist() == [1, 2]        # buffered rows were kept


def test_pending_buffer_is_bounded(proj, obs, monkeypatch):
    mgr = CalibrationManager(proj)
    monkeypatch.setattr(run_log.RunLog, "MAX_PENDING_ROWS", 3)
    monkeypatch.setattr(run_log.time, "sleep", lambda s: None)
    monkeypatch.setattr(run_log, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError("x")),
                        raising=False)
    for i in range(6):
        mgr.record_run({"CN2.mgt": float(i)}, {"nse": 1.0})
    (rows,) = [v for k, v in mgr._log._pending.items() if k.name.endswith("_metrics.csv")]
    assert len(rows) == 3


def test_column_change_starts_new_session_without_raising(proj, obs):
    """glue-like batch (nse) then a run with kge and one more parameter: two sessions."""
    mgr = CalibrationManager(proj)
    df = mgr.run_batch([_v(50.0), _v(FAIL_CN2), _v(60.0)], obs, metrics=["nse"])
    first = mgr.session_files["metrics"]
    _setup_iteration(proj, _run_writes_rch)
    score = mgr.run_iteration({"CN2.mgt": 0.1, "ALPHA_BF.gw": 0.2}, obs, metric="kge",
                              methods={"CN2.mgt": "r", "ALPHA_BF.gw": "a"})
    second = mgr.session_files["metrics"]
    assert score == pytest.approx(3.0)
    assert df["nse"].isna().tolist() == [False, True, False] and len(df) == 3
    assert first != second and second.name.endswith("_2_metrics.csv")
    m1, m2 = pd.read_csv(first), pd.read_csv(second)
    assert m1["run_id"].tolist() == [1, 2, 3] and "kge" not in m1.columns
    assert m2["run_id"].tolist() == [1] and {"kge", "ALPHA_BF.gw"} <= set(m2.columns)
    assert len(pd.read_csv(second.with_name(second.name.replace("metrics", "outputs")))) == 10


def test_record_run_is_public_and_never_raises(proj):
    mgr = CalibrationManager(proj)
    sim = pd.Series(np.arange(10.0), index=DATES)
    mgr.record_run({"CN2.mgt": 55.0}, {"nse": 0.5}, sim=sim, mode="uncertainty",
                   reach_id=2, output_variable="FLOW_OUTcms")
    mgr.record_run({"CN2.mgt": [(0.1, "r"), (0.05, "r", [71, 45])]}, None,
                   status="failed", error="bad")
    m = _metrics(mgr)
    assert m["mode"].tolist() == ["uncertainty", "sequential"]
    assert m["CN2.mgt__spec"].tolist() == ["55:v:All", "0.1:r:All|0.05:r:71,45"]
    assert m.loc[1, "CN2.mgt"] == 0.1 and m.loc[1, "CN2.mgt__method"] == "r"
    assert m.loc[1, "status"] == "failed" and np.isnan(m.loc[1, "nse"])
    assert set(_outputs(mgr)["run_id"]) == {1}
    mgr.record_run(object(), "not a dict", sim=42)          # garbage must not raise


def test_log_outputs_options(proj, obs):
    _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    with pytest.raises(ValueError):
        mgr.log_outputs = "some"
    mgr.log_outputs = "none"
    _iter(mgr, obs)
    assert len(_metrics(mgr)) == 1 and not mgr.session_path("outputs").exists()

    m2 = CalibrationManager(proj)
    m2._session_base = "obsonly"
    m2.log_outputs = "observed"
    _iter(m2, obs.iloc[:4])
    o = _outputs(m2)
    assert len(o) == 4 and o["date"].iloc[-1] == "2000-01-04"
    m2.record_run({"CN2.mgt": 1.0}, {"nse": 1.0}, sim=pd.Series(np.arange(10.0), index=DATES))
    assert len(_outputs(m2)) == 14          # no observations known -> all dates


def test_outputs_use_six_significant_digits(proj):
    mgr = CalibrationManager(proj)
    mgr.record_run({"CN2.mgt": 1.0}, {"nse": 1.0},
                   sim=pd.Series([1.23456789, 1000000.5], index=DATES[:2]))
    text = mgr.session_files["outputs"].read_text().splitlines()
    assert text[1].endswith(",1.23457") and text[2].endswith(",1e+06")


def test_session_file_is_created_exclusively_at_first_write(proj):
    a, b = CalibrationManager(proj), CalibrationManager(proj)
    b._session_base = a._session_base
    a.record_run({"CN2.mgt": 1.0}, {"nse": 1.0})
    b.session_files                                  # planned before a's file is taken ...
    b._session_id = None                             # ... and forget the plan (race simulation)
    b._session_id, b._session_dir = a._session_id, a._session_dir
    b._session_claimed = False
    b._session_n = a._session_n
    b.record_run({"CN2.mgt": 2.0}, {"nse": 1.0})     # O_EXCL fails on a's file -> next id
    fa = a.session_path("metrics")
    fb = b.session_path("metrics")
    assert fa != fb and fb.name.endswith("_2_metrics.csv")
    assert len(pd.read_csv(fa)) == 1 and len(pd.read_csv(fb)) == 1


def _tree(d: Path):
    return sorted(str(p.relative_to(d)) for p in d.rglob("*")) if d.exists() else []


def test_reading_properties_creates_nothing(proj):
    mgr = CalibrationManager(proj)
    work = proj.working_folder
    before = _tree(work)
    _ = mgr.results_dir, mgr.log_outputs, mgr.session_files, mgr.session_path("best_params")
    assert _tree(work) == before
    assert not (work / "calibration_results").exists()
    assert set(mgr.session_files) == {"metrics", "outputs"}      # paths that WILL be used


def test_invalid_records_create_nothing_and_keep_session(proj):
    mgr = CalibrationManager(proj)
    work = proj.working_folder
    mgr.record_run(None, "not-a-dict", status=123)
    mgr.record_run({"CN2.mgt": 1.0}, {"nse": 1.0}, status="weird")
    mgr.record_run({"CN2.mgt": 1.0}, ["nse"])
    mgr.record_run({"CN2.mgt": 1.0}, {"nse": 1.0}, sim=42)
    assert not (work / "calibration_results").exists()
    mgr.record_run({"CN2.mgt": 1.0}, {"nse": 1.0})              # one valid session
    files = mgr.session_files
    snap = _tree(work)
    mgr.record_run({"ALPHA_BF.gw": 1.0}, "garbage")             # invalid: no switch
    mgr.record_run(None, None, status=123)
    assert mgr.session_files == files and _tree(work) == snap


def test_every_metrics_file_has_header_and_a_row_after_switches(proj, obs):
    mgr = CalibrationManager(proj)
    mgr.record_run({"CN2.mgt": 1.0}, {"nse": 1.0})
    mgr.record_run({"CN2.mgt": 1.0, "ALPHA_BF.gw": 2.0}, {"nse": 1.0})   # switch 1
    mgr.record_run({"CN2.mgt": 1.0, "ALPHA_BF.gw": 2.0}, {"kge": 1.0})   # switch 2
    mgr.record_run(None, None, status=123)                                 # invalid
    files = sorted((proj.working_folder / "calibration_results").glob("*_metrics.csv"))
    assert len(files) == 3
    for f in files:
        lines = [l for l in f.read_text().splitlines() if l.strip()]
        assert len(lines) >= 2 and lines[0].startswith("run_id,"), f


def test_validation_run_is_logged_with_mode_validation(proj, obs, monkeypatch):
    base, before, runner = _validation_setup(proj, monkeypatch, obs)
    runner.run()
    m = pd.read_csv(runner.manager.session_files["metrics"])
    assert m["mode"].tolist() == ["validation"]


def test_project_without_working_folder_warns_once_mock_stays_silent(proj, caplog):
    from unittest.mock import MagicMock
    with caplog.at_level("WARNING"):
        silent = CalibrationManager(MagicMock())
        assert silent.results_dir is None
        assert not [r for r in caplog.records if "working_folder" in r.message]
        bare = CalibrationManager(types.SimpleNamespace())
        assert bare.results_dir is None and bare.results_dir is None
    assert len([r for r in caplog.records if "working_folder" in r.message]) == 1


def test_results_dir_none_disables_and_session_collision_gets_counter(proj, obs):
    _setup_iteration(proj, _run_writes_rch)
    off = CalibrationManager(proj)
    off.results_dir = None
    _iter(off, obs)
    assert off.session_files == {}
    assert not (proj.working_folder / "calibration_results").exists()

    a, b = CalibrationManager(proj), CalibrationManager(proj)
    b._session_base = a._session_base
    _iter(a, obs)
    _iter(b, obs)
    assert a.session_files["metrics"] != b.session_files["metrics"]
    assert b.session_files["metrics"].name.endswith("_2_metrics.csv")


def test_month_end_observations_get_a_specific_message():
    idx = pd.date_range("2000-01-31", periods=4, freq="ME")
    with pytest.raises(ValueError, match=r"END of each month.*to_period"):
        check_observation_step(idx, "MS")


# ── review PHASE1-1 (task REV-1) ─────────────────────────────────────

def test_validation_best_params_scalar_subbasin_does_not_crash(proj, obs, monkeypatch):
    """Finding 3: a single subbasin number used to raise TypeError after calibration."""
    base, before, runner = _validation_setup(proj, monkeypatch, obs)
    runner.param_ranges = {"CN2.mgt": ((-0.2, 0.2), "r", 1)}
    runner.run(restore=True)
    bp = pd.read_csv(runner.manager.session_path("best_params"), dtype=str)
    assert bp.loc[0, "subbasins"] == "1"


def test_run_iteration_restores_even_if_observed_has_no_index(proj, obs):
    """Finding 4: a non-Series `observed` must never leave TxtInOut modified."""
    base, before = _setup_iteration(proj, _run_writes_rch)
    with pytest.raises(Exception):
        CalibrationManager(proj).run_iteration({"CN2.mgt": 0.1}, obs.to_numpy(), metric="nse",
                                               methods={"CN2.mgt": "r"})
    assert snapshot(base) == before


def test_backup_covers_only_extensions_of_changed_parameters(proj):
    """Finding 6: changing CN2.mgt backs up file.cio and .mgt files, not .gw files."""
    mgr = CalibrationManager(proj)
    mgr._backup_state(names=["CN2.mgt"])
    try:
        names = sorted(p.suffix or p.name for p in mgr._backup_dir.iterdir())
    finally:
        mgr._restore_state()
    assert ".gw" not in names and ".mgt" in names and ".cio" in names


def test_sim_freq_never_inferred_from_observations(proj, obs):
    """Finding 9: the simulation step comes from IPRINT only (design rule 6)."""
    proj.FileCIO = types.SimpleNamespace(get_iprint=lambda: None)
    with pytest.raises((ValueError, TypeError)):
        CalibrationManager(proj)._sim_freq(obs)
