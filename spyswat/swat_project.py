import os
from pathlib import Path
from typing import Optional, Union
import logging

from spyswat.swat_calib.core import TxInOut, OutputFileManager, HRUManager, WorkingFolderManager
from spyswat.swat_calib.io import SWATParam, FileCIO
from spyswat.swat_calib.run import SWATRun
from spyswat.swat_calib.analysis import SWATAnalysis
from spyswat.logger import Logger

logger = logging.getLogger(__name__)




class SWATProject:
    """
        >>> project = SWATProject(
        ...     txinout_dir="D:/SWAT/my_project/TxtInOut",
        ...     working_dir="D:/SWAT/my_project/working",
        ...     swat_exe="D:/SWAT/swat2012.exe"
        ... )
        >>> project.run()
        >>> df = project.Output.read_rch()

    Parameter editing (``project.HRU``, ``read_params_values``) needs a
    parameter definition file:

        >>> project = SWATProject(
        ...     txinout_dir="D:/SWAT/my_project/TxtInOut",
        ...     working_dir="D:/SWAT/my_project/working",
        ...     swat_exe="D:/SWAT/swat2012.exe",
        ...     param_file="D:/SWAT/my_project/params.txt",
        ... )
        >>> project.HRU.update_params({'CN2.mgt': [(75, 'v')]})
    """

    def __init__(
            self,
            txinout_dir: Union[str, Path],
            working_dir: Union[str, Path],
            swat_exe:    Union[str, Path],
            param_file:  Optional[Union[str, Path]] = None,
            n_parallel: int = 1
            ):
        n_parallel = self._validate_n_parallel(n_parallel)

        self.txinout        = TxInOut(str(txinout_dir))
        self.working_folder = Path(working_dir)
        # param_file is optional: parameter functions are unavailable without it.
        self.param_file     = SWATParam(param_file) if param_file else None
        self.swat_exe       = SWATRun(swat_exe)

        # ==========================================

        self._hru_manager     = (HRUManager(self.txinout, self.param_file)
                                 if self.param_file is not None else None)
        self._file_cio        = FileCIO(self.txinout)
        self._file_cio_stamp  = self._cio_stamp()
        self._output_manager  = OutputFileManager(self.txinout)


        # ============= Statistic ======================
        self._statistic     = SWATAnalysis(self)

        self._wf_manager = WorkingFolderManager(
            txinout      = self.txinout,
            working_dir  = self.working_folder,
            n_parallel   = n_parallel,
            param_path   = param_file
        )
        #============================================

        # Initialise logging once for the main process.
        # Workers bypass this via Logger.init_worker(queue) in run_parallel.
        Logger.init(log_dir="logs", log_file="run.log")

        logger.info(f"SWAT Project initialized: {self.txinout}")
        logger.info(f"Found {self.txinout.number_hru} HRUs in {self.txinout.number_sub} subbasins")

    @staticmethod
    def _validate_n_parallel(n_parallel) -> int:
        """Return n_parallel as an int >= 1 (int-like strings are converted)."""
        if isinstance(n_parallel, bool):
            raise ValueError(f"n_parallel must be an integer >= 1, got {n_parallel!r}")
        if isinstance(n_parallel, str):
            try:
                n_parallel = int(n_parallel.strip())
            except ValueError:
                raise ValueError(
                    f"n_parallel must be an integer >= 1, got {n_parallel!r}") from None
        if not isinstance(n_parallel, int):
            raise ValueError(f"n_parallel must be an integer >= 1, got {n_parallel!r}")
        if n_parallel < 1:
            raise ValueError(f"n_parallel must be an integer >= 1, got {n_parallel!r}")
        return n_parallel

    def _require_param_file(self) -> None:
        if self._hru_manager is None:
            raise RuntimeError(
                "No parameter file was given: pass param_file=<path to params file> "
                "to SWATProject to use parameter functions (HRU, read_params_values)."
            )

    # ================ Read data =============================
    def worker(self, index: int) -> "SWATProject":
        worker_dirs = self._wf_manager.worker_dirs
        if not worker_dirs:
            raise RuntimeError("Worker dirs not initialised. Call setup() first.")
        if index < 1 or index > len(worker_dirs):
            raise IndexError(f"Worker index {index} out of range. "
                             f"{len(worker_dirs)} workers available (1..{len(worker_dirs)}).")

        target_dir = worker_dirs[index - 1]  # TxInOut1 → index 0
        return SWATProject(
            txinout_dir=target_dir,
            working_dir=self.working_folder,
            swat_exe= self.swat_exe.swat_exe_path,
            param_file=self.param_file.param_path if self.param_file is not None else None,
            n_parallel=1
            )

    def get_date_range(self, freq: str='D', year_start_non_skip: bool=False):
        return self.FileCIO.get_date_range_sim(freq, year_start_non_skip)

    def read_params_values(self, param: list):
        self._require_param_file()
        return self._hru_manager.read_multi_hru_param_values(param)

    def run(self):
        try:
            return self.swat_exe.run(self.txinout.directory)
        finally:
            # SWAT rewrote the output files: drop everything cached from earlier runs.
            self._output_manager.invalidate()

    def info(self):
        """Print project information"""
        print(f"TxtInOut: {self.txinout.directory}")
        print("=" * 20)
        print(f"SWAT Executable: {self.swat_exe.swat_exe_path}")
        self.txinout.info()

    def __repr__(self):
        return (f"SWATProject('{self.txinout.directory}', "
                f"\n hrs={self.txinout.number_hru}, "
                f"\n subs={self.txinout.number_sub})")

    @property
    def HRU(self):
        self._require_param_file()
        return self._hru_manager

    @property
    def Output(self):
        return self._output_manager

    @property
    def Statistic(self):
        return self._statistic

    @property
    def FileCIO(self):
        """file.cio, re-read whenever the file changed on disk (same rule as the output
        cache), so IPRINT and the simulation dates never disagree with read_rch."""
        stamp = self._cio_stamp()
        if stamp != self._file_cio_stamp:
            self._file_cio = FileCIO(self.txinout)
            self._file_cio_stamp = stamp
        return self._file_cio

    def _cio_stamp(self):
        try:
            st = os.stat(self._file_cio.file_path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    @property
    def WorkingFolder(self):
        return self._wf_manager

    # ── Visualization ────────────────────────────────────────────────────

    def fig_viewer(
        self,
        red_reaches=None,
        output_path=None,
        open_browser: bool = True,
    ):
        """
        Build an interactive HTML viewer for fig.fig.

        Args:
            red_reaches:  List of hydrograph/reach IDs to highlight in red.
            output_path:  Save path for HTML file.
                          Default: <TxtInOut directory> / 'fig_viewer.html'.
            open_browser: Open the viewer in default browser after saving.

        Returns:
            Path to the saved HTML file.

        Example:
            project.fig_viewer(red_reaches=[32, 33])
        """
        from spyswat.swat_calib.visualization import FigViewer

        out = output_path or (self.txinout.directory / "fig_viewer.html")
        viewer = FigViewer(self.txinout.directory)
        return viewer.build(
            red_reaches  = red_reaches,
            output_path  = out,
            open_browser = open_browser,
        )

    # ── 0.3.0 facade (API-4) ─────────────────────────────────────────────

    def _warmup_end(self):
        """First day after the warm-up: ``Timestamp(IYR + NYSKIP, 1, 1)`` from file.cio."""
        import pandas as pd
        year_start = getattr(self.FileCIO, "year_start", None)
        if year_start is None:
            return None
        return pd.Timestamp(int(year_start), 1, 1)

    @staticmethod
    def _serialize_period(period):
        """Return ``period`` with Timestamp/date bounds as ISO strings (JSON-safe).

        ``calib_period``/``valid_period`` may be ``(start, end)`` pairs of strings,
        ``pd.Timestamp``, ``datetime`` or ``date`` (the vocabulary). ``session.json``
        is written with ``json.dumps``, so any Timestamp/date bound must be
        stringified first.
        """
        if period is None:
            return None
        from datetime import date, datetime
        import numpy as np

        def _iso(v):
            if isinstance(v, (datetime, date)):   # includes pd.Timestamp
                return v.isoformat()
            if isinstance(v, np.datetime64):
                return str(v)
            return v
        return [_iso(period[0]), _iso(period[1])]

    def calibration(self, param_ranges, observed, calib_period, valid_period=None, *,
                    algorithm="glue", metric="nse",
                    metrics=("nse", "kge", "pbias", "r2"), weights=None, outputs=None,
                    step=None, agg=None, n_parallel=None, seed=None, results_dir=None,
                    session=None, resume=True, sensitivity=True, param_methods=None,
                    param_subbasins=None, **algorithm_options):
        """Run a calibration and return a :class:`CalibrationResult`.

        ``algorithm`` is one of ``"glue"``, ``"pso"``, ``"de"``, ``"dds"``. The
        whole simulation period is run on every evaluation; the objective uses
        ``calib_period`` while ``calib_period`` and ``valid_period`` are both
        scored and stored. TxtInOut is never modified. Every run is stored in a
        session folder under ``results_dir`` (default
        ``<working_dir>/calibration_results``) and the best run's series is
        evaluated back into ``res.metrics``.
        """
        from spyswat.swat_calib.analysis.algorithms import (
            GLUE, ParallelDE, PSOCalibration, DDSCalibration,
        )
        from spyswat.swat_calib.analysis.algorithms.dds import _resolve_seed
        from spyswat.swat_calib.calibration import CalibrationManager
        from spyswat.swat_calib.calibration.param_spec import format_params
        from spyswat.swat_calib.calibration.result import (
            CalibrationResult, RawParamsStore, best_run, evaluate_best_metrics,
            raw_params_for_run, regression_for_store,
        )
        from spyswat.swat_calib.calibration.scoring import (
            normalise_observed, check_weights, preflight, _validate_config,
            _resolve_metrics, _flatten_sites,
        )
        from spyswat.swat_calib.calibration.session_store import SessionStore
        from spyswat.swat_calib.calibration.replay import ReplayCursor, check_param_order
        import numpy as np

        if algorithm not in ("glue", "pso", "de", "dds"):
            raise ValueError(
                f"algorithm must be one of glue/pso/de/dds, got {algorithm!r}")

        manager = CalibrationManager(self)

        bounds, methods, subbasins = manager._parse_spec(param_ranges)
        methods = {**methods, **(param_methods or {})}
        subbasins = {**subbasins, **(param_subbasins or {})}
        param_names = list(bounds)

        observed_dict, outputs_dict = normalise_observed(observed, outputs)
        observed_sites = sorted(observed_dict)
        weights_norm = check_weights(weights, list(observed_dict))
        preflight(observed_dict, calib_period)
        _validate_config(valid_period, step, agg)
        reported = _resolve_metrics(metric, metrics)

        n_parallel = (n_parallel if n_parallel is not None
                      else self.WorkingFolder.n_parallel)
        n_parallel = self._validate_n_parallel(n_parallel)
        if algorithm != "dds":
            if n_parallel != self.WorkingFolder.n_parallel:
                self.WorkingFolder.n_parallel = n_parallel
                manager.setup_parallel(overwrite=True)
            else:
                manager.setup_parallel(overwrite=False)

        results_dir = Path(results_dir) if results_dir is not None else (
            self.working_folder / "calibration_results")
        sites = _flatten_sites(outputs_dict)           # gauged + ungauged sites

        # ── session resolution (fresh vs. resume by replay) ──────────────
        session_dir = self._resolve_session_dir(
            results_dir, session, algorithm, metric)
        session_exists = (session_dir / "session.json").exists()

        def _signature():
            """The session signature, built exactly as on creation (decision 8)."""
            return {
                "algorithm": algorithm,
                "metric": metric,
                "metrics": list(reported),
                "seed": seed,
                "param_ranges": param_ranges,
                "methods": methods,
                "subbasins": subbasins,
                "calib_period": self._serialize_period(calib_period),
                "valid_period": self._serialize_period(valid_period),
                "weights": {f"{v}@{r}": w for (v, r), w in weights_norm.items()},
                "step": step,
                "agg": agg,
                "n_parallel": n_parallel,
                "outputs": {v: list(rs) for v, rs in outputs_dict.items()},
                "observed_sites": [[v, r] for (v, r) in observed_sites],
                "observed_hash": _hash_observed(observed_dict),
                "options": dict(algorithm_options),
                "on_failure": algorithm_options.get("on_failure", "raise"),
                "numpy_version": np.__version__,
            }

        replay = None
        if session_exists:
            if not resume:
                raise FileExistsError(f"Session already exists at {session_dir}")
            # Resume by replay: open the committed store and validate the
            # configuration BEFORE anything is (re)written (decision 9).
            store = SessionStore.open(session_dir)
            stored_seed = (store.signature or {}).get("seed")
            if seed is None:
                if stored_seed is None:
                    raise ValueError(
                        "cannot resume: the stored session has no seed; pass "
                        "seed= explicitly to continue."
                    )
                seed = stored_seed
            else:
                seed = _resolve_seed(seed)
            check_param_order(store, param_ranges)
            store.check_signature(_signature())   # ValueError listing differences
            replay = ReplayCursor(store)
            wrapped = RawParamsStore(store)
        else:
            if session is not None and resume:
                raise FileNotFoundError(
                    f"No session at {session_dir}: session.json not found"
                )
            seed = _resolve_seed(seed)            # decision 9: resolve first
            store = SessionStore(session_dir, signature=_signature(),
                                 param_names=param_names, sites=sites)
            wrapped = RawParamsStore(store)

        algo_cls = {"glue": GLUE, "pso": PSOCalibration,
                    "de": ParallelDE, "dds": DDSCalibration}[algorithm]
        algo = algo_cls(manager)

        try:
            algo.run(
                param_ranges, observed,
                metric=metric, metrics=metrics, weights=weights, outputs=outputs,
                calib_period=calib_period, valid_period=valid_period,
                step=step, agg=agg, store=wrapped, seed=seed, replay=replay,
                param_methods=param_methods, param_subbasins=param_subbasins,
                **algorithm_options,
            )
            store.flush()
            runs = store.runs()
            best_run_id, best_score = best_run(runs, metric)
            best_raw = raw_params_for_run(runs, best_run_id)

            metrics_table = evaluate_best_metrics(
                store, observed_dict, observed_sites, best_run_id,
                calib_period=calib_period, valid_period=valid_period,
                metrics=reported, freq=self.FileCIO.get_iprint(), step=step,
                agg=agg, warmup_end=self._warmup_end(),
            )

            sens_df, sens_status = self._regression_sensitivity(
                store, param_ranges, param_names, sensitivity)

            store.write_best(best_raw)
            if sens_df is not None:
                store.write_sensitivity(sens_df)
        finally:
            store.close()

        best_params = format_params(best_raw, methods, subbasins)
        return CalibrationResult(
            best_params=best_params, best_score=best_score,
            best_run_id=best_run_id, metric=metric, runs=runs,
            metrics=metrics_table, sensitivity=sens_df,
            sensitivity_status=sens_status, session_dir=session_dir, seed=seed,
            algorithm=algorithm, methods=methods, subbasins=subbasins,
            sites=observed_sites, store=store,
        )

    @staticmethod
    def _regression_sensitivity(store, param_ranges, param_names, sensitivity):
        """Regression sensitivity on ``is_initial`` rows; errors become a status.

        Constant/collinear parameters are filtered out before the regression and
        reinserted with ``coef=0.0, t_stat=0.0, p_value=NaN`` (decision 11) instead
        of raising.
        """
        import warnings
        from spyswat.swat_calib.calibration.result import (
            regression_for_store, constant_parameters, reinsert_constant,
        )

        if not sensitivity:
            return None, ""

        constant = constant_parameters(store, param_ranges, param_names)
        usable = [n for n in param_names if n not in constant]
        try:
            sens = regression_for_store(
                store, {name: param_ranges[name] for name in usable})
            if constant:
                sens = reinsert_constant(sens, constant)
            n_used = sens.attrs.get("n_used", len(sens))
            r2 = sens.attrs.get("r2")
            k = len(param_names)
            if n_used < max(20, 3 * k):
                warnings.warn(
                    f"regression sensitivity used only {n_used} runs "
                    f"(recommend at least {max(20, 3 * k)}); treat the ranking as indicative.",
                    stacklevel=2,
                )
            if r2 is not None and r2 < 0.3:
                warnings.warn(
                    f"regression sensitivity explains little variance (r2={r2:.3f}).",
                    stacklevel=2,
                )
            return sens, "ok"
        except ValueError as exc:
            if "Not enough usable runs" in str(exc):
                return None, "insufficient runs"
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001 - sensitivity must never break calibration
            return None, str(exc)

    @staticmethod
    def _resolve_session_dir(results_dir, session, algorithm, metric):
        """The session folder path for a calibration (nothing is created here)."""
        from datetime import datetime
        results_dir = Path(results_dir)
        if session is not None:
            return results_dir / str(session)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{algorithm}_{metric}"
        session_dir = results_dir / base
        n = 2
        while (session_dir / "session.json").exists():
            session_dir = results_dir / f"{base}_{n}"
            n += 1
        return session_dir

    def evaluate(self, sim, observed, periods=None, **kw):
        """Pure evaluation with the project's print step and warm-up end filled in."""
        from spyswat.swat_calib.analysis import evaluate as evaluate_fn
        kw.setdefault("freq", self.FileCIO.get_iprint())
        kw.setdefault("warmup_end", self._warmup_end())
        return evaluate_fn(sim, observed, periods, **kw)

    def sensitivity(self, param_ranges=None, observed=None, method="morris", *,
                    from_session=None, **options):
        """Sensitivity analysis, dispatching to :class:`SWATSensitivity`.

        ``from_session`` recomputes the regression sensitivity of a saved session
        without running SWAT. Otherwise ``method`` is one of ``"oat"``,
        ``"morris"``, ``"morris_salib"``, ``"sobol"`` or ``"regression"`` (the
        last runs a GLUE/LHS sample first, then the regression sensitivity).
        """
        from spyswat.swat_calib.analysis import SWATSensitivity
        from spyswat.swat_calib.analysis.regression_sensitivity import regression_sensitivity
        from spyswat.swat_calib.calibration.session_store import SessionStore

        if from_session is not None:
            store = SessionStore.open(from_session)
            sig = store.signature or {}
            param_ranges = sig.get("param_ranges")
            if param_ranges is None:
                raise ValueError("session has no 'param_ranges' in its signature")
            runs = store.runs()
            if "is_initial" in runs.columns:
                runs = runs[runs["is_initial"].astype(bool)]
            return regression_sensitivity(runs, param_ranges, score_col="score")

        sens = SWATSensitivity(self)
        if method == "oat":
            return sens.one_at_a_time(param_ranges, observed=observed, **options)
        if method == "morris":
            return sens.morris_method(param_ranges, observed=observed, **options)
        if method == "morris_salib":
            return sens.morris_salib(param_ranges, observed=observed, **options)
        if method == "sobol":
            return sens.sobol_method(param_ranges, observed=observed, **options)
        if method == "regression":
            if param_ranges is None or observed is None:
                raise ValueError("regression sensitivity needs param_ranges and observed")
            calib_period = options.pop("calib_period", None)
            return self.calibration(param_ranges, observed, calib_period,
                                    algorithm="glue", sensitivity=True,
                                    **options).sensitivity
        raise ValueError(
            "method must be one of oat/morris/morris_salib/sobol/regression, "
            f"got {method!r}")

    def scenarios(self, scenarios, param_sets, outputs, observed=None,
                  results_dir=None, **options):
        """Run scenarios x parameter sets (``ScenarioBatch.run``).

        ``param_sets`` may mix :class:`ParamSet`, a :class:`CalibrationResult`
        (its best) and the lists returned by ``CalibrationResult.top`` /
        ``CalibrationResult.select``.
        """
        from spyswat.swat_calib.calibration.result import CalibrationResult
        from spyswat.swat_calib.scenarios import ScenarioBatch
        from spyswat.swat_calib.scenarios.model import ParamSet

        results_dir = (Path(results_dir) if results_dir is not None
                       else (self.working_folder / "scenario_results"))
        if isinstance(param_sets, (ParamSet, CalibrationResult)):
            resolved = _to_param_sets(param_sets)
        else:
            resolved = []
            for ps in param_sets:
                resolved.extend(_to_param_sets(ps))
        batch = ScenarioBatch(self, results_dir)
        return batch.run(scenarios, resolved, outputs=outputs, observed=observed,
                         **options)

    def apply(self, x, methods=None, subbasins=None):
        """Write parameters into TxtInOut (the only facade call that does).

        ``x`` is a :class:`ParamSet`, a :class:`CalibrationResult` (its best
        parameters) or a raw ``{name: value}`` dict (formatted with ``methods`` /
        ``subbasins``, default absolute ``"v"``). A dict that already carries
        non-``"v"`` methods without an explicit ``methods=`` raises. A warning is
        logged: the change is not restored automatically.
        """
        from spyswat.swat_calib.calibration.param_spec import format_params, is_raw
        from spyswat.swat_calib.calibration.result import CalibrationResult, raw_params
        from spyswat.swat_calib.scenarios.model import ParamSet

        if isinstance(x, ParamSet):
            updates = x.updates
        elif isinstance(x, CalibrationResult):
            updates = x.best_params
        elif isinstance(x, dict):
            if is_raw(x):
                updates = format_params(x, methods, subbasins)
            else:
                if methods is None:
                    non_v = _non_v_methods(x)
                    if non_v:
                        raise ValueError(
                            "apply() got a dict with non-'v' methods "
                            f"({sorted(non_v)}) but no methods=; pass methods= or a "
                            "ParamSet / CalibrationResult."
                        )
                if methods is not None or subbasins is not None:
                    # Reformatted with the explicit methods/subbasins (decision 4).
                    updates = format_params(raw_params(x), methods, subbasins)
                else:
                    updates = x
        else:
            raise TypeError(
                "apply() takes a ParamSet, CalibrationResult or dict, got "
                f"{type(x).__name__}")

        self.HRU.update_params(updates)
        logger.warning("apply() modified TxtInOut parameters (not restored automatically).")
        return updates


def _hash_observed(observed_dict) -> str:
    """SHA-256 over sorted ``(variable, reach)`` + ISO index + float64 bytes (decision 8)."""
    import hashlib
    import numpy as np
    import pandas as pd

    h = hashlib.sha256()
    for var, reach in sorted(observed_dict):
        series = observed_dict[(var, reach)]
        h.update(f"{var}\0{reach}\0".encode("utf-8"))
        idx = pd.DatetimeIndex(series.index)
        for ts in idx:
            h.update(ts.isoformat().encode("utf-8"))
            h.update(b"\0")
        vals = np.array(series.to_numpy(dtype="<f8"), dtype="<f8", copy=True)
        vals[vals == 0.0] = 0.0                    # normalise -0.0 -> 0.0
        h.update(vals.tobytes())
    return h.hexdigest()


def _to_param_sets(x):
    """Normalise a ``scenarios`` param-set entry into a list of :class:`ParamSet`."""
    from spyswat.swat_calib.calibration.result import CalibrationResult
    from spyswat.swat_calib.scenarios.model import ParamSet

    if isinstance(x, ParamSet):
        return [x]
    if isinstance(x, CalibrationResult):
        return [x.best_param_set()]
    if isinstance(x, (list, tuple)):
        out = []
        for item in x:
            out.extend(_to_param_sets(item))
        return out
    raise TypeError(
        "param_sets entries must be a ParamSet, CalibrationResult or a list of "
        f"them, got {type(x).__name__}")


def _non_v_methods(updates):
    """Names of parameters whose formatted dict uses a method other than ``"v"``."""
    out = []
    for name, groups in updates.items():
        if isinstance(groups, tuple):
            groups = [groups]
        for g in groups:
            method = g[1] if len(g) > 1 else "v"
            if method != "v":
                out.append(name)
                break
    return out