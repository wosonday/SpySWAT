"""Calibration session folder storage: write, flush and load runs, series and metrics.

``SessionStore`` is pure I/O: it knows nothing about SWAT, metric computation or
calibration algorithms. It writes a per-session folder with the following layout
(exact names)::

    <session_dir>/session.json            metadata (signature, param_names, sites, versions)
    <session_dir>/runs.csv                one row per run (run_id, ..., <params...>, score)
    <session_dir>/best.csv                parameter,value
    <session_dir>/sensitivity.csv
    <session_dir>/reach_<reach>/<variable>.csv           date,run_<id>,...
    <session_dir>/reach_<reach>/<variable>_metrics.csv   run_id,<metric>_<period>,...

Floats in ``runs.csv`` and ``*_metrics.csv`` are written with ``repr()`` (``-0.0`` is
normalised to ``0.0``, NaN is written empty) and read back with the stdlib ``csv``
module + ``float()``, so ``runs()`` returns bit-identical values. Series files use
pandas. Runs are buffered in memory and flushed in batches; a run counts as stored
only once it is in ``runs.csv``.
"""

import csv
import json
import logging
import os
import time as _time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("spyswat.swat_calib.calibration.session_store")

_MISSING = object()

_FIXED_COLUMNS = ("run_id", "time", "status", "error", "is_initial")


def _fmt_float(value):
    """repr-exact float formatting: -0.0 -> 0.0, NaN/None -> empty string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:            # NaN
        return ""
    if f == 0.0:          # normalise -0.0 to 0.0
        f = 0.0
    return repr(f)


def _parse_float(text):
    if text is None or text == "":
        return float("nan")
    return float(text)


def _parse_bool(text):
    return str(text).strip().lower() in ("true", "1", "yes")


def _run_id_from_col(col):
    if isinstance(col, str) and col.startswith("run_"):
        try:
            return int(col[4:])
        except ValueError:
            return None
    return None


def _canon(value):
    """Canonical form for signature comparison (tuples -> lists, keys sorted).

    ``default=str`` matches how ``_write_session_json()`` serialises the stored
    signature, so ``Path``/``Timestamp`` values compare equal after a re-open.
    """
    try:
        return json.loads(json.dumps(value, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return value


def _spyswat_version():
    try:
        import spyswat

        return getattr(spyswat, "__version__", None)
    except Exception:  # noqa: BLE001 - version is metadata only
        return None


class SessionStore:
    """Write, flush and load a calibration session folder."""

    def __init__(self, session_dir, *, signature, param_names, sites,
                 flush_every: int = 1, flush_seconds: float = 10.0,
                 max_columns: int = 16000, create: bool = True):
        self.session_dir = Path(session_dir)
        self.param_names = list(param_names)
        self.sites = [tuple(site) for site in sites]
        self.flush_every = int(flush_every)
        self.flush_seconds = float(flush_seconds)
        self.max_columns = int(max_columns)
        self._signature = dict(signature)

        self._runs = []                                    # list of run dicts, in run_id order
        self._series = {}                                  # {(var, reach): {run_id: pd.Series}}
        self._metrics = {}                                 # {(var, reach): {run_id: {metric: value}}}
        self._pending_best = None                          # buffered best.csv payload
        self._pending_sensitivity = None                   # buffered sensitivity.csv payload
        self._pending = 0
        self._last_flush = _time.monotonic()
        self._locked_files = set()
        self._warned = set()
        self._closed = False

        if create:
            self._create_new()

    # ------------------------------------------------------------------ create

    def _create_new(self):
        meta_path = self.session_dir / "session.json"
        if meta_path.exists():
            raise FileExistsError(f"Session already exists at {self.session_dir}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._write_session_json()

    def _write_session_json(self):
        meta = {
            "signature": self._signature,
            "param_names": list(self.param_names),
            "sites": [list(site) for site in self.sites],
            "spyswat_version": _spyswat_version(),
            "numpy_version": np.__version__,
            "max_columns": self.max_columns,
        }

        def write(tmp):
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2, sort_keys=True, default=str)

        self._commit_file(self.session_dir / "session.json", write)

    # ------------------------------------------------------------------- open

    @classmethod
    def open(cls, session_dir) -> "SessionStore":
        """Open an existing session for resume / load."""
        session_dir = Path(session_dir)
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No session at {session_dir}: session.json not found")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        store = cls(
            session_dir,
            signature=meta.get("signature", {}),
            param_names=meta.get("param_names", []),
            sites=[tuple(site) for site in meta.get("sites", [])],
            max_columns=meta.get("max_columns", 16000),
            create=False,
        )
        store._load_committed()
        return store

    def _load_committed(self):
        """Seed the in-memory state from the committed files, ignoring torn tails."""
        header, rows = self._read_csv(self.session_dir / "runs.csv")
        committed = set()
        if header:
            col = {name: i for i, name in enumerate(header)}
            for row in rows:
                run_id = int(row[col["run_id"]])
                committed.add(run_id)
                self._runs.append({
                    "run_id": run_id,
                    "time": row[col["time"]],
                    "status": row[col["status"]],
                    "error": row[col["error"]],
                    "is_initial": _parse_bool(row[col["is_initial"]]),
                    "params": {name: _parse_float(row[col[name]])
                               for name in self.param_names if name in col},
                    "score": _parse_float(row[col["score"]]),
                })
        for variable, reach in self.sites:
            self._load_site_data(variable, reach, committed)

    def _load_site_data(self, variable, reach, committed):
        site_dir = self.session_dir / f"reach_{reach}"
        series_dict = {}
        for part in self._series_part_files(site_dir, variable):
            frame = pd.read_csv(part, index_col="date", parse_dates=True)
            for col in frame.columns:
                run_id = _run_id_from_col(col)
                if run_id is not None and run_id in committed:
                    series_dict[run_id] = frame[col]
        if series_dict:
            self._series[(variable, reach)] = series_dict

        metrics_path = site_dir / f"{variable}_metrics.csv"
        header, rows = self._read_csv(metrics_path)
        if header:
            metric_map = {}
            for row in rows:
                run_id = int(row[0])
                if run_id not in committed:
                    continue
                metric_map[run_id] = {
                    name: _parse_float(row[j + 1]) for j, name in enumerate(header[1:])
                }
            if metric_map:
                self._metrics[(variable, reach)] = metric_map

    # ------------------------------------------------------------------- write

    def add_run(self, run_id, *, params, status, error, score, is_initial,
                series, site_metrics, time: str | None = None) -> None:
        if self._closed:
            raise RuntimeError("SessionStore is closed")
        run_id = int(run_id)
        run = {
            "run_id": run_id,
            "time": time if time is not None else datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "error": "" if error is None else str(error),
            "is_initial": bool(is_initial),
            "params": dict(params),
            "score": score,
        }
        self._runs.append(run)
        for (variable, reach), ser in (series or {}).items():
            self._series.setdefault((variable, reach), {})[run_id] = ser
        for (variable, reach), metrics in (site_metrics or {}).items():
            self._metrics.setdefault((variable, reach), {})[run_id] = dict(metrics)

        self._pending += 1
        if self._pending >= self.flush_every or \
                (_time.monotonic() - self._last_flush) >= self.flush_seconds:
            self.flush()

    def flush(self) -> None:
        """Write pending runs. Series and metric files first, ``runs.csv`` last.

        Buffered ``best.csv`` / ``sensitivity.csv`` payloads are retried here too, so a
        file that was locked when written is committed by the next flush or by ``close()``.
        """
        if self._closed:
            return
        self._flush_best()
        self._flush_sensitivity()
        if not self._runs:
            return
        ok = True
        for site in sorted(self._series):
            if not self._write_series_files(site):
                ok = False
        for site in sorted(self._metrics):
            if not self._write_metrics_file(site):
                ok = False
        if ok and self._write_runs_csv():
            self._pending = 0
            self._last_flush = _time.monotonic()

    def close(self) -> None:
        """Flush and mark closed. Retries once more, then raises if a file stays locked."""
        if self._closed:
            return
        self.flush()
        if self._locked_files:
            self.flush()                # one more retry for files still locked
        if self._locked_files:
            names = ", ".join(str(p) for p in sorted(self._locked_files))
            raise OSError(f"[SessionStore] Cannot write session files (still locked): {names}")
        self._closed = True

    def write_best(self, params) -> None:
        if self._closed:
            raise RuntimeError("SessionStore is closed")
        self._pending_best = dict(params)
        self._flush_best()

    def write_sensitivity(self, df: pd.DataFrame) -> None:
        if self._closed:
            raise RuntimeError("SessionStore is closed")
        self._pending_sensitivity = df.copy()
        self._flush_sensitivity()

    # ------------------------------------------------------------ flush helpers

    def _flush_best(self) -> bool:
        if self._pending_best is None:
            return True
        params = self._pending_best
        path = self.session_dir / "best.csv"

        def write(tmp):
            with open(tmp, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["parameter", "value"])
                for name in sorted(params):
                    w.writerow([name, _fmt_float(params[name])])

        if self._commit_file(path, write):
            self._pending_best = None
            return True
        return False

    def _flush_sensitivity(self) -> bool:
        if self._pending_sensitivity is None:
            return True
        path = self.session_dir / "sensitivity.csv"
        if self._commit_csv(path, self._pending_sensitivity):
            self._pending_sensitivity = None
            return True
        return False

    def _write_series_files(self, site) -> bool:
        series_dict = self._series.get(site)
        if not series_dict:
            return True
        frame = self._build_series_frame(series_dict)
        variable, reach = site
        site_dir = self.session_dir / f"reach_{reach}"
        columns = sorted(frame.columns, key=_run_id_from_col)
        ok = True
        parts = 0
        for start in range(0, len(columns), self.max_columns):
            chunk = columns[start:start + self.max_columns]
            index = start // self.max_columns
            name = f"{variable}.csv" if index == 0 else f"{variable}_part{index + 1}.csv"
            sub = frame[chunk].reset_index()          # "date" column + run columns
            if not self._commit_csv(site_dir / name, sub):
                ok = False
            parts += 1
        if ok:
            self._remove_stale_parts(site_dir, variable, parts)
        return ok

    @staticmethod
    def _remove_stale_parts(site_dir, variable, keep_parts) -> None:
        """Remove ``_part<k>.csv`` files beyond the chunks just written."""
        k = keep_parts + 1
        while True:
            stale = site_dir / f"{variable}_part{k}.csv"
            if not stale.exists():
                break
            try:
                stale.unlink()
            except OSError:
                break
            k += 1

    def _write_metrics_file(self, site) -> bool:
        metric_map = self._metrics.get(site)
        if not metric_map:
            return True
        variable, reach = site
        path = self.session_dir / f"reach_{reach}" / f"{variable}_metrics.csv"
        metric_names = sorted({m for metrics in metric_map.values() for m in metrics})
        run_ids = sorted(metric_map)
        header = ["run_id"] + metric_names

        def write(tmp):
            with open(tmp, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(header)
                for run_id in run_ids:
                    w.writerow([run_id] + [_fmt_float(metric_map[run_id].get(m))
                                           for m in metric_names])

        return self._commit_file(path, write)

    def _write_runs_csv(self) -> bool:
        path = self.session_dir / "runs.csv"
        header = list(_FIXED_COLUMNS) + list(self.param_names) + ["score"]

        def write(tmp):
            with open(tmp, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(header)
                for run in self._runs:
                    row = [run["run_id"], run["time"], run["status"], run["error"],
                           "True" if run["is_initial"] else "False"]
                    row += [_fmt_float(run["params"].get(name)) for name in self.param_names]
                    row.append(_fmt_float(run["score"]))
                    w.writerow(row)

        return self._commit_file(path, write)

    def _build_series_frame(self, series_dict) -> pd.DataFrame:
        if not series_dict:
            return pd.DataFrame()
        index = None
        for ser in series_dict.values():
            index = ser.index if index is None else index.union(ser.index)
        if index is None:
            return pd.DataFrame()
        index = index.sort_values()
        frame = pd.DataFrame(
            {f"run_{run_id}": series_dict[run_id].reindex(index)
             for run_id in sorted(series_dict)},
            index=index,
        )
        frame.index.name = "date"
        return frame

    # ------------------------------------------------------------------- read

    def runs(self) -> pd.DataFrame:
        """``runs.csv`` as a DataFrame with bit-identical floats."""
        header, rows = self._read_csv(self.session_dir / "runs.csv")
        if not header:
            return pd.DataFrame()
        col = {name: i for i, name in enumerate(header)}

        def parse(name, value):
            if name == "run_id":
                return int(value)
            if name == "is_initial":
                return _parse_bool(value)
            if name in ("time", "status", "error"):
                return value
            return _parse_float(value)        # params and score

        out = {name: [] for name in header}
        for row in rows:
            for name in header:
                out[name].append(parse(name, row[col[name]]))
        return pd.DataFrame(out)

    def series(self, variable, reach) -> pd.DataFrame:
        """Dates x run columns for one site, all parts joined."""
        site_dir = self.session_dir / f"reach_{reach}"
        frames = [pd.read_csv(part, index_col="date", parse_dates=True)
                  for part in self._series_part_files(site_dir, variable)]
        if not frames:
            return pd.DataFrame()
        frame = pd.concat(frames, axis=1)
        committed = self._committed_run_ids()
        columns = [c for c in frame.columns if _run_id_from_col(c) in committed]
        return frame[columns]

    def site_metrics(self, variable, reach) -> pd.DataFrame:
        path = self.session_dir / f"reach_{reach}" / f"{variable}_metrics.csv"
        header, rows = self._read_csv(path)
        if not header:
            return pd.DataFrame()
        committed = self._committed_run_ids()
        metric_cols = header[1:]
        out = {"run_id": []}
        for name in metric_cols:
            out[name] = []
        for row in rows:
            run_id = int(row[0])
            if run_id not in committed:
                continue
            out["run_id"].append(run_id)
            for j, name in enumerate(metric_cols):
                out[name].append(_parse_float(row[j + 1]))
        return pd.DataFrame(out)

    @property
    def signature(self) -> dict:
        return dict(self._signature)

    def check_signature(self, signature) -> None:
        """Compare the stored signature to the given one; ValueError lists differing keys."""
        given = dict(signature)
        stored = dict(self._signature)
        differing = sorted(
            key for key in set(stored) | set(given)
            if _canon(stored.get(key, _MISSING)) != _canon(given.get(key, _MISSING))
        )
        if differing:
            raise ValueError(f"Session signature mismatch for keys: {differing}")

    # ------------------------------------------------------------- internals

    def _commit_csv(self, path, df: pd.DataFrame) -> bool:
        def write(tmp):
            df.to_csv(tmp, index=False)

        return self._commit_file(path, write)

    def _commit_file(self, path, write_fn) -> bool:
        """Write ``path`` atomically (temp + os.replace); buffer on PermissionError."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        try:
            write_fn(tmp)
            os.replace(tmp, path)
        except PermissionError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._locked_files.add(path)
            self._warn_once(
                str(path),
                f"[SessionStore] Cannot write {path} ({exc}); data is buffered and "
                f"retried on the next flush.",
            )
            return False
        self._locked_files.discard(path)
        return True

    def _warn_once(self, key, message) -> None:
        if key not in self._warned:
            self._warned.add(key)
            logger.warning(message)

    def _read_csv(self, path):
        if not path.exists():
            return [], []
        with open(path, "r", newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            return [], []
        return rows[0], rows[1:]

    def _committed_run_ids(self) -> set:
        header, rows = self._read_csv(self.session_dir / "runs.csv")
        if not header:
            return set()
        i = header.index("run_id")
        return {int(row[i]) for row in rows}

    @staticmethod
    def _series_part_files(site_dir, variable):
        parts = []
        first = site_dir / f"{variable}.csv"
        if first.exists():
            parts.append(first)
        k = 2
        while True:
            part = site_dir / f"{variable}_part{k}.csv"
            if not part.exists():
                break
            parts.append(part)
            k += 1
        return parts
