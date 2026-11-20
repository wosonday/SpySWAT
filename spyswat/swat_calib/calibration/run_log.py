"""Per-run CSV results and session management for calibration runs."""

import csv
import logging
import os
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .param_spec import format_params, is_raw, param_columns


# Preserve the logger name used before this implementation was extracted.
logger = logging.getLogger("spyswat.swat_calib.calibration.calib_manager")

_UNSET = object()


class RunLog:
    """Append per-run results without interrupting a calibration on log failures."""

    MAX_PENDING_ROWS = 10_000

    def __init__(self, project):
        self.project = project
        self._results_dir = _UNSET
        self._session_base = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_n = 1
        self._session_id: str | None = None
        self._session_dir: Path | None = None
        self._session_claimed = False
        self._prev_metrics: Path | None = None
        self._run_counter = 0
        self._log_columns: Tuple[Tuple[str, ...], Tuple[str, ...]] | None = None
        self._warned: set = set()
        self._pending: Dict[Path, list] = {}     # unsaved rows per file (locked file)
        self._pending_header: Dict[Path, list] = {}
        self._log_outputs = "all"

    def _warn_once(self, key, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            logger.warning(message)

    @property
    def log_outputs(self) -> str:
        """What goes to <session>_outputs.csv: 'all' | 'observed' | 'none'."""
        return self._log_outputs

    @log_outputs.setter
    def log_outputs(self, value: str) -> None:
        if value not in ("all", "observed", "none"):
            raise ValueError(f"log_outputs must be 'all', 'observed' or 'none', got {value!r}")
        self._log_outputs = value

    @property
    def results_dir(self) -> Path | None:
        """Folder of the per-run result files (None disables logging)."""
        if self._results_dir is _UNSET:
            wf = getattr(self.project, "working_folder", _UNSET)
            if wf is _UNSET:
                self._warn_once("no-working-folder",
                                "[Results] The project has no 'working_folder' attribute, so "
                                "per-run results are not saved. Set manager.results_dir to "
                                "enable the log.")
                return None
            return Path(wf) / "calibration_results" if isinstance(wf, (str, Path)) else None
        return self._results_dir

    @results_dir.setter
    def results_dir(self, value) -> None:
        self._results_dir = None if value is None else Path(value)
        self._session_id = None
        self._session_n = 1
        self._session_claimed = False
        self._prev_metrics = None
        self._log_columns = None
        self._run_counter = 0

    def _plan_session(self) -> str | None:
        """
        Session id that WILL be used (first id with no existing result file). Touches
        nothing on disk; None when logging is disabled.
        """
        d = self.results_dir
        if d is None:
            return None
        if self._session_id is not None and self._session_dir == d:
            return self._session_id
        n = self._session_n
        while True:
            sid = self._session_base if n == 1 else f"{self._session_base}_{n}"
            if not any((d / f"{sid}_{k}.csv").exists()
                       for k in ("metrics", "outputs", "best_params", "validation")):
                break
            n += 1
        self._session_n, self._session_id, self._session_dir = n, sid, d
        self._session_claimed = False
        return sid

    def _claim_session(self) -> bool:
        """
        Create the planned session's metrics file exclusively (O_EXCL), only when its first
        row is about to be written. On a name collision the next free id is taken.
        """
        if self._plan_session() is None:
            return False
        if self._session_claimed:
            return True
        d = self._session_dir
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._warn_once(("mkdir", str(d)), f"[Results] Cannot create {d}: {exc}")
            return False
        while True:
            path = d / f"{self._session_id}_metrics.csv"
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                self._session_n += 1
                self._session_id = (self._session_base if self._session_n == 1
                                    else f"{self._session_base}_{self._session_n}")
            except OSError as exc:
                self._warn_once(("create", str(path)), f"[Results] Cannot create {path}: {exc}")
                return False
        self._session_claimed = True
        self._run_counter = 0
        prev = self._prev_metrics
        logger.info(
            f"[Results] Per-run results are appended to {path} and "
            f"{d / (self._session_id + '_outputs.csv')}"
            + (f" (columns changed; previous session: {prev})" if prev else "")
        )
        self._prev_metrics = path
        return True

    def session_path(self, suffix: str) -> Path | None:
        """Path ``<results_dir>/<session>_<suffix>.csv`` that will be used (nothing is created)."""
        sid = self._plan_session()
        return None if sid is None else self._session_dir / f"{sid}_{suffix}.csv"

    @property
    def session_files(self) -> dict:
        """{'metrics': Path, 'outputs': Path} of the current session ({} when disabled)."""
        if self._plan_session() is None:
            return {}
        return {"metrics": self.session_path("metrics"), "outputs": self.session_path("outputs")}

    def _append_csv(self, path: Path, header: list, rows: list) -> bool:
        """
        Append rows (header on creation). Rows that cannot be written (file locked) are
        buffered and written together with the next successful append / flush_log().
        Never raises.
        """
        try:
            combined = self._pending.get(path, []) + list(rows)
            if not combined:
                return True
            last: Exception | None = None
            for attempt in range(4):
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    new = (not path.exists()) or path.stat().st_size == 0
                    with open(path, "a", newline="", encoding="utf-8") as fh:
                        w = csv.writer(fh)
                        if new:
                            w.writerow(header)
                        w.writerows(combined)
                        fh.flush()
                    self._pending.pop(path, None)
                    self._pending_header.pop(path, None)
                    return True
                except PermissionError as exc:      # e.g. file open in Excel
                    last = exc
                    time.sleep(0.2 * (attempt + 1))
                except OSError as exc:
                    last = exc
                    break
            if len(combined) > self.MAX_PENDING_ROWS:
                self._warn_once(("drop", str(path)),
                                f"[Results] Too many unsaved rows for {path}; dropping the oldest.")
                combined = combined[-self.MAX_PENDING_ROWS:]
            self._pending[path] = combined
            self._pending_header[path] = header
            self._warn_once(("write", str(path)),
                            f"[Results] Cannot write {path} ({last}); rows are kept in memory "
                            f"and written at the next successful append (or flush_log()). "
                            f"Calibration continues.")
            return False
        except Exception as exc:  # noqa: BLE001
            self._warn_once(("append", str(path), str(exc)), f"[Results] Log error for {path}: {exc}")
            return False

    def flush_log(self) -> bool:
        """Try to write rows buffered while a log file was locked. True if nothing is left."""
        ok = True
        for path in list(self._pending):
            ok = self._append_csv(path, self._pending_header.get(path, []), []) and ok
        return ok

    @staticmethod
    def _fmt(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        return "nan" if np.isnan(f) else repr(f)

    @staticmethod
    def _g(v):
        try:
            return "%.6g" % float(v)
        except (TypeError, ValueError):
            return v

    def _logged_metric_names(self) -> List[str] | None:
        return list(self._log_columns[1]) if self._log_columns else None

    def _record_run(self, params, scores, *, status="ok", error=None, sim=None,
                    mode="sequential", reach_id=None, output_variable=None,
                    obs_index=None) -> None:
        try:
            # 1. validate the record BEFORE any session/column decision
            if not isinstance(params, Mapping):
                raise TypeError(f"params must be a mapping, got {type(params).__name__}")
            if scores is not None and not isinstance(scores, Mapping):
                raise TypeError(f"scores must be a mapping or None, got {type(scores).__name__}")
            if status not in ("ok", "failed"):
                raise ValueError(f"status must be 'ok' or 'failed', got {status!r}")
            if sim is not None and not hasattr(sim, "items"):
                raise TypeError(f"sim must be a pandas Series or None, got {type(sim).__name__}")
            if self._plan_session() is None:
                return
            formatted = format_params(params) if (params and is_raw(params)) else params
            pcols = param_columns(formatted)
            mnames = list(scores) if scores else (self._logged_metric_names() or [])

            # 2. column set: unchanged / first / changed (new session, created lazily)
            if self._log_columns is None:
                self._log_columns = (tuple(pcols), tuple(mnames))
            elif (set(self._log_columns[0]) != set(pcols)
                  or set(self._log_columns[1]) != set(mnames)):
                self._log_columns = (tuple(pcols), tuple(mnames))
                if self._session_claimed:               # rows already written: switch session
                    self._session_n += 1
                    self._session_id = None
                    self._session_claimed = False
                    self._plan_session()
            if not self._claim_session():
                return
            pnames, metric_cols = self._log_columns
            self._run_counter += 1
            run_id = self._run_counter
            header = (["run_id", "time", "mode", "status", "error", "reach_id", "output_variable"]
                      + list(pnames) + [f"{n}__method" for n in pnames]
                      + [f"{n}__spec" for n in pnames] + list(metric_cols))
            row = [run_id, datetime.now().isoformat(timespec="seconds"), mode, status,
                   "" if error is None else str(error),
                   "" if reach_id is None else reach_id,
                   "" if output_variable is None else output_variable]
            row += ([self._fmt(pcols[n][0]) for n in pnames]
                    + [pcols[n][1] for n in pnames] + [pcols[n][2] for n in pnames])
            row += [self._fmt((scores or {}).get(m, np.nan)) for m in metric_cols]
            self._append_csv(self.session_path("metrics"), header, [row])

            if status == "ok" and sim is not None and self._log_outputs != "none":
                series = sim
                if self._log_outputs == "observed" and obs_index is not None:
                    series = sim.loc[sim.index.intersection(obs_index)]
                rows = [[run_id, pd.Timestamp(d).date().isoformat(),
                         "" if output_variable is None else output_variable,
                         "" if reach_id is None else reach_id, self._g(v)]
                        for d, v in series.items()]
                self._append_csv(self.session_path("outputs"),
                                 ["run_id", "date", "variable", "reach", "value"], rows)
        except Exception as exc:  # noqa: BLE001 - the log must never break a calibration
            self._warn_once(("record", type(exc).__name__, str(exc)),
                            f"[Results] Run not logged: {type(exc).__name__}: {exc}")
