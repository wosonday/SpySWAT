"""API-5b: facade resume-by-replay end-to-end (``project.calibration(resume=True)``).

A real ``SWATProject`` is built on a synthetic TxtInOut with the SWAT layer faked
in-process (no ``swat.exe``, no worker subprocesses).  Each test runs a reference
calibration, an interrupted calibration (the fake runner raises ``KeyboardInterrupt``
at evaluation k+1), then resumes the same ``session=`` and checks the result is
identical to the reference and that only the uncommitted tail re-runs.
"""
import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat import SWATProject
from spyswat.logger import Logger
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.calibration.session_store import SessionStore
from spyswat.swat_calib.core.workingFolder_manager import WorkerResult

from test_working_folder import build_param_file, build_txinout, read_cn2

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
    p = SWATProject(base, tmp_path / "work", exe, param_file=param, n_parallel=1)
    p.WorkingFolder.setup()
    p.get_date_range = lambda freq="D": DATES
    p._output_manager = FakeOutputManager(base)
    return p


def _install(proj, counter=None, interrupt_at=None):
    """Replace the parallel and sequential runners with deterministic in-process fakes.

    ``counter`` (a dict with key ``"n"``) counts evaluations; the fake raises
    ``KeyboardInterrupt`` at the ``interrupt_at + 1``-th evaluation (a
    ``BaseException``, so the interrupted run is *not* committed as failed).
    """
    wf = proj.WorkingFolder

    def fake_run_parallel(swat_exe, param_sets=None, log_queue=None, *,
                          extract=None, runner=None, prepare=None, overlays=None,
                          timeout_s=None):
        results = []
        for i, ps in enumerate(param_sets):
            if counter is not None:
                counter["n"] += 1
                if interrupt_at is not None and counter["n"] > interrupt_at:
                    raise KeyboardInterrupt
            wdir = wf.worker_dirs[i]
            cn2 = float(ps["CN2.mgt"][0][0])
            n_vals = len(proj.get_date_range("D"))
            (wdir / "output.rch").write_text("\n".join([repr(cn2)] * n_vals) + "\n")
            extractor = pickle.loads(pickle.dumps(extract))
            payload = extractor(str(wdir))
            results.append(WorkerResult(True, None, 0.0, str(wdir), payload))
        return results

    wf.run_parallel = fake_run_parallel

    def fake_swat_run(directory):
        if counter is not None:
            counter["n"] += 1
            if interrupt_at is not None and counter["n"] > interrupt_at:
                raise KeyboardInterrupt
        cn2 = read_cn2(directory)
        n_vals = len(proj.get_date_range("D"))
        (Path(directory) / "output.rch").write_text(
            "\n".join([repr(cn2)] * n_vals) + "\n")

    proj.swat_exe.run = fake_swat_run


def _runs_without_time(res):
    return res.runs.drop(columns=["time"]).reset_index(drop=True)


def _committed_count(proj, name):
    return len(SessionStore.open(proj.working_folder / "calibration_results" / name).runs())


# ── reference == interrupted + resumed (per algorithm) ──────────────────────

FACADE_CASES = [
    ("glue", dict(n_samples=8), 4),
    ("pso", dict(n_particles=4, max_iterations=2, tol=0.0, patience=100), 6),
    ("de", dict(pop_size=4, max_generations=2, tol=0.0, patience=100), 6),
    ("dds", dict(n_iterations=6), 3),
]


@pytest.mark.parametrize("algorithm,kwargs,k", FACADE_CASES)
def test_facade_resume_matches_reference(proj, algorithm, kwargs, k):
    obs = _obs()

    # reference: full, uninterrupted run
    _install(proj, counter={"n": 0})
    ref = proj.calibration(PARAM_RANGES, obs, CALIB, VALID,
                           algorithm=algorithm, seed=42, sensitivity=False,
                           session="ref", resume=False, **kwargs)
    assert ref.seed == 42

    # interrupted: KeyboardInterrupt at evaluation k+1
    _install(proj, counter={"n": 0}, interrupt_at=k)
    with pytest.raises(KeyboardInterrupt):
        proj.calibration(PARAM_RANGES, obs, CALIB, VALID,
                         algorithm=algorithm, seed=42, sensitivity=False,
                         session="int", resume=False, **kwargs)
    committed = _committed_count(proj, "int")
    assert committed == k

    # resume: replay the committed prefix, run the rest
    resume_counter = {"n": 0}
    _install(proj, counter=resume_counter)
    res = proj.calibration(PARAM_RANGES, obs, CALIB, VALID,
                           algorithm=algorithm, seed=42, sensitivity=False,
                           session="int", resume=True, **kwargs)

    total = len(ref.runs)
    assert resume_counter["n"] == total - committed
    assert res.best_score == pytest.approx(ref.best_score)
    assert res.best_params == ref.best_params
    pd.testing.assert_frame_equal(_runs_without_time(res), _runs_without_time(ref))


def test_facade_resume_completed_session_zero_runner_calls(proj):
    obs = _obs()
    _install(proj, counter={"n": 0})
    ref = proj.calibration(PARAM_RANGES, obs, CALIB, algorithm="glue",
                           n_samples=8, seed=1, sensitivity=False,
                           session="done", resume=False)

    resume_counter = {"n": 0}
    _install(proj, counter=resume_counter)
    res = proj.calibration(PARAM_RANGES, obs, CALIB, algorithm="glue",
                           n_samples=8, seed=1, sensitivity=False,
                           session="done", resume=True)

    assert resume_counter["n"] == 0
    assert res.best_score == pytest.approx(ref.best_score)
    pd.testing.assert_frame_equal(_runs_without_time(res), _runs_without_time(ref))


def test_facade_resume_seed_none_uses_stored_seed(proj):
    obs = _obs()
    _install(proj, counter={"n": 0})
    ref = proj.calibration(PARAM_RANGES, obs, CALIB, algorithm="glue",
                           n_samples=8, seed=None, sensitivity=False,
                           session="s", resume=False)
    assert isinstance(ref.seed, int)

    resume_counter = {"n": 0}
    _install(proj, counter=resume_counter)
    res = proj.calibration(PARAM_RANGES, obs, CALIB, algorithm="glue",
                           n_samples=8, seed=None, sensitivity=False,
                           session="s", resume=True)

    assert resume_counter["n"] == 0          # completed session: nothing re-runs
    assert res.seed == ref.seed
    assert res.best_score == pytest.approx(ref.best_score)
    pd.testing.assert_frame_equal(_runs_without_time(res), _runs_without_time(ref))


# ── resume refuses a changed configuration, leaving the session untouched ────

def _dir_hash(directory):
    """{relative path: sha256 hex} of every file under ``directory``."""
    out = {}
    for p in sorted(Path(directory).rglob("*")):
        if p.is_file():
            out[p.relative_to(directory).as_posix()] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


def _make_session(proj, name):
    _install(proj, counter={"n": 0})
    proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                     n_samples=4, seed=7, sensitivity=False,
                     session=name, resume=False)


def test_facade_resume_different_seed_raises_valueerror(proj):
    _make_session(proj, "s")
    session_dir = proj.working_folder / "calibration_results" / "s"
    before = _dir_hash(session_dir)
    with pytest.raises(ValueError, match="seed"):
        proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                         n_samples=4, seed=8, sensitivity=False,
                         session="s", resume=True)
    assert _dir_hash(session_dir) == before


def test_facade_resume_changed_param_ranges_raises_valueerror(proj):
    _make_session(proj, "s")
    session_dir = proj.working_folder / "calibration_results" / "s"
    before = _dir_hash(session_dir)
    changed = {"CN2.mgt": (35.0, 99.0), "ALPHA_BF.gw": (0.0, 1.0)}
    with pytest.raises(ValueError, match="param_ranges"):
        proj.calibration(changed, _obs(), CALIB, algorithm="glue",
                         n_samples=4, seed=7, sensitivity=False,
                         session="s", resume=True)
    assert _dir_hash(session_dir) == before


def test_facade_resume_reordered_param_ranges_raises_valueerror(proj):
    _make_session(proj, "s")
    session_dir = proj.working_folder / "calibration_results" / "s"
    before = _dir_hash(session_dir)
    reordered = {"ALPHA_BF.gw": (0.0, 1.0), "CN2.mgt": (35.0, 98.0)}
    with pytest.raises(ValueError, match="order"):
        proj.calibration(reordered, _obs(), CALIB, algorithm="glue",
                         n_samples=4, seed=7, sensitivity=False,
                         session="s", resume=True)
    assert _dir_hash(session_dir) == before


def test_facade_resume_changed_observed_raises_valueerror(proj):
    _make_session(proj, "s")
    session_dir = proj.working_folder / "calibration_results" / "s"
    before = _dir_hash(session_dir)
    changed = _obs()
    changed[("FLOW_OUTcms", 1)] = changed[("FLOW_OUTcms", 1)] + 1.0
    with pytest.raises(ValueError, match="observed_hash"):
        proj.calibration(PARAM_RANGES, changed, CALIB, algorithm="glue",
                         n_samples=4, seed=7, sensitivity=False,
                         session="s", resume=True)
    assert _dir_hash(session_dir) == before


def test_facade_resume_missing_session_raises_filenotfound(proj):
    with pytest.raises(FileNotFoundError):
        proj.calibration(PARAM_RANGES, _obs(), CALIB, algorithm="glue",
                         n_samples=4, seed=7, sensitivity=False,
                         session="does-not-exist", resume=True)
