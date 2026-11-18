# spyswat/calibration/manager.py
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import csv
import os
from collections.abc import Mapping
import time
import shutil, tempfile
import logging
from datetime import datetime
from pathlib import Path

from spyswat.swat_calib.core.workingFolder_manager import (
    _copy_over, _stamp_output_rch, _check_fresh_output_rch, _param_exts, _baseline_files,
)

from spyswat.logger import Logger

logger = logging.getLogger(__name__)

_UNSET = object()


def check_observation_step(obs_index: pd.DatetimeIndex, sim_freq: str) -> None:
    """
    Raise ValueError unless the observation step matches the simulation print step.

    Observations count as monthly when every timestamp is the first day of a month at
    midnight and no two timestamps fall in the same month; otherwise they count as
    daily (gaps are fine; pd.infer_freq is deliberately not used). A single observation
    is always accepted. Observations are never resampled: aggregate them to the model's
    print step (IPRINT in file.cio) before calibrating.
    """
    if sim_freq not in ('D', 'MS'):
        raise ValueError(
            f"Unsupported simulation frequency {sim_freq!r}: only daily ('D') and "
            f"monthly ('MS') print steps are supported."
        )
    idx = pd.DatetimeIndex(obs_index)
    if len(idx) <= 1:
        return
    monthly = bool(
        (idx.day == 1).all()
        and (idx == idx.normalize()).all()
        and not idx.to_period('M').duplicated().any()
    )
    if monthly and sim_freq == 'D':
        raise ValueError(
            "Observations are monthly but the simulation prints daily output (IPRINT in "
            "file.cio). Aggregate the observations to the model's print step first, or "
            "change IPRINT."
        )
    if (not monthly and sim_freq == 'MS' and bool(idx.is_month_end.all())
            and not idx.to_period('M').duplicated().any()):
        raise ValueError(
            "Observations look monthly but are dated at the END of each month (pandas "
            "resample('M') default). Monthly observations must be dated on the 1st of the "
            "month: use obs.index = obs.index.to_period('M').to_timestamp()."
        )
    if not monthly and sim_freq == 'MS':
        raise ValueError(
            "Observations are daily but the simulation prints monthly output (IPRINT in "
            "file.cio). Aggregate the observations to the model's print step first "
            "(e.g. monthly means for flow), or change IPRINT."
        )


class CalibrationManager:
    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None
        # per-run result log (see _log_run)
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

    # ── Per-run result log ───────────────────────────────────────────
    #
    # Every run (sequential, parallel, validation, or reported through record_run)
    # is appended to <session>_metrics.csv / <session>_outputs.csv. Nothing here
    # may raise into the calibration: problems are logged once as WARNING.

    _MAX_PENDING_ROWS = 10_000

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
            if len(combined) > self._MAX_PENDING_ROWS:
                self._warn_once(("drop", str(path)),
                                f"[Results] Too many unsaved rows for {path}; dropping the oldest.")
                combined = combined[-self._MAX_PENDING_ROWS:]
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

    @staticmethod
    def _param_columns(params: dict) -> Dict[str, tuple]:
        """{name: (first value, first method, full spec text)} of every formatted parameter."""
        out = {}
        for name, groups in (params or {}).items():
            if isinstance(groups, tuple):
                groups = [groups]
            parts = []
            for g in groups:
                subs = g[2] if len(g) > 2 else None
                subs_txt = ("All" if subs is None or subs == "All" else
                            ",".join(str(x) for x in (subs if isinstance(subs, (list, tuple, set))
                                                      else [subs])))
                parts.append(f"{format(float(g[0]), '.10g')}:{g[1] if len(g) > 1 else 'v'}:{subs_txt}")
            first = groups[0]
            out[name] = (first[0], first[1] if len(first) > 1 else "v", "|".join(parts))
        return out

    def _logged_metric_names(self) -> List[str] | None:
        return list(self._log_columns[1]) if self._log_columns else None

    def record_run(self, params: dict, scores: dict | None, *, status: str = "ok",
                   error: str | None = None, sim: "pd.Series | None" = None,
                   mode: str = "sequential", reach_id=None,
                   output_variable: str | None = None) -> None:
        """
        Append one run to the per-run log. Public hook for algorithms that run SWAT
        outside run_iteration/run_batch (GLUE uncertainty runs, sensitivity analysis).

        Args:
            params: raw {name: float} or formatted {name: [(value, method[, subs]), ...]}.
            scores: {metric: value} (None for a failed run: NaN in the metric columns).
            sim:    simulated target series already indexed by date (None = no output rows;
                    only written for status 'ok').
        A change of the parameter/metric column set starts a new session. Never raises.
        """
        self._record_run(params, scores, status=status, error=error, sim=sim, mode=mode,
                         reach_id=reach_id, output_variable=output_variable)

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
            formatted = self._format_params(params) if (params and self._is_raw(params)) else params
            pcols = self._param_columns(formatted)
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

    # ── Unified param_ranges parser ──────────────────────────────────

    @staticmethod
    def _parse_spec(param_ranges: dict) -> Tuple[dict, dict, dict]:
        """
        Parse unified param_ranges into (bounds, methods, subbasins).

        Supported formats (can mix freely in same dict):
            "CN2.mgt": (60, 98)                        # old format -- bounds only
            "CN2.mgt": ((60, 98), "r")                 # bounds + method
            "CN2.mgt": ((60, 98), "r", [71, 45, 70])  # bounds + method + subbasins
        """
        bounds, methods, subbasins = {}, {}, {}
        for name, spec in param_ranges.items():
            if isinstance(spec[0], (int, float)):
                # Old format: (min, max)
                if len(spec) > 2:
                    raise ValueError(
                        f"Parameter '{name}': old format (min, max) accepts exactly 2 values, "
                        f"got {len(spec)}. Use new format: ((min, max), method, subbasins)."
                    )
                bounds[name] = (float(spec[0]), float(spec[1]))
            else:
                # New format: ((min, max), method?, subbasins?)
                bounds[name] = (float(spec[0][0]), float(spec[0][1]))
                if len(spec) >= 2 and spec[1] is not None:
                    methods[name] = spec[1]
                if len(spec) >= 3 and spec[2] is not None:
                    subbasins[name] = spec[2]
        return bounds, methods, subbasins

    def _format_params(self, raw: dict,
                       methods: dict = None, subbasins: dict = None) -> dict:
        """Convert {name: float} -> {name: [(val, method, [subs])]}."""
        _m = methods   or {}
        _s = subbasins or {}
        out = {}
        for name, val in raw.items():
            method = _m.get(name, "v")
            subs   = _s.get(name)
            out[name] = [(float(val), method, subs)] if subs is not None else [(float(val), method)]
        return out

    @staticmethod
    def _is_raw(param_dict: dict) -> bool:
        """True if {name: float}, False if already formatted {name: [tuple]}."""
        for v in param_dict.values():
            return isinstance(v, (int, float))
        return True

    # ── Core run methods ─────────────────────────────────────────────

    def run_iteration(self, param_dict, observed, metric=None,
                      reach_id=1, output_variable='FLOW_OUTcms',
                      methods=None, subbasins=None) -> float:
        formatted = self._format_params(param_dict, methods, subbasins) if self._is_raw(param_dict) else param_dict
        self._backup_state()
        err: Exception | None = None
        score = None
        sim_dated = None
        try:
            self.project.HRU.update_params(formatted)

            out_dir = self._txinout_dir()
            before = _stamp_output_rch(out_dir) if out_dir is not None else None
            self.project.run()
            if out_dir is not None:
                _check_fresh_output_rch(out_dir, before)

            sim = self.project.Output.read_rch(
                columns=['RCH', 'MON', output_variable],
                reach_id=reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]
            if self.results_dir is not None:
                sim_dated = self._to_model_dates(sim, self._sim_freq(observed))
        except Exception as e:
            err = e
        except BaseException:
            try:
                self._restore_state()
            except Exception as restore_err:
                logger.error(f"Restore after interruption failed: {restore_err}")
            raise

        # Save this run before anything else can go wrong (restore, next run).
        self._record_run(formatted,
                         {metric: np.nan} if err is not None else {metric: score},
                         status="failed" if err is not None else "ok", error=err,
                         sim=sim_dated, mode="sequential", reach_id=reach_id,
                         output_variable=output_variable, obs_index=observed.index)

        # Always restore baseline inputs so that relative-change methods ('r', 'a')
        # start from the original parameter values on the next iteration.
        try:
            self._restore_state()
        except Exception as restore_err:
            if err is not None:
                raise RuntimeError(
                    f"Iteration failed: {err}; additionally the input files could not be "
                    f"restored: {restore_err}"
                ) from err
            raise
        if err is not None:
            raise RuntimeError(f"Iteration failed: {err}") from err
        return score

    def _txinout_dir(self) -> Path | None:
        """The project's TxtInOut directory as a Path (None if it cannot be resolved)."""
        try:
            return Path(self.project.txinout.directory)
        except TypeError:
            return None

    def _input_files(self) -> List[Path]:
        """file.cio + every input file of all extensions in the parameter file."""
        tx = self.project.txinout
        directory = Path(tx.directory)
        files: List[Path] = []
        cio = directory / "file.cio"
        if cio.exists():
            files.append(cio)
        param_file = getattr(self.project, "param_file", None)
        if param_file is not None:
            exts = _param_exts(str(param_file.param_path))
            files.extend(_baseline_files(tx, exts))
        seen, out = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def _backup_state(self):
        """Back up only the input files that calibration can modify (never outputs)."""
        if self._backup_dir is not None:
            # A previous restore failed: finish it first, never overwrite that backup.
            try:
                self._restore_state()
            except RuntimeError as exc:
                raise RuntimeError(
                    f"Cannot take a new backup: the original input files are still kept "
                    f"unrestored in {self._backup_dir}. Close whatever locks the TxtInOut "
                    f"files, then retry (or copy that folder's files back by hand). {exc}"
                ) from exc
        backup = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        try:
            for f in self._input_files():
                shutil.copyfile(f, backup / f.name)
        except Exception:
            shutil.rmtree(backup, ignore_errors=True)
            raise
        self._backup_dir = backup

    def _restore_state(self):
        """
        Copy the backed-up input files back; the TxtInOut folder itself is never removed.

        The backup is deleted only after EVERY file was copied back. If any copy fails the
        backup is kept (its path is logged and named in the RuntimeError) so the next
        ``_backup_state`` / ``_restore_state`` can finish the job.
        """
        if self._backup_dir is None:
            return
        backup = self._backup_dir
        dst_dir = Path(self.project.txinout.directory)
        failed = []
        for f in sorted(backup.iterdir()):
            try:
                _copy_over(f, dst_dir / f.name)
            except Exception as exc:
                failed.append((f.name, exc))
        if failed:
            logger.error(
                f"Could not restore {len(failed)} input file(s) ({failed[0][0]}: "
                f"{failed[0][1]}); backup kept in {backup}"
            )
            raise RuntimeError(
                f"Could not restore {len(failed)} input file(s) in {dst_dir} "
                f"(first: {failed[0][0]}: {failed[0][1]}). The backup is kept in {backup}."
            ) from failed[0][1]
        shutil.rmtree(backup, ignore_errors=True)
        self._backup_dir = None

    def setup_parallel(self, overwrite: bool = False) -> None:
        """Create worker directories for parallel execution."""
        self.project.WorkingFolder.setup(overwrite=overwrite)
        logger.info(
            f"Parallel setup: {self.project.WorkingFolder.n_parallel} workers at "
            f"{self.project.WorkingFolder.working_dir}"
        )

    def run_batch(self, param_sets, observed, metrics=None,
                  reach_id=1, output_variable='FLOW_OUTcms',
                  methods=None, subbasins=None) -> pd.DataFrame:
        """
        Return DataFrame. param_sets can be list of {name: float} (raw) or
        {name: [(val, method, ...)]} (pre-formatted) -- both are accepted.

        Logging
        ───────
        Progress is written to both tqdm (visual) and logger.info (file/console)
        at every chunk boundary so runs are inspectable in the log file.

        Worker log records are routed through a multiprocessing.Queue so
        multiple subprocesses never write to the log file simultaneously.
        """
        if metrics is None:
            metrics = ['nse', 'kge', 'r2', 'rmse', 'pbias']
        elif isinstance(metrics, str):
            metrics = [metrics]

        formatted_sets = [
            self._format_params(p, methods, subbasins) if self._is_raw(p) else p
            for p in param_sets
        ]

        total       = len(formatted_sets)
        wf          = self.project.WorkingFolder
        n_workers   = wf.n_parallel
        total_batches = (total + n_workers - 1) // n_workers

        try:
            from tqdm import tqdm
            pbar = tqdm(total=total, desc="SWAT runs", unit="run")
        except ImportError:
            pbar = None

        # ── start queue listener so workers log through the queue ──────
        log_queue = Logger.init_queue_listener()
        logger.info(
            f"[run_batch] Starting — {total} runs, "
            f"{n_workers} workers, {total_batches} batches"
        )

        all_rows = []
        try:
            for chunk_start in range(0, total, n_workers):
                batch_num = chunk_start // n_workers + 1
                chunk     = formatted_sets[chunk_start: chunk_start + n_workers]

                results = wf.run_parallel(
                    self.project.swat_exe.swat_exe_path,
                    param_sets=chunk,
                    log_queue=log_queue,
                )

                # ── read outputs (rows stay in input order) ────────────
                batch_scores = []
                for j, res in enumerate(results):
                    row = {m: np.nan for m in metrics}
                    run_error = None
                    sim_dated = None
                    if not res.ok:
                        run_error = res.error
                        logger.error(f"[run_batch] Run {chunk_start + j + 1} failed "
                                     f"(worker {j+1}): {res.error}")
                    else:
                        try:
                            w_proj = self.project.worker(j + 1)
                            sim = w_proj.Output.read_rch(
                                columns=['RCH', 'MON', output_variable],
                                reach_id=reach_id
                            )[output_variable]
                            obs_a, sim_a = self._align_series(observed, sim)
                            scores = w_proj.Statistic.calculate_statistics(
                                obs_a, sim_a, metrics=metrics
                            )
                            for m in metrics:
                                row[m] = scores.get(m, np.nan)
                            if self.results_dir is not None:
                                sim_dated = self._to_model_dates(sim, self._sim_freq(observed))
                        except Exception as e:
                            run_error = f"output unreadable: {e}"
                            row = {m: np.nan for m in metrics}
                            logger.warning(
                                f"[run_batch] Run {chunk_start + j + 1} (worker {j+1}) "
                                f"output unreadable: {e}"
                            )
                    batch_scores.append(row)
                    all_rows.append(row)
                    # save every run immediately (before the next job/batch)
                    self._record_run(chunk[j], row, status="ok" if run_error is None else "failed",
                                     error=run_error, sim=sim_dated, mode="parallel",
                                     reach_id=reach_id, output_variable=output_variable,
                                     obs_index=observed.index)

                # ── progress: tqdm + logger ────────────────────────────
                done = chunk_start + len(chunk)
                last = batch_scores[-1] if batch_scores else {}
                score_summary = "  ".join(
                    f"{m}={last[m]:.3f}" for m in metrics if m in last
                )
                logger.info(
                    f"[Batch {batch_num}/{total_batches}] "
                    f"{done}/{total} runs ({done/total:.0%})  |  {score_summary}"
                )
                if pbar is not None:
                    pbar.update(len(chunk))

        finally:
            if pbar is not None:
                pbar.close()
            Logger.stop_listener()
            self.flush_log()

        logger.info(f"[run_batch] Done — {total} runs complete")
        return pd.DataFrame(all_rows, columns=metrics)

    _FREQ_LEVEL = {'D': 0, 'MS': 1, 'YS': 2}  # IPRINT values accepted from file.cio

    def _sim_freq(self, obs: pd.Series | None = None) -> str:
        """Simulation output frequency from IPRINT in file.cio (contract C4)."""
        freq = self.project.FileCIO.get_iprint()
        if not isinstance(freq, str):
            # Duck-typed / mocked project without a real FileCIO: infer from the observations.
            inferred = pd.infer_freq(obs.index) if obs is not None and len(obs) >= 3 else None
            return 'MS' if (inferred and inferred.upper().startswith(('M', 'Q', 'A', 'Y'))) else 'D'
        if freq not in self._FREQ_LEVEL:
            raise ValueError(f"Unsupported simulation frequency {freq!r} from file.cio")
        return freq

    def _to_model_dates(self, sim: pd.Series, freq: str) -> pd.Series:
        """Return ``sim`` indexed by the model's own date range (ValueError on length mismatch)."""
        date_range = self.project.get_date_range(freq=freq)
        sim = sim.reset_index(drop=True)
        if len(sim) != len(date_range):
            raise ValueError(
                f"Simulated series has {len(sim)} values but the simulation period "
                f"(file.cio, freq={freq}) has {len(date_range)} expected values. "
                f"Partial-year runs (IDAF/IDAL) are not supported."
            )
        sim.index = date_range
        return sim

    def _align_series(self, obs: pd.Series, sim: pd.Series):
        """
        Give ``sim`` the simulation date index and intersect it with ``obs``.

        The simulation frequency comes from IPRINT in file.cio. Raises ValueError
        when the simulated length does not match the simulation period (partial-year
        runs via IDAF/IDAL are not supported), when the observation step differs from
        the simulation step (see ``check_observation_step``), or when there is no
        common date.
        """
        freq = self._sim_freq(obs)
        check_observation_step(obs.index, freq)
        sim = self._to_model_dates(sim, freq)

        common = obs.index.intersection(sim.index)
        if len(common) == 0:
            raise ValueError(
                f"No common dates between observations "
                f"({obs.index.min()} .. {obs.index.max()}) and simulation "
                f"({sim.index.min()} .. {sim.index.max()})."
            )
        return obs.loc[common], sim.loc[common]
