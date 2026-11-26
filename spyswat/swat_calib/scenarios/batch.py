"""Run scenarios x parameter sets over the parallel worker folders.

The calling script must be guarded by ``if __name__ == "__main__":`` (Windows spawns
worker processes that re-import it).
"""
import concurrent.futures
from concurrent.futures.process import BrokenProcessPool
import hashlib
import json
import multiprocessing
import os
import shutil
import time
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from spyswat.logger import Logger
from spyswat.swat_calib.core import TxInOut, OutputFileManager
from spyswat.swat_calib.core.workingFolder_manager import (
    WorkerResult, _OUTPUT_IGNORE, _rmtree, _worker_job,
)
from spyswat.swat_calib.io import FileCIO

from .model import Job, ParamSet, RunResult, Scenario
from .scheduler import Scheduler
from .signature import txinout_fingerprint

logger = Logger.get_logger(__name__)

SUMMARY_COLS = ["job_id", "scenario", "param_set", "status", "error",
                "duration_s", "n_rows", "series_file", "evaluated", "eval_note"]
METRIC_COLS = ["job_id", "scenario", "param_set", "variable", "reach", "metric", "value"]
WORK_SUBDIR = "_scenario_batch"
SIGNATURE_FILE = ".signature.json"
_IPRINT_TO_FREQ = FileCIO._IPRINT_TO_FREQ   # one source: file_cio.py
_RETRY_SLEEP = 0.2   # seconds, times the attempt number (summary.csv open in Excel, ...)
_SAVE_INTERVAL_S = 10.0                     # save at most this often (seconds)
_SEED_FAILED_PREFIX = "seed failed: "       # base TxtInOut could not be copied
_SLOT_LOCKED_PREFIX = "slot locked: "       # worker folder could not be removed
_ALL_UNUSABLE_MSG = (
    "no usable worker folder remains (each is locked by an orphaned swat.exe); "
    "the remaining jobs could not be run"
)


def _replace_retry(src: str, dst: str, retries: int = 5) -> None:
    """os.replace that retries on PermissionError (target locked by another program)."""
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(_RETRY_SLEEP * (attempt + 1))


# ══════════════════════════════════════════════════════════════════════
#  Functions executed inside the worker processes (module level: picklable)
# ══════════════════════════════════════════════════════════════════════

def _prepare_dispatch(worker_dir: str, cio_by_dir: Dict[str, dict]) -> None:
    cio = cio_by_dir.get(str(worker_dir))
    if cio:
        FileCIO(TxInOut(worker_dir)).set(**cio)


def _build_table(worker_dir: str, outputs: Dict[str, List[int]]) -> pd.DataFrame:
    """date x '{variable}@{reach}' table; reaches are labelled by the RCH column."""
    txinout = TxInOut(worker_dir)
    freq = FileCIO(txinout).get_iprint()
    dates = FileCIO(txinout).get_date_range_sim(freq)
    out = OutputFileManager(txinout, use_cache=False)
    cols: Dict[str, np.ndarray] = {}
    for variable, reaches in outputs.items():
        df = out.read_rch(columns=[variable], reach_id=list(reaches))
        rch = df["RCH"].to_numpy().astype(int)
        values = df[variable].to_numpy()
        for r in reaches:
            v = values[rch == r]
            if v.size == 0:
                raise ValueError(f"reach {r} not found in output.rch")
            if v.size != len(dates):
                raise ValueError(
                    f"{variable} at reach {r}: output.rch has {v.size} rows but file.cio "
                    f"({freq}) implies {len(dates)} dates ({dates[0].date()} .. "
                    f"{dates[-1].date()})")
            cols[f"{variable}@{r}"] = v.astype(float)
    return pd.DataFrame(cols, index=pd.Index(dates, name="date"))


def _extract_dispatch(worker_dir: str, jobs: Dict[str, str], outputs: Dict[str, List[int]],
                      series_dir: str, observed: Optional[dict],
                      metrics: Tuple[str, ...]) -> dict:
    job_id, evaluate = jobs[str(worker_dir)]
    table = _build_table(worker_dir, outputs)
    fname = f"{job_id}.csv"
    final = os.path.join(series_dir, fname)
    tmp = final + f".{os.getpid()}.tmp"
    table.to_csv(tmp)
    _replace_retry(tmp, final)

    rows: List[tuple] = []
    evaluated, note = False, None
    if not evaluate:
        note = "evaluate=False"
    elif not observed:
        note = "no observations given"
    else:
        from spyswat.swat_calib.analysis import SWATAnalysis
        stats = SWATAnalysis(None)
        for (variable, reach), (obs_idx, obs_val) in observed.items():
            obs = pd.Series(obs_val, index=pd.DatetimeIndex(obs_idx))
            sim = table[f"{variable}@{reach}"]
            common = obs.index.intersection(sim.index)
            if len(common) == 0:
                continue
            res = stats.calculate_statistics(obs.loc[common], sim.loc[common], list(metrics))
            for m, val in res.items():
                rows.append((variable, int(reach), m, float(val)))
        evaluated = bool(rows)
        if not evaluated:
            note = "no overlap with observations"
    for p in Path(worker_dir).iterdir():
        if p.is_file() and (p.name.startswith("output.") or p.name == "watout.dat"):
            try:
                p.unlink()
            except OSError:
                pass
    return {"n_rows": int(len(table)), "series_file": fname, "metrics": rows,
            "evaluated": evaluated, "eval_note": note}


def _seed_and_run(slot_dir: str, base_dir: str, reseed: bool, swat_exe: str,
                  params: Optional[dict], param_path: Optional[str],
                  overlay: Optional[Dict[str, str]],
                  prepare: Optional[Callable], extract: Optional[Callable],
                  runner: Optional[Callable], timeout_s: Optional[float],
                  log_queue=None) -> WorkerResult:
    """(worker process) Optionally re-copy the base into the slot, then run one job.

    With ``reseed=True`` the slot folder is removed and re-copied from the job's
    base TxtInOut using the same output-ignore rule as ``WorkingFolderManager.setup``.
    It never raises: it returns ``WorkerResult(ok=False, ...)`` whose error is
    prefixed ``_SLOT_LOCKED_PREFIX`` (folder could not be removed) or
    ``_SEED_FAILED_PREFIX`` (the base copy failed); otherwise it delegates to the
    unchanged ``_worker_job``. Copies for different slots therefore run in parallel.
    """
    t0 = time.perf_counter()
    sdir = Path(slot_dir)
    if reseed:
        if sdir.exists():
            _rmtree(sdir)
            if sdir.exists():
                return WorkerResult(
                    False,
                    _SLOT_LOCKED_PREFIX + f"{sdir} could not be removed "
                    "(a swat.exe is probably still running in it)",
                    time.perf_counter() - t0, slot_dir, None)
        try:
            shutil.copytree(src=base_dir, dst=sdir, ignore=_OUTPUT_IGNORE)
        except BaseException as exc:  # noqa: BLE001 - classified by the parent
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return WorkerResult(
                False, _SEED_FAILED_PREFIX + f"{type(exc).__name__}: {exc}",
                time.perf_counter() - t0, slot_dir, None)
    return _worker_job(slot_dir, base_dir, swat_exe, params, param_path,
                       overlay, prepare, extract, runner, timeout_s, log_queue)


# ══════════════════════════════════════════════════════════════════════
#  Result container
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BatchResult:
    results_dir: Path
    results: List[RunResult]
    summary: pd.DataFrame
    metrics: pd.DataFrame
    failed: List[RunResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def series(self, variable: str) -> pd.DataFrame:
        """Date-indexed table, columns MultiIndex (scenario, param_set, reach)."""
        frames, keys = [], []
        prefix = f"{variable}@"
        for r in self.results:
            if r.status not in ("ok", "skipped") or not r.series_path:
                continue
            df = pd.read_csv(r.series_path, index_col="date", parse_dates=True)
            for c in df.columns:
                if c.startswith(prefix):
                    frames.append(df[c])
                    keys.append((r.scenario, r.param_set, int(c[len(prefix):])))
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, axis=1)
        out.columns = pd.MultiIndex.from_tuples(keys, names=["scenario", "param_set", "reach"])
        return out.sort_index()

    def to_csv(self, variable: str, path) -> Path:
        """Write ``series(variable)`` with flat column names 'scenario|param_set|reach'."""
        df = self.series(variable)
        df.columns = ["|".join(str(x) for x in c) for c in df.columns]
        df.index.name = "date"
        df.to_csv(path)
        return Path(path)


# ══════════════════════════════════════════════════════════════════════
#  Batch runner
# ══════════════════════════════════════════════════════════════════════

def _atomic_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False)
    _replace_retry(str(tmp), str(path))


def _series_hash(ser: pd.Series) -> str:
    h = hashlib.sha1()
    h.update(ser.index.to_numpy().astype("datetime64[ns]").tobytes())
    h.update(ser.to_numpy(dtype=float).tobytes())
    return h.hexdigest()


def _work_dir_key(results_dir) -> str:
    """10 hex chars naming the work dir of one ``results_dir`` (same dir -> same key)."""
    resolved = str(Path(results_dir).resolve()).lower()
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:10]


def _scenario_sig(s: Scenario) -> str:
    weather = []
    if s.weather_dir:
        for f in sorted(Path(s.weather_dir).iterdir()):
            if f.is_file():
                st = f.stat()
                weather.append((f.name, st.st_size, st.st_mtime_ns))
    return json.dumps([s.txinout_dir, s.weather_dir, weather, s.cio, s.evaluate],
                      sort_keys=True)


def _param_sig(p: ParamSet) -> str:
    return json.dumps(p.updates, sort_keys=True, default=str)


def _read_csv_or_empty(path: Path, cols: List[str]) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path, dtype={"error": object, "series_file": object})
    except Exception:  # noqa: BLE001 - unreadable bookkeeping file: start over
        logger.warning("Cannot read %s; ignoring it", path)
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


class ScenarioBatch:
    """Run scenarios x parameter sets with a ``SWATProject``'s settings.

    The batch works in ``<project working dir>/_scenario_batch/<key>``, one folder per
    ``results_dir`` (``<key>`` is 10 hex chars of the resolved ``results_dir``), so two
    batches with different result folders never share worker folders while a re-run of
    the same ``results_dir`` keeps them. The project's own worker folders are left alone.
    Needs ``project.param_file`` only when a ParamSet
    has updates. ``results_dir/.signature.json`` records outputs, metrics, observations
    and the definition of every scenario / parameter set name; ``resume=True`` with a
    different signature raises ValueError (use a new ``results_dir`` or ``resume=False``).
    Observations must have the same time step as every scenario's print step (daily vs
    monthly) of every scenario with ``evaluate=True``: a mismatch raises ValueError before
    any job runs. Scenarios with ``evaluate=False`` (future / GCM projections) are never
    evaluated and never checked. An evaluated scenario whose period shares no dates
    with the observations is treated like evaluate=False (no metric rows,
    ``evaluated=False`` and an ``eval_note`` in summary.csv; one INFO line per scenario).
    """

    def __init__(self, project, results_dir):
        self.project = project
        self.results_dir = Path(results_dir)

    # ------------------------------------------------------------------
    @staticmethod
    def _signature_diff(old: dict, new: dict) -> List[str]:
        out = [k for k in ("outputs", "metrics", "observed") if old.get(k) != new.get(k)]
        for kind in ("scenarios", "param_sets"):
            o, n = old.get(kind, {}), new.get(kind, {})
            out += [f"{kind[:-1]} {name!r} changed" for name in n if name in o and o[name] != n[name]]
        old_in, new_in = old.get("scenario_inputs"), new.get("scenario_inputs", {})
        if old_in is None:      # results written by 0.2.6: no fingerprints to compare
            logger.info("[Scenarios] cannot verify that scenario TxtInOut inputs are "
                        "unchanged (results written by an older version)")
        else:
            out += [f"scenario {name!r} inputs changed"
                    for name in new_in if name in old_in and old_in[name] != new_in[name]]
        return out

    def _check_observation_steps(self, jobs: List[Job], observed) -> None:
        """Raise ValueError when an observation step differs from the print step of an
        evaluated scenario (evaluate=False scenarios are skipped)."""
        from spyswat.swat_calib.calibration.calib_manager import check_observation_step
        from spyswat.swat_calib.io import FileCIO
        default_base = str(self.project.txinout.directory)
        freqs: Dict[str, str] = {}
        for j in jobs:
            s = j.scenario
            if s.name in freqs or not s.evaluate:
                continue
            if s.cio and "IPRINT" in s.cio:
                if s.cio["IPRINT"] not in _IPRINT_TO_FREQ:
                    raise ValueError(f"Scenario {s.name!r}: IPRINT must be 0, 1 or 2")
                freqs[s.name] = _IPRINT_TO_FREQ[s.cio["IPRINT"]]
            else:
                freqs[s.name] = FileCIO(TxInOut(s.txinout_dir or default_base)).get_iprint()
        for s_name, freq in freqs.items():
            for key, ser in observed.items():
                try:
                    check_observation_step(ser.index, freq)
                except ValueError as exc:
                    raise ValueError(f"observed {tuple(key)!r} vs scenario {s_name!r} "
                                     f"(print step {freq}): {exc}") from None

    # ------------------------------------------------------------------
    def _plan(self, scenarios, param_sets, pairs) -> List[Job]:
        scenarios, param_sets = list(scenarios), list(param_sets)
        if not scenarios or not param_sets:
            raise ValueError("At least one scenario and one parameter set are required")
        for kind, items in (("Scenario", scenarios), ("ParamSet", param_sets)):
            names = [x.name for x in items]
            dup = sorted({n for n in names if names.count(n) > 1})
            if dup:
                raise ValueError(f"Duplicate {kind} name(s): {dup}")
        by_s = {s.name: s for s in scenarios}
        by_p = {p.name: p for p in param_sets}
        jobs = self._pairs_to_jobs(scenarios, param_sets, by_s, by_p, pairs)
        ids = [j.job_id for j in jobs]
        clash = sorted({i for i in ids if ids.count(i) > 1})
        if clash:
            raise ValueError(f"Different jobs share the job id(s) {clash}")
        return jobs

    @staticmethod
    def _pairs_to_jobs(scenarios, param_sets, by_s, by_p, pairs) -> List[Job]:
        if pairs is None:
            return [Job(s, p) for s in scenarios for p in param_sets]
        jobs, seen = [], set()
        for pair in pairs:
            sn, pn = pair
            if sn not in by_s or pn not in by_p:
                raise ValueError(f"Unknown pair {(sn, pn)!r}: scenario names {sorted(by_s)}, "
                                 f"parameter set names {sorted(by_p)}")
            if (sn, pn) not in seen:
                seen.add((sn, pn))
                jobs.append(Job(by_s[sn], by_p[pn]))
        return jobs

    def run(self, scenarios: Sequence[Scenario], param_sets: Sequence[ParamSet], *,
            pairs: Optional[Sequence[Tuple[str, str]]] = None,
            outputs: Dict[str, Sequence[int]],
            observed: Optional[Dict[Tuple[str, int], pd.Series]] = None,
            metrics: Sequence[str] = ("nse", "kge", "pbias"),
            resume: bool = True, timeout_s: Optional[float] = None,
            runner=None, log_queue=None, cleanup: bool = False) -> BatchResult:
        """
        Args:
            outputs:  {variable: [reach ids]} read from output.rch.
            observed: {(variable, reach): Series with a DatetimeIndex}; metrics are only
                      computed for these (each must also be in ``outputs``).
            pairs:    explicit [(scenario_name, param_set_name)]; default = full product.
                      Their time step (daily / monthly) must match every scenario's print
                      step, else ValueError before any job runs (only scenarios with
                      evaluate=True are checked and evaluated).
            resume:   skip jobs already 'ok' in summary.csv (series file present). Raises
                      ValueError if outputs, metrics, observations or the definition of a
                      scenario / parameter set name differ from the stored signature.
            runner:   picklable ``runner(worker_dir)`` replacing the SWAT executable
                      (used by tests).
            log_queue: queue from ``Logger.init_queue_listener()`` so worker log records
                      reach the main process; default (``None``) uses
                      ``Logger._log_queue`` when a listener is already running. No
                      listener is started here: the caller owns its lifetime.
            cleanup:  remove this batch's worker folder under ``_scenario_batch`` after
                      the batch completes normally (default ``False`` keeps slots for reuse).
        """
        if multiprocessing.parent_process() is not None:
            raise RuntimeError(
                "ScenarioBatch.run() was called inside a child process: put the script's "
                "code under  if __name__ == \"__main__\":  so spawned workers do not re-run it.")
        jobs = self._plan(scenarios, param_sets, pairs)

        outs: Dict[str, List[int]] = {}
        for var, reaches in outputs.items():
            rl = [int(r) for r in ([reaches] if isinstance(reaches, (int, np.integer))
                                   else reaches)]
            outs[var] = list(dict.fromkeys(rl))
            if not outs[var]:
                raise ValueError(f"No reaches given for output {var!r}")
        if not outs:
            raise ValueError("outputs must name at least one variable")
        obs_payload: Optional[dict] = None
        if observed:
            obs_payload = {}
            for (var, reach), ser in observed.items():
                if var not in outs or int(reach) not in outs[var]:
                    raise ValueError(f"observed key {(var, reach)!r} is not in outputs")
                if not isinstance(ser.index, pd.DatetimeIndex):
                    raise ValueError(f"observed {(var, reach)!r} needs a DatetimeIndex")
                obs_payload[(var, int(reach))] = (ser.index.to_numpy(),
                                                  ser.to_numpy(dtype=float))
            from spyswat.swat_calib.analysis.statistics import known_metrics
            bad = [m for m in metrics if m not in known_metrics()]
            if bad:
                raise ValueError(f"Unknown metric(s) {bad}; known: {known_metrics()}")
            self._check_observation_steps(jobs, observed)

        proj = self.project
        param_file = proj.param_file.param_path if proj.param_file is not None else None
        if param_file is None and any(j.param_set.updates for j in jobs):
            raise ValueError("The project has no param_file but a ParamSet has updates")
        n_parallel = proj._wf_manager.n_parallel
        swat_exe = proj.swat_exe.swat_exe_path
        base_default = str(proj.txinout.directory)
        res_dir = self.results_dir
        work_dir = Path(proj.working_folder) / WORK_SUBDIR / _work_dir_key(res_dir)
        log_q = Logger._log_queue if log_queue is None else log_queue

        series_dir = res_dir / "series"
        series_dir.mkdir(parents=True, exist_ok=True)
        summary_path, metrics_path = res_dir / "summary.csv", res_dir / "metrics.csv"
        summary = _read_csv_or_empty(summary_path, SUMMARY_COLS)
        metrics_df = _read_csv_or_empty(metrics_path, METRIC_COLS)
        rows = {r["job_id"]: r for r in summary.to_dict("records")}

        sig_path = res_dir / SIGNATURE_FILE
        new_sig = {
            "outputs": {v: r for v, r in outs.items()},
            "metrics": list(metrics),
            "observed": {f"{k[0]}@{int(k[1])}": _series_hash(ser)
                         for k, ser in (observed or {}).items()},
            "scenarios": {j.scenario.name: _scenario_sig(j.scenario) for j in jobs},
            "scenario_inputs": {name: txinout_fingerprint(directory)
                                for name, directory in
                                {j.scenario.name: j.scenario.txinout_dir or base_default
                                 for j in jobs}.items()},
            "param_sets": {j.param_set.name: _param_sig(j.param_set) for j in jobs},
        }
        old_sig = None
        if sig_path.is_file():
            try:
                old_sig = json.loads(sig_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old_sig = None
        diff = self._signature_diff(old_sig, new_sig) if old_sig is not None else []
        if resume and diff:
            raise ValueError(
                "resume=True but this batch differs from the one stored in "
                f"{res_dir}: {', '.join(diff)}. Use a new results_dir or resume=False.")
        if diff:   # resume=False: old rows of other jobs no longer match; forget them
            keep = {j.job_id for j in jobs}
            rows = {k: v for k, v in rows.items() if k in keep}
            metrics_df = metrics_df[metrics_df["job_id"].isin(keep)]
        merged = dict(new_sig)
        if old_sig is not None and not diff:   # keep definitions of names not in this call
            merged["scenarios"] = {**old_sig.get("scenarios", {}), **new_sig["scenarios"]}
            merged["scenario_inputs"] = {**old_sig.get("scenario_inputs", {}),
                                         **new_sig["scenario_inputs"]}
            merged["param_sets"] = {**old_sig.get("param_sets", {}), **new_sig["param_sets"]}
        tmp_sig = sig_path.with_name(sig_path.name + ".tmp")
        tmp_sig.write_text(json.dumps(merged, sort_keys=True), encoding="utf-8")
        _replace_retry(str(tmp_sig), str(sig_path))

        dirty = {"warned": False}
        warns: List[str] = []
        # plan order (job id → index): summary.csv / metrics.csv stay in this order
        job_order = {j.job_id: i for i, j in enumerate(jobs)}

        def save(final: bool = False) -> None:
            """metrics.csv first, then summary.csv (an 'ok' row never lacks its metrics)."""
            nonlocal metrics_df
            # rows are filled in completion order; keep summary.csv and metrics.csv in
            # plan order so the file layout is stable regardless of how jobs finish.
            ordered_rows = sorted(rows.values(),
                                  key=lambda r: job_order.get(r["job_id"], len(jobs)))
            summary_df = pd.DataFrame(ordered_rows, columns=SUMMARY_COLS)
            if not metrics_df.empty:
                metrics_df = (metrics_df.assign(_ord=metrics_df["job_id"].map(job_order))
                              .sort_values("_ord", kind="stable")
                              .drop(columns="_ord").reset_index(drop=True))
            if final:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                for df, path in ((metrics_df, metrics_path), (summary_df, summary_path)):
                    try:
                        _atomic_csv(df, path)
                    except OSError as exc:
                        alt = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
                        _atomic_csv(df, alt)       # raises only if this also fails
                        msg = (f"cannot write {path} ({exc}); results saved to {alt} instead. "
                               f"resume=True reads {path.name}, not {alt.name}: close the "
                               f"program using it and copy or re-run to update it.")
                        logger.warning("[Scenarios] %s", msg)
                        warns.append(msg)
                dirty["pending"] = False
                return
            try:
                _atomic_csv(metrics_df, metrics_path)
                _atomic_csv(summary_df, summary_path)
                dirty["pending"] = False
            except OSError as exc:
                dirty["pending"] = True
                if not dirty["warned"]:
                    dirty["warned"] = True
                    logger.warning("[Scenarios] cannot write results in %s (%s); is it open "
                                   "in another program? Continuing, will retry at the end.",
                                   res_dir, exc)

        results: Dict[str, RunResult] = {}
        todo: List[Job] = []
        for j in jobs:
            old = rows.get(j.job_id)
            sf = series_dir / f"{j.job_id}.csv"
            if resume and old is not None and old["status"] == "ok" and sf.is_file():
                n = old["n_rows"]
                ev = old.get("evaluated")
                ev = True if ev is None or pd.isna(ev) else str(ev).lower() == "true"
                note = old.get("eval_note")
                results[j.job_id] = RunResult(
                    j.job_id, j.scenario.name, j.param_set.name, "skipped", None, 0.0,
                    int(n) if pd.notna(n) else 0, str(sf), ev,
                    note if isinstance(note, str) else None)
            else:
                todo.append(j)
        if len(results):
            logger.info("[Scenarios] resume: skipping %d finished job(s)", len(results))

        def base_of(j: Job) -> str:
            return str(j.scenario.txinout_dir or base_default)

        sched = Scheduler(todo, base_of, n_parallel)
        setup_errors: Dict[str, str] = {}

        done = 0
        noted: set = set()
        t_all = time.perf_counter()

        def _record_success(j: Job, w: WorkerResult) -> None:
            nonlocal done, metrics_df
            p = w.payload
            sf = series_dir / f"{j.job_id}.csv"
            rr = RunResult(j.job_id, j.scenario.name, j.param_set.name, "ok",
                           None, float(w.duration_s), int(p["n_rows"]), str(sf),
                           bool(p["evaluated"]), p["eval_note"])
            if (p["eval_note"] == "no overlap with observations"
                    and j.scenario.name not in noted):
                noted.add(j.scenario.name)
                logger.info("[Scenarios] scenario %s: simulated period does not "
                            "overlap the observations; no metrics (treated as "
                            "evaluate=False)", j.scenario.name)
            new = pd.DataFrame(
                [(j.job_id, j.scenario.name, j.param_set.name, v, r, m, val)
                 for v, r, m, val in p["metrics"]], columns=METRIC_COLS)
            metrics_df = pd.concat(
                [metrics_df[metrics_df["job_id"] != j.job_id], new], ignore_index=True)
            results[j.job_id] = rr
            rows[j.job_id] = {
                "job_id": rr.job_id, "scenario": rr.scenario,
                "param_set": rr.param_set, "status": rr.status, "error": rr.error,
                "duration_s": round(rr.duration_s, 3), "n_rows": rr.n_rows,
                "series_file": sf.name, "evaluated": rr.evaluated,
                "eval_note": rr.eval_note}
            done += 1

        def _record_failure(j: Job, msg: str, duration_s: float = 0.0) -> None:
            nonlocal done, metrics_df
            sf = series_dir / f"{j.job_id}.csv"
            rr = RunResult(j.job_id, j.scenario.name, j.param_set.name, "failed",
                           msg, float(duration_s), 0, None, j.scenario.evaluate, None)
            metrics_df = metrics_df[metrics_df["job_id"] != j.job_id]
            try:
                sf.unlink()
            except OSError:
                pass
            results[j.job_id] = rr
            rows[j.job_id] = {
                "job_id": rr.job_id, "scenario": rr.scenario,
                "param_set": rr.param_set, "status": rr.status, "error": rr.error,
                "duration_s": round(rr.duration_s, 3), "n_rows": rr.n_rows,
                "series_file": None, "evaluated": rr.evaluated,
                "eval_note": rr.eval_note}
            done += 1

        def _mark_base_bad(j: Job, seed_error: str) -> str:
            base = base_of(j)
            msg = f"setup of {base} failed: {seed_error[len(_SEED_FAILED_PREFIX):]}"
            if not sched.is_base_bad(base):
                sched.mark_base_bad(base)
                setup_errors[base] = msg
                logger.error("[Scenarios] %s", msg)
            return msg

        if todo:
            executor = concurrent.futures.ProcessPoolExecutor(max_workers=n_parallel)
            futures: dict = {}
            results_since_save = 0
            last_save = time.perf_counter()

            def _dispatch(slot_idx: int) -> None:
                nonlocal results_since_save
                while True:
                    j, reseed = sched.take(slot_idx)
                    if j is None:
                        return
                    base = base_of(j)
                    slot_dir = str(work_dir / f"TxInOut{slot_idx + 1}")
                    wd = j.scenario.weather_dir
                    try:
                        overlay = ({f.name: str(f) for f in sorted(Path(wd).iterdir())
                                    if f.is_file()} if wd else None)
                    except OSError as exc:
                        _record_failure(j, f"weather_dir unreadable: {exc}")
                        sched.finish(slot_idx, ok=False)
                        results_since_save += 1
                        logger.info("[Scenarios] %d/%d jobs done (%.1fs)", done, len(todo),
                                    time.perf_counter() - t_all)
                        continue
                    extract = partial(
                        _extract_dispatch,
                        jobs={slot_dir: (j.job_id, j.scenario.evaluate)},
                        outputs=outs, series_dir=str(series_dir),
                        observed=(obs_payload if j.scenario.evaluate else None),
                        metrics=tuple(metrics))
                    prepare = partial(
                        _prepare_dispatch,
                        cio_by_dir={slot_dir: j.scenario.cio} if j.scenario.cio else {})
                    fut = executor.submit(
                        _seed_and_run, slot_dir, base, reseed, str(swat_exe),
                        j.param_set.updates, param_file, overlay, prepare, extract,
                        runner, timeout_s, log_q)
                    futures[fut] = (slot_idx, j)
                    return

            def _record_result(j: Job, slot_idx: int, w: WorkerResult) -> int:
                if w is not None and w.ok and isinstance(w.payload, dict):
                    _record_success(j, w)
                    sched.finish(slot_idx, ok=True)
                    return 1
                if w is not None and not w.ok and w.error \
                        and w.error.startswith(_SLOT_LOCKED_PREFIX):
                    sched.mark_slot_unusable(slot_idx)
                    sched.finish(slot_idx, ok=False)
                    _record_failure(j, w.error, w.duration_s)
                    return 1
                if w is not None and not w.ok and w.error \
                        and w.error.startswith(_SEED_FAILED_PREFIX):
                    sched.finish(slot_idx, ok=False)
                    _record_failure(j, _mark_base_bad(j, w.error), w.duration_s)
                    drained = sched.drain_bad_base_jobs()
                    for dj in drained:
                        _record_failure(dj, setup_errors[base_of(dj)])
                    return 1 + len(drained)
                sched.finish(slot_idx, ok=False)
                if w is not None and w.ok:
                    msg = "worker returned no result payload"
                else:
                    msg = w.error if w is not None else "worker returned no result payload"
                _record_failure(j, msg, w.duration_s if w else 0.0)
                return 1

            try:
                for slot_idx in range(n_parallel):
                    _dispatch(slot_idx)

                broken_err = None
                while sched.has_pending() or futures:
                    if not futures:
                        # every slot is unusable: fail the rest with one message
                        for dj in sched.drain_all_pending():
                            _record_failure(dj, _ALL_UNUSABLE_MSG)
                        break
                    done_futures, _ = concurrent.futures.wait(
                        futures, return_when=concurrent.futures.FIRST_COMPLETED)
                    freed_slots = []
                    for fut in done_futures:
                        slot_idx, j = futures.pop(fut)
                        try:
                            w = fut.result()
                        except BrokenProcessPool as exc:
                            broken_err = f"{type(exc).__name__}: {exc}"
                            _record_failure(j, broken_err)
                            results_since_save += 1
                            continue
                        except Exception as exc:  # noqa: BLE001 - unpicklable result
                            w = WorkerResult(False, f"{type(exc).__name__}: {exc}",
                                            0.0, "", None)
                        results_since_save += _record_result(j, slot_idx, w)
                        logger.info("[Scenarios] %d/%d jobs done (%.1fs)", done, len(todo),
                                    time.perf_counter() - t_all)
                        freed_slots.append(slot_idx)
                    if broken_err is not None:
                        # The pool broke: stop dispatching, fail the rest with one message.
                        broken_msg = (f"worker pool broke ({broken_err}); "
                                      f"re-run with resume=True")
                        for fut in list(futures):
                            slot_idx, j = futures.pop(fut)
                            try:
                                w = fut.result()
                            except BrokenProcessPool:
                                _record_failure(j, broken_err)
                            except Exception as exc:  # noqa: BLE001 - unpicklable result
                                w = WorkerResult(False, f"{type(exc).__name__}: {exc}",
                                                0.0, "", None)
                                _record_result(j, slot_idx, w)
                            else:
                                _record_result(j, slot_idx, w)
                        for dj in sched.drain_all_pending():
                            _record_failure(dj, broken_msg)
                        break
                    for slot_idx in freed_slots:
                        _dispatch(slot_idx)
                    if results_since_save >= n_parallel or \
                            time.perf_counter() - last_save >= _SAVE_INTERVAL_S:
                        save()
                        results_since_save = 0
                        last_save = time.perf_counter()
            except BaseException as orig_exc:
                executor.shutdown(wait=False, cancel_futures=True)
                try:
                    save(final=True)
                except Exception as save_exc:  # noqa: BLE001 - preserve original exception
                    logger.warning("[Scenarios] could not save partial results during %s: %s",
                                   type(orig_exc).__name__, save_exc)
                raise
            else:
                executor.shutdown(wait=True)

        save(final=True)
        if cleanup and work_dir.exists():
            _rmtree(work_dir)
        ordered = [results[j.job_id] for j in jobs]
        ids = [r.job_id for r in ordered]
        out_summary = pd.DataFrame(
            [{"job_id": r.job_id, "scenario": r.scenario, "param_set": r.param_set,
              "status": r.status, "error": r.error, "duration_s": r.duration_s,
              "n_rows": r.n_rows,
              "series_file": Path(r.series_path).name if r.series_path else None,
              "evaluated": r.evaluated, "eval_note": r.eval_note}
             for r in ordered], columns=SUMMARY_COLS)
        out_metrics = metrics_df[metrics_df["job_id"].isin(ids)].reset_index(drop=True)
        return BatchResult(res_dir, ordered, out_summary, out_metrics,
                           [r for r in ordered if r.status == "failed"], warns)
