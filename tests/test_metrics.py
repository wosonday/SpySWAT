"""
Tests for the metric registry and for the best-score direction of every
calibration algorithm (GLUE, ParallelDE, PSO, DDS, SWATCalibration.optimize),
NaN handling, evaluate_performance and GLUE.uncertainty_band.
All SWAT runs are mocked (run_batch / run_iteration).
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.calibration import SWATCalibration
from spyswat.swat_calib.analysis.statistics import (
    SWATAnalysis, best_index, is_maximize, known_metrics,
    sanitize_scores, to_objective, worst_score,
)

NAN = float("nan")
RANGES = {"CN2.mgt": (35.0, 98.0), "ALPHA_BF.gw": (0.0, 1.0)}


def make_calib():
    project = MagicMock()
    project.WorkingFolder.n_parallel = 4
    return SWATCalibration(project)


@pytest.fixture
def calib():
    return make_calib()


@pytest.fixture
def obs():
    idx = pd.date_range("2000-01-01", periods=60, freq="D")
    return pd.Series(np.random.default_rng(0).uniform(1, 10, 60), index=idx)


def fixed_batch(scores, metric):
    return MagicMock(return_value=pd.DataFrame({metric: list(scores)}))


# ── registry ─────────────────────────────────────────────────────────────────

class TestRegistry:
    @pytest.mark.parametrize("m", ["nse", "r2", "kge", "correlation"])
    def test_maximise(self, m):
        assert is_maximize(m)
        assert to_objective(m, 0.7) == pytest.approx(-0.7)
        assert worst_score(m) < -1e3

    @pytest.mark.parametrize("m", ["rmse", "mae", "rsr", "pbias"])
    def test_minimise(self, m):
        assert not is_maximize(m)
        assert worst_score(m) > 1e3

    def test_pbias_uses_abs(self):
        assert to_objective("pbias", -12.0) == 12.0
        assert to_objective("rmse", -12.0) == -12.0
        np.testing.assert_allclose(to_objective("pbias", np.array([-2.0, 1.0])), [2.0, 1.0])

    def test_unknown_metric_lists_known(self):
        with pytest.raises(ValueError) as e:
            is_maximize("foo")
        for m in known_metrics():
            assert m in str(e.value)

    def test_sanitize_maps_nan_and_inf_to_worst(self):
        out = sanitize_scores([0.5, NAN, -np.inf], "nse")
        assert out[0] == 0.5 and out[1] == out[2] == worst_score("nse")

    @pytest.mark.parametrize("metric,scores,best", [
        ("nse",   [0.1, 0.8, NAN, 0.5], 1),
        ("rmse",  [5, 2, NAN, 9],       1),
        ("pbias", [-20, 3, -1, 15],     2),
        ("pbias", [NAN, 40, -30, 25],   3),
    ])
    def test_best_index(self, metric, scores, best):
        assert best_index(scores, metric) == best

    def test_best_index_all_nan(self):
        with pytest.raises(RuntimeError, match="all runs failed"):
            best_index([NAN, NAN], "nse")


# ── GLUE ─────────────────────────────────────────────────────────────────────

class TestGlueDirection:
    @pytest.mark.parametrize("metric,scores,best,n_beh,thr", [
        ("nse",   [0.2, 0.9, 0.6, 0.4],  0.9, 2, 0.5),
        ("rmse",  [5, 2, NAN, 9],        2,   1, 3.0),
        ("pbias", [-20, 3, -1, 15],     -1,   2, 5.0),
    ])
    def test_best_and_behavioural(self, calib, obs, metric, scores, best, n_beh, thr):
        calib.manager.run_batch = fixed_batch(scores, metric)
        r = calib.glue.run(RANGES, obs, n_samples=4, threshold=thr, metric=metric, seed=1)
        assert r["best_score"] == best
        assert len(r["behavioral_results"]) == n_beh

    def test_best_params_belong_to_best_row(self, calib, obs):
        calib.manager.run_batch = fixed_batch([5, 2, NAN, 9], "rmse")
        r = calib.glue.run(RANGES, obs, n_samples=4, metric="rmse", seed=1)
        row = r["all_results"].iloc[1]
        assert r["best_params"]["CN2.mgt"][0][0] == pytest.approx(row["CN2.mgt"])

    def test_all_nan_raises(self, calib, obs):
        calib.manager.run_batch = fixed_batch([NAN] * 4, "nse")
        with pytest.raises(RuntimeError, match="all runs failed"):
            calib.glue.run(RANGES, obs, n_samples=4, seed=1)

    def test_unknown_metric(self, calib, obs):
        with pytest.raises(ValueError):
            calib.glue.run(RANGES, obs, n_samples=4, metric="foo")


# ── ParallelDE / PSO ─────────────────────────────────────────────────────────

class TestPopulationAlgorithms:
    @pytest.mark.parametrize("metric,scores,best", [
        ("nse",   [0.2, 0.9, NAN, 0.4], 0.9),
        ("rmse",  [5, 2, NAN, 9],       2),
        ("pbias", [-20, 3, -1, 15],     -1),
    ])
    def test_de_best(self, calib, obs, metric, scores, best):
        calib.manager.run_batch = fixed_batch(scores, metric)
        r = calib.de.run(RANGES, obs, metric=metric, pop_size=4, max_generations=2, seed=0)
        assert r["best_score"] == best
        assert r["history"]["best_score"].iloc[0] == best
        assert not r["history"]["mean_score"].isna().any()

    @pytest.mark.parametrize("metric,scores,best", [
        ("nse",   [0.2, 0.9, NAN, 0.4], 0.9),
        ("rmse",  [5, 2, NAN, 9],       2),
        ("pbias", [-20, 3, -1, 15],     -1),
    ])
    def test_pso_best(self, calib, obs, metric, scores, best):
        calib.manager.run_batch = fixed_batch(scores, metric)
        r = calib.pso.run(RANGES, obs, metric=metric, n_particles=4, max_iterations=2, seed=0)
        assert r["best_score"] == best
        assert not r["history"]["mean_score"].isna().any()

    def test_de_all_nan_raises(self, calib, obs):
        calib.manager.run_batch = fixed_batch([NAN] * 4, "nse")
        with pytest.raises(RuntimeError, match="all runs failed"):
            calib.de.run(RANGES, obs, pop_size=4, max_generations=2)

    def test_pso_all_nan_raises(self, calib, obs):
        calib.manager.run_batch = fixed_batch([NAN] * 4, "rmse")
        with pytest.raises(RuntimeError, match="all runs failed"):
            calib.pso.run(RANGES, obs, metric="rmse", n_particles=4, max_iterations=2)

    @pytest.mark.parametrize("algo", ["de", "pso"])
    def test_pbias_converges_to_zero(self, calib, obs, algo):
        """pbias = x - 60 (signed): the optimum is |pbias| -> 0, not the minimum."""
        def batch(sets, *a, **kw):
            return pd.DataFrame({"pbias": [s["CN2.mgt"][0][0] - 60.0 for s in sets]})
        calib.manager.run_batch = batch
        if algo == "de":
            r = calib.de.run(RANGES, obs, metric="pbias", pop_size=10, max_generations=30, seed=0)
        else:
            r = calib.pso.run(RANGES, obs, metric="pbias", n_particles=10, max_iterations=30, seed=0)
        assert abs(r["best_score"]) < 1.0
        ev = r["all_evaluations"]
        assert abs(r["best_score"]) == pytest.approx(ev["score"].abs().min())

    def test_nan_runs_never_win(self, calib, obs):
        """Failed members (NaN) must not be chosen for rmse (min) or nse (max)."""
        for metric, scores in (("rmse", [NAN, 3.0, NAN, 7.0]), ("nse", [NAN, -3.0, NAN, -7.0])):
            calib.manager.run_batch = fixed_batch(scores, metric)
            r = calib.de.run(RANGES, obs, metric=metric, pop_size=4, max_generations=2, seed=0)
            assert r["best_score"] == scores[1]


# ── DDS ──────────────────────────────────────────────────────────────────────

class TestDDSCalibration:
    @pytest.mark.parametrize("metric,scores,best", [
        ("nse",   [0.2, 0.9, NAN, 0.4], 0.9),
        ("rmse",  [5, 2, NAN, 9],       2),
        ("pbias", [-20, 3, -1, 15],     -1),
    ])
    def test_best(self, calib, obs, metric, scores, best):
        calib.manager.run_iteration = MagicMock(side_effect=scores)
        r = calib.dds.run(RANGES, obs, n_iterations=4, seed=0, metric=metric,
                          on_failure="penalize")
        assert r["best_score"] == best
        assert r["history"]["best_score"].iloc[-1] == best

    def test_explicit_maximize_overrides_metric(self, calib, obs):
        calib.manager.run_iteration = MagicMock(side_effect=[5, 2, 9, 7])
        r = calib.dds.run(RANGES, obs, n_iterations=4, seed=0, metric="rmse", maximize=True)
        assert r["best_score"] == 9

    def test_all_nan_penalize_raises(self, calib, obs):
        calib.manager.run_iteration = MagicMock(return_value=NAN)
        with pytest.raises(RuntimeError, match="all runs failed"):
            calib.dds.run(RANGES, obs, n_iterations=4, seed=0, on_failure="penalize")

    def test_default_propagates_exception(self, calib, obs):
        calib.manager.run_iteration = MagicMock(
            side_effect=[0.4, RuntimeError("boom"), 0.2, 0.1])
        with pytest.raises(RuntimeError, match="boom"):
            calib.dds.run(RANGES, obs, n_iterations=4, seed=0)

    def test_default_nan_score_raises(self, calib, obs):
        calib.manager.run_iteration = MagicMock(return_value=NAN)
        with pytest.raises(RuntimeError, match="no valid score"):
            calib.dds.run(RANGES, obs, n_iterations=4, seed=0)

    def test_penalize_continues_and_marks_failed(self, calib, obs):
        calib.manager.run_iteration = MagicMock(
            side_effect=[RuntimeError("boom"), 0.4, RuntimeError("boom"), 0.2])
        r = calib.dds.run(RANGES, obs, n_iterations=4, seed=0, on_failure="penalize")
        assert r["best_score"] == 0.4
        assert r["history"]["score"].isna().sum() == 2

    def test_invalid_on_failure(self, calib, obs):
        with pytest.raises(ValueError):
            calib.dds.run(RANGES, obs, n_iterations=4, on_failure="ignore")


# ── SWATCalibration.optimize / analyze ───────────────────────────────────────

class TestOptimizeAnalyze:
    @pytest.mark.parametrize("metric,fn", [
        ("nse",   lambda x: 1.0 - abs(x - 60.0) / 100.0),
        ("rmse",  lambda x: abs(x - 60.0)),
        ("pbias", lambda x: x - 60.0),
    ])
    def test_optimize_direction(self, calib, obs, metric, fn):
        calib.manager.run_iteration = MagicMock(
            side_effect=lambda raw, *a, **kw: fn(raw["CN2.mgt"]))
        r = calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, metric=metric, max_iter=15)
        assert r["best_params"]["CN2.mgt"] == pytest.approx(60.0, abs=1.0)
        h = r["history"]
        if metric == "pbias":
            assert abs(r["best_score"]) == pytest.approx(h["score"].abs().min())
            assert abs(r["best_score"]) < 1.0
        elif metric == "rmse":
            assert r["best_score"] == pytest.approx(h["score"].min())
        else:
            assert r["best_score"] == pytest.approx(h["score"].max())

    def test_optimize_penalize_all_failed_raises(self, calib, obs):
        calib.manager.run_iteration = MagicMock(side_effect=RuntimeError("Iteration failed"))
        with pytest.raises(RuntimeError, match="all runs failed"):
            calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, max_iter=2, on_failure="penalize")

    def test_optimize_default_propagates_exception(self, calib, obs):
        calib.manager.run_iteration = MagicMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, max_iter=2)

    def test_optimize_default_nan_score_raises(self, calib, obs):
        calib.manager.run_iteration = MagicMock(return_value=NAN)
        with pytest.raises(RuntimeError, match="no valid score"):
            calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, max_iter=2)

    def test_optimize_penalize_continues(self, calib, obs):
        calls = []

        def fn(raw, *a, **kw):
            calls.append(1)
            if len(calls) % 3 == 0:
                raise RuntimeError("boom")
            return abs(raw["CN2.mgt"] - 60.0)
        calib.manager.run_iteration = MagicMock(side_effect=fn)
        r = calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, metric="rmse",
                           max_iter=5, on_failure="penalize")
        assert r["history"]["score"].isna().any()
        assert r["best_score"] == pytest.approx(r["history"]["score"].min())

    def test_optimize_invalid_on_failure(self, calib, obs):
        with pytest.raises(ValueError):
            calib.optimize({"CN2.mgt": (35.0, 98.0)}, obs, on_failure="skip")

    def test_analyze_best_for_pbias(self, obs):
        project = MagicMock()
        project.WorkingFolder.n_parallel = 4
        project.get_date_range.return_value = obs.index
        project.Output.read_rch.return_value = {"FLOW_OUTcms": pd.Series(np.ones(60) * 5.0)}
        c = SWATCalibration(project)
        c.manager.run_batch = fixed_batch([-20, 3, -1, 15], "pbias")
        c.manager.run_iteration = MagicMock(return_value=-1)
        r = c.analyze(RANGES, obs, n_samples=4, threshold=50, metric="pbias", seed=0)
        assert r["best_score"] == -1


# ── evaluate_performance ─────────────────────────────────────────────────────

class TestEvaluatePerformance:
    def test_rsr_is_rated(self):
        a = SWATAnalysis(None)
        o = np.random.default_rng(0).uniform(1, 10, 200)
        assert a.evaluate_performance(o, o)["rsr"] == "Very Good"
        good = a.evaluate_performance(o, o + 0.55 * np.std(o))["rsr"]
        assert good == "Good"
        assert a.evaluate_performance(o, o + 2.0 * np.std(o))["rsr"] == "Unsatisfactory"

    def test_nan_is_not_available(self):
        a = SWATAnalysis(None)
        r = a.evaluate_performance(np.array([]), np.array([]))
        assert r == {"nse": "N/A", "pbias": "N/A", "rsr": "N/A"}

    def test_constant_observed_gives_na_rsr(self):
        a = SWATAnalysis(None)
        o = np.full(20, 3.0)
        assert a.evaluate_performance(o, o + 1.0)["rsr"] == "N/A"

    def test_calculate_statistics_contract(self):
        o = np.array([1.0, 2.0, 3.0, 4.0])
        res = SWATAnalysis(None).calculate_statistics(o, o, ["nse", "rmse"])
        assert res == {"nse": 1.0, "rmse": 0.0}


# ── uncertainty_band ─────────────────────────────────────────────────────────

class TestUncertaintyBand:
    def _setup(self, obs):
        calib = make_calib()
        calib.manager.project.get_date_range.return_value = obs.index
        calib.manager.project.Output.read_rch.side_effect = (
            lambda **kw: {"FLOW_OUTcms": pd.Series(np.linspace(1, 9, len(obs)))})
        order = []
        calib.manager._backup_state = MagicMock(side_effect=lambda: order.append("backup"))
        calib.manager._restore_state = MagicMock(side_effect=lambda: order.append("restore"))
        calib.manager.project.run = MagicMock(side_effect=lambda *a, **k: order.append("run"))
        calib.manager._format_params = MagicMock(return_value={"X": [(1.0, "r")]})
        calib.manager._txinout_dir = lambda: None   # mock project: no real TxtInOut
        calib.manager.record_run = MagicMock()
        return calib, order

    def test_methods_subbasins_forwarded_and_state_restored(self, obs):
        calib, order = self._setup(obs)
        df = pd.DataFrame({"CN2.mgt": [50.0, 60.0, 70.0], "nse": [0.6, 0.7, 0.8]})
        methods, subs = {"CN2.mgt": "r"}, {"CN2.mgt": [1, 2]}
        res = calib.glue.uncertainty_band(df, obs, param_methods=methods, param_subbasins=subs)
        calls = calib.manager._format_params.call_args_list
        assert len(calls) == 3
        for c in calls:
            assert c.args[1] == methods and c.args[2] == subs
        assert order == ["backup", "run", "restore"] * 3
        assert 0.0 <= res["p_factor"] <= 1.0

    def test_record_run_once_per_run_with_sim(self, obs):
        calib, _ = self._setup(obs)
        df = pd.DataFrame({"CN2.mgt": [50.0, 60.0, 70.0], "nse": [0.6, 0.7, 0.8]})
        calib.glue.uncertainty_band(df, obs, reach_id=2, output_variable="FLOW_OUTcms")
        calls = calib.manager.record_run.call_args_list
        assert len(calls) == 3
        for c in calls:
            assert c.kwargs["mode"] == "uncertainty_band" and c.kwargs["status"] == "ok"
            assert c.kwargs["reach_id"] == 2
            assert isinstance(c.kwargs["sim"], pd.Series)
            assert c.args[1] is None

    def test_record_run_failed_when_run_raises(self, obs):
        calib, _ = self._setup(obs)
        calib.manager.project.run = MagicMock(side_effect=RuntimeError("swat died"))
        df = pd.DataFrame({"CN2.mgt": [50.0], "nse": [0.6]})
        with pytest.raises(RuntimeError):
            calib.glue.uncertainty_band(df, obs)
        (c,) = calib.manager.record_run.call_args_list
        assert c.kwargs["status"] == "failed" and "swat died" in c.kwargs["error"]

    def test_uses_manager_align_series(self, obs):
        calib, _ = self._setup(obs)
        real = calib.manager._align_series
        calib.manager._align_series = MagicMock(side_effect=real)
        df = pd.DataFrame({"CN2.mgt": [50.0, 60.0], "nse": [0.6, 0.7]})
        calib.glue.uncertainty_band(df, obs)
        assert calib.manager._align_series.call_count == 2

    def test_restore_even_if_run_fails(self, obs):
        calib, order = self._setup(obs)
        calib.manager.project.run = MagicMock(side_effect=RuntimeError("swat died"))
        df = pd.DataFrame({"CN2.mgt": [50.0], "nse": [0.6]})
        with pytest.raises(RuntimeError):
            calib.glue.uncertainty_band(df, obs)
        assert order == ["backup", "restore"]

    def test_run_passes_methods_to_band(self, obs):
        calib, _ = self._setup(obs)
        calib.manager.run_batch = fixed_batch([0.6, 0.7, 0.8, 0.9], "nse")
        calib.glue.uncertainty_band = MagicMock(return_value={"p_factor": 1.0})
        calib.glue.run(RANGES, obs, n_samples=4, seed=0, compute_uncertainty=True,
                       param_methods={"CN2.mgt": "r"}, param_subbasins={"CN2.mgt": [3]})
        kw = calib.glue.uncertainty_band.call_args.kwargs
        assert kw["param_methods"]["CN2.mgt"] == "r"
        assert kw["param_subbasins"]["CN2.mgt"] == [3]


# ── uncertainty_band freshness check ─────────────────────────────────────────

class TestUncertaintyBandFreshness:
    def test_stale_run_excluded_with_warning(self, obs, tmp_path, caplog):
        import logging
        (tmp_path / "output.rch").write_text("old")
        calib = make_calib()
        calib.manager.project.get_date_range.return_value = obs.index
        calib.manager.project.Output.read_rch.side_effect = (
            lambda **kw: {"FLOW_OUTcms": pd.Series(np.linspace(1, 9, len(obs)))})
        calib.manager._backup_state = MagicMock()
        calib.manager._restore_state = MagicMock()
        calib.manager._format_params = MagicMock(return_value={"X": [(1.0, "v")]})
        calib.manager._txinout_dir = lambda: tmp_path
        calib.manager.record_run = MagicMock()
        n = [0]

        def run():
            n[0] += 1
            if n[0] != 2:                       # run 2 never writes output.rch
                (tmp_path / "output.rch").write_text("new %d" % n[0])
        calib.manager.project.run = MagicMock(side_effect=run)
        df = pd.DataFrame({"CN2.mgt": [50.0, 60.0, 70.0], "nse": [0.6, 0.7, 0.8]})
        with caplog.at_level(logging.WARNING):
            res = calib.glue.uncertainty_band(df, obs)
        assert "excluded" in caplog.text
        assert res["uncertainty_band"] is not None
        assert calib.manager._restore_state.call_count == 3
        modes = [(c.kwargs["mode"], c.kwargs["status"])
                 for c in calib.manager.record_run.call_args_list]
        assert modes == [("uncertainty_band", "ok"), ("uncertainty_band", "failed"),
                         ("uncertainty_band", "ok")]
