"""ARCH-1 step 1: one public sequential-run primitive (run_once + sandbox).

Before ARCH-1 the sequence update -> stamp -> run -> fresh check -> read_rch was
hand-written in four places and one copy lost its freshness check (review PHASE1-1 #2).
"""
from pathlib import Path

import pytest

from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.core.workingFolder_manager import StaleOutputError

from test_calib_manager import (  # noqa: F401  (pytest fixtures)
    proj, obs, _setup_iteration, _run_writes_rch, _all_cn2, snapshot,
)

ROOT = Path(__file__).resolve().parents[1] / "spyswat" / "swat_calib"


def test_run_once_applies_params_and_returns_the_fresh_series(proj):
    base, _ = _setup_iteration(proj, _run_writes_rch)
    sim = CalibrationManager(proj).run_once({"CN2.mgt": [(60.0, "v")]},
                                            reach_id=1, output_variable="FLOW_OUTcms")
    assert list(sim) == [3.0] * 10
    assert _all_cn2(base) == pytest.approx([60.0, 60.0, 60.0])   # no restore: caller decides


def test_run_once_formats_raw_values_as_absolute(proj):
    base, _ = _setup_iteration(proj, _run_writes_rch)
    CalibrationManager(proj).run_once({"CN2.mgt": 61.0})
    assert _all_cn2(base) == pytest.approx([61.0, 61.0, 61.0])


def test_run_once_rejects_stale_output(proj):
    _setup_iteration(proj, lambda p: None)          # SWAT "runs" but writes nothing
    with pytest.raises(StaleOutputError, match="fresh output.rch"):
        CalibrationManager(proj).run_once({"CN2.mgt": 50.0})
    assert issubclass(StaleOutputError, RuntimeError)   # old `except RuntimeError` still works


def test_sandbox_restores_after_success(proj):
    base, before = _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    with mgr.sandbox(names=["CN2.mgt"]):
        mgr.run_once({"CN2.mgt": 60.0})
        assert _all_cn2(base) == pytest.approx([60.0] * 3)
    assert snapshot(base) == before
    assert mgr._backup_dir is None


@pytest.mark.parametrize("exc", [RuntimeError("boom"), KeyboardInterrupt()])
def test_sandbox_restores_after_any_exception(proj, exc):
    base, before = _setup_iteration(proj, _run_writes_rch)
    mgr = CalibrationManager(proj)
    with pytest.raises(type(exc)):
        with mgr.sandbox():
            mgr.run_once({"CN2.mgt": 60.0})
            raise exc
    assert snapshot(base) == before


@pytest.mark.parametrize("module", [
    "analysis/sensitivity.py",
    "analysis/algorithms/glue.py",
    "calibration/validation_runner.py",
])
def test_sequential_callers_do_not_copy_the_run_sequence(module):
    """Only run_once may stamp/check output.rch; callers must not re-implement it."""
    src = (ROOT / module).read_text(encoding="utf-8")
    for name in ("_stamp_output_rch", "_check_fresh_output_rch", "_backup_state(",
                 "_restore_state("):
        assert name not in src, f"{module} re-implements the run sequence ({name})"
