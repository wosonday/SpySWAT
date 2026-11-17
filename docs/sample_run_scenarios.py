"""
Run several scenarios (here: four land-use TxtInOut folders) x several parameter
tables in parallel, and export flow / sediment series plus NSE / KGE / PBIAS.

Placeholder Windows paths: edit them before running. The code must stay under
``if __name__ == "__main__":`` because Windows spawns the worker processes.
"""
import pandas as pd

from spyswat import SWATProject
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch

SWAT_EXE = r"D:\RSWAT\_SWAT_RUN\swat_637_101.exe"
PARAM_FILE = r"D:\RSWAT\swatParam.txt"
BASE_TXTINOUT = r"D:\Project\SWAT\LUC1992\TxtInOut"
WORKING_DIR = r"D:\Project\SWAT\work"
RESULTS_DIR = r"D:\Project\SWAT\results"
PARAM_CSV = r"D:\Project\SWAT\best_param_sediment.csv"   # columns PARAM, method, MIN, SUBBASIN, TIME
OBS_CSV = r"D:\Project\SWAT\obs_flow_reach51.csv"         # columns date, flow
# Scenario and parameter set names must not contain "__" (two underscores).
LUC = ["LUC1992", "LUC2000", "LUC2010", "LUC2020"]


def main():
    project = SWATProject(BASE_TXTINOUT, WORKING_DIR, SWAT_EXE, PARAM_FILE, n_parallel=4)

    # A scenario is a complete TxtInOut folder ...
    scenarios = [Scenario(name, txinout_dir=rf"D:\Project\SWAT\{name}\TxtInOut") for name in LUC]
    # ... or weather files overlaid on the base TxtInOut (files already in SWAT format).
    # Future / GCM scenarios use evaluate=False: no observations exist, so no metrics and
    # no observation-step check (they may even use another print step); series still written.
    scenarios.append(Scenario("GCM_ssp245", weather_dir=r"D:\GCM\ssp245", evaluate=False,
                              cio={"IYR": 2030, "NBYR": 20, "NYSKIP": 0}))

    # One parameter set per value of TIME; every row is one pass (same parameter may repeat).
    table = pd.read_csv(PARAM_CSV)
    param_sets = [
        ParamSet.from_dataframe(table[table["TIME"] == t], f"par{t}",
                                param="PARAM", method="method", value="MIN", sub="SUBBASIN")
        for t in (1, 2, 3)
    ]

    obs = pd.read_csv(OBS_CSV, parse_dates=["date"], index_col="date")["flow"]
    batch = ScenarioBatch(project, RESULTS_DIR)
    result = batch.run(
        scenarios, param_sets,
        # pairs=[("LUC1992", "par1"), ("LUC2020", "par3")],   # default: full product
        outputs={"FLOW_OUTcms": [51, 55, 73], "SED_OUTtons": [51, 57, 77]},
        observed={("FLOW_OUTcms", 51): obs},
        metrics=("nse", "kge", "pbias"),
        # resume=True skips finished jobs; it raises if outputs/metrics/observations or a
        # scenario / parameter set definition changed (use a new RESULTS_DIR or resume=False).
        # Observations must have the same step (daily/monthly) as the simulation print step.
        # Historical scenarios (evaluate=True, default) get metrics against the observations;
        # a scenario that does not overlap them gets none (see evaluated / eval_note in
        # summary.csv). Future scenarios (evaluate=False) never get metrics.
        resume=True,
    )

    print(result.summary)
    print(result.metrics)
    for r in result.failed:
        print("FAILED", r.job_id, r.error)
    result.to_csv("SED_OUTtons", rf"{RESULTS_DIR}\sediment_all.csv")
    result.to_csv("FLOW_OUTcms", rf"{RESULTS_DIR}\flow_all.csv")


if __name__ == "__main__":
    main()
