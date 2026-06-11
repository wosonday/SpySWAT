"""
Unit tests for SWATCalibration — GLUE, analyze(), 95PPU, param_methods.
Calls algorithms directly: calib.glue.run(), calib.glue.uncertainty_band().
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.calibration import SWATCalibration


def make_project():
    project = MagicMock()
    project.WorkingFolder.n_parallel = 4
    return project


def mock_run_batch(scores, metric="nse"):
    return MagicMock(return_value=pd.DataFrame({metric: scores}))


@pytest.fixture
def calib():
    return SWATCalibration(make_project())


@pytest.fixture
def obs():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", periods=365, freq="D")
    return pd.Series(rng.uniform(1, 10, 365), index=idx)


PARAM_RANGES = {
    "CN2.mgt":     (35.0, 98.0),
    "ALPHA_BF.gw": (0.0,  1.0),
}


# ── calib.glue.run ────────────────────────────────────────────────────────────

class TestGlueAnalysis:
    def test_returns_expected_keys(self, calib, obs):
        scores = np.random.default_rng(1).uniform(0, 1, 20).tolist()
        calib.manager.run_batch = mock_run_batch(scores)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=20, threshold=0.5, seed=42)
        assert {"all_results", "behavioral_results", "behavioral_ratio",
                "parameter_ranges", "threshold"}.issubset(result.keys())

    def test_all_results_length(self, calib, obs):
        n = 30
        calib.manager.run_batch = mock_run_batch([0.6] * n)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=n, seed=0)
        assert len(result["all_results"]) == n

    def test_behavioral_filter(self, calib, obs):
        scores = [0.8, 0.7, 0.6, 0.6, 0.6, 0.6, 0.4, 0.3, 0.2, 0.1]
        calib.manager.run_batch = mock_run_batch(scores)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=10, threshold=0.5, seed=0)
        assert len(result["behavioral_results"]) == 6
        assert result["behavioral_ratio"] == pytest.approx(0.6)

    def test_seed_reproducible(self, obs):
        c1, c2 = SWATCalibration(make_project()), SWATCalibration(make_project())
        c1.manager.run_batch = mock_run_batch([0.5] * 10)
        c2.manager.run_batch = mock_run_batch([0.5] * 10)
        r1 = c1.glue.run(PARAM_RANGES, obs, n_samples=10, seed=99)
        r2 = c2.glue.run(PARAM_RANGES, obs, n_samples=10, seed=99)
        pd.testing.assert_frame_equal(
            r1["all_results"][list(PARAM_RANGES)],
            r2["all_results"][list(PARAM_RANGES)],
        )

    def test_metric_column_present(self, calib, obs):
        calib.manager.run_batch = mock_run_batch([0.5] * 10)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=10, metric="nse", seed=0)
        assert "nse" in result["all_results"].columns

    def test_param_values_in_range(self, calib, obs):
        calib.manager.run_batch = mock_run_batch([0.5] * 50)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=50, seed=0)
        df = result["all_results"]
        assert df["CN2.mgt"].between(35.0, 98.0).all()
        assert df["ALPHA_BF.gw"].between(0.0, 1.0).all()

    def test_no_uncertainty_keys_by_default(self, calib, obs):
        calib.manager.run_batch = mock_run_batch([0.6] * 10)
        result = calib.glue.run(PARAM_RANGES, obs, n_samples=10, seed=0)
        assert "p_factor" not in result
        assert "r_factor" not in result


# ── calib.glue.uncertainty_band ───────────────────────────────────────────────

class TestComputeUncertaintyBand:

    def _make_calib_with_sim(self, obs_idx, sim_values_per_run):
        project = make_project()
        project.get_date_range.return_value = obs_idx
        call_count = [0]

        def read_rch_side(**kwargs):
            i = call_count[0]; call_count[0] += 1
            sim = pd.Series(sim_values_per_run[i % len(sim_values_per_run)])
            return {kwargs.get("columns", ["FLOW_OUTcms"])[-1]: sim}

        project.Output.read_rch.side_effect = read_rch_side
        project.HRU.update_params = MagicMock()
        project.run = MagicMock()
        calib = SWATCalibration(project)
        calib.manager._backup_state  = MagicMock()
        calib.manager._restore_state = MagicMock()
        return calib

    def _behavioral_df(self, rng, n, idx):
        return pd.DataFrame({
            "CN2.mgt":     rng.uniform(35, 98, n),
            "ALPHA_BF.gw": rng.uniform(0,  1,  n),
            "nse":         rng.uniform(0.5, 0.9, n),
        })

    def test_p_factor_range(self, obs):
        rng = np.random.default_rng(42)
        sims = [rng.uniform(1, 10, len(obs)) for _ in range(5)]
        calib = self._make_calib_with_sim(obs.index, sims)
        unc = calib.glue.uncertainty_band(self._behavioral_df(rng, 5, obs.index), obs)
        assert 0.0 <= unc["p_factor"] <= 1.0

    def test_r_factor_positive(self, obs):
        rng = np.random.default_rng(7)
        sims = [rng.uniform(1, 10, len(obs)) for _ in range(4)]
        calib = self._make_calib_with_sim(obs.index, sims)
        unc = calib.glue.uncertainty_band(self._behavioral_df(rng, 4, obs.index), obs)
        assert unc["r_factor"] > 0

    def test_band_df_shape(self, obs):
        rng = np.random.default_rng(3)
        sims = [rng.uniform(1, 10, len(obs)) for _ in range(3)]
        calib = self._make_calib_with_sim(obs.index, sims)
        unc = calib.glue.uncertainty_band(self._behavioral_df(rng, 3, obs.index), obs)
        assert {"lower", "upper", "obs"}.issubset(set(unc["uncertainty_band"].columns))

    def test_lower_le_upper(self, obs):
        rng = np.random.default_rng(5)
        sims = [rng.uniform(0, 15, len(obs)) for _ in range(6)]
        calib = self._make_calib_with_sim(obs.index, sims)
        unc = calib.glue.uncertainty_band(self._behavioral_df(rng, 6, obs.index), obs)
        assert (unc["uncertainty_band"]["lower"] <= unc["uncertainty_band"]["upper"]).all()


# ── calib.analyze ─────────────────────────────────────────────────────────────

class TestAnalyze:
    def _mock_project(self):
        project = make_project()
        idx = pd.date_range("2000-01-01", periods=365, freq="D")
        project.Output.read_rch.return_value = {"FLOW_OUTcms": pd.Series(np.ones(365) * 5.0)}
        project.get_date_range.return_value  = idx
        return project

    def test_returns_expected_keys(self, obs):
        c = SWATCalibration(self._mock_project())
        n = 20
        c.manager.run_batch     = mock_run_batch([0.6] * n)
        c.manager.run_iteration = MagicMock(return_value=0.6)
        result = c.analyze(PARAM_RANGES, obs, n_samples=n, threshold=0.5, seed=0)
        assert {"best_params", "best_score", "all_results", "behavioral_results",
                "behavioral_ratio", "sensitivity", "performance"}.issubset(result.keys())

    def test_best_score_is_max(self, obs):
        c = SWATCalibration(self._mock_project())
        scores = [0.3, 0.8, 0.5, 0.6, 0.7, 0.4, 0.2, 0.9, 0.1, 0.55]
        c.manager.run_batch     = mock_run_batch(scores)
        c.manager.run_iteration = MagicMock(return_value=0.9)
        result = c.analyze(PARAM_RANGES, obs, n_samples=10, seed=0)
        assert result["best_score"] == pytest.approx(max(scores))


# ── param_methods ─────────────────────────────────────────────────────────────

class TestParamMethods:
    def test_default_method_is_v(self, calib, obs):
        captured = []
        def cap(ps, *a, **kw):
            captured.extend(ps)
            return pd.DataFrame({"nse": [0.6] * len(ps)})
        calib.manager.run_batch = cap
        calib.glue.run(PARAM_RANGES, obs, n_samples=5, seed=0)
        for ps in captured:
            for name, vlist in ps.items():
                assert vlist[0][1] == "v"

    def test_custom_method_applied(self, calib, obs):
        captured = []
        def cap(ps, *a, **kw):
            captured.extend(ps)
            return pd.DataFrame({"nse": [0.6] * len(ps)})
        calib.manager.run_batch = cap
        calib.glue.run(PARAM_RANGES, obs, n_samples=5, seed=0,
                       param_methods={"CN2.mgt": "r", "ALPHA_BF.gw": "a"})
        for ps in captured:
            assert ps["CN2.mgt"][0][1] == "r"
            assert ps["ALPHA_BF.gw"][0][1] == "a"

    def test_partial_methods_fallback_to_v(self, calib, obs):
        captured = []
        def cap(ps, *a, **kw):
            captured.extend(ps)
            return pd.DataFrame({"nse": [0.6] * len(ps)})
        calib.manager.run_batch = cap
        calib.glue.run(PARAM_RANGES, obs, n_samples=5, seed=0,
                       param_methods={"CN2.mgt": "r"})
        for ps in captured:
            assert ps["CN2.mgt"][0][1] == "r"
            assert ps["ALPHA_BF.gw"][0][1] == "v"
