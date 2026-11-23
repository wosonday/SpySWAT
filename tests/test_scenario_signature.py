"""Tests for scenarios/signature.py::txinout_fingerprint and the resume check that uses it."""
import json
import logging
import os
from pathlib import Path

import pytest

from spyswat.swat_calib.scenarios import Scenario, ScenarioBatch
from test_scenarios import OUTS, PARAMS, build_txinout, env, fake_runner, make_project


def _make_inputs(root: Path, name: str = "TxtInOut") -> Path:
    d = root / name
    d.mkdir()
    (d / "file.cio").write_text("cio line\n")
    (d / "pcp1.pcp").write_text("10.0\n")
    return d


def test_fingerprint_is_stable_for_unchanged_inputs(tmp_path):
    from spyswat.swat_calib.scenarios.signature import txinout_fingerprint

    d = _make_inputs(tmp_path)
    first = txinout_fingerprint(d)
    assert isinstance(first, str) and len(first) == 40     # sha1 hex digest
    assert txinout_fingerprint(d) == first
    assert txinout_fingerprint(str(d)) == first            # accepts str and Path


def test_fingerprint_changes_on_added_removed_resized_and_rewritten_inputs(tmp_path):
    from spyswat.swat_calib.scenarios.signature import txinout_fingerprint

    d = _make_inputs(tmp_path)
    seen = {txinout_fingerprint(d)}

    (d / "new.gw").write_text("gw\n")                       # added
    seen.add(txinout_fingerprint(d))

    (d / "pcp1.pcp").unlink()                               # removed
    seen.add(txinout_fingerprint(d))

    (d / "new.gw").write_text("gw, longer\n")               # size changed
    seen.add(txinout_fingerprint(d))

    os.utime(d / "file.cio", ns=(1_700_000_000_000_000_000,) * 2)   # mtime only
    seen.add(txinout_fingerprint(d))

    assert len(seen) == 5                                   # every edit gave a new digest


def test_fingerprint_ignores_swat_outputs_and_manifest(tmp_path):
    from spyswat.swat_calib.scenarios.signature import txinout_fingerprint

    d = _make_inputs(tmp_path)
    before = txinout_fingerprint(d)
    for name, text in (("output.rch", "REACH\n"), ("output.std", "std\n"),
                       ("watout.dat", "dat\n"), (".spyswat_manifest.json", "{}")):
        (d / name).write_text(text)
    assert txinout_fingerprint(d) == before


def test_resume_raises_when_a_scenario_input_changed(env, tmp_path):
    luc = build_txinout(tmp_path, "LUC", cn2="50.00")
    scen = [Scenario("base"), Scenario("luc", txinout_dir=luc)]
    batch = ScenarioBatch(make_project(env), tmp_path / "res")
    out = batch.run(scen, PARAMS[:1], outputs=OUTS, runner=fake_runner)
    assert [r.status for r in out.results] == ["ok", "ok"]

    (luc / "extra1.tmp").write_text("x\n")          # new input file in the scenario folder
    with pytest.raises(ValueError, match="scenario 'luc' inputs changed"):
        batch.run(scen, PARAMS[:1], outputs=OUTS, runner=fake_runner)

    out2 = batch.run(scen, PARAMS[:1], outputs=OUTS, resume=False, runner=fake_runner)
    assert [r.status for r in out2.results] == ["ok", "ok"]


def test_resume_raises_when_the_project_txinout_changed(env, tmp_path):
    base = env[1]                                   # Scenario("base") has txinout_dir=None
    batch = ScenarioBatch(make_project(env), tmp_path / "res")
    out = batch.run([Scenario("base")], PARAMS[:1], outputs=OUTS, runner=fake_runner)
    assert out.results[0].status == "ok"

    target = base / "pcp1.pcp"
    target.write_text("12.5\n")                     # re-written input (new mtime)
    with pytest.raises(ValueError, match="scenario 'base' inputs changed"):
        batch.run([Scenario("base")], PARAMS[:1], outputs=OUTS, runner=fake_runner)


def test_old_signature_without_scenario_inputs_resumes_with_one_info_line(env, tmp_path,
                                                                         caplog):
    luc = build_txinout(tmp_path, "LUC", cn2="50.00")
    scen = [Scenario("base"), Scenario("luc", txinout_dir=luc)]
    batch = ScenarioBatch(make_project(env), tmp_path / "res")
    batch.run(scen, PARAMS[:1], outputs=OUTS, runner=fake_runner)

    sig_path = tmp_path / "res" / ".signature.json"
    sig = json.loads(sig_path.read_text(encoding="utf-8"))
    del sig["scenario_inputs"]                      # results written by 0.2.6
    sig_path.write_text(json.dumps(sig), encoding="utf-8")

    (luc / "extra1.tmp").write_text("x\n")          # no stored fingerprint: not verifiable
    with caplog.at_level(logging.INFO):
        out = batch.run(scen, PARAMS[:1], outputs=OUTS, runner=fake_runner)
    assert [r.status for r in out.results] == ["skipped", "skipped"]
    lines = [r.message for r in caplog.records if "cannot verify" in r.message]
    assert len(lines) == 1
    assert "results written by an older version" in lines[0]


def test_removed_scenario_names_keep_their_fingerprint(env, tmp_path):
    luc = build_txinout(tmp_path, "LUC", cn2="50.00")
    batch = ScenarioBatch(make_project(env), tmp_path / "res")
    batch.run([Scenario("base"), Scenario("luc", txinout_dir=luc)], PARAMS[:1],
              outputs=OUTS, runner=fake_runner)
    batch.run([Scenario("luc", txinout_dir=luc)], PARAMS[:1], outputs=OUTS,
              runner=fake_runner)                   # 'base' is not in this call
    sig = json.loads((tmp_path / "res" / ".signature.json").read_text(encoding="utf-8"))
    assert set(sig["scenario_inputs"]) == {"base", "luc"}

    (env[1] / "extra1.tmp").write_text("x\n")       # edit the project TxtInOut of 'base'
    with pytest.raises(ValueError, match="scenario 'base' inputs changed"):
        batch.run([Scenario("base"), Scenario("luc", txinout_dir=luc)], PARAMS[:1],
                  outputs=OUTS, runner=fake_runner)
