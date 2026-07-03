"""
Utility for loading param_ranges from a clean CSV file.

Expected CSV columns:
    key      – parameter key in SpySWAT format, e.g. "CN2.mgt"
    method   – "relative" | "replace" | "add"  (or short: "r" | "v" | "a")
    min      – lower bound (float)
    max      – upper bound (float)
    subbasin – "All" or comma-separated subbasin IDs, e.g. "71,45,70" (optional)

Usage:
    from spyswat.swat_calib.utils import load_param_ranges

    param_ranges = load_param_ranges("src/user19Params_clean.csv")
    result = calib.de.run(param_ranges=param_ranges, observed_series=obs, reach_id=32)
"""

from __future__ import annotations

import pandas as pd


def load_param_ranges(csv_path: str) -> dict:
    """
    Load param_ranges dict from a clean CSV file.

    Parameters
    ----------
    csv_path : str
        Path to CSV with columns: key, method, min, max[, subbasin]

    Returns
    -------
    dict
        SpySWAT param_ranges format:
        - ``{key: ((min, max), method)}``              when subbasin == "All"
        - ``{key: ((min, max), method, [ids])}``       when subbasin is specified

    Raises
    ------
    ValueError
        If required columns (key, method, min, max) are missing.
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    required = {"name", "method", "min", "max"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {missing}. "
            f"Found: {list(df.columns)}"
        )

    param_ranges: dict = {}
    for _, row in df.iterrows():
        bounds = (float(row["min"]), float(row["max"]))
        method = str(row["method"]).strip()

        sub = str(row.get("subbasin", "All")).strip() if "subbasin" in df.columns else "All"
        if sub in ("All", "", "nan"):
            param_ranges[row["key"]] = (bounds, method)
        else:
            ids = [int(s.strip()) for s in sub.split(",")]
            param_ranges[row["key"]] = (bounds, method, ids)

    return param_ranges
