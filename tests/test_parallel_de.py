"""
Tests for SWATCalibration.parallel_de().

Khong can SWAT exe: run_batch bi mock.
Verifies: return structure, convergence on synthetic data,
bounds, seed reproducibility, early stopping, strategy variants.

Reference: Storn & Price (1997), Journal of Global Optimization, 11(4), 341-359.
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.calibration import SWATCalibration


def make_calib(n_parallel=4):
    project = MagicMock()
    project.WorkingFolder.n_parallel = n_parallel
    return SWATCalibration(project)


@pytest.fixture
def obs():
    rng = np.random.default_rng(0)
    idx = pd.date_range('2000-01-01', periods=100, freq='D')
    return pd.Series(rng.uniform(1, 10, 100), index=idx)


PARAM_RANGES = {
    'CN2.mgt':     (35.0, 98.0),
    'ALPHA_BF.gw': (0.0,  1.0),
    'ESCO.hru':    (0.0,  1.0),
}


def make_mock_run_batch(score_fn):
    """score_fn(param_sets) -> list of floats."""
    def _run_batch(param_sets, *args, **kwargs):
        scores = score_fn(param_sets)
        metric = kwargs.get('metrics', args[1] if len(args) > 1 else ['nse'])
        if isinstance(metric, list):
            m = metric[0]
        else:
            m = metric
        return pd.DataFrame({m: scores})
    return _run_batch


# ─── return structure ────────────────────────────────────────────────────────

class TestReturnStructure:
    def test_keys_present(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6)
        assert {'best_params', 'best_score', 'history', 'all_evaluations'}.issubset(result.keys())

    def test_best_params_keys(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6)
        assert set(result['best_params'].keys()) == set(PARAM_RANGES.keys())

    def test_history_shape(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=3, seed=0, pop_size=6,
                                tol=0.0, patience=100)
        # gen 0 + 3 generations = 4 rows
        assert result['history'].shape[0] == 4

    def test_history_columns(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6)
        assert {'generation', 'best_score', 'mean_score', 'std_score'}.issubset(
            result['history'].columns)

    def test_all_evaluations_has_score(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6,
                                tol=0.0, patience=100)
        assert 'score' in result['all_evaluations'].columns


# ─── bounds ──────────────────────────────────────────────────────────────────

class TestBounds:
    def test_best_params_within_bounds(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=3, seed=0, pop_size=8)
        for name, val_list in result['best_params'].items():
            val = val_list[0][0]
            lo, hi = PARAM_RANGES[name]
            assert lo <= val <= hi, "Out of bounds: " + name + "=" + str(val)

    def test_all_evaluations_within_bounds(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6,
                                tol=0.0, patience=100)
        df = result['all_evaluations']
        for name in PARAM_RANGES:
            lo, hi = PARAM_RANGES[name]
            assert df[name].between(lo, hi).all(), "History out of bounds: " + name


# ─── reproducibility ─────────────────────────────────────────────────────────

class TestReproducibility:
    def test_same_seed_same_result(self, obs):
        def scorer(ps): return [0.5] * len(ps)
        c1 = make_calib()
        c2 = make_calib()
        c1._manager.run_batch = make_mock_run_batch(scorer)
        c2._manager.run_batch = make_mock_run_batch(scorer)
        r1 = c1.parallel_de(PARAM_RANGES, obs, max_generations=3, seed=7, pop_size=6,
                             tol=0.0, patience=100)
        r2 = c2.parallel_de(PARAM_RANGES, obs, max_generations=3, seed=7, pop_size=6,
                             tol=0.0, patience=100)
        assert r1['best_score'] == pytest.approx(r2['best_score'])
        pd.testing.assert_frame_equal(r1['all_evaluations'], r2['all_evaluations'])


# ─── convergence ─────────────────────────────────────────────────────────────

class TestConvergence:
    def test_best_score_nondecreasing(self, obs):
        """best_score trong history phai khong giam theo the he."""
        rng = np.random.default_rng(42)
        # Simulate noisily increasing scores
        call_count = [0]
        def scorer(ps):
            call_count[0] += 1
            return [rng.uniform(0, 1) for _ in ps]

        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(scorer)
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=5, seed=0, pop_size=8,
                                tol=0.0, patience=100)
        hist = result['history']['best_score'].tolist()
        for i in range(1, len(hist)):
            assert hist[i] >= hist[i-1] - 1e-9, (
                "best_score decreased at gen " + str(i) + ": " + str(hist[i-1]) + " -> " + str(hist[i])
            )

    def test_best_score_equals_history_best(self, obs):
        """result['best_score'] phai bang max(all_evaluations['score'])."""
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(
            lambda ps: list(np.random.default_rng(1).uniform(0, 1, len(ps)))
        )
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=3, seed=1, pop_size=6,
                                tol=0.0, patience=100)
        assert result['best_score'] == pytest.approx(
            result['all_evaluations']['score'].max()
        )


# ─── early stopping ───────────────────────────────────────────────────────────

class TestEarlyStopping:
    def test_patience_stops_early(self, obs):
        """Neu best_score khong cai thien trong 'patience' gen, dung som."""
        c = make_calib()
        # Constant score -> no improvement ever
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=20, seed=0, pop_size=6,
                                patience=3, tol=0.0)
        # Should stop well before 20+1=21 history rows
        assert result['history'].shape[0] <= 5   # gen0 + 3 patience + 1

    def test_tol_stops_early(self, obs):
        """Khi population hoi tu (std=0 -> tol trigger), dung som."""
        c = make_calib()
        # All same score -> tol triggered immediately after gen 1
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.6] * len(ps))
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=20, seed=0, pop_size=6,
                                tol=1e-6, patience=100)
        assert result['history'].shape[0] <= 4


# ─── strategy variants ────────────────────────────────────────────────────────

class TestStrategy:
    def test_best_1_bin_runs(self, obs):
        """strategy='best/1/bin' khong raise loi."""
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(
            lambda ps: list(np.random.default_rng(0).uniform(0, 1, len(ps)))
        )
        result = c.parallel_de(PARAM_RANGES, obs, max_generations=2, seed=0, pop_size=6,
                                strategy='best/1/bin', tol=0.0, patience=100)
        assert 'best_params' in result

    def test_invalid_strategy(self, obs):
        c = make_calib()
        c._manager.run_batch = make_mock_run_batch(lambda ps: [0.5] * len(ps))
        with pytest.raises(ValueError, match="strategy"):
            c.parallel_de(PARAM_RANGES, obs, strategy='invalid')


# ─── param_methods ────────────────────────────────────────────────────────────

class TestParamMethodsDE:
    def test_custom_method_applied(self, obs):
        captured = []
        def capture(ps, *args, **kwargs):
            captured.extend(ps)
            return pd.DataFrame({'nse': [0.5] * len(ps)})

        c = make_calib()
        c._manager.run_batch = capture
        methods = {'CN2.mgt': 'r', 'ALPHA_BF.gw': 'a', 'ESCO.hru': 'v'}
        c.parallel_de(PARAM_RANGES, obs, max_generations=1, seed=0, pop_size=6,
                      param_methods=methods, tol=0.0, patience=100)

        for ps in captured:
            assert ps['CN2.mgt'][0][1] == 'r'
            assert ps['ALPHA_BF.gw'][0][1] == 'a'
            assert ps['ESCO.hru'][0][1] == 'v'
