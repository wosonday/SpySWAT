"""``CalibrationResult`` — the value returned by ``SWATProject.calibration``.

A result ties the algorithm's best parameters to the runs and series stored in
its session folder. The object is thin: the per-run data lives in the
``SessionStore`` (``runs.csv``, the per-site series and metric files); the result
only holds the metadata eagerly and reads series lazily through
``SessionStore.series``.

Dict-style access keeps old callers working::

    res["best_params"]   # {name: [(value, method, [subbasins])]}
    res["best_score"]    # float
    res["history"]       # == res.runs (DataFrame)

``top(n)`` and ``select(**conditions)`` return ``ParamSet`` objects named
``run_<id>`` carrying the parameters, methods and subbasins, ready to feed into
``SWATProject.scenarios`` / ``SWATProject.apply``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from spyswat.swat_calib.analysis.statistics import best_index, to_objective
from spyswat.swat_calib.calibration.param_spec import format_params
from spyswat.swat_calib.calibration.session_store import SessionStore
from spyswat.swat_calib.scenarios.model import ParamSet

_FIXED_COLS = ("run_id", "time", "status", "error", "is_initial", "score")

_OPERATORS = {
    "gt": lambda a, t: a > t,
    "gte": lambda a, t: a >= t,
    "lt": lambda a, t: a < t,
    "lte": lambda a, t: a <= t,
}


def raw_params(formatted: dict) -> dict:
    """Convert formatted params ``{name: [(value, method, ...)]}`` to raw floats.

    ``runs.csv`` stores repr-exact floats (decision 9), so the session store needs
    raw ``{name: value}`` even though the manager hands it the formatted dict it
    applies to TxtInOut. Only the first pass of each parameter is kept (a single
    value per parameter per run).
    """
    out = {}
    for name, groups in formatted.items():
        if isinstance(groups, tuple):
            groups = [groups]
        if isinstance(groups, (list, tuple)) and len(groups) and isinstance(groups[0], (list, tuple)):
            out[name] = groups[0][0]
        else:
            out[name] = groups
    return out


class RawParamsStore:
    """Duck-typed ``SessionStore`` adapter that stores raw floats.

    ``CalibrationManager`` passes the *formatted* parameter dict (with method and
    subbasin metadata) to ``store.add_run``. ``runs.csv`` must store plain
    repr-exact floats, so this adapter converts on the way in and delegates
    everything else (``write_best``, ``write_sensitivity``, ``flush``, ``close``,
    ``runs``, ``series``, ...) to the wrapped store.
    """

    def __init__(self, store):
        self._store = store

    def add_run(self, run_id, *, params, status, error, score, is_initial,
                series, site_metrics, time=None):
        self._store.add_run(
            run_id, params=raw_params(params), status=status, error=error,
            score=score, is_initial=is_initial, series=series,
            site_metrics=site_metrics, time=time,
        )

    def __getattr__(self, name):
        return getattr(self._store, name)


def best_run(runs: pd.DataFrame, metric: str):
    """``(run_id, score)`` of the best run by the registry direction of ``metric``.

    Failed runs (NaN score) rank worst; an all-failed ``runs`` raises RuntimeError.
    """
    if "score" not in runs.columns:
        raise ValueError("runs has no 'score' column")
    pos = best_index(runs["score"], metric)
    if "run_id" in runs.columns:
        run_id = int(runs["run_id"].iloc[pos])
    else:
        run_id = int(pos) + 1
    return run_id, float(runs["score"].iloc[pos])


def raw_params_for_run(runs: pd.DataFrame, run_id: int) -> dict:
    """The raw ``{name: float}`` parameters of one run (non-metadata columns)."""
    names = [c for c in runs.columns if c not in _FIXED_COLS]
    row = runs[runs["run_id"] == run_id]
    if row.empty:
        raise ValueError(f"run {run_id!r} not found in runs")
    return {name: float(row[name].iloc[0]) for name in names}


def evaluate_best_metrics(store, observed_dict, observed_sites, best_run_id, *,
                          calib_period, valid_period, metrics, freq, step, agg,
                          warmup_end) -> pd.DataFrame | None:
    """``EvaluationResult.table`` of the best run (calib + valid periods)."""
    from spyswat.swat_calib.analysis.evaluate import evaluate
    from spyswat.swat_calib.calibration.scoring import _whole_overlap

    sim = {}
    for (variable, reach) in observed_sites:
        frame = store.series(variable, reach)
        col = f"run_{best_run_id}"
        if col in frame.columns:
            sim[(variable, reach)] = frame[col]
    if not sim:
        return None

    periods = {}
    if calib_period is not None:
        periods["calib"] = calib_period
    elif valid_period is not None:
        periods["calib"] = _whole_overlap(sim, observed_dict, warmup_end)
    if valid_period is not None:
        periods["valid"] = valid_period

    return evaluate(
        sim, observed_dict, periods=periods or None, metrics=metrics,
        freq=freq, step=step, agg=agg, warmup_end=warmup_end,
    ).table


def regression_for_store(store, param_ranges) -> pd.DataFrame:
    """OLS regression sensitivity on the ``is_initial`` rows of a session.

    Raises the same ``ValueError`` cases as ``regression_sensitivity`` (too few
    usable rows, a constant parameter, a missing column); the facade turns those
    into ``sensitivity_status``.
    """
    from spyswat.swat_calib.analysis.regression_sensitivity import regression_sensitivity

    runs = store.runs()
    if "is_initial" in runs.columns:
        runs = runs[runs["is_initial"].astype(bool)]
    return regression_sensitivity(runs, param_ranges, score_col="score")


class CalibrationResult:
    """The result of a ``SWATProject.calibration(...)`` call.

    Parameters are keyword-only. ``runs`` is the ``runs.csv`` DataFrame (one row
    per run: run_id, time, status, error, is_initial, the raw parameters and the
    aggregated ``score``). ``store`` is kept (a closed ``SessionStore``) so series
    and per-site metrics stay reachable lazily.
    """

    def __init__(self, *, best_params, best_score, best_run_id, metric, runs,
                 metrics=None, sensitivity=None, sensitivity_status="",
                 session_dir, seed=None, algorithm=None, methods=None,
                 subbasins=None, sites=None, store=None):
        self.best_params = dict(best_params)
        self.best_score = best_score
        self.best_run_id = best_run_id
        self.metric = metric
        self.runs = runs
        self.metrics = metrics
        self.sensitivity = sensitivity
        self.sensitivity_status = sensitivity_status
        self.session_dir = Path(session_dir)
        self.seed = seed
        self.algorithm = algorithm
        self.methods = dict(methods or {})
        self.subbasins = dict(subbasins or {})
        self._sites = [tuple(s) for s in (sites or [])]
        self._store = store

    # ── dict-style access (backward compatibility) ──────────────────────────

    def __getitem__(self, key):
        if key == "history":
            return self.runs
        if key in ("best_params", "best_score"):
            return getattr(self, key)
        raise KeyError(key)

    def __repr__(self):
        return (f"CalibrationResult(algorithm={self.algorithm!r}, metric={self.metric!r}, "
                f"best_score={self.best_score!r}, runs={len(self.runs)}, "
                f"session_dir={str(self.session_dir)!r})")

    # ── lazy series / per-site metrics ──────────────────────────────────────

    def series(self, variable, reach) -> pd.DataFrame:
        """The stored simulated series (dates x run columns) of one site."""
        if self._store is None:
            raise RuntimeError("no session store attached; series are only available "
                               "from a calibration session")
        return self._store.series(variable, reach)

    def site_metrics(self, variable, reach) -> pd.DataFrame:
        """The per-site metric rows (run_id + <metric>_<period> columns)."""
        if self._store is None:
            raise RuntimeError("no session store attached")
        return self._store.site_metrics(variable, reach)

    # ── parameter-set extraction ────────────────────────────────────────────

    def best_param_set(self) -> ParamSet:
        """The best parameters as a ``ParamSet`` named ``run_<best_run_id>``."""
        return ParamSet(f"run_{self.best_run_id}", dict(self.best_params))

    def top(self, n: int):
        """The ``n`` best runs as ``ParamSet`` objects, best first.

        Failed / NaN runs are dropped before ranking (registry direction of
        ``self.metric``), so the returned list never contains a failed run.
        """
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError(f"n must be a non-negative integer, got {n!r}")
        return [self._param_set(run_id) for run_id in self._ranked_run_ids()[:n]]

    def select(self, **conditions):
        """Runs matching the given conditions as ``ParamSet`` objects.

        Conditions are ``<metric>__<op>=threshold`` with ``op`` in
        ``gt/gte/lt/lte``, e.g. ``select(score__gt=0.5)`` or
        ``select(nse__gt=0.5, site=("FLOW_OUTcms", 1), period="calib")``. The
        ``score`` condition uses the aggregated objective; any other metric uses
        the per-site metric of ``period`` (default ``"calib"``). With no ``site``
        the condition applies to every calibrated site and ``how`` (default
        ``"all"``) selects whether all or any site must satisfy it.
        """
        site = conditions.pop("site", None)
        period = conditions.pop("period", "calib")
        how = conditions.pop("how", "all")
        if how not in ("all", "any"):
            raise ValueError(f"how must be 'all' or 'any', got {how!r}")
        if period not in ("calib", "valid"):
            raise ValueError(f"period must be 'calib' or 'valid', got {period!r}")
        if site is not None and (not isinstance(site, tuple) or len(site) != 2):
            raise ValueError(f"site must be a (variable, reach) tuple, got {site!r}")
        if not conditions:
            raise ValueError("select() needs at least one condition, e.g. select(score__gt=0.5)")

        runs = self.runs
        if "run_id" not in runs.columns or "score" not in runs.columns:
            raise ValueError("runs needs 'run_id' and 'score' columns")
        keep = np.ones(len(runs), dtype=bool)
        for key, threshold in conditions.items():
            name, op = _split_condition(key)
            keep = keep & self._condition_mask(name, op, threshold, site, period, how)
        return [self._param_set(int(rid)) for rid in runs.loc[keep, "run_id"]]

    # ── internals ───────────────────────────────────────────────────────────

    def _ranked_run_ids(self):
        runs = self.runs
        if "run_id" not in runs.columns or "score" not in runs.columns:
            raise ValueError("runs needs 'run_id' and 'score' columns")
        scores = runs["score"].to_numpy(dtype=float)
        ok = np.isfinite(scores)
        if "status" in runs.columns:
            ok = ok & (runs["status"].to_numpy() == "ok")
        idx = np.where(ok)[0]
        if idx.size == 0:
            return []
        objective = np.asarray(to_objective(self.metric, scores[idx]), dtype=float)
        order = np.argsort(objective, kind="stable")
        return [int(runs["run_id"].iloc[i]) for i in idx[order]]

    def _param_set(self, run_id) -> ParamSet:
        raw = raw_params_for_run(self.runs, run_id)
        return ParamSet(f"run_{run_id}", format_params(raw, self.methods, self.subbasins))

    def _condition_mask(self, name, op, threshold, site, period, how):
        if name == "score":
            return _OPERATORS[op](self.runs["score"].to_numpy(dtype=float), threshold)
        if site is not None:
            return _OPERATORS[op](self._site_metric_values(name, period, site), threshold)
        if not self._sites:
            raise ValueError("no calibrated sites known; pass site=(variable, reach)")
        masks = [_OPERATORS[op](self._site_metric_values(name, period, s), threshold)
                 for s in self._sites]
        result = masks[0].copy()
        for m in masks[1:]:
            result = result & m if how == "all" else result | m
        return result

    def _site_metric_values(self, name, period, site):
        """Per-run values of ``name`` at ``site`` for ``period``, aligned to ``runs``."""
        runs = self.runs
        values = np.full(len(runs), np.nan)
        if self._store is not None:
            variable, reach = site
            df = self._store.site_metrics(variable, reach)
            col = f"{name}_{period}"
            if not df.empty and col in df.columns:
                by_id = dict(zip(df["run_id"].tolist(), df[col].tolist()))
                for i, rid in enumerate(runs["run_id"].tolist()):
                    if rid in by_id:
                        values[i] = by_id[rid]
        # Runs carry the calibration-period per-site columns as a fallback.
        fallback = f"{name}@{site[0]}@{site[1]}"
        if fallback in runs.columns:
            vals = runs[fallback].to_numpy(dtype=float)
            values[~np.isnan(vals)] = vals[~np.isnan(vals)]
        return values

    # ── load ────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, session_dir) -> "CalibrationResult":
        """Open a session folder: metadata eager, series lazy.

        ``best_params``, ``best_score``, ``best_run_id`` and ``runs`` are read from
        ``session.json`` / ``runs.csv``; ``sensitivity`` is read from
        ``sensitivity.csv`` when present. The simulated series are *not* loaded —
        use ``series(variable, reach)``.
        """
        store = SessionStore.open(session_dir)
        sig = store.signature or {}
        metric = sig.get("metric", "nse")
        runs = store.runs()
        if runs.empty:
            raise ValueError(f"no runs recorded in session {session_dir}")
        run_id, score = best_run(runs, metric)
        methods = sig.get("methods") or {}
        subbasins = sig.get("subbasins") or {}
        best_params = format_params(raw_params_for_run(runs, run_id), methods, subbasins)

        sensitivity = None
        sens_path = Path(session_dir) / "sensitivity.csv"
        if sens_path.exists():
            try:
                sensitivity = pd.read_csv(sens_path)
            except Exception:  # noqa: BLE001 - unreadable sensitivity is not fatal
                sensitivity = None

        sites = [tuple(s) for s in sig.get("observed_sites", [])]
        return cls(
            best_params=best_params, best_score=score, best_run_id=run_id,
            metric=metric, runs=runs, metrics=None, sensitivity=sensitivity,
            sensitivity_status="", session_dir=Path(session_dir),
            seed=sig.get("seed"), algorithm=sig.get("algorithm"),
            methods=methods, subbasins=subbasins, sites=sites, store=store,
        )


def _split_condition(key):
    if not isinstance(key, str) or "__" not in key:
        raise ValueError(f"condition {key!r} must look like '<metric>__<op>' (e.g. 'nse__gt')")
    name, op = key.rsplit("__", 1)
    if op not in _OPERATORS:
        raise ValueError(f"unknown operator {op!r} in {key!r}; use one of {sorted(_OPERATORS)}")
    return name, op
