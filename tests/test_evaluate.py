"""
Tests for the pure ``evaluate()`` module: periods, warm-up guard, print-step
check and monthly aggregation of the simulation. Synthetic data only, no SWAT.
"""
import numpy as np
import pandas as pd
import pytest

from spyswat.swat_calib.analysis import EvaluationResult, evaluate


def series(start, values):
    """Daily float series starting at ``start``."""
    return pd.Series(
        [float(v) for v in values],
        index=pd.date_range(start, periods=len(values), freq="D"),
    )


def monthly(start, values):
    """Month-start float series starting at ``start``."""
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series([float(v) for v in values], index=idx)


@pytest.fixture
def pair():
    # obs [1, 2, 3, 4]: mean 2.5, SS=5.0; sim [1, 2, 3, 5]: SS of errors = 1
    # NSE = 1 - 1/5 = 0.8
    return series("2000-01-01", [1, 2, 3, 5]), series("2000-01-01", [1, 2, 3, 4])


# ── table shape and hand-computed metrics ────────────────────────────────────

def test_series_pair_returns_hand_computed_nse(pair):
    sim, obs = pair
    res = evaluate(sim, obs, metrics=("nse",))

    assert isinstance(res, EvaluationResult)
    assert res.table.index.names == ["variable", "reach", "period"]
    row = res.table.loc[(None, None, "all")]
    assert int(row["n"]) == 4
    assert row["nse"] == pytest.approx(0.8)


def test_columns_follow_metrics_order_and_end_with_n(pair):
    sim, obs = pair
    res = evaluate(sim, obs, metrics=("kge", "rmse"))
    assert list(res.table.columns) == ["kge", "rmse", "n"]


def test_default_metrics(pair):
    sim, obs = pair
    assert list(evaluate(sim, obs).table.columns) == ["nse", "kge", "pbias", "r2", "n"]


def test_metrics_accepts_a_single_name(pair):
    sim, obs = pair
    assert list(evaluate(sim, obs, metrics="nse").table.columns) == ["nse", "n"]


def test_dict_sites_and_unobserved_sim_key_is_ignored():
    sim = {
        ("FLOW_OUTcms", 1): series("2000-01-01", [1, 2, 3, 5]),
        ("SED_OUTtons", 51): series("2000-01-01", [10, 20, 25]),
        ("FLOW_OUTcms", 2): series("2000-01-01", [7, 7, 7]),
    }
    obs = {
        ("FLOW_OUTcms", 1): series("2000-01-01", [1, 2, 3, 4]),
        ("SED_OUTtons", 51): series("2000-01-01", [10, 20, 30]),
    }
    res = evaluate(sim, obs, metrics=("nse",))

    assert len(res.table) == 2
    assert res.table.loc[("FLOW_OUTcms", 1, "all"), "nse"] == pytest.approx(0.8)
    # obs mean 20, SS=200, error SS = 25 -> NSE = 1 - 25/200
    assert res.table.loc[("SED_OUTtons", 51, "all"), "nse"] == pytest.approx(0.875)
    assert res.table.loc[("FLOW_OUTcms", 1, "all"), "n"] == 4
    assert res.table.loc[("SED_OUTtons", 51, "all"), "n"] == 3


def test_two_periods_give_their_own_nse():
    sim = series("2000-01-01", [1, 2, 3, 5, 5, 6, 7, 10])
    obs = series("2000-01-01", [1, 2, 3, 4, 5, 6, 7, 8])
    res = evaluate(
        sim, obs,
        periods={"calib": ("2000-01-01", "2000-01-04"),
                 "valid": ("2000-01-05", "2000-01-08")},
        metrics=("nse",),
    )

    assert res.table.loc[(None, None, "calib"), "nse"] == pytest.approx(0.8)
    assert res.table.loc[(None, None, "valid"), "nse"] == pytest.approx(0.2)
    assert res.table.loc[(None, None, "calib"), "n"] == 4
    assert res.table.loc[(None, None, "valid"), "n"] == 4


def test_nan_pairs_are_dropped_and_counted_out(pair):
    sim, obs = pair
    obs.iloc[2] = np.nan
    res = evaluate(sim, obs, metrics=("rmse",))
    assert res.table.loc[(None, None, "all"), "n"] == 3
    assert res.table.loc[(None, None, "all"), "rmse"] == pytest.approx(1.0 / 3.0 ** 0.5)


def test_empty_period_gives_nan_and_zero_pairs():
    sim = series("2000-01-01", [1, 2, 3, 4, 5, 6, 7, 8])
    obs = series("2000-01-01", [1, 2, 3, 4])
    res = evaluate(sim, obs, periods={"late": ("2000-01-06", "2000-01-08")},
                   metrics=("nse", "kge"))

    row = res.table.loc[(None, None, "late")]
    assert row["n"] == 0
    assert np.isnan(row["nse"]) and np.isnan(row["kge"])


# ── print step, warm-up and period guards ────────────────────────────────────

def test_monthly_observations_with_daily_simulation_raise():
    sim = series("2000-01-01", [1, 2, 3, 4])
    obs = monthly("2000-01-01", [1, 3])
    with pytest.raises(ValueError, match="daily"):
        evaluate(sim, obs)


def test_monthly_simulation_with_monthly_observations_is_accepted():
    sim = monthly("2000-01-01", [1, 2, 3])
    obs = monthly("2000-01-01", [1, 2, 3])
    res = evaluate(sim, obs, metrics=("nse",), freq="monthly")
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(1.0)


def test_freq_is_inferred_from_a_monthly_simulation():
    sim = monthly("2000-01-01", [1, 2, 3])
    obs = series("2000-01-01", [1, 2, 3])  # daily obs vs inferred monthly
    with pytest.raises(ValueError, match="monthly"):
        evaluate(sim, obs)


def test_period_starting_before_the_simulation_raises(pair):
    sim, obs = pair
    with pytest.raises(ValueError, match="early.*before the simulation start"):
        evaluate(sim, obs, periods={"early": ("1999-12-31", "2000-01-04")})


def test_period_ending_after_the_simulation_raises(pair):
    sim, obs = pair
    with pytest.raises(ValueError, match="late.*after the simulation end"):
        evaluate(sim, obs, periods={"late": ("2000-01-01", "2000-01-05")})


def test_period_inside_the_warmup_raises(pair):
    sim, obs = pair
    with pytest.raises(ValueError, match="calib.*warm-up"):
        evaluate(sim, obs, periods={"calib": ("2000-01-01", "2000-01-04")},
                 warmup_end="2000-01-03")


def test_period_starting_after_it_ends_raises(pair):
    sim, obs = pair
    with pytest.raises(ValueError, match="reversed"):
        evaluate(sim, obs, periods={"reversed": ("2000-01-04", "2000-01-02")})


def test_default_period_skips_the_warmup():
    sim = series("2000-01-01", [1, 2, 3, 4, 5, 6, 7, 8])
    obs = series("2000-01-01", [1, 2, 3, 4, 5, 6, 7, 8])
    res = evaluate(sim, obs, metrics=("nse",), warmup_end="2000-01-04")
    assert res.table.loc[(None, None, "all"), "n"] == 5
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(1.0)


def test_unknown_metric_raises_before_computing():
    sim = series("2000-01-01", [1, 2, 3, 4])
    obs = series("2000-01-01", [1, 2, 3, 5])
    with pytest.raises(ValueError, match="foo"):
        evaluate(sim, obs, metrics=("nse", "foo"))


def test_observed_key_missing_from_simulation_raises():
    sim = {("FLOW_OUTcms", 1): series("2000-01-01", [1, 2, 3, 4])}
    obs = {("SED_OUTtons", 2): series("2000-01-01", [1, 2, 3, 4])}
    with pytest.raises(ValueError, match="SED_OUTtons"):
        evaluate(sim, obs)


def test_series_and_dict_cannot_be_mixed():
    with pytest.raises(ValueError, match="both"):
        evaluate(series("2000-01-01", [1, 2, 3, 4]),
                 {("FLOW_OUTcms", 1): series("2000-01-01", [1, 2, 3, 4])})


# ── step="M": aggregate the simulation, never the observations ───────────────

def _daily_two_months():
    idx = list(pd.date_range("2000-01-01", periods=4, freq="D")) + \
          list(pd.date_range("2000-02-01", periods=4, freq="D"))
    return pd.Series([2.0, 4.0, 6.0, 8.0, 10.0, 20.0, 30.0, 40.0], index=idx)


def test_step_m_mean_aggregation():
    sim = _daily_two_months()
    obs = monthly("2000-01-01", [5, 25])
    res = evaluate(sim, obs, metrics=("nse", "pbias"), step="M")

    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(1.0)
    assert res.table.loc[(None, None, "all"), "pbias"] == pytest.approx(0.0)
    assert res.table.loc[(None, None, "all"), "n"] == 2


def test_step_m_sum_aggregation_is_explicit():
    sim = _daily_two_months()
    obs = monthly("2000-01-01", [5, 25])
    res = evaluate(sim, obs, metrics=("pbias",), step="M", agg={None: "sum"})

    # simulated month totals 20 and 100 vs observed 5 and 25
    assert res.table.loc[(None, None, "all"), "pbias"] == pytest.approx(-300.0)


def test_step_m_default_aggregation_is_mean_but_sum_for_sediment():
    sim = _daily_two_months()
    obs = monthly("2000-01-01", [5, 25])
    res = evaluate(
        {("FLOW_OUTcms", 1): sim, ("SED_OUTtons", 1): sim},
        {("FLOW_OUTcms", 1): obs, ("SED_OUTtons", 1): monthly("2000-01-01", [20, 100])},
        metrics=("nse", "pbias"),
        step="M",
    )

    assert res.table.loc[("FLOW_OUTcms", 1, "all"), "nse"] == pytest.approx(1.0)
    assert res.table.loc[("SED_OUTtons", 1, "all"), "nse"] == pytest.approx(1.0)
    assert res.table.loc[("SED_OUTtons", 1, "all"), "pbias"] == pytest.approx(0.0)


def test_step_m_with_daily_observations_raises():
    sim = _daily_two_months()
    obs = series("2000-01-01", [5] * 8)
    with pytest.raises(ValueError, match="monthly"):
        evaluate(sim, obs, step="M")


def test_step_m_with_monthly_simulation_is_a_no_op():
    sim = monthly("2000-01-01", [1, 2, 3])
    obs = monthly("2000-01-01", [1, 2, 3])
    res = evaluate(sim, obs, metrics=("nse",), step="M", agg={None: "sum"})
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(1.0)
    assert res.table.loc[(None, None, "all"), "n"] == 3


def test_step_m_rejects_unknown_aggregation():
    sim = _daily_two_months()
    obs = monthly("2000-01-01", [5, 25])
    with pytest.raises(ValueError, match="median"):
        evaluate(sim, obs, step="M", agg={None: "median"})


# ── rework regressions (review round 1) ──────────────────────────────────────

def test_step_m_aggregates_before_deriving_the_simulation_bounds():
    # The daily simulation starts mid-January: after aggregation it covers
    # 2000-01-01, so the first month must be scored and a January period is valid.
    idx = list(pd.date_range("2000-01-15", periods=4, freq="D")) + \
          list(pd.date_range("2000-02-01", periods=4, freq="D"))
    sim = pd.Series([2.0, 4.0, 6.0, 8.0, 6.0, 8.0, 10.0, 12.0], index=idx)
    obs = monthly("2000-01-01", [5, 9])

    res = evaluate(sim, obs, metrics=("nse",), step="M")
    assert res.table.loc[(None, None, "all"), "n"] == 2
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(1.0)

    jan = evaluate(sim, obs, metrics=("pbias",), step="M",
                   periods={"jan": ("2000-01-01", "2000-01-31")})
    assert jan.table.loc[(None, None, "jan"), "n"] == 1
    assert jan.table.loc[(None, None, "jan"), "pbias"] == pytest.approx(0.0)


def test_unobserved_simulation_site_is_ignored_for_frequency_and_bounds():
    # The unobserved daily site would make the inferred print step daily and
    # would drag the simulation start back to 1999; both must be ignored.
    sim = {
        ("FLOW_OUTcms", 1): monthly("2000-01-01", [1, 2, 3]),
        ("SED_OUTtons", 2): series("1999-06-01", [9] * 10),
    }
    obs = {("FLOW_OUTcms", 1): monthly("2000-01-01", [1, 2, 3])}

    res = evaluate(sim, obs, metrics=("nse",))

    assert len(res.table) == 1
    row = res.table.loc[("FLOW_OUTcms", 1, "all")]
    assert row["n"] == 3
    assert row["nse"] == pytest.approx(1.0)


def test_default_period_without_overlap_gives_nan_and_zero_pairs():
    sim = series("2000-01-01", [1, 2, 3, 4])
    obs = series("2000-06-01", [1, 2, 3, 4])

    res = evaluate(sim, obs, metrics=("nse", "kge"))

    row = res.table.loc[(None, None, "all")]
    assert row["n"] == 0
    assert np.isnan(row["nse"]) and np.isnan(row["kge"])


def test_default_period_with_warmup_beyond_the_record_gives_nan_and_zero_pairs():
    sim = series("2000-01-01", [1, 2, 3, 4])
    obs = series("2000-01-01", [1, 2, 3, 4])

    res = evaluate(sim, obs, metrics=("nse",), warmup_end="2000-01-20")

    row = res.table.loc[(None, None, "all")]
    assert row["n"] == 0
    assert np.isnan(row["nse"])


def test_duplicate_metric_names_are_collapsed(pair):
    sim, obs = pair

    res = evaluate(sim, obs, metrics=("nse", "nse", "kge"))

    assert list(res.table.columns) == ["nse", "kge", "n"]
    assert res.table.loc[(None, None, "all"), "nse"] == pytest.approx(0.8)


def test_step_m_sum_keeps_an_all_nan_month_nan():
    idx = list(pd.date_range("2000-01-01", periods=3, freq="D")) + \
          list(pd.date_range("2000-02-01", periods=3, freq="D"))
    sim = pd.Series([np.nan] * 3 + [2.0, 4.0, 6.0], index=idx)
    obs = monthly("2000-01-01", [6, 12])

    res = evaluate(sim, obs, metrics=("pbias",), step="M", agg={None: "sum"})

    # January summed to 0.0 before the fix; it must stay NaN and drop out.
    assert res.table.loc[(None, None, "all"), "n"] == 1
    assert res.table.loc[(None, None, "all"), "pbias"] == pytest.approx(0.0)


def test_agg_must_be_a_mapping():
    sim = _daily_two_months()
    obs = monthly("2000-01-01", [5, 25])

    with pytest.raises(ValueError, match="agg"):
        evaluate(sim, obs, step="M", agg=["mean", "sum"])


def test_empty_simulation_series_raises():
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    obs = series("2000-01-01", [1, 2, 3])

    with pytest.raises(ValueError, match="empty"):
        evaluate(empty, obs)


# ── rework regressions (review round 2) ──────────────────────────────────────

def test_step_m_period_may_end_on_the_last_simulated_day():
    # A full-year daily simulation aggregated to "MS" ends 2000-12-01 internally,
    # but a period ending on the real last day (2000-12-31) must be accepted.
    idx = pd.date_range("2000-01-01", "2000-12-31", freq="D")
    sim = pd.Series([float(month) for month in idx.month], index=idx)
    obs = monthly("2000-01-01", list(range(1, 13)))

    res = evaluate(sim, obs, metrics=("nse",), step="M",
                   periods={"valid": ("2000-01-01", "2000-12-31")})

    row = res.table.loc[(None, None, "valid")]
    assert row["n"] == 12
    assert row["nse"] == pytest.approx(1.0)


def test_step_m_period_may_end_mid_the_last_simulated_month():
    # The simulation stops on 2000-02-04: the aggregated series ends 2000-02-01,
    # yet a period ending on the real last simulated day is valid.
    idx = pd.date_range("2000-01-01", "2000-02-04", freq="D")
    sim = pd.Series([5.0] * 31 + [25.0] * 4, index=idx)
    obs = monthly("2000-01-01", [5, 25])

    res = evaluate(sim, obs, metrics=("nse",), step="M",
                   periods={"valid": ("2000-01-01", "2000-02-04")})

    row = res.table.loc[(None, None, "valid")]
    assert row["n"] == 2
    assert row["nse"] == pytest.approx(1.0)


@pytest.mark.parametrize("bound", [None, pd.NaT])
def test_period_bound_that_is_not_a_date_raises(pair, bound):
    sim, obs = pair

    with pytest.raises(ValueError, match="bad"):
        evaluate(sim, obs, periods={"bad": (bound, "2000-01-04")})
    with pytest.raises(ValueError, match="bad"):
        evaluate(sim, obs, periods={"bad": ("2000-01-01", bound)})


def test_warmup_end_that_is_not_a_date_raises(pair):
    sim, obs = pair

    with pytest.raises(ValueError, match="warmup_end"):
        evaluate(sim, obs, warmup_end=pd.NaT)


def test_reaches_are_sorted_numerically():
    sim = {
        ("FLOW_OUTcms", 10): series("2000-01-01", [1, 2, 3]),
        ("FLOW_OUTcms", 2): series("2000-01-01", [1, 2, 3]),
    }
    obs = {
        ("FLOW_OUTcms", 10): series("2000-01-01", [1, 2, 3]),
        ("FLOW_OUTcms", 2): series("2000-01-01", [1, 2, 3]),
    }

    res = evaluate(sim, obs, metrics=("nse",))

    order = list(res.table.index.droplevel("period"))
    assert order == [("FLOW_OUTcms", 2), ("FLOW_OUTcms", 10)]


# ── export ───────────────────────────────────────────────────────────────────

def test_to_csv_writes_the_table(pair, tmp_path):
    sim, obs = pair
    out = tmp_path / "eval.csv"
    assert evaluate(sim, obs).to_csv(out) is None
    text = out.read_text(encoding="utf-8")
    assert "variable,reach,period" in text
    assert "n" in text.splitlines()[0]
