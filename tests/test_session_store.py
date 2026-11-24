"""Tests for SessionStore: the calibration session folder (write, flush, load)."""
import csv
import json
import math
import os

import numpy as np
import pandas as pd
import pytest

import spyswat.swat_calib.calibration.session_store as session_store
from spyswat.swat_calib.calibration.session_store import SessionStore

DATES = pd.date_range("2000-01-01", periods=5, freq="D")
PARAMS = ["CN2.mgt", "ALPHA_BF.gw"]
SITES = [("FLOW_OUTcms", 1)]


def make_store(tmp_path, **kw):
    return SessionStore(
        tmp_path / "session",
        signature={"seed": 42, "metric": "nse"},
        param_names=PARAMS,
        sites=SITES,
        **kw,
    )


def series_for(values):
    return pd.Series(list(values), index=DATES, name="FLOW_OUTcms")


def add_simple_run(store, run_id, score=0.5, vals=None):
    store.add_run(
        run_id,
        params={"CN2.mgt": 70.0 + run_id, "ALPHA_BF.gw": 0.5},
        status="ok",
        error=None,
        score=score,
        is_initial=False,
        series={("FLOW_OUTcms", 1): series_for(vals or [float(run_id)] * 5)},
        site_metrics={("FLOW_OUTcms", 1): {"nse_calib": score, "nse_valid": score}},
    )


def test_layout_and_exact_file_names(tmp_path):
    store = make_store(tmp_path)
    add_simple_run(store, 1)
    store.write_best({"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.5})
    store.write_sensitivity(pd.DataFrame({"parameter": ["CN2.mgt"], "t": [1.0]}))
    store.close()

    session_dir = tmp_path / "session"
    rel = sorted(p.relative_to(session_dir).as_posix() for p in session_dir.rglob("*"))
    assert rel == [
        "best.csv",
        "reach_1",
        "reach_1/FLOW_OUTcms.csv",
        "reach_1/FLOW_OUTcms_metrics.csv",
        "runs.csv",
        "sensitivity.csv",
        "session.json",
    ]

    meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert meta["param_names"] == PARAMS
    assert meta["sites"] == [["FLOW_OUTcms", 1]]
    assert meta["signature"] == {"seed": 42, "metric": "nse"}
    assert "spyswat_version" in meta and "numpy_version" in meta

    runs = store.runs()
    assert list(runs.columns) == ["run_id", "time", "status", "error", "is_initial",
                                  "CN2.mgt", "ALPHA_BF.gw", "score"]
    assert runs["run_id"].tolist() == [1]


def test_repr_float_round_trip(tmp_path):
    store = make_store(tmp_path)
    vals = [0.1 + 0.2, 1e-17, -0.0, float("nan")]
    for i, v in enumerate(vals, start=1):
        store.add_run(
            i,
            params={"CN2.mgt": v, "ALPHA_BF.gw": 0.5},
            status="ok",
            error=None,
            score=v,
            is_initial=False,
            series={("FLOW_OUTcms", 1): series_for([1, 2, 3, 4, 5])},
            site_metrics={("FLOW_OUTcms", 1): {"nse_calib": v}},
        )
    store.close()

    runs = store.runs()
    assert runs["score"].iloc[0] == 0.1 + 0.2
    assert runs["score"].iloc[1] == 1e-17
    assert runs["score"].iloc[2] == 0.0
    assert math.copysign(1.0, runs["score"].iloc[2]) == 1.0  # -0.0 normalised to +0.0
    assert np.isnan(runs["score"].iloc[3])
    assert runs["CN2.mgt"].iloc[0] == 0.1 + 0.2
    assert runs["CN2.mgt"].iloc[1] == 1e-17

    text = (tmp_path / "session" / "runs.csv").read_text(encoding="utf-8")
    assert "0.30000000000000004" in text
    assert "1e-17" in text
    assert "0.0," in text          # -0.0 stored as 0.0

    sm = store.site_metrics("FLOW_OUTcms", 1)
    assert sm["nse_calib"].iloc[0] == 0.1 + 0.2
    assert sm["nse_calib"].iloc[1] == 1e-17
    assert sm["nse_calib"].iloc[2] == 0.0
    assert np.isnan(sm["nse_calib"].iloc[3])


def test_flush_every_batching(tmp_path):
    store = make_store(tmp_path, flush_every=3)
    runs_csv = tmp_path / "session" / "runs.csv"
    for i in range(1, 3):
        add_simple_run(store, i)
    assert not runs_csv.exists()          # below the threshold: nothing committed

    add_simple_run(store, 3)
    assert runs_csv.exists()
    assert store.runs()["run_id"].tolist() == [1, 2, 3]
    assert list(store.series("FLOW_OUTcms", 1).columns) == ["run_1", "run_2", "run_3"]
    store.close()


def test_flush_seconds_triggers(tmp_path):
    store = make_store(tmp_path, flush_every=100, flush_seconds=0.0)
    add_simple_run(store, 1)
    assert (tmp_path / "session" / "runs.csv").exists()


def test_torn_tail_ignored_by_open(tmp_path):
    store = make_store(tmp_path)
    add_simple_run(store, 1)
    store.close()

    # Simulate a torn tail: a series column and a metric row whose run_id is not in runs.csv.
    series_path = tmp_path / "session" / "reach_1" / "FLOW_OUTcms.csv"
    df = pd.read_csv(series_path, index_col="date", parse_dates=True)
    df["run_999"] = 9.0
    df.to_csv(series_path)

    metrics_path = tmp_path / "session" / "reach_1" / "FLOW_OUTcms_metrics.csv"
    with open(metrics_path, "a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([999, 0.99])

    opened = SessionStore.open(tmp_path / "session")
    assert opened.runs()["run_id"].tolist() == [1]

    ser = opened.series("FLOW_OUTcms", 1)
    assert "run_1" in ser.columns and "run_999" not in ser.columns

    sm = opened.site_metrics("FLOW_OUTcms", 1)
    assert sm["run_id"].tolist() == [1]


def test_part2_split_with_small_max_columns(tmp_path):
    store = make_store(tmp_path, max_columns=2)
    for i in range(1, 6):
        add_simple_run(store, i)
    store.close()

    d = tmp_path / "session" / "reach_1"
    p1 = pd.read_csv(d / "FLOW_OUTcms.csv", index_col="date")
    p2 = pd.read_csv(d / "FLOW_OUTcms_part2.csv", index_col="date")
    p3 = pd.read_csv(d / "FLOW_OUTcms_part3.csv", index_col="date")
    assert list(p1.columns) == ["run_1", "run_2"]
    assert list(p2.columns) == ["run_3", "run_4"]
    assert list(p3.columns) == ["run_5"]

    ser = store.series("FLOW_OUTcms", 1)
    assert list(ser.columns) == ["run_1", "run_2", "run_3", "run_4", "run_5"]
    assert isinstance(ser.index, pd.DatetimeIndex)


def test_locked_file_buffered_then_written(tmp_path, monkeypatch, caplog):
    store = make_store(tmp_path, flush_every=1)
    real_replace = os.replace
    state = {"fail": True}

    def fake_replace(src, dst):
        if state["fail"] and str(dst).endswith("runs.csv"):
            raise PermissionError("open in Excel")
        return real_replace(src, dst)

    monkeypatch.setattr(session_store.os, "replace", fake_replace, raising=False)
    with caplog.at_level("WARNING"):
        add_simple_run(store, 1)
        assert not (tmp_path / "session" / "runs.csv").exists()  # locked: not committed
        state["fail"] = False
        add_simple_run(store, 2)

    assert store.runs()["run_id"].tolist() == [1, 2]           # buffered rows were kept
    warns = [r for r in caplog.records if "Cannot write" in r.message and "runs.csv" in r.message]
    assert len(warns) == 1                                     # warned once per file
    store.close()


def test_close_retries_then_raises_naming_file(tmp_path, monkeypatch):
    store = make_store(tmp_path, flush_every=1)
    real_replace = os.replace

    def fake_replace(src, dst):
        if str(dst).endswith("runs.csv"):
            raise PermissionError("locked")
        return real_replace(src, dst)

    monkeypatch.setattr(session_store.os, "replace", fake_replace, raising=False)
    add_simple_run(store, 1)
    with pytest.raises(OSError) as exc:
        store.close()
    assert "runs.csv" in str(exc.value)


def test_create_existing_raises_file_exists(tmp_path):
    make_store(tmp_path)
    with pytest.raises(FileExistsError):
        make_store(tmp_path)


def test_open_missing_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        SessionStore.open(tmp_path / "nope")


def test_check_signature_diff_message(tmp_path):
    store = make_store(tmp_path)
    store.check_signature({"seed": 42, "metric": "nse"})       # no raise
    with pytest.raises(ValueError) as exc:
        store.check_signature({"seed": 43, "metric": "kge"})
    msg = str(exc.value)
    assert "seed" in msg and "metric" in msg


def test_best_and_sensitivity_files(tmp_path):
    store = make_store(tmp_path)
    store.write_best({"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.5})
    store.write_sensitivity(pd.DataFrame({"parameter": ["CN2.mgt", "ALPHA_BF.gw"],
                                          "t": [2.0, -1.0]}))
    store.close()

    best = pd.read_csv(tmp_path / "session" / "best.csv", dtype=str)
    assert list(best.columns) == ["parameter", "value"]
    assert best.set_index("parameter")["value"].to_dict() == {
        "CN2.mgt": "75.0", "ALPHA_BF.gw": "0.5",
    }

    sens = pd.read_csv(tmp_path / "session" / "sensitivity.csv")
    assert sens["parameter"].tolist() == ["CN2.mgt", "ALPHA_BF.gw"]


def test_close_is_idempotent_and_signature_property(tmp_path):
    store = make_store(tmp_path)
    assert store.signature == {"seed": 42, "metric": "nse"}
    add_simple_run(store, 1)
    store.close()
    store.close()                      # safe to call twice
