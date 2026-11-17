"""Run scenarios x parameter sets over the parallel worker folders.

The calling script must be guarded by ``if __name__ == "__main__":`` (Windows spawns
worker processes that re-import it).
"""
import multiprocessing
import os
import time
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from spyswat.logger import Logger
from spyswat.swat_calib.core import TxInOut, OutputFileManager
from spyswat.swat_calib.core.workingFolder_manager import WorkingFolderManager
from spyswat.swat_calib.io import FileCIO

from .model import Job, ParamSet, RunResult, Scenario

logger = Logger.get_logger(__name__)

SUMMARY_COLS = ["job_id", "scenario", "param_set", "status", "error",
                "duration_s", "n_rows", "series_file"]
METRIC_COLS = ["job_id", "scenario", "param_set", "variable", "reach", "metric", "value"]
WORK_SUBDIR = "_scenario_batch"


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
    job_id = jobs[str(worker_dir)]
    table = _build_table(worker_dir, outputs)
    fname = f"{job_id}.csv"
    final = os.path.join(series_dir, fname)
    tmp = final + f".{os.getpid()}.tmp"
    table.to_csv(tmp)
    os.replace(tmp, final)

    rows: List[tuple] = []
    if observed:
        from spyswat.swat_calib.analysis import SWATAnalysis
        stats = SWATAnalysis(None)
        for (variable, reach), (obs_idx, obs_val) in observed.items():
            obs = pd.Series(obs_val, index=pd.DatetimeIndex(obs_idx))
            sim = table[f"{variable}@{reach}"]
            common = obs.index.intersection(sim.index)
            if len(common) == 0:
                raise ValueError(f"no common dates between observations and simulation "
                                 f"for {variable}@{reach}")
            res = stats.calculate_statistics(obs.loc[common], sim.loc[common], list(metrics))
            for m, val in res.items():
                rows.append((variable, int(reach), m, float(val)))
    return {"n_rows": int(len(table)), "series_file": fname, "metrics": rows}


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
    os.replace(tmp, path)


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

    The batch works in ``<project working dir>/_scenario_batch`` so the project's own
    worker folders are left alone. Needs ``project.param_file`` only when a ParamSet
    has updates. If the inputs behind a name change, use a new ``results_dir`` (or
    ``resume=False``): resume trusts names, not contents.
    """

    def __init__(self, project, results_dir):
        self.project = project
        self.results_dir = Path(results_dir)

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
            runner=None) -> BatchResult:
        """
        Args:
            outputs:  {variable: [reach ids]} read from output.rch.
            observed: {(variable, reach): Series with a DatetimeIndex}; metrics are only
                      computed for these (each must also be in ``outputs``).
            pairs:    explicit [(scenario_name, param_set_name)]; default = full product.
            resume:   skip jobs already 'ok' in summary.csv (series file present).
            runner:   picklable ``runner(worker_dir)`` replacing the SWAT executable
                      (used by tests).
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

        proj = self.project
        param_file = proj.param_file.param_path if proj.param_file is not None else None
        if param_file is None and any(j.param_set.updates for j in jobs):
            raise ValueError("The project has no param_file but a ParamSet has updates")
        n_parallel = proj._wf_manager.n_parallel
        swat_exe = proj.swat_exe.swat_exe_path
        base_default = str(proj.txinout.directory)
        work_dir = Path(proj.working_folder) / WORK_SUBDIR

        res_dir = self.results_dir
        series_dir = res_dir / "series"
        series_dir.mkdir(parents=True, exist_ok=True)
        summary_path, metrics_path = res_dir / "summary.csv", res_dir / "metrics.csv"
        summary = _read_csv_or_empty(summary_path, SUMMARY_COLS)
        metrics_df = _read_csv_or_empty(metrics_path, METRIC_COLS)
        rows = {r["job_id"]: r for r in summary.to_dict("records")}

        def save():
            _atomic_csv(pd.DataFrame(list(rows.values()), columns=SUMMARY_COLS), summary_path)
            _atomic_csv(metrics_df, metrics_path)

        results: Dict[str, RunResult] = {}
        todo: List[Job] = []
        for j in jobs:
            old = rows.get(j.job_id)
            sf = series_dir / f"{j.job_id}.csv"
            if resume and old is not None and old["status"] == "ok" and sf.is_file():
                n = old["n_rows"]
                results[j.job_id] = RunResult(
                    j.job_id, j.scenario.name, j.param_set.name, "skipped", None, 0.0,
                    int(n) if pd.notna(n) else 0, str(sf))
            else:
                todo.append(j)
        if len(results):
            logger.info("[Scenarios] resume: skipping %d finished job(s)", len(results))

        groups: Dict[str, List[Job]] = {}
        for j in todo:
            groups.setdefault(str(j.scenario.txinout_dir or base_default), []).append(j)

        done = 0
        t_all = time.perf_counter()
        for base, gjobs in groups.items():
            k = min(n_parallel, len(gjobs))
            wf = None
            setup_error = None
            try:
                wf = WorkingFolderManager(TxInOut(base), work_dir, n_parallel=k,
                                          param_path=param_file)
                wf.setup(overwrite=True)
            except Exception as exc:  # noqa: BLE001
                setup_error = f"setup of {base} failed: {type(exc).__name__}: {exc}"
                logger.error("[Scenarios] %s", setup_error)

            for i in range(0, len(gjobs), k):
                chunk = gjobs[i:i + k]
                setup_error_chunk = None
                if setup_error is not None:
                    wres = [None] * len(chunk)
                else:
                    dirs = [str(d) for d in wf.worker_dirs[:len(chunk)]]
                    overlays = []
                    for j in chunk:
                        wd = j.scenario.weather_dir
                        overlays.append(
                            {f.name: str(f) for f in sorted(Path(wd).iterdir()) if f.is_file()}
                            if wd else None)
                    extract = partial(
                        _extract_dispatch,
                        jobs={d: j.job_id for d, j in zip(dirs, chunk)},
                        outputs=outs, series_dir=str(series_dir),
                        observed=obs_payload, metrics=tuple(metrics))
                    prepare = partial(
                        _prepare_dispatch,
                        cio_by_dir={d: j.scenario.cio for d, j in zip(dirs, chunk)
                                    if j.scenario.cio})
                    try:
                        wres = wf.run_parallel(
                            swat_exe, param_sets=[j.param_set.updates for j in chunk],
                            overlays=overlays, prepare=prepare, extract=extract,
                            runner=runner, timeout_s=timeout_s)
                    except Exception as exc:  # noqa: BLE001
                        err = f"{type(exc).__name__}: {exc}"
                        logger.error("[Scenarios] chunk failed: %s", err)
                        wres = [None] * len(chunk)
                        setup_error_chunk = err

                for idx, j in enumerate(chunk):
                    w = wres[idx]
                    sf = series_dir / f"{j.job_id}.csv"
                    if w is not None and w.ok and isinstance(w.payload, dict):
                        p = w.payload
                        rr = RunResult(j.job_id, j.scenario.name, j.param_set.name, "ok",
                                       None, float(w.duration_s), int(p["n_rows"]), str(sf))
                        new = pd.DataFrame(
                            [(j.job_id, j.scenario.name, j.param_set.name, v, r, m, val)
                             for v, r, m, val in p["metrics"]], columns=METRIC_COLS)
                        metrics_df = pd.concat(
                            [metrics_df[metrics_df["job_id"] != j.job_id], new],
                            ignore_index=True)
                    else:
                        if w is None:
                            msg = setup_error or setup_error_chunk
                        elif w.ok:
                            msg = "worker returned no result payload"
                        else:
                            msg = w.error
                        rr = RunResult(j.job_id, j.scenario.name, j.param_set.name, "failed",
                                       msg, float(w.duration_s) if w else 0.0, 0, None)
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
                        "series_file": sf.name if rr.status == "ok" else None}
                done += len(chunk)
                save()
                logger.info("[Scenarios] %d/%d jobs done (%.1fs)", done, len(todo),
                            time.perf_counter() - t_all)

        if not todo:
            save()
        ordered = [results[j.job_id] for j in jobs]
        ids = [r.job_id for r in ordered]
        out_summary = pd.DataFrame(
            [{"job_id": r.job_id, "scenario": r.scenario, "param_set": r.param_set,
              "status": r.status, "error": r.error, "duration_s": r.duration_s,
              "n_rows": r.n_rows,
              "series_file": Path(r.series_path).name if r.series_path else None}
             for r in ordered], columns=SUMMARY_COLS)
        out_metrics = metrics_df[metrics_df["job_id"].isin(ids)].reset_index(drop=True)
        return BatchResult(res_dir, ordered, out_summary, out_metrics,
                           [r for r in ordered if r.status == "failed"])
