"""
Run several scenarios (here: four land-use TxtInOut folders + one GCM overlay)
x several parameter sets in parallel, and export flow / sediment series plus metrics.

Placeholder Windows paths: edit them before running. The code must stay under
``if __name__ == "__main__":`` because Windows spawns the worker processes.
"""
import pandas as pd

from spyswat import SWATProject
from spyswat.swat_calib.calibration.result import CalibrationResult
from spyswat.swat_calib.scenarios import ParamSet, Scenario

SWAT_EXE = "D:/SWAT/swat_rev688.exe"
PARAM_FILE = "D:/SWAT/params.txt"
BASE_TXTINOUT = "D:/SWAT/LUC1992/TxtInOut"
WORKING_DIR = "D:/SWAT/working"
RESULTS_DIR = "D:/SWAT/scenario_results"
PARAM_CSV = "D:/SWAT/best_param_sediment.csv"   # columns PARAM, method, MIN, SUBBASIN, TIME
OBS_CSV = "D:/SWAT/obs_flow_reach51.csv"         # columns date, flow
# Scenario and parameter set names must not contain "__" (two underscores).
LUC = ["LUC1992", "LUC2000", "LUC2010", "LUC2020"]


def main():
    project = SWATProject(BASE_TXTINOUT, WORKING_DIR, SWAT_EXE, PARAM_FILE, n_parallel=4)

    # A scenario is a complete TxtInOut folder ...
    scenarios = [
        Scenario(name, txinout_dir=f"D:/SWAT/{name}/TxtInOut")
        for name in LUC
    ]
    # ... or weather files overlaid on the base TxtInOut (files already in SWAT format).
    # Future / GCM scenarios use evaluate=False: no observations exist, so no metrics and
    # no observation-step check (they may even use another print step); series still written.
    scenarios.append(
        Scenario(
            "GCM_ssp245",
            weather_dir="D:/SWAT/GCM/ssp245",
            evaluate=False,
            cio={"IYR": 2030, "NBYR": 20, "NYSKIP": 0},
        )
    )

    # Parameter sets from CSV, or directly from a saved CalibrationResult (res.top(5))
    table = pd.read_csv(PARAM_CSV)
    param_sets = [
        ParamSet.from_dataframe(
            table[table["TIME"] == t],
            f"par{t}",
            param="PARAM",
            method="method",
            value="MIN",
            sub="SUBBASIN",
        )
        for t in (1, 2, 3)
    ]
    # Example using a saved calibration session:
    # cal_res = CalibrationResult.load("D:/SWAT/working/calibration_results/20261125_120000_glue_nse")
    # param_sets = cal_res.top(5)

    obs = pd.read_csv(OBS_CSV, parse_dates=["date"], index_col="date")["flow"]
    result = project.scenarios(
        scenarios,
        param_sets,
        outputs={"FLOW_OUTcms": [51, 55, 73], "SED_OUTtons": [51, 57, 77]},
        observed={("FLOW_OUTcms", 51): obs},
        results_dir=RESULTS_DIR,
        metrics=("nse", "kge", "pbias"),
        # pairs=[("LUC1992", "par1"), ("LUC2020", "par3")],   # default: full product
        resume=True,
    )

    print(result.summary)
    print(result.metrics)
    for r in result.failed:
        print("FAILED", r.job_id, r.error)
    result.to_csv("SED_OUTtons", f"{RESULTS_DIR}/sediment_all.csv")
    result.to_csv("FLOW_OUTcms", f"{RESULTS_DIR}/flow_all.csv")


if __name__ == "__main__":
    main()
