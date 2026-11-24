"""
Pure multi-site scoring helpers for ``CalibrationManager``.

No SWAT run, no parameters, no files touched: observed/simulated series go in,
one aggregated ``score`` and a per-site/period metric table come out. The single
metric implementation lives in ``analysis/evaluate.py``; this module only turns
that into the vocabulary the manager uses (``outputs`` / ``observed`` /
``weights`` / ``calib_period`` / ``valid_period``) and the aggregated score.

``evaluate`` is imported lazily inside ``score_sites``: ``evaluate`` imports
``calib_manager.check_observation_step`` back, and ``calib_manager`` imports this
module, so a top-level import would create a cycle.
"""
from __future__ import annotations

import warnings
from collections.abc import Mapping

import numpy as np
import pandas as pd

from spyswat.swat_calib.analysis.statistics import METRIC_DIRECTIONS

DEFAULT_OUTPUTS = {"FLOW_OUTcms": [1]}
DEFAULT_METRICS = ("nse", "kge", "pbias", "r2")


def _normalise_outputs(outputs) -> dict:
    """``{variable: [reach, ...]}`` with every reach list materialised."""
    if not isinstance(outputs, Mapping):
        raise ValueError(
            f"outputs must be a mapping {{variable: [reach, ...]}}, got "
            f"{type(outputs).__name__}."
        )
    out = {}
    for var, reaches in outputs.items():
        if isinstance(reaches, (str, int, float)):
            reaches = [reaches]
        try:
            out[var] = [int(r) for r in reaches]
        except (TypeError, ValueError):
            raise ValueError(
                f"outputs[{var!r}] must be a list of reach ids, got {reaches!r}."
            ) from None
    return out


def _flatten_sites(outputs: dict) -> list:
    """Every ``(variable, reach)`` in ``outputs``, in a deterministic order."""
    return [(var, reach) for var in sorted(outputs) for reach in outputs[var]]


def _check_site_key(key, label: str) -> None:
    if not (isinstance(key, tuple) and len(key) == 2):
        raise ValueError(
            f"{label} keys must be (variable, reach) tuples, got {key!r}."
        )


def normalise_observed(observed, outputs=None):
    """Normalise ``observed`` into ``(observed_dict, outputs_dict)``.

    A bare ``pd.Series`` is wrapped as ``{(variable, reach): series}`` using the
    single site of ``outputs`` (default ``{"FLOW_OUTcms": [1]}``); it is a
    ``ValueError`` when ``outputs`` describes more than one site. A dict of series
    keyed ``(variable, reach)`` is returned as-is, and any of its keys missing
    from ``outputs`` are added. ``outputs_dict`` is always ``{variable: [reaches]}``.
    """
    outputs_dict = _normalise_outputs(DEFAULT_OUTPUTS if outputs is None else outputs)
    if isinstance(observed, pd.Series):
        sites = _flatten_sites(outputs_dict)
        if len(sites) != 1:
            raise ValueError(
                "A bare observed Series needs exactly one (variable, reach) site "
                f"in outputs; got {len(sites)} sites from {outputs_dict!r}."
            )
        return {sites[0]: observed}, outputs_dict
    if isinstance(observed, Mapping):
        observed_dict = {}
        for key, series in observed.items():
            _check_site_key(key, "observed")
            observed_dict[key] = series
            var, reach = key
            if var not in outputs_dict:
                outputs_dict[var] = [reach]
            elif reach not in outputs_dict[var]:
                outputs_dict[var] = list(outputs_dict[var]) + [reach]
        return observed_dict, outputs_dict
    raise ValueError(
        f"observed must be a pandas Series or a dict keyed (variable, reach), "
        f"got {type(observed).__name__}."
    )


def check_weights(weights, sites) -> dict:
    """Validate ``weights`` and return them as ``{site: float}`` summing to 1.

    ``None`` means equal weights. Every given weight must be a positive number
    for a known site; the returned weights are normalised to sum to 1 (sites
    without a weight keep weight 0 and drop out of the aggregated score).
    """
    site_list = list(sites)
    if weights is None:
        n = len(site_list)
        if n == 0:
            return {}
        return {site: 1.0 / n for site in site_list}
    if not isinstance(weights, Mapping):
        raise ValueError(
            f"weights must be a mapping {{(variable, reach): float}} or None, got "
            f"{type(weights).__name__}."
        )
    out = {}
    for key, w in weights.items():
        _check_site_key(key, "weights")
        if key not in site_list:
            raise ValueError(
                f"weight given for unknown site {key!r}; known sites: {site_list!r}."
            )
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not np.isfinite(w) or w <= 0:
            raise ValueError(
                f"weight for {key!r} must be a positive finite number, got {w!r}."
            )
        out[key] = float(w)
    total = sum(out.values())
    if total <= 0:
        raise ValueError("weights must contain at least one positive weight.")
    return {k: v / total for k, v in out.items()}


def _period_bounds(calib_period):
    """``(start, end)`` Timestamps, or ``(None, None)`` when ``calib_period`` is None."""
    if calib_period is None:
        return None, None
    try:
        start_raw, end_raw = calib_period
    except (TypeError, ValueError):
        raise ValueError(
            f"calib_period must be a (start, end) pair, got {calib_period!r}."
        ) from None
    start, end = pd.Timestamp(start_raw), pd.Timestamp(end_raw)
    if pd.isna(start) or pd.isna(end):
        raise ValueError(f"calib_period needs two real dates, got {calib_period!r}.")
    return start, end


def preflight(observed_dict, calib_period) -> None:
    """Fail fast before any SWAT run.

    Each observed site must overlap ``calib_period`` (skipped when it is ``None``,
    i.e. "whole overlap") and have non-zero variance; otherwise ``ValueError``.
    """
    start, end = _period_bounds(calib_period)
    for key, series in observed_dict.items():
        if not isinstance(series, pd.Series):
            raise ValueError(
                f"observed[{key!r}] must be a pandas Series, got {type(series).__name__}."
            )
        idx = pd.DatetimeIndex(series.index)
        vals = series.to_numpy(dtype=float)
        if start is not None:
            mask = (idx >= start) & (idx <= end)
            if not mask.any():
                raise ValueError(
                    f"observed[{key!r}] has no data within the calibration period "
                    f"{start.date()} .. {end.date()}."
                )
            vals = vals[mask]
        vals = vals[np.isfinite(vals)]
        if vals.size < 2 or np.nanstd(vals) == 0.0:
            raise ValueError(
                f"observed[{key!r}] has zero variance within the calibration period; "
                f"it cannot be scored."
            )


def _resolve_metrics(metric, metrics) -> tuple:
    """Reported metric names in order; ``metric`` is always included (last)."""
    if metrics is None:
        names = list(DEFAULT_METRICS)
    elif isinstance(metrics, str):
        names = [metrics]
    else:
        names = list(metrics)
    names = list(dict.fromkeys(names))          # drop duplicates, keep order
    for name in names + [metric]:
        if name not in METRIC_DIRECTIONS:
            raise ValueError(
                f"Unknown metric {name!r}; known metrics: "
                f"{', '.join(sorted(METRIC_DIRECTIONS))}."
            )
    if metric not in names:
        names.append(metric)
    return tuple(names)


def _warn_cross_variable(metric, observed, weights) -> None:
    if metric not in ("rmse", "mae"):
        return
    if weights is not None:
        return
    variables = {key[0] for key in observed}
    if len(variables) > 1:
        warnings.warn(
            f"Aggregating {metric!r} across variables {sorted(variables)!r} without "
            f"explicit weights mixes different units; pass weights to control the "
            f"aggregated score.",
            stacklevel=2,
        )


def _whole_overlap(sim, observed, warmup_end):
    """The default calibration period: (warm-up end | sim start) .. last common date."""
    sim_min = min(s.index.min() for s in sim.values())
    sim_max = max(s.index.max() for s in sim.values())
    start = sim_min if warmup_end is None or warmup_end <= sim_min else warmup_end
    common = None
    for key, obs in observed.items():
        site = obs.index.intersection(sim[key].index)
        site = site[(site >= start) & (site <= sim_max)]
        common = site if common is None else common.union(site)
    if common is None or len(common) == 0:
        return (start, start)
    return (common.min(), common.max())


def score_sites(sim: dict, observed: dict, *, metric, metrics, weights, calib_period,
                valid_period=None, freq=None, step=None, agg=None,
                warmup_end=None):
    """Score every observed site and return ``(score, site_metrics)``.

    ``sim`` and ``observed`` are dicts keyed ``(variable, reach)``; ``sim`` may hold
    unobserved sites (ignored). ``evaluate`` is called with a ``calib`` period (and a
    ``valid`` period when given); ``calib_period=None`` means the whole overlap.

    Returns ``(score, {(variable, reach): {"<metric>_calib": x, "<metric>_valid": y}})`.
    ``score`` is the weighted mean (sites with weight > 0) of the calibration
    objective in the direction of ``metric``, using ``|pbias|`` for pbias; any NaN
    site objective makes ``score`` NaN.
    """
    from spyswat.swat_calib.analysis.evaluate import evaluate  # avoid import cycle

    metric_names = _resolve_metrics(metric, metrics)
    weights_norm = check_weights(weights, list(observed))
    _warn_cross_variable(metric, observed, weights)

    periods = {}
    if calib_period is not None:
        periods["calib"] = calib_period
        calib_key = "calib"
    elif valid_period is not None:
        periods["calib"] = _whole_overlap(sim, observed, warmup_end)
        calib_key = "calib"
    else:
        calib_key = "all"
    if valid_period is not None:
        periods["valid"] = valid_period

    table = evaluate(
        sim, observed, periods=periods or None, metrics=metric_names,
        freq=freq, step=step, agg=agg, warmup_end=warmup_end,
    ).table

    report_periods = ["calib"] + (["valid"] if valid_period is not None else [])
    table_periods = [calib_key] + (["valid"] if valid_period is not None else [])

    site_metrics = {}
    for key in observed:
        entry = {}
        for report, actual in zip(report_periods, table_periods):
            for name in metric_names:
                entry[f"{name}_{report}"] = float(
                    table.loc[(key[0], key[1], actual), name]
                )
        site_metrics[key] = entry

    return _aggregate_score(table, metric, weights_norm, calib_key), site_metrics


def _aggregate_score(table, metric, weights_norm, calib_key) -> float:
    objs, ws = [], []
    for key, w in weights_norm.items():
        if w <= 0:
            continue
        value = float(table.loc[(key[0], key[1], calib_key), metric])
        objs.append(abs(value) if METRIC_DIRECTIONS[metric] == "min_abs" else value)
        ws.append(w)
    if not objs:
        return float("nan")
    if any(pd.isna(o) for o in objs):
        return float("nan")
    return float(sum(w * o for w, o in zip(ws, objs)) / sum(ws))
