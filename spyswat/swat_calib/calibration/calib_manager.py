# spyswat/calibration/manager.py
from typing import List
from collections.abc import Mapping
import pandas as pd
import numpy as np
from contextlib import contextmanager
import shutil, tempfile
import logging
import warnings
from functools import partial
from pathlib import Path

from spyswat.swat_calib.core.workingFolder_manager import (
    _copy_over, _stamp_output_rch, _check_fresh_output_rch, _param_exts, _baseline_files,
)
from spyswat.swat_calib.core.txinout import TxInOut
from spyswat.swat_calib.core.output_manager import OutputFileManager

from spyswat.logger import Logger
from .param_spec import parse_spec, format_params, is_raw, param_columns
from .run_log import RunLog
from .scoring import (
    normalise_observed, check_weights, preflight, score_sites, _resolve_metrics,
    _normalise_outputs, _validate_config,
)

logger = logging.getLogger(__name__)

# Sentinel for the deprecated reach_id / output_variable kwargs: lets the manager
# tell "not passed" (use the old defaults, no warning) from "passed explicitly".
_SENTINEL = object()


def _resolve_deprecated_reach(reach_id, output_variable):
    """Resolve the deprecated ``reach_id`` / ``output_variable`` sentinels.

    Returns ``(reach_id, output_variable)`` with the old defaults (1 and
    'FLOW_OUTcms'), emitting a ``DeprecationWarning`` only when either was
    passed explicitly (never on the new multi-site ``outputs`` path).
    """
    explicit = reach_id is not _SENTINEL or output_variable is not _SENTINEL
    reach_id = 1 if reach_id is _SENTINEL else reach_id
    output_variable = 'FLOW_OUTcms' if output_variable is _SENTINEL else output_variable
    if explicit:
        warnings.warn(
            "reach_id and output_variable are deprecated; pass "
            f"outputs={{{output_variable!r}: [{reach_id}]}} instead.",
            DeprecationWarning, stacklevel=3,
        )
    return reach_id, output_variable


def _raw_param_values(params: dict) -> dict:
    """Formatted ``{name: [(value, method[, subs])]}`` -> raw ``{name: value}``.

    The session store writes one float column per parameter, so it must receive the
    raw value (the first group's value), never the formatted tuples. A raw
    ``{name: value}`` dict passes through unchanged.
    """
    out = {}
    for name, spec in (params or {}).items():
        if isinstance(spec, (list, tuple)):
            first = spec[0] if spec else None
            out[name] = first[0] if isinstance(first, (list, tuple)) else first
        else:
            out[name] = spec
    return out


def _extract_outputs(worker_dir: str, outputs: dict) -> dict:
    """Module-level picklable extract: read ``{(variable, reach): Series}`` from output.rch.

    Runs inside every worker process; the series are returned undated (file order)
    and get their model dates in the main process via ``_to_model_dates``.
    """
    out = OutputFileManager(TxInOut(worker_dir))
    sim = {}
    for var, reaches in outputs.items():
        for reach in reaches:
            sim[(var, reach)] = out.read_rch(
                columns=['RCH', 'MON', var], reach_id=reach
            )[var]
    return sim


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
        self._log = RunLog(project)
        self._store_counter = 0

    # Compatibility for callers that set session state to simulate name races.

    @property
    def _session_base(self):
        return self._log._session_base

    @_session_base.setter
    def _session_base(self, value):
        self._log._session_base = value

    @property
    def _session_id(self):
        return self._log._session_id

    @_session_id.setter
    def _session_id(self, value):
        self._log._session_id = value

    @property
    def _session_dir(self):
        return self._log._session_dir

    @_session_dir.setter
    def _session_dir(self, value):
        self._log._session_dir = value

    @property
    def _session_claimed(self):
        return self._log._session_claimed

    @_session_claimed.setter
    def _session_claimed(self, value):
        self._log._session_claimed = value

    @property
    def _session_n(self):
        return self._log._session_n

    @_session_n.setter
    def _session_n(self, value):
        self._log._session_n = value

    # ── Per-run result log delegates ─────────────────────────────────

    def _warn_once(self, key, message: str) -> None:
        self._log._warn_once(key, message)

    @property
    def log_outputs(self) -> str:
        """What goes to <session>_outputs.csv: 'all' | 'observed' | 'none'."""
        return self._log.log_outputs

    @log_outputs.setter
    def log_outputs(self, value: str) -> None:
        self._log.log_outputs = value

    @property
    def results_dir(self) -> Path | None:
        """Folder of the per-run result files (None disables logging)."""
        return self._log.results_dir

    @results_dir.setter
    def results_dir(self, value) -> None:
        self._log.results_dir = value

    def session_path(self, suffix: str) -> Path | None:
        """Path ``<results_dir>/<session>_<suffix>.csv`` that will be used (nothing is created)."""
        return self._log.session_path(suffix)

    @property
    def session_files(self) -> dict:
        """{'metrics': Path, 'outputs': Path} of the current session ({} when disabled)."""
        return self._log.session_files

    def _append_csv(self, path: Path, header: list, rows: list) -> bool:
        return self._log._append_csv(path, header, rows)

    def flush_log(self) -> bool:
        """Try to write rows buffered while a log file was locked. True if nothing is left."""
        return self._log.flush_log()

    @staticmethod
    def _fmt(v):
        return RunLog._fmt(v)

    @staticmethod
    def _g(v):
        return RunLog._g(v)

    def _logged_metric_names(self) -> List[str] | None:
        return self._log._logged_metric_names()

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
        self._log._record_run(params, scores, status=status, error=error, sim=sim, mode=mode,
                              reach_id=reach_id, output_variable=output_variable)

    def _record_run(self, params, scores, *, status="ok", error=None, sim=None,
                    mode="sequential", reach_id=None, output_variable=None,
                    obs_index=None) -> None:
        self._log._record_run(params, scores, status=status, error=error, sim=sim, mode=mode,
                              reach_id=reach_id, output_variable=output_variable,
                              obs_index=obs_index)

    # ── Unified param_ranges parser ──────────────────────────────────

    _parse_spec = staticmethod(parse_spec)
    _param_columns = staticmethod(param_columns)

    def _format_params(self, raw: dict,
                       methods: dict = None, subbasins: dict = None) -> dict:
        """Convert {name: float} -> {name: [(val, method, [subs])]}."""
        return format_params(raw, methods, subbasins)

    _is_raw = staticmethod(is_raw)

    # ── Core run methods ─────────────────────────────────────────────

    def run_once(self, params: dict, *, outputs=None,
                 reach_id=_SENTINEL, output_variable=_SENTINEL,
                 methods=None, subbasins=None):
        """
        Apply ``params`` to the project's TxtInOut, run SWAT once and return the
        simulated series.

        With ``outputs={variable: [reach, ...]}`` the return is
        ``{(variable, reach): Series}`` with real model dates (``_to_model_dates``).
        Without ``outputs`` the deprecated single-site behaviour is kept: a bare
        ``pd.Series`` of ``output_variable`` at ``reach_id`` (defaults 1 and
        'FLOW_OUTcms'), with a ``DeprecationWarning`` only when ``reach_id`` /
        ``output_variable`` are passed explicitly.

        The single implementation of the sequential run: every sequential caller
        (run_iteration, sensitivity, GLUE 95PPU, ValidationRunner) goes through it.
        ``params`` is formatted ({name: [(value, method, ...)]}) or raw ({name: value},
        formatted with ``methods`` / ``subbasins``, default absolute 'v').

        Nothing is backed up: wrap the call in ``with manager.sandbox(...)`` unless the
        change must stay. Raises StaleOutputError (a RuntimeError) when SWAT did not
        write a fresh output.rch, so an old result is never read as this run's result.
        """
        formatted = (self._format_params(params, methods, subbasins)
                     if self._is_raw(params) else params)
        if outputs is not None:
            outputs = _normalise_outputs(outputs)   # fail before touching TxtInOut
        self._apply_and_run(formatted)
        if outputs is not None:
            freq = self._sim_freq()
            sim = {}
            for var, reaches in outputs.items():
                for reach in reaches:
                    series = self.project.Output.read_rch(
                        columns=['RCH', 'MON', var], reach_id=reach
                    )[var]
                    sim[(var, reach)] = self._to_model_dates(series, freq)
            return sim
        reach_id, output_variable = _resolve_deprecated_reach(reach_id, output_variable)
        return self.project.Output.read_rch(
            columns=['RCH', 'MON', output_variable], reach_id=reach_id
        )[output_variable]

    def _apply_and_run(self, formatted: dict) -> None:
        """Apply ``formatted`` params, run SWAT once, and check output freshness."""
        self.project.HRU.update_params(formatted)
        out_dir = self._txinout_dir()
        before = _stamp_output_rch(out_dir) if out_dir is not None else None
        self.project.run()
        if out_dir is not None:
            _check_fresh_output_rch(out_dir, before)

    @contextmanager
    def sandbox(self, names=None):
        """
        Back up the input files that ``names`` ('name.ext' keys; None = every parameter
        extension) can change, and restore them when the block exits -- normally, on an
        exception or on KeyboardInterrupt. Outputs are never touched.

            with manager.sandbox(names=["CN2.mgt"]):
                sim = manager.run_once({"CN2.mgt": 60.0})
        """
        if names is None:
            self._backup_state()
        else:
            self._backup_state(names=list(names))
        try:
            yield self
        finally:
            self._restore_state()

    def run_iteration(self, param_dict, observed, metric=None,
                      reach_id=_SENTINEL, output_variable=_SENTINEL,
                      methods=None, subbasins=None,
                      *, outputs=None, weights=None, metrics=None,
                      calib_period=None, valid_period=None, step=None, agg=None,
                      store=None, run_id=None, is_initial=False) -> float:
        if self._new_path(observed, outputs, weights, calib_period, store,
                          valid_period=valid_period, step=step, agg=agg,
                          metrics=metrics, run_id=run_id, is_initial=is_initial):
            return self._run_iteration_multi(
                param_dict, observed, metric, outputs, weights, metrics,
                calib_period, valid_period, step, agg, store, run_id, is_initial,
                methods, subbasins,
            )
        # ── deprecated single-site path (behaviour unchanged) ──────────────
        reach_id, output_variable = _resolve_deprecated_reach(reach_id, output_variable)
        formatted = self._format_params(param_dict, methods, subbasins) if self._is_raw(param_dict) else param_dict
        # Resolved before the backup: nothing between backup and restore may raise.
        obs_index = observed.index if isinstance(observed, pd.Series) else None
        self._backup_state(names=formatted.keys())
        err: Exception | None = None
        score = None
        sim_dated = None
        try:
            sim = self._run_once_single(formatted, reach_id, output_variable)

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
                         output_variable=output_variable, obs_index=obs_index)

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

    def _run_once_single(self, formatted, reach_id, output_variable) -> pd.Series:
        """Apply + run + read one series — ``run_once`` without the deprecation warning."""
        self._apply_and_run(formatted)
        return self.project.Output.read_rch(
            columns=['RCH', 'MON', output_variable], reach_id=reach_id
        )[output_variable]

    @staticmethod
    def _new_path(observed, outputs, weights, calib_period, store,
                  valid_period=None, step=None, agg=None,
                  metric=None, metrics=None, run_ids=None, run_id=None,
                  is_initial=False) -> bool:
        """True when the multi-site vocabulary is used.

        Covers the design vocabulary (``outputs``, a dict ``observed``,
        ``weights``, ``calib_period`` or ``store``) plus every keyword-only
        argument the old single-site path would silently drop: ``valid_period``,
        ``step``, ``agg``, ``metric`` / ``metrics`` / ``run_ids`` (run_batch) and
        ``run_id`` / ``is_initial`` (run_iteration).
        """
        return (outputs is not None
                or isinstance(observed, Mapping)
                or weights is not None
                or calib_period is not None
                or store is not None
                or valid_period is not None
                or step is not None
                or agg is not None
                or metric is not None
                or metrics is not None
                or run_ids is not None
                or run_id is not None
                or is_initial)

    def _store_next_id(self) -> int:
        """Next run id for the session store (continues the manager's counter)."""
        self._store_counter += 1
        return self._store_counter

    def _add_run_to_store(self, store, run_id, *, params, status, error, score,
                          is_initial, series, site_metrics) -> None:
        """Call ``store.add_run`` without ever breaking the calibration (rule 10)."""
        try:
            store.add_run(
                run_id, params=_raw_param_values(params), status=status, error=error,
                score=score, is_initial=is_initial, series=series,
                site_metrics=site_metrics,
            )
        except Exception as exc:  # noqa: BLE001 - the store must never break a run
            logger.warning(f"store.add_run failed for run {run_id}: {exc}")

    def _run_iteration_multi(self, param_dict, observed, metric, outputs, weights,
                             metrics, calib_period, valid_period, step, agg, store,
                             run_id, is_initial, methods, subbasins) -> float:
        observed_dict, outputs_dict = normalise_observed(observed, outputs)
        metric = "nse" if metric is None else metric
        check_weights(weights, list(observed_dict.keys()))
        preflight(observed_dict, calib_period)
        _validate_config(valid_period, step, agg)
        _resolve_metrics(metric, metrics)   # unknown metric fails before any SWAT run
        formatted = (self._format_params(param_dict, methods, subbasins)
                     if self._is_raw(param_dict) else param_dict)
        freq = self._sim_freq()
        warmup = self.warmup_end()
        self._backup_state(names=formatted.keys())
        err: Exception | None = None
        score = None
        site_metrics = None
        sim_dated = None
        try:
            sim = self.run_once(formatted, outputs=outputs_dict)
            score, site_metrics = score_sites(
                sim, observed_dict, metric=metric, metrics=metrics, weights=weights,
                calib_period=calib_period, valid_period=valid_period, freq=freq,
                step=step, agg=agg, warmup_end=warmup,
            )
            sim_dated = sim
        except Exception as e:
            err = e
        except BaseException:
            try:
                self._restore_state()
            except Exception as restore_err:
                logger.error(f"Restore after interruption failed: {restore_err}")
            raise

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

        if store is not None:
            rid = run_id if run_id is not None else self._store_next_id()
            self._add_run_to_store(
                store, rid, params=formatted,
                status="ok" if err is None else "failed",
                error=str(err) if err is not None else None,
                score=np.nan if err is not None else score,
                is_initial=is_initial, series=sim_dated, site_metrics=site_metrics,
            )

        if err is not None:
            raise RuntimeError(f"Iteration failed: {err}") from err
        return score

    def _txinout_dir(self) -> Path | None:
        """The project's TxtInOut directory as a Path (None if it cannot be resolved)."""
        try:
            return Path(self.project.txinout.directory)
        except TypeError:
            return None

    def _input_files(self, names=None) -> List[Path]:
        """
        file.cio + the input files of the extensions that ``names`` ('name.ext' keys) can
        modify; every extension in the parameter file when ``names`` is None.
        """
        tx = self.project.txinout
        directory = Path(tx.directory)
        files: List[Path] = []
        cio = directory / "file.cio"
        if cio.exists():
            files.append(cio)
        param_file = getattr(self.project, "param_file", None)
        if param_file is not None:
            exts = _param_exts(str(param_file.param_path),
                               None if names is None else list(names))
            files.extend(_baseline_files(tx, exts))
        seen, out = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def _backup_state(self, names=None):
        """
        Back up only the input files that calibration can modify (never outputs).

        ``names``: the 'name.ext' keys about to be changed; only their extensions (plus
        file.cio) are copied. None backs up every extension in the parameter file.
        """
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
            for f in self._input_files(names):
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
                  reach_id=_SENTINEL, output_variable=_SENTINEL,
                  methods=None, subbasins=None,
                  *, metric=None, outputs=None, weights=None,
                  calib_period=None, valid_period=None, step=None, agg=None,
                  store=None, run_ids=None, is_initial=False) -> pd.DataFrame:
        """
        Return DataFrame. param_sets can be list of {name: float} (raw) or
        {name: [(val, method, ...)]} (pre-formatted) -- both are accepted.

        Multi-site path (``outputs`` / a dict ``observed`` / ``weights`` /
        ``calib_period`` / ``store`` given): returns a DataFrame with a ``score``
        column followed by ``<metric>@<variable>@<reach>`` (calibration period) for
        every site and reported metric, in submission order. With ``store`` each run
        is written to the store (the flat RunLog is not used). The deprecated
        single-site path is unchanged and still logs through the flat RunLog.

        Logging
        ───────
        Progress is written to both tqdm (visual) and logger.info (file/console)
        at every chunk boundary so runs are inspectable in the log file.

        Worker log records are routed through a multiprocessing.Queue so
        multiple subprocesses never write to the log file simultaneously.
        """
        if self._new_path(observed, outputs, weights, calib_period, store,
                          valid_period=valid_period, step=step, agg=agg,
                          metric=metric, run_ids=run_ids, is_initial=is_initial):
            return self._run_batch_multi(
                param_sets, observed, metric, outputs, weights, metrics,
                calib_period, valid_period, step, agg, store, run_ids, is_initial,
                methods, subbasins,
            )
        # ── deprecated single-site path (behaviour unchanged) ──────────────
        reach_id, output_variable = _resolve_deprecated_reach(reach_id, output_variable)
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

    def _run_batch_multi(self, param_sets, observed, metric, outputs, weights,
                         metrics, calib_period, valid_period, step, agg, store,
                         run_ids, is_initial, methods, subbasins) -> pd.DataFrame:
        observed_dict, outputs_dict = normalise_observed(observed, outputs)
        metric = "nse" if metric is None else metric
        check_weights(weights, list(observed_dict.keys()))
        preflight(observed_dict, calib_period)
        _validate_config(valid_period, step, agg)
        reported = _resolve_metrics(metric, metrics)

        formatted_sets = [
            self._format_params(p, methods, subbasins) if self._is_raw(p) else p
            for p in param_sets
        ]
        total = len(formatted_sets)
        wf = self.project.WorkingFolder
        n_workers = wf.n_parallel
        total_batches = (total + n_workers - 1) // n_workers

        freq = self._sim_freq()
        warmup = self.warmup_end()
        extract = partial(_extract_outputs, outputs=outputs_dict)

        if store is not None:
            if run_ids is None:
                run_ids = list(range(self._store_counter + 1, self._store_counter + total + 1))
                self._store_counter += total
            else:
                run_ids = list(run_ids)
                if len(run_ids) != total:
                    raise ValueError(
                        f"run_ids has {len(run_ids)} entries, expected {total}."
                    )

        try:
            from tqdm import tqdm
            pbar = tqdm(total=total, desc="SWAT runs", unit="run")
        except ImportError:
            pbar = None

        log_queue = Logger.init_queue_listener()
        logger.info(
            f"[run_batch] Starting — {total} runs, "
            f"{n_workers} workers, {total_batches} batches"
        )

        all_rows = []
        try:
            for chunk_start in range(0, total, n_workers):
                batch_num = chunk_start // n_workers + 1
                chunk = formatted_sets[chunk_start: chunk_start + n_workers]

                results = wf.run_parallel(
                    self.project.swat_exe.swat_exe_path,
                    param_sets=chunk,
                    log_queue=log_queue,
                    extract=extract,
                )

                for j, res in enumerate(results):
                    idx = chunk_start + j
                    run_error = None
                    score = np.nan
                    site_metrics = None
                    sim_dated = None
                    if not res.ok:
                        run_error = res.error
                        logger.error(f"[run_batch] Run {idx + 1} failed "
                                     f"(worker {j + 1}): {res.error}")
                    else:
                        try:
                            sim_dated = {
                                key: self._to_model_dates(s, freq)
                                for key, s in res.payload.items()
                            }
                            score, site_metrics = score_sites(
                                sim_dated, observed_dict, metric=metric,
                                metrics=metrics, weights=weights,
                                calib_period=calib_period, valid_period=valid_period,
                                freq=freq, step=step, agg=agg, warmup_end=warmup,
                            )
                        except ValueError:
                            # A misconfigured period / step / metric must surface,
                            # not be turned into NaN rows after every batch ran.
                            raise
                        except Exception as e:
                            run_error = f"output unreadable: {e}"
                            score = np.nan
                            site_metrics = None
                            sim_dated = None
                            logger.warning(
                                f"[run_batch] Run {idx + 1} (worker {j + 1}) "
                                f"output unreadable: {e}"
                            )
                    row = self._build_multisite_row(score, site_metrics, reported,
                                                    observed_dict)
                    all_rows.append(row)
                    if store is not None:
                        rid = run_ids[idx] if run_ids is not None else self._store_next_id()
                        self._add_run_to_store(
                            store, rid, params=chunk[j],
                            status="ok" if run_error is None else "failed",
                            error=run_error, score=score, is_initial=is_initial,
                            series=sim_dated, site_metrics=site_metrics,
                        )

                done = chunk_start + len(chunk)
                logger.info(
                    f"[Batch {batch_num}/{total_batches}] "
                    f"{done}/{total} runs ({done / total:.0%})"
                )
                if pbar is not None:
                    pbar.update(len(chunk))

        finally:
            if pbar is not None:
                pbar.close()
            Logger.stop_listener()
            self.flush_log()

        logger.info(f"[run_batch] Done — {total} runs complete")
        columns = ["score"] + [
            f"{m}@{var}@{reach}"
            for (var, reach) in sorted(observed_dict) for m in reported
        ]
        return pd.DataFrame(all_rows, columns=columns)

    @staticmethod
    def _build_multisite_row(score, site_metrics, reported, observed_dict) -> dict:
        """One row of the multi-site DataFrame: score + per-site calib metrics."""
        row = {"score": score}
        for key in sorted(observed_dict):
            var, reach = key
            entry = site_metrics.get(key, {}) if site_metrics is not None else {}
            for m in reported:
                row[f"{m}@{var}@{reach}"] = entry.get(f"{m}_calib", np.nan)
        return row

    def warmup_end(self) -> "pd.Timestamp | None":
        """First day after the warm-up: ``pd.Timestamp(IYR + NYSKIP, 1, 1)`` from file.cio.

        ``None`` when the project's FileCIO does not expose ``year_start`` (test stubs).
        """
        cio = self.project.FileCIO
        year_start = getattr(cio, "year_start", None)
        if year_start is None:
            return None
        return pd.Timestamp(int(year_start), 1, 1)

    _FREQ_LEVEL = {'D': 0, 'MS': 1, 'YS': 2}  # IPRINT values accepted from file.cio

    def _sim_freq(self, obs: pd.Series | None = None) -> str:
        """Simulation output frequency from IPRINT in file.cio (contract C4)."""
        # Never inferred from the observations (design rule 6); mocks must stub get_iprint().
        freq = self.project.FileCIO.get_iprint()
        if not isinstance(freq, str) or freq not in self._FREQ_LEVEL:
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
