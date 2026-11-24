"""
Tests for the pure multi-site scoring helpers (``scoring.py``): no SWAT run,
no files — hand-computed metrics on synthetic series.
"""
import numpy as np
import pandas as pd
import pytest

from spyswat.swat_calib.calibration.scoring import (
    normalise_observed, check_weights, preflight, score_sites,
)


def daily(start, values):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range(start, periods=len(values), freq="D"))


# ── normalise_observed ──────────────────────────────────────────────────────

def test_normalise_bare_series_uses_single_output_site():
    s = daily("2000-01-01", [1, 2, 3])
    obs, outputs = normalise_observed(s)
    assert list(obs) == [("FLOW_OUTcms", 1)]
    assert obs[("FLOW_OUTcms", 1)] is s
    assert outputs == {"FLOW_OUTcms": [1]}


def test_normalise_bare_series_rejects_multiple_sites():
    with pytest.raises(ValueError, match="exactly one"):
        normalise_observed(daily("2000-01-01", [1, 2]), {"FLOW_OUTcms": [1, 2]})


def test_normalise_dict_adds_missing_output_keys():
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2]),
        ("SED_OUTtons", 51): daily("2000-01-01", [1, 2]),
    }
    out_obs, outputs = normalise_observed(obs, {"FLOW_OUTcms": [1, 2]})
    assert out_obs == obs
    assert outputs == {"FLOW_OUTcms": [1, 2], "SED_OUTtons": [51]}


def test_normalise_rejects_bad_observed_key():
    with pytest.raises(ValueError, match="tuple"):
        normalise_observed({"FLOW_OUTcms": daily("2000-01-01", [1, 2])})


def test_normalise_rejects_non_series_non_dict():
    with pytest.raises(ValueError, match="Series"):
        normalise_observed([1, 2, 3])


def test_normalise_scalar_reach_is_wrapped():
    _, outputs = normalise_observed(daily("2000-01-01", [1, 2]), {"FLOW_OUTcms": 1})
    assert outputs == {"FLOW_OUTcms": [1]}


# ── check_weights ───────────────────────────────────────────────────────────

def test_weights_none_gives_equal_weights():
    sites = [("FLOW_OUTcms", 1), ("SED_OUTtons", 51)]
    w = check_weights(None, sites)
    assert w == {("FLOW_OUTcms", 1): 0.5, ("SED_OUTtons", 51): 0.5}


def test_weights_are_normalised_to_sum_one():
    w = check_weights({("FLOW_OUTcms", 1): 1.0, ("SED_OUTtons", 51): 3.0},
                      [("FLOW_OUTcms", 1), ("SED_OUTtons", 51)])
    assert w == {("FLOW_OUTcms", 1): 0.25, ("SED_OUTtons", 51): 0.75}


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_weights_reject_non_positive(bad):
    with pytest.raises(ValueError, match="positive"):
        check_weights({("FLOW_OUTcms", 1): bad}, [("FLOW_OUTcms", 1)])


def test_weights_reject_unknown_site():
    with pytest.raises(ValueError, match="unknown site"):
        check_weights({("FLOW_OUTcms", 99): 1.0}, [("FLOW_OUTcms", 1)])


def test_weights_reject_non_mapping():
    with pytest.raises(ValueError, match="mapping"):
        check_weights([1.0], [("FLOW_OUTcms", 1)])


# ── preflight ───────────────────────────────────────────────────────────────

def test_preflight_passes_for_valid_observations():
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4])}
    assert preflight(obs, ("2000-01-01", "2000-01-04")) is None


def test_preflight_rejects_no_overlap():
    obs = {("FLOW_OUTcms", 1): daily("2000-06-01", [1, 2, 3])}
    with pytest.raises(ValueError, match="no data within"):
        preflight(obs, ("2000-01-01", "2000-01-04"))


def test_preflight_rejects_zero_variance():
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [5, 5, 5, 5])}
    with pytest.raises(ValueError, match="zero variance"):
        preflight(obs, ("2000-01-01", "2000-01-04"))


def test_preflight_none_period_checks_variance_only():
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3])}
    assert preflight(obs, None) is None
    with pytest.raises(ValueError, match="zero variance"):
        preflight({("FLOW_OUTcms", 1): daily("2000-01-01", [9, 9, 9])}, None)


# ── score_sites ─────────────────────────────────────────────────────────────

def test_two_sites_two_variables_equal_weights_nse():
    sim = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 25]),
    }
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4]),   # NSE = 0.8
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 30]),  # NSE = 0.875
    }
    score, site = score_sites(sim, obs, metric="nse", metrics=("nse",),
                              weights=None, calib_period=("2000-01-01", "2000-01-04"))
    assert score == pytest.approx(0.5 * 0.8 + 0.5 * 0.875)
    assert site[("FLOW_OUTcms", 1)]["nse_calib"] == pytest.approx(0.8)
    assert site[("SED_OUTtons", 51)]["nse_calib"] == pytest.approx(0.875)


def test_weights_shift_the_score():
    sim = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 25]),
    }
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 30]),
    }
    weights = {("FLOW_OUTcms", 1): 0.25, ("SED_OUTtons", 51): 0.75}
    score, _ = score_sites(sim, obs, metric="nse", metrics=("nse",),
                           weights=weights, calib_period=("2000-01-01", "2000-01-04"))
    assert score == pytest.approx(0.25 * 0.8 + 0.75 * 0.875)


def test_pbias_score_uses_abs_but_site_metrics_stay_signed():
    sim = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 25]),
    }
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4]),   # pbias = -10
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 30]),  # pbias = +8.3333
    }
    score, site = score_sites(sim, obs, metric="pbias", metrics=("pbias",),
                              weights=None, calib_period=("2000-01-01", "2000-01-04"))
    assert site[("FLOW_OUTcms", 1)]["pbias_calib"] == pytest.approx(-10.0)
    assert site[("SED_OUTtons", 51)]["pbias_calib"] == pytest.approx(100 * 5 / 60)
    assert score == pytest.approx(0.5 * 10.0 + 0.5 * (100 * 5 / 60))


def test_calib_and_valid_metrics():
    sim = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5, 5, 6, 7, 10])}
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4, 5, 6, 7, 8])}
    score, site = score_sites(
        sim, obs, metric="nse", metrics=("nse",), weights=None,
        calib_period=("2000-01-01", "2000-01-04"),
        valid_period=("2000-01-05", "2000-01-08"),
    )
    s = site[("FLOW_OUTcms", 1)]
    assert s["nse_calib"] == pytest.approx(0.8)
    assert s["nse_valid"] == pytest.approx(0.2)
    assert score == pytest.approx(0.8)


def test_nan_site_gives_nan_score():
    sim = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): daily("2000-06-01", [1, 2, 3]),  # no overlap w/ calib
    }
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4]),
        ("SED_OUTtons", 51): daily("2000-06-01", [1, 2, 3]),
    }
    score, _ = score_sites(sim, obs, metric="nse", metrics=("nse",),
                           weights=None, calib_period=("2000-01-01", "2000-01-04"))
    assert np.isnan(score)


def test_whole_overlap_when_calib_period_is_none():
    sim = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5])}
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4])}
    score, site = score_sites(sim, obs, metric="nse", metrics=("nse",),
                              weights=None, calib_period=None)
    assert site[("FLOW_OUTcms", 1)]["nse_calib"] == pytest.approx(0.8)
    assert score == pytest.approx(0.8)


def test_metric_is_always_reported():
    sim = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5])}
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4])}
    _, site = score_sites(sim, obs, metric="kge", metrics=("nse",),
                          weights=None, calib_period=("2000-01-01", "2000-01-04"))
    keys = list(site[("FLOW_OUTcms", 1)])
    assert keys == ["nse_calib", "kge_calib"]


def test_cross_variable_rmse_without_weights_warns():
    sim = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 25]),
    }
    obs = {
        ("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4]),
        ("SED_OUTtons", 51): daily("2000-01-01", [10, 20, 30]),
    }
    with pytest.warns(UserWarning, match="without explicit weights"):
        score_sites(sim, obs, metric="rmse", metrics=("rmse",), weights=None,
                    calib_period=("2000-01-01", "2000-01-04"))


def test_unknown_metric_raises():
    sim = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 5])}
    obs = {("FLOW_OUTcms", 1): daily("2000-01-01", [1, 2, 3, 4])}
    with pytest.raises(ValueError, match="Unknown metric"):
        score_sites(sim, obs, metric="foo", metrics=("nse",), weights=None,
                    calib_period=("2000-01-01", "2000-01-04"))
