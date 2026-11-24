"""
API-5a: resume by replay.

Every algorithm is exercised against a real ``SessionStore`` + ``ReplayCursor``
(no facade): a reference full run is compared to a run interrupted with
``KeyboardInterrupt`` (a ``BaseException``, so the interrupted evaluation is
*not* committed as failed) and then resumed.  Fake runner / plain-number
``output.rch`` -- no SWAT executable (helpers reused from
``test_calib_multisite`` and ``test_working_folder``).
"""
import csv
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spyswat.logger import Logger
from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.calibration import calib_manager as cm
from spyswat.swat_calib.calibration.replay import (
    ReplayCursor, ResumeMismatchError, check_param_order,
)
from spyswat.swat_calib.calibration.session_store import SessionStore
from spyswat.swat_calib.core.workingFolder_manager import WorkerResult
from spyswat.swat_calib.analysis.algorithms.dds import DDSCalibration
from spyswat.swat_calib.analysis.algorithms.glue import GLUE
from spyswat.swat_calib.analysis.algorithms.parallel_de import ParallelDE
from spyswat.swat_calib.analysis.algorithms.pso import PSOCalibration

from test_calib_multisite import (
    DATES, FakeOutputFileManager, StubProject, _two_site_obs,
)
from test_working_folder import build_txinout, build_param_file


PARAM_RANGES = {"CN2.mgt": (35.0, 98.0), "ALPHA_BF.gw": (0.0, 1.0)}
PARAM_NAMES = list(PARAM_RANGES)
OUTPUTS = {"FLOW_OUTcms": [1], "SED_OUTtons": [51]}
SITES = [("FLOW_OUTcms", 1), ("SED_OUTtons", 51)]
CALIB_PERIOD = ("2000-01-01", "2000-01-10")
SEED = 42


def _make_proj(tmp_path, monkeypatch, n_parallel):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logger, "init_queue_listener", classmethod(lambda cls, **k: None))
    monkeypatch.setattr(Logger, "stop_listener", classmethod(lambda cls: None))
    monkeypatch.setattr(cm, "OutputFileManager", FakeOutputFileManager)
    base = build_txinout(tmp_path)
    param = build_param_file(tmp_path)
    return StubProject(base, param, tmp_path / "work", n_parallel=n_parallel)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    return _make_proj(tmp_path, monkeypatch, n_parallel=1)


@pytest.fixture
def proj2(tmp_path, monkeypatch):
    return _make_proj(tmp_path, monkeypatch, n_parallel=2)


def _store(tmp_path, name, param_names=PARAM_NAMES, sites=SITES, signature=None):
    return SessionStore(
        tmp_path / name,
        signature=signature or {"seed": SEED, "metric": "nse"},
        param_names=list(param_names),
        sites=[tuple(s) for s in sites],
    )


# ── fake runners ────────────────────────────────────────────────────────────

def _parallel_fake(proj, counter=None, interrupt_at=None, fail_params=()):
    """Replace ``WorkingFolder.run_parallel`` with a deterministic in-process fake.

    Each evaluation writes ``output.rch`` holding the CN2 value; a CN2 in
    ``fail_params`` fails the job.  With ``counter`` the fake counts evaluations
    and raises ``KeyboardInterrupt`` at the ``interrupt_at + 1``-th one.
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
            try:
                cn2 = float(ps["CN2.mgt"][0][0])
                if fail_params and cn2 in fail_params:
                    results.append(WorkerResult(False, "RuntimeError: boom",
                                                0.0, str(wdir), None))
                    continue
                (wdir / "output.rch").write_text("\n".join([repr(cn2)] * 10) + "\n")
                extractor = pickle.loads(pickle.dumps(extract))
                payload = extractor(str(wdir))
                results.append(WorkerResult(True, None, 0.0, str(wdir), payload))
            except Exception as e:
                results.append(WorkerResult(False, f"{type(e).__name__}: {e}",
                                            0.0, str(wdir), None))
        return results

    wf.run_parallel = fake_run_parallel
    return fake_run_parallel


def _dds_fake(proj, counter=None, interrupt_at=None, fail_on=()):
    """Deterministic sequential runner: write the applied CN2 to ``output.rch``.

    ``fail_on`` is a set of 1-based evaluation indices that raise ``RuntimeError``.
    """
    base = Path(proj.txinout.directory)

    def run_impl(p):
        if counter is not None:
            counter["n"] += 1
            if interrupt_at is not None and counter["n"] > interrupt_at:
                raise KeyboardInterrupt
            if fail_on and counter["n"] in fail_on:
                raise RuntimeError("boom")
        first = sorted(base.glob("0*.mgt"))[0]
        cn2 = float(first.read_text().splitlines()[10][:16])
        (base / "output.rch").write_text("\n".join([repr(cn2)] * 10) + "\n")

    proj.run_impl = run_impl
    return run_impl


def _install_fake(name, proj, counter=None, interrupt_at=None, fail_params=(),
                  fail_on=()):
    if name == "dds":
        return _dds_fake(proj, counter=counter, interrupt_at=interrupt_at,
                         fail_on=fail_on)
    return _parallel_fake(proj, counter=counter, interrupt_at=interrupt_at,
                          fail_params=fail_params)


# ── algorithm dispatch ──────────────────────────────────────────────────────

def _run_dds(manager, obs, store=None, replay=None, seed=SEED,
             on_failure="raise", n_iterations=6):
    return DDSCalibration(manager).run(
        PARAM_RANGES, obs, n_iterations=n_iterations, seed=seed, metric="nse",
        metrics=("nse", "kge"), outputs=OUTPUTS, calib_period=CALIB_PERIOD,
        store=store, replay=replay, on_failure=on_failure,
    )


def _run_algo(name, manager, obs, store=None, replay=None, seed=SEED):
    common = dict(metric="nse", metrics=("nse", "kge"), outputs=OUTPUTS,
                  calib_period=CALIB_PERIOD, store=store, replay=replay, seed=seed)
    if name == "glue":
        return GLUE(manager).run(PARAM_RANGES, obs, n_samples=8, **common)
    if name == "pso":
        return PSOCalibration(manager).run(
            PARAM_RANGES, obs, n_particles=4, max_iterations=2,
            tol=0.0, patience=100, **common)
    if name == "de":
        return ParallelDE(manager).run(
            PARAM_RANGES, obs, pop_size=4, max_generations=2,
            tol=0.0, patience=100, **common)
    if name == "dds":
        return _run_dds(manager, obs, store=store, replay=replay, seed=seed)
    raise ValueError(name)


# ── csv helpers ─────────────────────────────────────────────────────────────

def _runs_cells(session_dir):
    with open(session_dir / "runs.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    t = header.index("time")
    return [[v for j, v in enumerate(row) if j != t] for row in rows[1:]]


def _run_ids(session_dir):
    return [int(r[0]) for r in _runs_cells(session_dir)]


# ── resume by replay: reference == interrupted + resumed ────────────────────

RESUME_CASES = [
    ("glue", 8, 4),
    ("pso", 12, 6),
    ("de", 12, 6),
    ("dds", 6, 3),
]


@pytest.mark.parametrize("name,total,k", RESUME_CASES)
def test_resume_matches_reference(proj, tmp_path, name, total, k):
    obs = _two_site_obs()

    # reference: full, uninterrupted run
    ref_store = _store(tmp_path, "ref")
    ref_counter = {"n": 0}
    _install_fake(name, proj, counter=ref_counter)
    ref = _run_algo(name, CalibrationManager(proj), obs, store=ref_store)
    ref_store.close()
    assert ref_counter["n"] == total

    # interrupted: KeyboardInterrupt at evaluation k+1
    int_store = _store(tmp_path, "int")
    int_counter = {"n": 0}
    _install_fake(name, proj, counter=int_counter, interrupt_at=k)
    with pytest.raises(KeyboardInterrupt):
        _run_algo(name, CalibrationManager(proj), obs, store=int_store)
    int_store.close()
    assert int_counter["n"] == k + 1           # k succeeded, k+1 raised uncommitted

    # resume: replay the committed prefix, run the rest
    opened = SessionStore.open(tmp_path / "int")
    cursor = ReplayCursor(opened)
    resume_counter = {"n": 0}
    _install_fake(name, proj, counter=resume_counter)
    res = _run_algo(name, CalibrationManager(proj), obs,
                    store=opened, replay=cursor)
    opened.close()

    assert resume_counter["n"] == total - k    # only the uncommitted tail ran
    assert res["best_score"] == ref["best_score"]
    assert res["best_params"] == ref["best_params"]
    pd.testing.assert_frame_equal(res["runs"], ref["runs"])
    # exact runs.csv cells (excluding time), contiguous run ids 1..N
    assert _runs_cells(tmp_path / "int") == _runs_cells(tmp_path / "ref")
    assert _run_ids(tmp_path / "int") == list(range(1, total + 1))


def test_glue_mid_chunk_interrupt_discards_partial_chunk(proj2, tmp_path):
    """n_workers=2: interrupting mid-chunk commits only full chunks."""
    obs = _two_site_obs()

    ref_store = _store(tmp_path, "ref")
    _install_fake("glue", proj2, counter={"n": 0})
    ref = _run_algo("glue", CalibrationManager(proj2), obs, store=ref_store)
    ref_store.close()

    int_store = _store(tmp_path, "int")
    int_counter = {"n": 0}
    _install_fake("glue", proj2, counter=int_counter, interrupt_at=3)
    with pytest.raises(KeyboardInterrupt):
        _run_algo("glue", CalibrationManager(proj2), obs, store=int_store)
    int_store.close()
    assert int_counter["n"] == 4                # evals 1,2 committed; 3 ran, 4 raised -> chunk [3,4] discarded

    opened = SessionStore.open(tmp_path / "int")
    cursor = ReplayCursor(opened)
    assert cursor.next_run_id == 3              # only runs 1..2 committed
    resume_counter = {"n": 0}
    _install_fake("glue", proj2, counter=resume_counter)
    res = _run_algo("glue", CalibrationManager(proj2), obs,
                    store=opened, replay=cursor)
    opened.close()

    assert resume_counter["n"] == 6             # 8 - 2 committed
    pd.testing.assert_frame_equal(res["runs"], ref["runs"])
    assert res["best_score"] == ref["best_score"]
    assert _runs_cells(tmp_path / "int") == _runs_cells(tmp_path / "ref")


def test_resume_completed_session_makes_zero_runner_calls(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    _install_fake("glue", proj, counter={"n": 0})
    ref = _run_algo("glue", CalibrationManager(proj), obs, store=store)
    store.close()

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    resume_counter = {"n": 0}
    _install_fake("glue", proj, counter=resume_counter)
    res = _run_algo("glue", CalibrationManager(proj), obs,
                    store=opened, replay=cursor)
    opened.close()
    assert resume_counter["n"] == 0
    assert res["best_score"] == ref["best_score"]
    pd.testing.assert_frame_equal(res["runs"], ref["runs"])
    assert _run_ids(tmp_path / "s") == list(range(1, 9))


def test_resume_empty_session_runs_all_from_run_id_1(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    store.close()                               # committed nothing

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    assert cursor.next_run_id == 1
    assert cursor.remaining == 0

    counter = {"n": 0}
    _install_fake("glue", proj, counter=counter)
    res = _run_algo("glue", CalibrationManager(proj), obs,
                    store=opened, replay=cursor)
    opened.close()
    assert counter["n"] == 8
    assert _run_ids(tmp_path / "s") == list(range(1, 9))
    assert len(res["runs"]) == 8


# ── failed runs replay as failed, never retried ─────────────────────────────

def test_run_batch_replays_failed_run_as_nan_not_retried(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    counter = {"n": 0}
    _install_fake("glue", proj, counter=counter, fail_params={77.0})
    param_sets = [
        {"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.1},
        {"CN2.mgt": 77.0, "ALPHA_BF.gw": 0.2},
        {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.3},
    ]
    df = CalibrationManager(proj).run_batch(
        param_sets, obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=store)
    store.close()
    assert counter["n"] == 3
    assert np.isnan(df["score"].iloc[1])
    assert np.isnan(df["nse@FLOW_OUTcms@1"].iloc[1])

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    resume_counter = {"n": 0}
    _install_fake("glue", proj, counter=resume_counter)
    df2 = CalibrationManager(proj).run_batch(
        param_sets + [{"CN2.mgt": 70.0, "ALPHA_BF.gw": 0.4}],
        obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=opened, replay=cursor)
    opened.close()
    assert resume_counter["n"] == 1            # only the new run executed
    assert np.isnan(df2["score"].iloc[1])      # failed run replayed as NaN
    assert np.isnan(df2["nse@FLOW_OUTcms@1"].iloc[1])
    assert df2["score"].iloc[0] == pytest.approx(df["score"].iloc[0])
    assert df2["score"].iloc[2] == pytest.approx(df["score"].iloc[2])


def test_dds_failed_run_penalize_replays_nan(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    counter = {"n": 0}
    _install_fake("dds", proj, counter=counter, fail_on={1})
    ref = _run_dds(CalibrationManager(proj), obs, store=store,
                   on_failure="penalize")
    store.close()
    assert counter["n"] == 6
    runs = SessionStore.open(tmp_path / "s").runs()
    assert runs["status"].iloc[0] == "failed"
    assert np.isnan(runs["score"].iloc[0])
    assert (runs["status"].iloc[1:] == "ok").all()

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    resume_counter = {"n": 0}
    _install_fake("dds", proj, counter=resume_counter)   # no failure on resume
    res = _run_dds(CalibrationManager(proj), obs, store=opened, replay=cursor,
                   on_failure="penalize")
    opened.close()
    assert resume_counter["n"] == 0            # failed run replayed, never re-run
    assert res["best_score"] == ref["best_score"]
    assert res["best_params"] == ref["best_params"]
    pd.testing.assert_frame_equal(res["runs"], ref["runs"])
    assert np.isnan(res["runs"]["score"].iloc[0])


def test_dds_failed_run_raise_reraises_without_retry(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    counter = {"n": 0}
    _install_fake("dds", proj, counter=counter, fail_on={1})
    with pytest.raises(RuntimeError, match="Iteration failed"):
        _run_dds(CalibrationManager(proj), obs, store=store, on_failure="raise")
    store.close()
    assert counter["n"] == 1
    assert SessionStore.open(tmp_path / "s").runs()["status"].iloc[0] == "failed"

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    resume_counter = {"n": 0}
    _install_fake("dds", proj, counter=resume_counter)
    with pytest.raises(RuntimeError, match="Iteration failed"):
        _run_dds(CalibrationManager(proj), obs, store=opened, replay=cursor,
                 on_failure="raise")
    opened.close()
    assert resume_counter["n"] == 0            # failed run replayed, not retried


# ── ReplayCursor validation & integrity ─────────────────────────────────────

def _add_run(store, run_id, cn2=50.0, alpha=0.5, status="ok", score=0.5):
    store.add_run(
        run_id, params={"CN2.mgt": cn2, "ALPHA_BF.gw": alpha},
        status=status, error=None, score=score, is_initial=False,
        series={("FLOW_OUTcms", 1): pd.Series([1.0] * 5, index=DATES[:5])},
        site_metrics={("FLOW_OUTcms", 1): {"nse_calib": score}},
    )


@pytest.mark.parametrize("ids", [[2, 3], [1, 1], [2], [1, 3]])
def test_replay_cursor_rejects_noncontiguous_run_ids(tmp_path, ids):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    for rid in ids:
        _add_run(store, rid)
    store.close()
    opened = SessionStore.open(tmp_path / "s")
    with pytest.raises(ResumeMismatchError):
        ReplayCursor(opened)


def test_replay_cursor_param_mismatch_names_run_and_values(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1, cn2=50.0, alpha=0.5)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    with pytest.raises(ResumeMismatchError) as excinfo:
        cursor.take([{"CN2.mgt": 99.0, "ALPHA_BF.gw": 0.5}])
    message = str(excinfo.value)
    assert "run 1" in message
    assert "CN2.mgt" in message
    assert "50.0" in message
    assert "99.0" in message


def test_replay_cursor_unwraps_formatted_param_dicts(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1, cn2=50.0, alpha=0.5)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    taken = cursor.take([
        {"CN2.mgt": [(50.0, "v")], "ALPHA_BF.gw": [(0.5, "v")]},
    ])
    assert len(taken) == 1 and taken[0] is not None
    assert taken[0].run_id == 1
    assert taken[0].params == {"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.5}


def test_replay_cursor_does_not_advance_on_batch_mismatch(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1, cn2=50.0, alpha=0.5)
    _add_run(store, 2, cn2=60.0, alpha=0.5)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    assert cursor.remaining == 2
    with pytest.raises(ResumeMismatchError):
        cursor.take([{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.5},
                     {"CN2.mgt": 99.0, "ALPHA_BF.gw": 0.5}])
    # a mismatch mid-batch leaves the cursor untouched
    assert cursor.remaining == 2
    assert cursor.next_run_id == 3


def test_run_batch_replay_without_store_routes_multisite(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    _install_fake("glue", proj, counter={"n": 0})
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.1},
         {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.2}],
        obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=store)
    store.close()

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    counter = {"n": 0}
    _install_fake("glue", proj, counter=counter)
    df = CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.1},
         {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.2},
         {"CN2.mgt": 70.0, "ALPHA_BF.gw": 0.3}],
        obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=None, replay=cursor)
    opened.close()
    assert counter["n"] == 1            # only the new run executed
    assert list(df.columns) == ["score", "nse@FLOW_OUTcms@1", "nse@SED_OUTtons@51"]
    assert len(df) == 3
    assert not np.isnan(df["score"].iloc[0])


def test_replay_cursor_minus_zero_matches_zero(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1, cn2=0.0, alpha=-0.0)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    taken = cursor.take([{"CN2.mgt": -0.0, "ALPHA_BF.gw": 0.0}])
    assert len(taken) == 1 and taken[0] is not None
    assert taken[0].run_id == 1
    assert taken[0].params["CN2.mgt"] == 0.0


def test_replay_cursor_param_order_mismatch(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    with pytest.raises(ResumeMismatchError, match="order"):
        cursor.take([{"ALPHA_BF.gw": 0.5, "CN2.mgt": 50.0}])


def test_replay_cursor_exhaustion_returns_none_and_tracks_remaining(tmp_path):
    store = _store(tmp_path, "s", sites=[("FLOW_OUTcms", 1)])
    _add_run(store, 1)
    _add_run(store, 2, cn2=60.0)
    store.close()
    cursor = ReplayCursor(SessionStore.open(tmp_path / "s"))
    assert cursor.remaining == 2
    assert cursor.next_run_id == 3
    taken = cursor.take([{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.5},
                         {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.5},
                         {"CN2.mgt": 70.0, "ALPHA_BF.gw": 0.5}])
    assert [t.run_id if t else None for t in taken] == [1, 2, None]
    assert cursor.remaining == 0


def test_check_param_order_rejects_reordered_keys(tmp_path):
    store = _store(tmp_path, "s")
    check_param_order(store, {"CN2.mgt": (35, 98), "ALPHA_BF.gw": (0, 1)})
    with pytest.raises(ValueError, match="order"):
        check_param_order(store, {"ALPHA_BF.gw": (0, 1), "CN2.mgt": (35, 98)})


def test_torn_tail_ignored_and_overwritten_on_resume(proj, tmp_path):
    obs = _two_site_obs()
    store = _store(tmp_path, "s")
    _install_fake("glue", proj, counter={"n": 0})
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.1},
         {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.2}],
        obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=store)
    store.close()

    series_path = tmp_path / "s" / "reach_1" / "FLOW_OUTcms.csv"
    df = pd.read_csv(series_path, index_col="date", parse_dates=True)
    df["run_999"] = 9.0
    df.to_csv(series_path)
    metrics_path = tmp_path / "s" / "reach_1" / "FLOW_OUTcms_metrics.csv"
    with open(metrics_path, "a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([999, 0.99])

    opened = SessionStore.open(tmp_path / "s")
    cursor = ReplayCursor(opened)
    assert [r.run_id for r in cursor._runs] == [1, 2]

    resume_counter = {"n": 0}
    _install_fake("glue", proj, counter=resume_counter)
    CalibrationManager(proj).run_batch(
        [{"CN2.mgt": 50.0, "ALPHA_BF.gw": 0.1},
         {"CN2.mgt": 60.0, "ALPHA_BF.gw": 0.2},
         {"CN2.mgt": 70.0, "ALPHA_BF.gw": 0.3}],
        obs, metrics=("nse",), metric="nse", outputs=OUTPUTS,
        calib_period=CALIB_PERIOD, store=opened, replay=cursor)
    opened.close()
    assert resume_counter["n"] == 1
    assert "run_999" not in series_path.read_text(encoding="utf-8")
    assert "999" not in metrics_path.read_text(encoding="utf-8")
