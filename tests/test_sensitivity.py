"""
Failed-run handling of SWATSensitivity (OAT, Morris, Morris/SALib, Sobol/SALib).
run_batch is mocked: a failed run is NaN (contract C1). No substitute value may
ever reach a sensitivity index.
"""
import logging

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.sensitivity import SWATSensitivity

RANGES = {"A.mgt": (0.0, 1.0), "B.gw": (0.0, 1.0)}


def make_sens():
    project = MagicMock()
    project.WorkingFolder.n_parallel = 4
    s = SWATSensitivity(project)
    s._manager.setup_parallel = MagicMock()
    s._manager.record_run = MagicMock()
    return s


def batch_fn(fail_idx=(), fail_all=False):
    """run_batch mock: score = A + 2B; rows in fail_idx (global index) are NaN."""
    def fn(param_sets, obs, metrics, *a, **kw):
        vals = [ps["A.mgt"][0][0] + 2 * ps["B.gw"][0][0] for ps in param_sets]
        for i in range(len(vals)):
            if fail_all or i in fail_idx:
                vals[i] = float("nan")
        return pd.DataFrame({metrics[0]: vals})
    return fn


@pytest.fixture
def obs():
    return pd.Series(np.ones(10), index=pd.date_range("2000-01-01", periods=10))


# ── OAT ──────────────────────────────────────────────────────────────────────

class TestOAT:
    def test_failed_runs_are_nan_and_warned(self, obs, caplog):
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_idx=(1,))
        with caplog.at_level(logging.WARNING):
            df, idx = s.one_at_a_time(RANGES, n_steps=4, observed_series=obs)
        assert df["metric"].isna().sum() == 1
        assert "failed 1 of 8 runs" in caplog.text
        assert np.isfinite(idx["sensitivity_index"]).all()
        assert df["metric"].abs().max() < 10          # no 1e6 substitute

    def test_no_obs_restores_inputs_byte_identical(self, tmp_path):
        s = make_sens()
        f = tmp_path / "000010001.mgt"
        f.write_bytes(b"CN2 = 70\n")
        original = f.read_bytes()
        backup = {}
        s._manager._backup_state = MagicMock(side_effect=lambda: backup.update(b=f.read_bytes()))
        s._manager._restore_state = MagicMock(side_effect=lambda: f.write_bytes(backup["b"]))
        s.project.HRU.update_params.side_effect = lambda p: f.write_bytes(b"CN2 = 99\n")
        s.project.Output.read_rch.return_value = {"FLOW_OUTcms": pd.Series([1.0, 2.0])}
        s.one_at_a_time(RANGES, n_steps=3)
        assert f.read_bytes() == original
        assert s._manager._backup_state.call_count == s._manager._restore_state.call_count == 6

    def test_no_obs_records_every_run(self):
        s = make_sens()
        s._manager._backup_state = MagicMock()
        s._manager._restore_state = MagicMock()
        s.project.Output.read_rch.return_value = {"FLOW_OUTcms": pd.Series([1.0, 3.0])}
        calls = {"n": 0}

        def run():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
        s.project.run.side_effect = run
        s.one_at_a_time(RANGES, n_steps=2)           # 4 runs, the 2nd fails
        rec = s._manager.record_run.call_args_list
        assert len(rec) == 4
        assert all(c.kwargs["mode"] == "sensitivity" for c in rec)
        assert [c.kwargs["status"] for c in rec] == ["ok", "failed", "ok", "ok"]
        assert rec[0].args[1] == {"mean_FLOW_OUTcms": 2.0}
        assert rec[1].args[1] is None and "boom" in rec[1].kwargs["error"]

    def test_no_obs_restores_when_run_fails(self, tmp_path):
        s = make_sens()
        s._manager._backup_state = MagicMock()
        s._manager._restore_state = MagicMock()
        s.project.run.side_effect = RuntimeError("swat died")
        df, _ = s.one_at_a_time(RANGES, n_steps=2)
        assert df["metric"].isna().all()
        assert s._manager._restore_state.call_count == 4


# ── Morris (built-in) ────────────────────────────────────────────────────────

class TestMorrisBuiltin:
    def test_drops_trajectory_with_failure(self, obs, caplog):
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_idx=(1,))        # inside trajectory 0
        with caplog.at_level(logging.WARNING):
            r = s.morris_method(RANGES, n_trajectories=4, observed_series=obs, seed=0)
        assert "failed 1 of 12 runs" in caplog.text
        assert "dropped 1 of 4 trajectories" in caplog.text
        mu_star = r["morris_indices"]["mu_star"]
        assert (mu_star < 100).all()                          # no 1e6 / delta blow-up

    def test_fewer_than_two_trajectories_raises(self, obs):
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_all=True)
        with pytest.raises(RuntimeError, match="0 of 4"):
            s.morris_method(RANGES, n_trajectories=4, observed_series=obs, seed=0)


# ── SALib based (skipped when SALib is not installed) ───────────────────────

class TestSALib:
    def test_morris_salib_drops_failed_trajectory(self, obs, caplog):
        pytest.importorskip("SALib")
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_idx=(4,))
        with caplog.at_level(logging.WARNING):
            r = s.morris_salib(RANGES, obs, n_trajectories=6, num_resamples=50)
        assert "failed 1 of 18 runs" in caplog.text
        assert "dropped 1 of 6 trajectories" in caplog.text
        assert (r["mu_star"] < 100).all()
        assert np.isnan(s.last_scores).sum() == 1

    def test_morris_salib_too_few_raises(self, obs):
        pytest.importorskip("SALib")
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_all=True)
        with pytest.raises(RuntimeError, match="at least 2"):
            s.morris_salib(RANGES, obs, n_trajectories=4)

    def test_morris_salib_clean_run(self, obs, caplog):
        pytest.importorskip("SALib")
        s = make_sens()
        s._manager.run_batch = batch_fn()
        r = s.morris_salib(RANGES, obs, n_trajectories=6, num_resamples=50)
        assert r.iloc[0]["parameter"] == "B.gw"

    def test_sobol_failure_raises_and_keeps_data(self, obs):
        pytest.importorskip("SALib")
        s = make_sens()
        s._manager.run_batch = batch_fn(fail_idx=(2,))
        with pytest.raises(RuntimeError, match="1 of"):
            s.sobol_method(RANGES, obs, N=16, num_resamples=50)
        assert s.last_samples is not None and len(s.last_samples) == len(s.last_scores)
        assert int(np.isnan(s.last_scores).sum()) == 1

    def test_sobol_clean_run(self, obs):
        pytest.importorskip("SALib")
        s = make_sens()
        s._manager.run_batch = batch_fn()
        r = s.sobol_method(RANGES, obs, N=16, num_resamples=50)
        assert r.iloc[0]["parameter"] == "B.gw"


# ── OAT index, num_levels, < 2 successes ────────────────────────────────────

class TestOATIndex:
    RANGES3 = {"x1": (0.0, 1.0), "x2": (0.0, 1.0), "x3": (0.0, 1.0)}

    def _run(self, obs, fail=None):
        s = make_sens()

        def fn(param_sets, o, metrics, *a, **kw):
            vals = []
            for ps in param_sets:
                x = {k: v[0][0] for k, v in ps.items()}
                vals.append(3.0 * x["x1"] + 1.0 * x["x2"] + 0.0 * x["x3"])
            if fail:
                vals = [float("nan") if (i % 4 in fail.get(k, ())) else v
                        for i, (k, v) in enumerate(zip(["x1"] * 4 + ["x2"] * 4 + ["x3"] * 4, vals))]
            return pd.DataFrame({metrics[0]: vals})
        s._manager.run_batch = fn
        return s.one_at_a_time(self.RANGES3, n_steps=4, observed_series=obs,
                               baseline_params={"x1": 0.5, "x2": 0.5, "x3": 0.5})[1]

    def test_ranking_follows_effect_size(self, obs):
        idx = self._run(obs)
        assert idx["parameter"].tolist() == ["x1", "x2", "x3"]
        d = idx.set_index("parameter")
        assert d.loc["x1", "sensitivity_index"] == pytest.approx(1.0)
        assert d.loc["x2", "sensitivity_index"] == pytest.approx(1.0 / 3.0)
        assert d.loc["x3", "sensitivity_index"] == 0.0
        assert {"metric_range", "metric_std", "range_over_std"} <= set(idx.columns)

    def test_fewer_than_two_successes_is_nan(self, obs, caplog):
        with caplog.at_level(logging.WARNING):
            idx = self._run(obs, fail={"x2": (0, 1, 2)})   # x2: one success only
        d = idx.set_index("parameter")
        assert np.isnan(d.loc["x2", "sensitivity_index"])
        assert d.loc["x1", "sensitivity_index"] == pytest.approx(1.0)
        assert "parameter 'x2' has 1 successful" in caplog.text
        assert idx["parameter"].iloc[-1] == "x2"


class TestMorrisLevels:
    def test_num_levels_6_recovers_linear_mu_star(self, obs):
        pytest.importorskip("SALib")
        ranges = {"x1": (0, 1), "x2": (0, 1), "x3": (0, 1)}
        s = make_sens()

        def fn(param_sets, o, metrics, *a, **kw):
            X = np.array([[ps[n][0][0] for n in ("x1", "x2", "x3")] for ps in param_sets])
            return pd.DataFrame({metrics[0]: 2.0 * X[:, 0] + 1.0 * X[:, 1]})
        s._manager.run_batch = fn
        r = s.morris_salib(ranges, obs, n_trajectories=10, num_levels=6,
                           num_resamples=20).set_index("parameter")["mu_star"]
        assert r["x1"] == pytest.approx(2.0, abs=1e-9)
        assert r["x2"] == pytest.approx(1.0, abs=1e-9)
        assert r["x3"] == pytest.approx(0.0, abs=1e-9)
