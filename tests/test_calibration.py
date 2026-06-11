"""
Unit tests for SWATCalibration — GLUE, analyze(), 95PPU, param_methods.
Khong can SWAT exe: run_batch bi mock de tra ve DataFrame gia.
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from spyswat.swat_calib.analysis.calibration import SWATCalibration
from spyswat.swat_calib.analysis.statistics import SWATAnalysis


def make_project():
    """Project mock du de SWATCalibration khoi tao."""
    project = MagicMock()
    project.WorkingFolder.n_parallel = 4
    return project


def mock_run_batch(scores, metric='nse'):
    """Tao mock run_batch tra ve DataFrame (dung interface thuc)."""
    return MagicMock(return_value=pd.DataFrame({metric: scores}))


@pytest.fixture
def calib():
    project = make_project()
    return SWATCalibration(project)


@pytest.fixture
def obs():
    rng = np.random.default_rng(0)
    idx = pd.date_range('2000-01-01', periods=365, freq='D')
    return pd.Series(rng.uniform(1, 10, 365), index=idx)


PARAM_RANGES = {
    'CN2.mgt':     (35.0, 98.0),
    'ALPHA_BF.gw': (0.0,  1.0),
}


# ── glue_analysis ─────────────────────────────────────────────────────────────

class TestGlueAnalysis:
    def test_returns_expected_keys(self, calib, obs):
        scores = np.random.default_rng(1).uniform(0, 1, 20).tolist()
        calib._manager.run_batch = mock_run_batch(scores)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=20, threshold=0.5, seed=42)
        assert {'all_results', 'behavioral_results', 'behavioral_ratio',
                'parameter_ranges', 'threshold'}.issubset(result.keys())

    def test_all_results_length(self, calib, obs):
        n = 30
        calib._manager.run_batch = mock_run_batch([0.6] * n)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=n, seed=0)
        assert len(result['all_results']) == n

    def test_behavioral_filter(self, calib, obs):
        scores = [0.8, 0.7, 0.6, 0.6, 0.6, 0.6, 0.4, 0.3, 0.2, 0.1]
        calib._manager.run_batch = mock_run_batch(scores)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=10, threshold=0.5, seed=0)
        assert len(result['behavioral_results']) == 6
        assert result['behavioral_ratio'] == pytest.approx(0.6)

    def test_seed_reproducible(self, obs):
        """Cung seed -> cung bo tham so LHS."""
        project = make_project()
        c1 = SWATCalibration(project)
        c2 = SWATCalibration(project)
        c1._manager.run_batch = mock_run_batch([0.5] * 10)
        c2._manager.run_batch = mock_run_batch([0.5] * 10)
        r1 = c1.glue_analysis(PARAM_RANGES, obs, n_samples=10, seed=99)
        r2 = c2.glue_analysis(PARAM_RANGES, obs, n_samples=10, seed=99)
        pd.testing.assert_frame_equal(
            r1['all_results'][list(PARAM_RANGES)],
            r2['all_results'][list(PARAM_RANGES)]
        )

    def test_metric_column_present(self, calib, obs):
        calib._manager.run_batch = mock_run_batch([0.5] * 10)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=10, metric='nse', seed=0)
        assert 'nse' in result['all_results'].columns

    def test_param_values_in_range(self, calib, obs):
        calib._manager.run_batch = mock_run_batch([0.5] * 50)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=50, seed=0)
        df = result['all_results']
        assert df['CN2.mgt'].between(35.0, 98.0).all()
        assert df['ALPHA_BF.gw'].between(0.0, 1.0).all()

    def test_no_uncertainty_keys_by_default(self, calib, obs):
        """compute_uncertainty=False (default) khong them keys ppu."""
        calib._manager.run_batch = mock_run_batch([0.6] * 10)
        result = calib.glue_analysis(PARAM_RANGES, obs, n_samples=10, seed=0)
        assert 'p_factor' not in result
        assert 'r_factor' not in result


# ── _compute_uncertainty_band ─────────────────────────────────────────────────

class TestComputeUncertaintyBand:
    """Test 95PPU logic voi SWAT mock."""

    def _make_calib_with_sim(self, obs_idx, sim_values_per_run):
        project = make_project()
        project.get_date_range.return_value = obs_idx

        call_count = [0]
        def read_rch_side_effect(**kwargs):
            idx = call_count[0]
            call_count[0] += 1
            sim = pd.Series(sim_values_per_run[idx % len(sim_values_per_run)])
            return {kwargs.get('columns', ['FLOW_OUTcms'])[-1]: sim}

        project.Output.read_rch.side_effect = read_rch_side_effect
        project.HRU.update_params = MagicMock()
        project.run = MagicMock()

        calib = SWATCalibration(project)
        calib._manager._backup_state = MagicMock()
        calib._manager._restore_state = MagicMock()
        return calib

    def test_p_factor_range(self, obs):
        """p-factor phai nam trong [0, 1]."""
        rng = np.random.default_rng(42)
        idx = obs.index
        n_behavioral = 5
        sim_values = [rng.uniform(1, 10, len(idx)) for _ in range(n_behavioral)]

        calib = self._make_calib_with_sim(idx, sim_values)

        behavioral_df = pd.DataFrame({
            'CN2.mgt': rng.uniform(35, 98, n_behavioral),
            'ALPHA_BF.gw': rng.uniform(0, 1, n_behavioral),
            'nse': rng.uniform(0.5, 0.9, n_behavioral),
        })

        unc = calib._compute_uncertainty_band(behavioral_df, obs)
        assert 0.0 <= unc['p_factor'] <= 1.0

    def test_r_factor_positive(self, obs):
        """r-factor phai > 0."""
        rng = np.random.default_rng(7)
        idx = obs.index
        n_behavioral = 4
        sim_values = [rng.uniform(1, 10, len(idx)) for _ in range(n_behavioral)]
        calib = self._make_calib_with_sim(idx, sim_values)

        behavioral_df = pd.DataFrame({
            'CN2.mgt': rng.uniform(35, 98, n_behavioral),
            'ALPHA_BF.gw': rng.uniform(0, 1, n_behavioral),
            'nse': rng.uniform(0.5, 0.9, n_behavioral),
        })

        unc = calib._compute_uncertainty_band(behavioral_df, obs)
        assert unc['r_factor'] > 0

    def test_band_df_shape(self, obs):
        """uncertainty_band phai co cot lower/upper/obs."""
        rng = np.random.default_rng(3)
        idx = obs.index
        n_behavioral = 3
        sim_values = [rng.uniform(1, 10, len(idx)) for _ in range(n_behavioral)]
        calib = self._make_calib_with_sim(idx, sim_values)

        behavioral_df = pd.DataFrame({
            'CN2.mgt': rng.uniform(35, 98, n_behavioral),
            'ALPHA_BF.gw': rng.uniform(0, 1, n_behavioral),
            'nse': rng.uniform(0.5, 0.9, n_behavioral),
        })

        unc = calib._compute_uncertainty_band(behavioral_df, obs)
        band = unc['uncertainty_band']
        assert set(band.columns) >= {'lower', 'upper', 'obs'}

    def test_lower_le_upper(self, obs):
        """ppu_lower <= ppu_upper tai moi time step."""
        rng = np.random.default_rng(5)
        idx = obs.index
        n_behavioral = 6
        sim_values = [rng.uniform(0, 15, len(idx)) for _ in range(n_behavioral)]
        calib = self._make_calib_with_sim(idx, sim_values)

        behavioral_df = pd.DataFrame({
            'CN2.mgt': rng.uniform(35, 98, n_behavioral),
            'ALPHA_BF.gw': rng.uniform(0, 1, n_behavioral),
            'nse': rng.uniform(0.5, 0.9, n_behavioral),
        })

        unc = calib._compute_uncertainty_band(behavioral_df, obs)
        band = unc['uncertainty_band']
        assert (band['lower'] <= band['upper']).all()


# ── analyze ───────────────────────────────────────────────────────────────────

class TestAnalyze:
    def _mock_project_for_analyze(self):
        project = make_project()
        idx = pd.date_range('2000-01-01', periods=365, freq='D')
        sim_series = pd.Series(np.ones(365) * 5.0)
        project.Output.read_rch.return_value = {'FLOW_OUTcms': sim_series}
        project.get_date_range.return_value = idx
        return project

    def test_analyze_returns_expected_keys(self, obs):
        project = self._mock_project_for_analyze()
        calib = SWATCalibration(project)
        n = 20
        calib._manager.run_batch = mock_run_batch([0.6] * n)
        calib._manager.run_iteration = MagicMock(return_value=0.6)

        result = calib.analyze(PARAM_RANGES, obs, n_samples=n, threshold=0.5, seed=0)
        expected = {'best_params', 'best_score', 'all_results',
                    'behavioral_results', 'behavioral_ratio',
                    'sensitivity', 'performance'}
        assert expected.issubset(result.keys())

    def test_best_score_is_max(self, obs):
        project = self._mock_project_for_analyze()
        calib = SWATCalibration(project)
        scores = [0.3, 0.8, 0.5, 0.6, 0.7, 0.4, 0.2, 0.9, 0.1, 0.55]
        calib._manager.run_batch = mock_run_batch(scores)
        calib._manager.run_iteration = MagicMock(return_value=0.9)

        result = calib.analyze(PARAM_RANGES, obs, n_samples=10, seed=0)
        assert result['best_score'] == pytest.approx(max(scores))


# ── param_methods ─────────────────────────────────────────────────────────────

class TestParamMethods:
    """param_methods dict duoc truyen vao param_sets dung phuong phap chi dinh."""

    def test_default_method_is_v(self, calib, obs):
        """Neu param_methods=None, tat ca params phai dung 'v'."""
        captured = []
        def capture_run_batch(param_sets, *args, **kwargs):
            captured.extend(param_sets)
            return pd.DataFrame({'nse': [0.6] * len(param_sets)})

        calib._manager.run_batch = capture_run_batch
        calib.glue_analysis(PARAM_RANGES, obs, n_samples=5, seed=0)
        for ps in captured:
            for name, val_list in ps.items():
                assert val_list[0][1] == 'v', "Expected 'v' for " + name + ", got " + val_list[0][1]

    def test_custom_method_applied(self, calib, obs):
        """param_methods chi dinh method cho moi tham so."""
        captured = []
        def capture_run_batch(param_sets, *args, **kwargs):
            captured.extend(param_sets)
            return pd.DataFrame({'nse': [0.6] * len(param_sets)})

        calib._manager.run_batch = capture_run_batch
        methods = {'CN2.mgt': 'r', 'ALPHA_BF.gw': 'a'}
        calib.glue_analysis(PARAM_RANGES, obs, n_samples=5, seed=0, param_methods=methods)

        for ps in captured:
            assert ps['CN2.mgt'][0][1] == 'r'
            assert ps['ALPHA_BF.gw'][0][1] == 'a'

    def test_partial_methods_fallback_to_v(self, calib, obs):
        """Tham so khong co trong param_methods -> mac dinh 'v'."""
        captured = []
        def capture_run_batch(param_sets, *args, **kwargs):
            captured.extend(param_sets)
            return pd.DataFrame({'nse': [0.6] * len(param_sets)})

        calib._manager.run_batch = capture_run_batch
        methods = {'CN2.mgt': 'r'}
        calib.glue_analysis(PARAM_RANGES, obs, n_samples=5, seed=0, param_methods=methods)

        for ps in captured:
            assert ps['CN2.mgt'][0][1] == 'r'
            assert ps['ALPHA_BF.gw'][0][1] == 'v'
