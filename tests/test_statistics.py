"""
Unit tests for SWATAnalysis — metrics and sampling.
Runs without SWAT exe: all computations are pure numpy/pandas.
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.statistics import SWATAnalysis


@pytest.fixture
def analysis():
    project = MagicMock()
    return SWATAnalysis(project)


# ── Metrics ───────────────────────────────────────────────────────────────────

class TestNSE:
    def test_perfect(self, analysis):
        x = np.array([1.0, 2.0, 3.0, 4.0])
        assert analysis._nse(x, x) == pytest.approx(1.0)

    def test_known_value(self, analysis):
        obs = np.array([2.0, 4.0, 6.0, 8.0])
        sim = np.array([1.0, 3.0, 5.0, 7.0])
        # numerator = 4, denominator = 20, NSE = 1 - 4/20 = 0.8
        assert analysis._nse(obs, sim) == pytest.approx(0.8)

    def test_mean_predictor(self, analysis):
        obs = np.array([1.0, 2.0, 3.0, 4.0])
        sim = np.full(4, np.mean(obs))
        assert analysis._nse(obs, sim) == pytest.approx(0.0)


class TestKGE:
    def test_perfect(self, analysis):
        x = np.array([1.0, 2.0, 3.0, 4.0])
        assert analysis._kge(x, x) == pytest.approx(1.0)

    def test_range(self, analysis):
        obs = np.array([1.0, 2.0, 3.0, 4.0])
        sim = np.array([1.1, 2.1, 3.1, 4.1])
        kge = analysis._kge(obs, sim)
        assert kge < 1.0


class TestPBIAS:
    def test_no_bias(self, analysis):
        x = np.array([1.0, 2.0, 3.0])
        assert analysis._pbias(x, x) == pytest.approx(0.0)

    def test_overestimate(self, analysis):
        obs = np.array([1.0, 2.0, 3.0])
        sim = np.array([2.0, 3.0, 4.0])  # sim > obs → negative PBIAS
        pbias = analysis._pbias(obs, sim)
        assert pbias < 0.0

    def test_underestimate(self, analysis):
        obs = np.array([2.0, 3.0, 4.0])
        sim = np.array([1.0, 2.0, 3.0])  # sim < obs → positive PBIAS
        assert analysis._pbias(obs, sim) > 0.0


class TestRSR:
    def test_perfect(self, analysis):
        x = np.array([1.0, 2.0, 3.0, 4.0])
        assert analysis._rsr(x, x) == pytest.approx(0.0)

    def test_zero_std(self, analysis):
        obs = np.array([2.0, 2.0, 2.0])
        sim = np.array([1.0, 2.0, 3.0])
        assert np.isnan(analysis._rsr(obs, sim))


class TestCalculateStatistics:
    def test_returns_all_default_metrics(self, analysis):
        obs = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sim = pd.Series([1.1, 1.9, 3.1, 3.9, 5.1])
        stats = analysis.calculate_statistics(obs, sim)
        assert set(stats.keys()) >= {'nse', 'r2', 'rmse', 'pbias', 'kge'}

    def test_nan_removal(self, analysis):
        obs = pd.Series([1.0, np.nan, 3.0])
        sim = pd.Series([1.0, 2.0, 3.0])
        stats = analysis.calculate_statistics(obs, sim)
        assert not np.isnan(stats['nse'])


class TestEvaluatePerformance:
    def test_very_good(self, analysis):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        ratings = analysis.evaluate_performance(x, x)
        assert ratings['nse'] == 'Very Good'

    def test_unsatisfactory(self, analysis):
        obs = np.array([1.0, 2.0, 3.0])
        sim = np.array([10.0, 20.0, 30.0])
        ratings = analysis.evaluate_performance(obs, sim)
        assert ratings['nse'] == 'Unsatisfactory'


# ── Sampling ──────────────────────────────────────────────────────────────────

class TestGenerateSamples:
    def test_shape(self, analysis):
        ranges = {'CN2.mgt': (35.0, 98.0), 'ALPHA_BF.gw': (0.0, 1.0)}
        df = analysis._generate_samples(ranges, n_samples=50)
        assert df.shape == (50, 2)

    def test_bounds_respected(self, analysis):
        ranges = {'CN2.mgt': (35.0, 98.0), 'ALPHA_BF.gw': (0.0, 1.0)}
        df = analysis._generate_samples(ranges, n_samples=200)
        assert df['CN2.mgt'].between(35.0, 98.0).all()
        assert df['ALPHA_BF.gw'].between(0.0, 1.0).all()

    def test_seed_reproducible(self, analysis):
        ranges = {'CN2.mgt': (35.0, 98.0)}
        df1 = analysis._generate_samples(ranges, n_samples=10, seed=42)
        df2 = analysis._generate_samples(ranges, n_samples=10, seed=42)
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seeds_differ(self, analysis):
        ranges = {'CN2.mgt': (35.0, 98.0)}
        df1 = analysis._generate_samples(ranges, n_samples=10, seed=1)
        df2 = analysis._generate_samples(ranges, n_samples=10, seed=2)
        assert not df1.equals(df2)

    def test_returns_dataframe(self, analysis):
        ranges = {'p1': (0.0, 1.0)}
        result = analysis._generate_samples(ranges, n_samples=5)
        assert isinstance(result, pd.DataFrame)


# ── Sensitivity from results ──────────────────────────────────────────────────

class TestSensitivityFromResults:
    @pytest.fixture
    def results_df(self):
        rng = np.random.default_rng(0)
        n = 200
        x1 = rng.uniform(0, 1, n)
        x2 = rng.uniform(0, 1, n)
        # nse strongly driven by x1, weakly by x2
        nse = 0.9 * x1 + 0.1 * x2 + rng.normal(0, 0.01, n)
        return pd.DataFrame({'CN2.mgt': x1, 'ALPHA_BF.gw': x2, 'nse': nse})

    def test_spearman_ranking(self, analysis, results_df):
        s = analysis.sensitivity_from_results(
            results_df, metric='nse',
            param_names=['CN2.mgt', 'ALPHA_BF.gw'],
            method='spearman'
        )
        assert s.iloc[0]['parameter'] == 'CN2.mgt'

    def test_prcc_ranking(self, analysis, results_df):
        s = analysis.sensitivity_from_results(
            results_df, metric='nse',
            param_names=['CN2.mgt', 'ALPHA_BF.gw'],
            method='prcc'
        )
        assert s.iloc[0]['parameter'] == 'CN2.mgt'

    def test_output_columns(self, analysis, results_df):
        s = analysis.sensitivity_from_results(results_df, metric='nse')
        assert {'parameter', 'sensitivity_index', 'rank'}.issubset(s.columns)

    def test_rank_starts_at_1(self, analysis, results_df):
        s = analysis.sensitivity_from_results(results_df, metric='nse')
        assert s['rank'].iloc[0] == 1

    def test_invalid_method(self, analysis, results_df):
        with pytest.raises(ValueError, match="spearman.*prcc"):
            analysis.sensitivity_from_results(results_df, metric='nse', method='bad')
