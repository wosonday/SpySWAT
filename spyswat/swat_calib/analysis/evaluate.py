"""
Pure evaluation of simulated against observed time series.

No SWAT run, no parameters, no files touched: two series (or dicts of series
keyed ``(variable, reach)``) in, one ``EvaluationResult`` table out. The
``SWATProject.evaluate`` facade (API-4) only adds the project's print step and
warm-up end before calling this module.

Vocabulary (see ``docs/superpowers/specs/2026-11-24-api-standardisation-design.md``):

- ``step=None``: the observations must already be on the simulation's print
  step (checked with ``check_observation_step``).
- ``step="M"``: the **simulation** is aggregated to month-start timestamps
  (mean, or sum for sediment/mass variables) and the observations must be
  monthly. Observations are never resampled.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..calibration.calib_manager import check_observation_step
from .statistics import METRIC_DIRECTIONS, SWATAnalysis, known_metrics

SiteKey = Tuple[Optional[str], Optional[int]]

# Registry name -> SWATAnalysis metric method (the registry stays the single
# source of truth for which metrics exist and for their direction).
_METRIC_METHODS: Dict[str, str] = {
    "nse": "_nse",
    "r2": "_r_squared",
    "kge": "_kge",
    "correlation": "_correlation",
    "rmse": "_rmse",
    "mae": "_mae",
    "rsr": "_rsr",
    "pbias": "_pbias",
}

# Same print steps ``check_observation_step`` accepts internally.
_FREQ_CODES: Dict[str, str] = {"daily": "D", "D": "D", "monthly": "MS", "MS": "MS"}

_SEDIMENT_PREFIX = "SED_"
_MASS_SUFFIXES = ("tons", "kg")


@dataclass
class EvaluationResult:
    """Metrics of one or more sites for one or more periods.

    ``table`` has a ``(variable, reach, period)`` MultiIndex; its columns are the
    requested metrics plus ``n`` (the number of non-NaN pairs used).
    """

    table: pd.DataFrame

    def to_csv(self, path) -> None:
        """Write ``table`` to ``path`` (one row per site and period)."""
        self.table.to_csv(path)


def evaluate(
    sim,
    observed,
    periods=None,
    *,
    metrics=("nse", "kge", "pbias", "r2"),
    freq: Optional[str] = None,
    step: Optional[str] = None,
    agg: Optional[Dict[Optional[str], str]] = None,
    warmup_end=None,
) -> EvaluationResult:
    """Score simulated against observed series, site by site and period by period.

    Parameters
    ----------
    sim, observed:
        Both ``pd.Series`` with a ``DatetimeIndex`` (one site, key
        ``(None, None)``) or both dicts keyed ``(variable, reach)``. Every
        observed key must also be in ``sim``; simulated keys without
        observations are ignored.
    periods:
        ``{name: (start, end)}``, inclusive, strings or Timestamps. ``None``
        means ``{"all": (simulation start, last common date)}``; with a
        ``warmup_end`` the default period starts at the end of the warm-up so
        warm-up years are never scored.
    metrics:
        Registry metric names; unknown names raise ``ValueError`` before any
        computation.
    freq:
        Simulation print step, ``"daily"`` or ``"monthly"``. ``None`` infers it
        from the simulation index (month-start timestamps, one per month).
    step:
        ``None`` or ``"M"``. ``"M"`` aggregates the simulation to month-start
        timestamps before scoring; it is a no-op for a monthly simulation.
    agg:
        ``{variable: "mean" | "sum"}`` for ``step="M"``. The default is mean,
        or sum for variables starting with ``SED_`` or ending with ``tons`` or
        ``kg``.
    warmup_end:
        Last warm-up date. A period starting before it is rejected, and the
        default period starts there.

    Returns
    -------
    EvaluationResult
        Rows ``(variable, reach, period)``; columns are ``metrics`` plus
        ``n``. A period with no common (non-NaN) dates gives NaN metrics and
        ``n`` = 0.
    """
    sim_sites, obs_sites = _normalise_sites(sim, observed)
    metric_names = _check_metrics(metrics)
    _check_step(step, agg)

    print_step = _normalise_freq(freq) if freq is not None else _infer_freq(sim_sites)

    obs_sites = _prepare_observations(obs_sites, print_step, step)
    # Last real simulated day, before any monthly aggregation moves it back to
    # the first of the month: a period may still end on that day.
    raw_max = max(s.index.max() for s in sim_sites.values())
    if step == "M" and print_step == "D":
        sim_sites = {
            key: _aggregate_to_months(series, _aggregation_method(key[0], agg))
            for key, series in sim_sites.items()
        }

    # Bounds come from the simulation as it will actually be scored: after
    # aggregation (which may start a mid-month record on the 1st), only for the
    # sites that have observations, and never before the raw last day.
    sim_min = min(s.index.min() for s in sim_sites.values())
    sim_max = max(raw_max, max(s.index.max() for s in sim_sites.values()))

    warmup = None
    if warmup_end is not None:
        warmup = pd.Timestamp(warmup_end)
        if pd.isna(warmup):
            raise ValueError(
                f"warmup_end must be a real date, got {warmup_end!r}."
            )

    period_bounds = _resolve_periods(
        periods, obs_sites, sim_sites, sim_min, sim_max, warmup
    )

    analysis = SWATAnalysis(None)
    row_keys: List[Tuple[Optional[str], Optional[int], str]] = []
    values: Dict[str, List[float]] = {name: [] for name in metric_names}
    counts: List[int] = []

    for key in _sorted_keys(obs_sites):
        obs = obs_sites[key]
        sim_series = sim_sites[key]
        common = obs.index.intersection(sim_series.index)
        for period_name, (start, end) in period_bounds.items():
            dates = common[(common >= start) & (common <= end)]
            ob = obs.loc[dates].to_numpy(dtype=float)
            si = sim_series.loc[dates].to_numpy(dtype=float)
            keep = ~(np.isnan(ob) | np.isnan(si))
            ob, si = ob[keep], si[keep]

            row_keys.append((key[0], key[1], period_name))
            counts.append(int(ob.size))
            for name in metric_names:
                values[name].append(_metric_value(analysis, name, ob, si))

    index = pd.MultiIndex.from_tuples(
        row_keys, names=["variable", "reach", "period"]
    )
    data = dict(values)
    data["n"] = counts
    table = pd.DataFrame(data, index=index, columns=list(metric_names) + ["n"])
    return EvaluationResult(table)


# ── input normalisation ──────────────────────────────────────────────────────

def _normalise_sites(sim, observed) -> Tuple[Dict[SiteKey, pd.Series],
                                             Dict[SiteKey, pd.Series]]:
    sim_is_series = isinstance(sim, pd.Series)
    obs_is_series = isinstance(observed, pd.Series)
    if sim_is_series != obs_is_series:
        raise ValueError(
            "sim and observed must both be a pandas Series (one site) or both "
            "be dicts keyed (variable, reach); got "
            f"{type(sim).__name__} and {type(observed).__name__}."
        )
    single = (None, None)
    if sim_is_series:
        sim_sites = {single: sim}
        obs_sites = {single: observed}
    else:
        sim_sites = _as_site_dict(sim, "sim")
        obs_sites = _as_site_dict(observed, "observed")

    if not obs_sites:
        raise ValueError("observed contains no series to evaluate.")
    for key, series in list(obs_sites.items()):
        _check_time_series(series, "observed", key)
    for key in obs_sites:
        if key not in sim_sites:
            raise ValueError(
                f"observed site {key!r} has no simulated series; add it to sim "
                f"or drop it from observed."
            )
    # Simulated sites without observations are ignored: they do not affect the
    # print step, the simulation bounds or the periods.
    sim_sites = {key: sim_sites[key] for key in obs_sites}
    for key, series in list(sim_sites.items()):
        _check_time_series(series, "sim", key)
    return sim_sites, obs_sites


def _as_site_dict(value, label: str) -> Dict[SiteKey, pd.Series]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{label} must be a pandas Series or a dict keyed (variable, reach), "
            f"got {type(value).__name__}."
        )
    sites: Dict[SiteKey, pd.Series] = {}
    for key, series in value.items():
        if not (isinstance(key, tuple) and len(key) == 2):
            raise ValueError(
                f"{label} keys must be (variable, reach) tuples, got {key!r}."
            )
        sites[key] = series
    return sites


def _check_time_series(series, label: str, key: SiteKey) -> None:
    if not isinstance(series, pd.Series):
        raise ValueError(
            f"{label}[{key!r}] must be a pandas Series, got {type(series).__name__}."
        )
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(f"{label}[{key!r}] must have a DatetimeIndex, got {type(series.index).__name__}.")
    if len(series) == 0:
        raise ValueError(f"{label}[{key!r}] is empty; nothing to evaluate.")
    if series.index.has_duplicates:
        raise ValueError(f"{label}[{key!r}] has duplicate dates.")


def _sorted_keys(sites: Mapping[SiteKey, pd.Series]) -> List[SiteKey]:
    # Reaches sort numerically (2 before 10); a missing reach sorts last.
    return sorted(sites, key=lambda k: (str(k[0]), k[1] is None, k[1]))


def _check_metrics(metrics) -> Tuple[str, ...]:
    names = (metrics,) if isinstance(metrics, str) else tuple(metrics)
    # Duplicate names would append twice per row; collapse them, keeping order.
    names = tuple(dict.fromkeys(names))
    if not names:
        raise ValueError("metrics must contain at least one registry metric.")
    for name in names:
        if name not in METRIC_DIRECTIONS:
            raise ValueError(
                f"Unknown metric {name!r}; known metrics: {', '.join(known_metrics())}"
            )
        if name not in _METRIC_METHODS:
            raise ValueError(f"Metric {name!r} is registered but not supported by evaluate.")
    return names


def _check_step(step, agg) -> None:
    if step not in (None, "M"):
        raise ValueError(f"Unsupported step {step!r}: use None or 'M'.")
    if agg is not None:
        if step != "M":
            raise ValueError("agg is only used with step='M'.")
        if not isinstance(agg, Mapping):
            raise ValueError(
                f"agg must be a mapping {{variable: 'mean' | 'sum'}}, got "
                f"{type(agg).__name__}."
            )
        for variable, how in agg.items():
            if how not in ("mean", "sum"):
                raise ValueError(
                    f"Unsupported aggregation {how!r} for {variable!r}: "
                    f"use 'mean' or 'sum'."
                )


# ── print step and aggregation ───────────────────────────────────────────────

def _normalise_freq(freq) -> str:
    try:
        return _FREQ_CODES[freq]
    except (KeyError, TypeError):
        raise ValueError(
            f"Unsupported simulation frequency {freq!r}: use 'daily' or 'monthly'."
        ) from None


def _infer_freq(sim_sites: Mapping[SiteKey, pd.Series]) -> str:
    """Same rule ``check_observation_step`` applies: month-start, unique months -> MS."""
    index = None
    for series in sim_sites.values():
        index = series.index if index is None else index.union(series.index)
    if index is None or len(index) <= 1:
        return "D"
    monthly = bool(
        (index.day == 1).all()
        and (index == index.normalize()).all()
        and not index.to_period("M").duplicated().any()
    )
    return "MS" if monthly else "D"


def _prepare_observations(obs_sites: Dict[SiteKey, pd.Series],
                          print_step: str, step: Optional[str]) -> Dict[SiteKey, pd.Series]:
    """Reject observations whose step differs from the (possibly monthly) simulation."""
    required = "MS" if step == "M" else print_step
    for key, series in obs_sites.items():
        try:
            check_observation_step(series.index, required)
        except ValueError as exc:
            raise ValueError(f"observed[{key!r}]: {exc}") from None
    return obs_sites


def _aggregation_method(variable: Optional[str], agg) -> str:
    if agg is not None and variable in agg:
        return agg[variable]
    if variable is None:
        return "mean"
    name = str(variable)
    if name.startswith(_SEDIMENT_PREFIX) or name.endswith(_MASS_SUFFIXES):
        return "sum"
    return "mean"


def _aggregate_to_months(series: pd.Series, how: str) -> pd.Series:
    with np.errstate(all="ignore"):
        if how == "sum":
            # min_count=1 keeps an empty or all-NaN month NaN instead of 0.0.
            return series.resample("MS").sum(min_count=1)
        return series.resample("MS").mean()


# ── periods ──────────────────────────────────────────────────────────────────

def _resolve_periods(periods, obs_sites: Mapping[SiteKey, pd.Series],
                     sim_sites: Mapping[SiteKey, pd.Series],
                     sim_min: pd.Timestamp, sim_max: pd.Timestamp,
                     warmup: Optional[pd.Timestamp]) -> Dict[str, Tuple[pd.Timestamp, pd.Timestamp]]:
    if periods is None:
        start = sim_min if warmup is None or warmup <= sim_min else warmup
        common = _common_dates(obs_sites, sim_sites, start, sim_max)
        if len(common) == 0:
            # Non-overlapping records or a warm-up past the record: no pairs to
            # score, but not an error (metrics NaN, n = 0).
            return {"all": (start, start)}
        return {"all": (common.min(), common.max())}

    if not isinstance(periods, Mapping) or not periods:
        raise ValueError("periods must be a non-empty dict {name: (start, end)}.")
    resolved = {}
    for name, bounds in periods.items():
        resolved[name] = _period_bounds(name, bounds)

    for name, (start, end) in resolved.items():
        _validate_period(name, start, end, sim_min, sim_max, warmup)
    return resolved


def _period_bounds(name: str, bounds) -> Tuple[pd.Timestamp, pd.Timestamp]:
    try:
        start_raw, end_raw = bounds
    except (TypeError, ValueError):
        raise ValueError(
            f"Period {name!r} must be a (start, end) pair, got {bounds!r}."
        ) from None
    start = pd.Timestamp(start_raw)
    end = pd.Timestamp(end_raw)
    # None or NaT would make every comparison below False and hide the error.
    if pd.isna(start) or pd.isna(end):
        raise ValueError(
            f"Period {name!r} needs two real dates, got {bounds!r}."
        )
    return start, end


def _common_dates(obs_sites: Mapping[SiteKey, pd.Series],
                  sim_sites: Mapping[SiteKey, pd.Series],
                  start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Dates each site actually scores, unioned across sites, within [start, end]."""
    common: Optional[pd.DatetimeIndex] = None
    for key, obs in obs_sites.items():
        site = obs.index.intersection(sim_sites[key].index)
        site = site[(site >= start) & (site <= end)]
        common = site if common is None else common.union(site)
    return pd.DatetimeIndex([]) if common is None else common


def _validate_period(name: str, start: pd.Timestamp, end: pd.Timestamp,
                     sim_min: pd.Timestamp, sim_max: pd.Timestamp,
                     warmup: Optional[pd.Timestamp]) -> None:
    if start > end:
        raise ValueError(
            f"Period {name!r} is reversed: it starts {start.date()} after it ends "
            f"{end.date()}."
        )
    if start < sim_min:
        raise ValueError(
            f"Period {name!r} starts {start.date()} before the simulation start "
            f"{sim_min.date()}."
        )
    if end > sim_max:
        raise ValueError(
            f"Period {name!r} ends {end.date()} after the simulation end "
            f"{sim_max.date()}."
        )
    if warmup is not None and start < warmup:
        raise ValueError(
            f"Period {name!r} starts {start.date()} inside the warm-up (warm-up "
            f"ends {warmup.date()}); start on or after the warm-up end."
        )


# ── metrics ──────────────────────────────────────────────────────────────────

def _metric_value(analysis: SWATAnalysis, name: str,
                  obs: np.ndarray, sim: np.ndarray) -> float:
    if obs.size == 0:
        return float("nan")
    func = getattr(analysis, _METRIC_METHODS[name])
    with np.errstate(all="ignore"):
        try:
            return float(func(obs, sim))
        except (ValueError, ZeroDivisionError):
            return float("nan")
