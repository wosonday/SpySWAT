"""Run many scenarios (GCMs, land-use maps, ...) x many parameter sets in parallel.

    from spyswat.swat_calib.scenarios import (
        Scenario, ParamSet, ScenarioBatch, BatchResult)
"""
from .model import Scenario, ParamSet, Job, RunResult
from .batch import ScenarioBatch, BatchResult

__all__ = ["Scenario", "ParamSet", "Job", "RunResult", "ScenarioBatch", "BatchResult"]
