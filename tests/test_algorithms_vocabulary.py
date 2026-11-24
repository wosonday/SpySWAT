"""
API-3b: the calibration algorithms adopt the multi-site vocabulary.

Every test mocks ``manager.run_batch`` (or ``run_iteration`` for DDS) — no SWAT.
They exercise the *new* names (``observed``, ``outputs``, ``weights``, ...) and the
deprecated mapping (``observed_series`` / ``reach_id``+``output_variable``),
without running a single model.
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from spyswat.swat_calib.analysis.calibration import SWATCalibration
from spyswat.swat_calib.analysis.algorithms.dds import DDSCalibration
from spyswat.swat_calib.analysis.algorithms.glue import GLUE
from spyswat.swat_calib.analysis.algorithms.parallel_de import ParallelDE
from spyswat.swat_calib.analysis.algorithms.pso import PSOCalibration


DATES = pd.date_range("2000-01-01", periods=30, freq="D")

PARAM_RANGES = {
    "CN2.mgt":     (35.0, 98.0),
    "ALPHA_BF.gw": (0.0, 1.0),
}
PARAM_NAMES = list(PARAM_RANGES)


def two_site_obs():
    """A 2-site observed dict: two variables, two reaches."""
    return {
        ("FLOW_OUTcms", 1): pd.Series(np.linspace(1.0, 2.0, 30), index=DATES),
        ("SED_OUTtons", 51): pd.Series(np.linspace(2.0, 3.0, 30), index=DATES),
    }


WEIGHTS = {("FLOW_OUTcms", 1): 0.5, ("SED_OUTtons", 51): 0.5}


def make_calib():
    project = MagicMock()
    project.WorkingFolder.n_parallel = 4
    project.FileCIO.get_iprint.return_value = "D"
    return SWATCalibration(project)


def cn2_score(ps):
    """Score = the CN2 value of a formatted parameter set (raw rmse, lower is better)."""
    return float(ps["CN2.mgt"][0][0])


def raw_cn2(params, *a, **kw):
    """Score = the CN2 value of a *raw* parameter dict (DDS passes raw floats)."""
    return float(params["CN2.mgt"])


def capturing_batch(score_fn, captures, metric="rmse"):
    """Mock ``run_batch`` returning a ``score`` column + per-site columns (no bare metric)."""
    def run_batch(param_sets, observed, metrics, *a, **kw):
        m = kw.get("metric", metric)
        captures.append(dict(observed=observed, metrics=metrics, **kw))
        scores = [score_fn(ps) for ps in param_sets]
        df = pd.DataFrame({"score": scores})
        if isinstance(observed, dict):
            for (var, reach) in sorted(observed):
                df[f"{m}@{var}@{reach}"] = [s + 1.0 for s in scores]
        return df
    return run_batch


def proposed_sets(result):
    """The parameter columns of ``runs`` — the proposed parameter sets, in order."""
    return result["runs"][PARAM_NAMES].reset_index(drop=True)


# ── selects the best by ``score`` with a minimise metric (rmse) ──────────────

def test_glue_two_site_weights_selects_best_by_score():
    captures = []
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, captures, metric="rmse")
    result = calib.glue.run(PARAM_RANGES, two_site_obs(), weights=WEIGHTS,
                            metric="rmse", n_samples=12, seed=42)
    # the aggregate score (min = best) drives the selection, not a bare metric column
    assert result["best_score"] == pytest.approx(result["runs"]["score"].min())
    assert result["best_score"] == pytest.approx(result["all_results"]["rmse"].min())
    # the chosen parameters are the ones with the smallest CN2
    assert result["best_params"]["CN2.mgt"][0][0] == pytest.approx(
        result["all_results"]["CN2.mgt"].min()
    )
    # the new vocabulary reached run_batch
    assert set(captures[0]["observed"]) == {("FLOW_OUTcms", 1), ("SED_OUTtons", 51)}
    assert captures[0]["weights"] == WEIGHTS
    assert "score" in result["runs"].columns
    assert {"rmse@FLOW_OUTcms@1", "rmse@SED_OUTtons@51"} <= set(result["runs"].columns)
    assert isinstance(result["seed"], int)


@pytest.mark.parametrize("algo,kwargs", [
    ("de", dict(pop_size=6, max_generations=2)),
    ("pso", dict(n_particles=6, max_iterations=2)),
])
def test_population_algorithm_selects_best_by_score(algo, kwargs):
    captures = []
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, captures, metric="rmse")
    result = getattr(calib, algo).run(PARAM_RANGES, two_site_obs(), weights=WEIGHTS,
                                      metric="rmse", seed=7, **kwargs)
    assert result["best_score"] == pytest.approx(result["all_evaluations"]["score"].min())
    assert result["best_score"] == pytest.approx(result["runs"]["score"].min())
    assert captures[0]["weights"] == WEIGHTS
    assert captures[0]["metric"] == "rmse"
    assert "score" in result["runs"].columns


def test_dds_two_site_weights_selects_best_by_score():
    calls = []
    scores = [50.0, 40.0, 95.0, 38.0, 70.0]

    def run_iteration(params, observed, *a, **kw):
        calls.append(kw)
        return scores[len(calls) - 1]

    calib = make_calib()
    calib.manager.run_iteration = run_iteration
    result = calib.dds.run(PARAM_RANGES, two_site_obs(), weights=WEIGHTS,
                           metric="rmse", n_iterations=5, seed=0)
    assert result["best_score"] == pytest.approx(min(scores))
    assert result["runs"]["score"].min() == pytest.approx(min(scores))
    assert all(c["weights"] == WEIGHTS for c in calls)
    assert all(c["metric"] == "rmse" for c in calls)


# ── seed reproducibility (same seed → identical proposed sets) ────────────────

@pytest.mark.parametrize("algo,kwargs", [
    ("glue", dict(n_samples=12)),
    ("de", dict(pop_size=6, max_generations=2, tol=0.0, patience=100)),
    ("pso", dict(n_particles=6, max_iterations=2, tol=0.0, patience=100)),
    ("dds", dict(n_iterations=6)),
])
def test_same_seed_same_proposed_sets(algo, kwargs):
    def one():
        calib = make_calib()
        if algo == "dds":
            calib.manager.run_iteration = MagicMock(side_effect=raw_cn2)
            return getattr(calib, algo).run(PARAM_RANGES, two_site_obs(),
                                            metric="rmse", seed=123, **kwargs)
        calib.manager.run_batch = capturing_batch(cn2_score, [], metric="rmse")
        return getattr(calib, algo).run(PARAM_RANGES, two_site_obs(),
                                        metric="rmse", seed=123, **kwargs)

    r1, r2 = one(), one()
    pd.testing.assert_frame_equal(proposed_sets(r1), proposed_sets(r2))


@pytest.mark.parametrize("algo,kwargs", [
    ("glue", dict(n_samples=12)),
    ("de", dict(pop_size=6, max_generations=2, tol=0.0, patience=100)),
    ("pso", dict(n_particles=6, max_iterations=2, tol=0.0, patience=100)),
    ("dds", dict(n_iterations=6)),
])
def test_seed_none_resolves_and_replays(algo, kwargs):
    def one(seed):
        calib = make_calib()
        if algo == "dds":
            calib.manager.run_iteration = MagicMock(side_effect=raw_cn2)
            return getattr(calib, algo).run(PARAM_RANGES, two_site_obs(),
                                            metric="rmse", seed=seed, **kwargs)
        calib.manager.run_batch = capturing_batch(cn2_score, [], metric="rmse")
        return getattr(calib, algo).run(PARAM_RANGES, two_site_obs(),
                                        metric="rmse", seed=seed, **kwargs)

    r_none = one(None)
    assert isinstance(r_none["seed"], int) and not isinstance(r_none["seed"], bool)
    r_replay = one(r_none["seed"])
    pd.testing.assert_frame_equal(proposed_sets(r_none), proposed_sets(r_replay))


# ── is_initial flags ──────────────────────────────────────────────────────────

def test_glue_all_samples_are_initial():
    captures = []
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, captures, metric="rmse")
    calib.glue.run(PARAM_RANGES, two_site_obs(), n_samples=10, metric="rmse", seed=0)
    assert len(captures) == 1
    assert captures[0]["is_initial"] is True


def test_de_initial_population_only_is_initial():
    captures = []
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, captures, metric="rmse")
    calib.de.run(PARAM_RANGES, two_site_obs(), pop_size=6, max_generations=2,
                 metric="rmse", seed=0, tol=0.0, patience=100)
    assert captures[0]["is_initial"] is True
    assert all(c["is_initial"] is False for c in captures[1:])


def test_pso_initial_swarm_only_is_initial():
    captures = []
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, captures, metric="rmse")
    calib.pso.run(PARAM_RANGES, two_site_obs(), n_particles=6, max_iterations=2,
                  metric="rmse", seed=0, tol=0.0, patience=100)
    assert captures[0]["is_initial"] is True
    assert all(c["is_initial"] is False for c in captures[1:])


def test_dds_first_evaluation_is_initial():
    calls = []
    calib = make_calib()

    def run_iteration(params, observed, *a, **kw):
        calls.append(kw)
        return float(40.0)

    calib.manager.run_iteration = run_iteration
    calib.dds.run(PARAM_RANGES, two_site_obs(), n_iterations=5, metric="rmse", seed=0)
    assert calls[0]["is_initial"] is True
    assert all(c["is_initial"] is False for c in calls[1:])


# ── deprecated kwargs map to the new vocabulary ──────────────────────────────

def test_glue_observed_series_deprecated_matches_observed():
    single = pd.Series(np.linspace(1.0, 2.0, 30), index=DATES)
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")

    with pytest.warns(DeprecationWarning, match="observed_series"):
        old = calib.glue.run(PARAM_RANGES, observed_series=single, n_samples=8,
                             metric="nse", seed=42)
    new = calib.glue.run(PARAM_RANGES, observed=single, n_samples=8, metric="nse", seed=42)
    assert old["best_score"] == pytest.approx(new["best_score"])
    pd.testing.assert_frame_equal(proposed_sets(old), proposed_sets(new))


def test_glue_reach_output_variable_deprecated_matches_outputs():
    single = pd.Series(np.linspace(1.0, 2.0, 30), index=DATES)
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")

    with pytest.warns(DeprecationWarning, match="reach_id"):
        old = calib.glue.run(PARAM_RANGES, single, n_samples=8, metric="nse", seed=42,
                             reach_id=2, output_variable="FLOW_OUTcms")
    new = calib.glue.run(PARAM_RANGES, single, n_samples=8, metric="nse", seed=42,
                         outputs={"FLOW_OUTcms": [2]})
    assert old["best_score"] == pytest.approx(new["best_score"])
    pd.testing.assert_frame_equal(proposed_sets(old), proposed_sets(new))


@pytest.mark.parametrize("algo,kwargs", [
    ("de", dict(pop_size=6, max_generations=2, tol=0.0, patience=100)),
    ("pso", dict(n_particles=6, max_iterations=2, tol=0.0, patience=100)),
    ("dds", dict(n_iterations=6)),
])
def test_population_old_kwargs_warn_and_match(algo, kwargs):
    single = pd.Series(np.linspace(1.0, 2.0, 30), index=DATES)
    calib = make_calib()

    def one(**overrides):
        c = make_calib()
        if algo == "dds":
            c.manager.run_iteration = MagicMock(side_effect=raw_cn2)
        else:
            c.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")
        base = dict(metric="nse", seed=42)
        base.update(kwargs)
        base.update(overrides)
        return getattr(c, algo).run(PARAM_RANGES, **base)

    with pytest.warns(DeprecationWarning, match="observed_series"):
        old = one(observed_series=single)
    new = one(observed=single)
    assert old["best_score"] == pytest.approx(new["best_score"])
    pd.testing.assert_frame_equal(proposed_sets(old), proposed_sets(new))


# ── passing both old and new names → TypeError ───────────────────────────────

@pytest.mark.parametrize("algo", ["glue", "de", "pso", "dds"])
def test_old_and_new_observed_raise_typeerror(algo):
    single = pd.Series(np.linspace(1.0, 2.0, 30), index=DATES)
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")
    calib.manager.run_iteration = MagicMock(return_value=40.0)
    kwargs = dict(observed=single, observed_series=single)
    if algo == "glue":
        kwargs["n_samples"] = 8
    with pytest.raises(TypeError, match="both"):
        getattr(calib, algo).run(PARAM_RANGES, **kwargs)


@pytest.mark.parametrize("algo", ["glue", "de", "pso", "dds"])
def test_old_and_new_outputs_raise_typeerror(algo):
    single = pd.Series(np.linspace(1.0, 2.0, 30), index=DATES)
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")
    calib.manager.run_iteration = MagicMock(return_value=40.0)
    kwargs = dict(observed=single, reach_id=1, output_variable="FLOW_OUTcms",
                  outputs={"FLOW_OUTcms": [1]})
    if algo == "glue":
        kwargs["n_samples"] = 8
    with pytest.raises(TypeError, match="both"):
        getattr(calib, algo).run(PARAM_RANGES, **kwargs)


# ── SWATCalibration.optimize / analyze adopt the vocabulary too ──────────────

def test_optimize_passes_new_vocabulary_through():
    calib = make_calib()
    seen = {}
    calib.manager.run_iteration = MagicMock(side_effect=lambda raw, *a, **kw: 40.0)
    calib.optimize({"CN2.mgt": (35.0, 98.0)}, two_site_obs(), weights=WEIGHTS,
                   metric="rmse", max_iter=2, method="minimize")
    assert calib.manager.run_iteration.call_count >= 1


def test_optimize_old_observed_series_warns():
    calib = make_calib()
    single = pd.Series(np.linspace(1.0, 2.0, 6), index=DATES[:6])
    calib.manager.run_iteration = MagicMock(return_value=40.0)
    with pytest.warns(DeprecationWarning, match="observed_series"):
        calib.optimize({"CN2.mgt": (35.0, 98.0)}, observed_series=single,
                       metric="rmse", max_iter=2, method="minimize")


def test_analyze_passes_new_vocabulary_through():
    calib = make_calib()
    calib.manager.run_batch = capturing_batch(cn2_score, [], metric="nse")
    calib.manager.run_iteration = MagicMock(return_value=0.9)
    calib.project.Output.read_rch.return_value = {"FLOW_OUTcms": pd.Series(np.ones(6) * 5.0)}
    calib.project.get_date_range.return_value = DATES[:6]
    result = calib.analyze(PARAM_RANGES, two_site_obs(), weights=WEIGHTS,
                           n_samples=6, threshold=0.5, metric="nse", seed=0)
    assert "best_score" in result


# ── algorithms are directly constructible with the new vocabulary ────────────

def test_standalone_constructors_accept_new_names():
    calib = make_calib()
    manager = calib.manager
    single = pd.Series(np.linspace(1.0, 2.0, 6), index=DATES[:6])

    manager.run_batch = capturing_batch(cn2_score, [], metric="nse")
    GLUE(manager).run(PARAM_RANGES, observed=single, n_samples=6, metric="nse", seed=0)
    ParallelDE(manager).run(PARAM_RANGES, observed=single, metric="nse",
                            pop_size=6, max_generations=1, seed=0)
    PSOCalibration(manager).run(PARAM_RANGES, observed=single, metric="nse",
                                n_particles=6, max_iterations=1, seed=0)

    manager.run_iteration = MagicMock(return_value=0.5)
    DDSCalibration(manager).run(PARAM_RANGES, observed=single, metric="nse",
                                n_iterations=3, seed=0)
