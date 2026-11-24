"""Regression-based (SWAT-CUP global) sensitivity from calibration runs."""
import numpy as np
import pandas as pd
import pytest

from spyswat.swat_calib.analysis import regression_sensitivity


def synthetic_runs(n=200, seed=42):
    """score = 3*x1 + 0.5*x2 + noise; x3 is pure noise (independent)."""
    rng = np.random.default_rng(seed)
    x1, x2, x3 = rng.random(n), rng.random(n), rng.random(n)
    noise = rng.normal(0.0, 0.1, n)
    return pd.DataFrame({
        "K1.mgt": x1,
        "K2.mgt": x2,
        "K3.mgt": x3,
        "score": 3.0 * x1 + 0.5 * x2 + noise,
    })


def test_ranks_dominant_parameter_first():
    runs = synthetic_runs()
    result = regression_sensitivity(
        runs,
        {"K1.mgt": (0.0, 1.0), "K2.mgt": (0.0, 1.0), "K3.mgt": (0.0, 1.0)},
    )

    assert list(result.columns) == ["parameter", "coef", "t_stat", "p_value", "rank"]
    assert list(result["parameter"]) == ["K1.mgt", "K2.mgt", "K3.mgt"]
    assert list(result["rank"]) == [1, 2, 3]
    assert result.iloc[0]["p_value"] < 0.01
    assert result.loc[result["parameter"] == "K3.mgt", "p_value"].iloc[0] > 0.05


def test_drops_rows_with_nan_score_or_parameter():
    runs = synthetic_runs(n=120)
    runs.loc[0, "score"] = np.nan
    runs.loc[1, "K2.mgt"] = np.nan
    runs.loc[2, "K3.mgt"] = np.nan

    result = regression_sensitivity(
        runs,
        {"K1.mgt": (0.0, 1.0), "K2.mgt": (0.0, 1.0), "K3.mgt": (0.0, 1.0)},
    )

    assert result.attrs["n_runs"] == 117
    assert result.iloc[0]["parameter"] == "K1.mgt"


def test_too_few_usable_rows_raises():
    runs = synthetic_runs(n=20).iloc[:4]   # k = 3 parameters, need n > k + 1
    with pytest.raises(ValueError, match="Not enough usable runs"):
        regression_sensitivity(
            runs,
            {"K1.mgt": (0.0, 1.0), "K2.mgt": (0.0, 1.0), "K3.mgt": (0.0, 1.0)},
        )


def test_missing_parameter_column_raises():
    runs = synthetic_runs(n=50).drop(columns=["K3.mgt"])
    with pytest.raises(ValueError, match="K3.mgt"):
        regression_sensitivity(
            runs,
            {"K1.mgt": (0.0, 1.0), "K2.mgt": (0.0, 1.0), "K3.mgt": (0.0, 1.0)},
        )


def test_constant_parameter_raises():
    runs = synthetic_runs(n=50)
    runs["K2.mgt"] = 0.5
    with pytest.raises(ValueError, match="constant"):
        regression_sensitivity(
            runs,
            {"K1.mgt": (0.0, 1.0), "K2.mgt": (0.0, 1.0), "K3.mgt": (0.0, 1.0)},
        )


def test_method_decorated_specs_use_inner_bounds():
    rng = np.random.default_rng(7)
    n = 150
    cn2 = rng.uniform(35.0, 98.0, n)
    alpha = rng.random(n)
    score = 3.0 * (cn2 - 35.0) / 63.0 + 0.5 * alpha + rng.normal(0.0, 0.01, n)
    runs = pd.DataFrame({"CN2.mgt": cn2, "ALPHA_BF.gw": alpha, "score": score})

    result = regression_sensitivity(runs, {
        "CN2.mgt": ((35, 98), "r"),
        "ALPHA_BF.gw": ((0.0, 1.0), "a", [1, 2]),
    })

    coefs = result.set_index("parameter")["coef"]
    assert coefs["CN2.mgt"] == pytest.approx(3.0, rel=0.02)
    assert coefs["ALPHA_BF.gw"] == pytest.approx(0.5, rel=0.05)
