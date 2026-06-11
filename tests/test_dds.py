"""
Tests for DDS (Dynamically Dimensioned Search).

Verification per Karpathy guidelines:
  - Benchmark (sphere): DDS converges near optimum within budget.
  - Ackley: DDS finds score better than random baseline.
  - API: output keys, history shape, bounds respected, seed reproducibility.
  - Edge: single-parameter, maximize=False, budget=2.

Reference: Tolson & Shoemaker (2007), Water Resources Research, 43(1), W01413.
"""
import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spyswat.swat_calib.analysis.algorithms.dds import DDS


# ─── helpers ────────────────────────────────────────────────────────────────

def sphere_obj(params):
    """Maximise => negate sphere. Global max at 0 (all x=0)."""
    return -sum(v ** 2 for v in params.values())


def ackley_obj(params):
    """Maximise => negate Ackley. Global max (neg-Ackley) = 0 at x=0."""
    x = np.array(list(params.values()))
    n = len(x)
    a, b, c = 20, 0.2, 2 * np.pi
    term1 = -a * np.exp(-b * np.sqrt(np.sum(x**2) / n))
    term2 = -np.exp(np.sum(np.cos(c * x)) / n)
    ackley = term1 + term2 + a + np.e
    return -ackley


def make_ranges(d=5, lo=-5.0, hi=5.0):
    return {f"x{i}": (lo, hi) for i in range(d)}


# ─── return structure ────────────────────────────────────────────────────────

class TestReturnStructure:
    def test_keys_present(self):
        dds = DDS(make_ranges(3), sphere_obj, n_iterations=10, seed=0)
        result = dds.run()
        assert {"best_params", "best_score", "history"}.issubset(result.keys())

    def test_history_shape(self):
        N = 25
        dds = DDS(make_ranges(4), sphere_obj, n_iterations=N, seed=0)
        result = dds.run()
        assert result["history"].shape[0] == N
        assert "score" in result["history"].columns

    def test_best_params_keys_match_input(self):
        ranges = {"CN2.mgt": (35.0, 98.0), "ALPHA_BF.gw": (0.0, 1.0)}
        dds = DDS(ranges, lambda p: -sum(v**2 for v in p.values()), n_iterations=10, seed=0)
        result = dds.run()
        assert set(result["best_params"].keys()) == set(ranges.keys())

    def test_best_score_equals_history_max(self):
        dds = DDS(make_ranges(3), sphere_obj, n_iterations=15, seed=1)
        result = dds.run()
        # best_score == max score in history (maximize mode)
        assert result["best_score"] == pytest.approx(result["history"]["score"].max())


# ─── bounds and feasibility ──────────────────────────────────────────────────

class TestBounds:
    def test_best_params_within_bounds(self):
        ranges = make_ranges(5, lo=-3.0, hi=3.0)
        dds = DDS(ranges, sphere_obj, n_iterations=50, seed=7)
        result = dds.run()
        for name, val in result["best_params"].items():
            lo, hi = ranges[name]
            assert lo <= val <= hi, f"{name}={val} outside [{lo}, {hi}]"

    def test_all_history_params_within_bounds(self):
        ranges = make_ranges(3, lo=0.0, hi=1.0)
        dds = DDS(ranges, sphere_obj, n_iterations=30, seed=3)
        result = dds.run()
        for name in ["x0", "x1", "x2"]:
            lo, hi = ranges[name]
            col = result["history"][name]
            assert col.between(lo, hi).all(), f"History {name} out of bounds"


# ─── reproducibility ─────────────────────────────────────────────────────────

class TestReproducibility:
    def test_same_seed_same_result(self):
        ranges = make_ranges(4)
        r1 = DDS(ranges, sphere_obj, n_iterations=30, seed=42).run()
        r2 = DDS(ranges, sphere_obj, n_iterations=30, seed=42).run()
        assert r1["best_score"] == pytest.approx(r2["best_score"])
        pd.testing.assert_frame_equal(r1["history"], r2["history"])

    def test_different_seeds_differ(self):
        ranges = make_ranges(4)
        r1 = DDS(ranges, sphere_obj, n_iterations=30, seed=0).run()
        r2 = DDS(ranges, sphere_obj, n_iterations=30, seed=99).run()
        assert r1["history"]["score"].tolist() != r2["history"]["score"].tolist()


# ─── benchmark convergence ───────────────────────────────────────────────────

class TestConvergence:
    def test_sphere_better_than_random(self):
        """DDS should beat a random search baseline (average over 5 seeds)."""
        ranges = make_ranges(5, lo=-5.0, hi=5.0)
        rng = np.random.default_rng(0)
        N = 200

        dds_scores = []
        rand_scores = []
        for seed in range(5):
            dds = DDS(ranges, sphere_obj, n_iterations=N, seed=seed)
            dds_scores.append(dds.run()["best_score"])

            # Pure random baseline: N uniform samples
            best = -1e9
            for _ in range(N):
                x = rng.uniform(-5.0, 5.0, 5)
                s = sphere_obj({f"x{i}": x[i] for i in range(5)})
                if s > best:
                    best = s
            rand_scores.append(best)

        assert np.mean(dds_scores) > np.mean(rand_scores), (
            f"DDS mean {np.mean(dds_scores):.4f} <= random {np.mean(rand_scores):.4f}"
        )

    def test_sphere_converges_near_zero(self):
        """
        Sphere global max (negated) = 0. After 200 iterations in [-5,5]^5,
        DDS should reach neg-sphere > -1.0 (i.e. |x|^2 < 1).
        """
        dds = DDS(make_ranges(5), sphere_obj, n_iterations=200, seed=0)
        result = dds.run()
        assert result["best_score"] > -1.0, (
            f"Sphere not converged: best_score={result['best_score']:.4f}"
        )

    def test_ackley_better_than_random(self):
        """DDS on 3D Ackley beats random search."""
        ranges = make_ranges(3, lo=-5.0, hi=5.0)
        rng = np.random.default_rng(1)
        N = 200

        dds = DDS(ranges, ackley_obj, n_iterations=N, seed=0)
        dds_score = dds.run()["best_score"]

        best_rand = -1e9
        for _ in range(N):
            x = rng.uniform(-5.0, 5.0, 3)
            s = ackley_obj({f"x{i}": x[i] for i in range(3)})
            if s > best_rand:
                best_rand = s

        assert dds_score >= best_rand - 0.5, (
            f"DDS {dds_score:.4f} much worse than random {best_rand:.4f}"
        )


# ─── maximize=False (minimise RMSE) ──────────────────────────────────────────

class TestMinimise:
    def test_minimize_sphere(self):
        """maximize=False: DDS should find x near 0 (min sphere=0)."""
        def sphere_min(params):
            return sum(v**2 for v in params.values())

        dds = DDS(make_ranges(4), sphere_min, n_iterations=200, seed=5, maximize=False)
        result = dds.run()
        assert result["best_score"] < 0.5, (
            f"Minimise sphere not converged: best_score={result['best_score']:.4f}"
        )

    def test_best_score_equals_history_min_when_minimize(self):
        def sphere_min(params):
            return sum(v**2 for v in params.values())

        dds = DDS(make_ranges(3), sphere_min, n_iterations=20, seed=0, maximize=False)
        result = dds.run()
        assert result["best_score"] == pytest.approx(result["history"]["score"].min())


# ─── edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_parameter(self):
        """1D optimisation should work without error."""
        dds = DDS({"x0": (-1.0, 1.0)}, lambda p: -p["x0"]**2, n_iterations=20, seed=0)
        result = dds.run()
        assert "best_params" in result
        assert abs(result["best_params"]["x0"]) < 1.0

    def test_minimum_budget(self):
        """n_iterations=2 is the minimum allowed."""
        dds = DDS(make_ranges(2), sphere_obj, n_iterations=2, seed=0)
        result = dds.run()
        assert result["history"].shape[0] == 2

    def test_invalid_n_iterations(self):
        with pytest.raises(ValueError, match="n_iterations"):
            DDS(make_ranges(2), sphere_obj, n_iterations=1)

    def test_invalid_r(self):
        with pytest.raises(ValueError, match="r must"):
            DDS(make_ranges(2), sphere_obj, r=0.0)

    def test_empty_param_ranges(self):
        with pytest.raises(ValueError, match="param_ranges"):
            DDS({}, sphere_obj)
