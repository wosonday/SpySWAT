# spyswat/swat_calib/calibration/validation_runner.py

import logging
from dataclasses import dataclass
import pandas as pd

from spyswat.swat_calib.calibration import CalibrationManager
from spyswat.swat_calib.core.workingFolder_manager import (
    _stamp_output_rch, _check_fresh_output_rch,
)

logger = logging.getLogger(__name__)


@dataclass
class PeriodConfig:
    calib_start: str   # 'YYYY-MM-DD'
    calib_end:   str
    valid_start: str
    valid_end:   str


class ValidationRunner:
    """
    Chay hieu chinh + kiem dinh trong mot lenh.
    Su dung Differential Evolution cho hieu chinh.
    Neu can GLUE song song, dung SWATCalibration.analyze() + run_iteration() truc tiep.
    """

    def __init__(self, project, param_ranges: dict, observed: pd.Series,
                 period: PeriodConfig):
        self.project      = project
        self.param_ranges = param_ranges
        self.observed     = observed
        self.period       = period
        self.manager      = CalibrationManager(project)

    def run(self, metric='nse', method='differential_evolution',
            max_iter=100, reach_id=1,
            output_variable: str = 'FLOW_OUTcms',
            restore: bool = False) -> dict:
        """
        Calibrate, then run SWAT once with the best parameters and score the validation period.

        By default the best parameters STAY in the user's TxtInOut afterwards (a warning is
        logged: applying relative 'r'/'a' changes again would compound on top of them).
        Pass ``restore=True`` to put the original input files back after the validation run.
        The best parameters, calibration/validation metrics and the validation run are
        saved in ``manager.results_dir`` (``<session>_best_params.csv``,
        ``<session>_validation.csv`` and the per-run log) before any restore.

        Returns:
            best_parameters, calibration: {metric: score}, validation: {all metrics}
        """
        # 1. Hieu chinh (calibration period)
        obs_calib = self.observed.loc[self.period.calib_start:self.period.calib_end]
        best_params, calib_score = self._calibrate(
            obs_calib, metric, method, max_iter, reach_id, output_variable
        )

        manager = self.manager
        _, methods, subbasins = manager._parse_spec(self.param_ranges)
        formatted = (manager._format_params(best_params, methods, subbasins)
                     if manager._is_raw(best_params) else best_params)
        self._save_best_params(manager, formatted, subbasins)

        # 2. Ap dung best params va chay SWAT
        if restore:
            manager._backup_state()
        sim_dated = None
        try:
            try:
                self.project.HRU.update_params(formatted)
                out_dir = manager._txinout_dir()
                before = _stamp_output_rch(out_dir) if out_dir is not None else None
                self.project.run()
                if out_dir is not None:
                    _check_fresh_output_rch(out_dir, before)

                sim = self.project.Output.read_rch(
                    columns=['RCH', 'MON', output_variable], reach_id=reach_id
                )[output_variable]

                # 3. Kiem dinh (validation period)
                obs_valid = self.observed.loc[self.period.valid_start:self.period.valid_end]
                obs_a, sim_a = manager._align_series(obs_valid, sim)
                valid_stats = self.project.Statistic.calculate_statistics(obs_a, sim_a)
                if manager.results_dir is not None:
                    sim_dated = manager._to_model_dates(sim, manager._sim_freq(obs_valid))
            except Exception as exc:
                self._log_validation_run(manager, "failed", exc, reach_id, output_variable,
                                         formatted, None, None)
                raise
            self._save_validation(manager, metric, calib_score, valid_stats)
            self._log_validation_run(manager, "ok", None, reach_id, output_variable,
                                     formatted, valid_stats, sim_dated)
        finally:
            if restore:
                manager._restore_state()

        if not restore:
            logger.warning(
                "The TxtInOut folder now contains the CALIBRATED parameters. Applying "
                "relative ('r') or additive ('a') changes again will compound on top of "
                "them; use restore=True to get the original input files back."
            )

        return {
            'best_parameters': best_params,
            'calibration':     {metric: calib_score},
            'validation':      valid_stats,
        }

    # ── result files ──────────────────────────────────────────────────

    @staticmethod
    def _save_best_params(manager, formatted: dict, subbasins: dict) -> None:
        path = manager.session_path("best_params")
        if path is None:
            return
        rows = []
        for name, (value, method) in manager._param_columns(formatted).items():
            subs = subbasins.get(name)
            rows.append([name, manager._fmt(value), method,
                         "" if subs is None else ";".join(str(x) for x in subs)])
        manager._append_csv(path, ["name", "value", "method", "subbasins"], rows)

    @staticmethod
    def _save_validation(manager, metric, calib_score, valid_stats: dict) -> None:
        path = manager.session_path("validation")
        if path is None:
            return
        rows = [["calibration", metric, manager._fmt(calib_score)]]
        rows += [["validation", m, manager._fmt(v)] for m, v in valid_stats.items()]
        manager._append_csv(path, ["period", "metric", "value"], rows)

    @staticmethod
    def _log_validation_run(manager, status, error, reach_id, output_variable,
                            formatted, valid_stats, sim_dated) -> None:
        """Append the validation run to the per-run log (a column clash only warns)."""
        names = manager._logged_metric_names()
        metrics = names if names is not None else list((valid_stats or {}).keys())
        try:
            manager._log_run("sequential", status, error, reach_id, output_variable,
                             formatted, valid_stats, sim_dated, metrics=metrics)
        except ValueError as exc:
            logger.warning(f"[Results] Validation run not added to the run log: {exc}")

    def _calibrate(self, obs_calib, metric, method, max_iter, reach_id, output_variable):
        from spyswat.swat_calib.analysis.calibration import SWATCalibration
        calib = SWATCalibration(self.project)
        self.manager = calib.manager        # same results session as the calibration runs
        result = calib.optimize(
            self.param_ranges, obs_calib,
            method=method, metric=metric,
            max_iter=max_iter, reach_id=reach_id,
            output_variable=output_variable
        )
        return result['best_parameters'], result['best_objective_value']
