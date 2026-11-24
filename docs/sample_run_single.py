"""Single-run SWAT workflow using the 0.3.0 SWATProject facade.

Placeholder Windows paths: edit them before running. Keep code under
``if __name__ == "__main__":`` because Windows spawns child processes.
"""
import pandas as pd
from spyswat import SWATProject


def main():
    # 1. Initialize project
    project = SWATProject(
        txinout_dir="D:/SWAT/TxtInOut",
        working_dir="D:/SWAT/working",
        swat_exe="D:/SWAT/swat_rev688.exe",
        param_file="D:/SWAT/params.txt",
        n_parallel=1,
    )

    # 2. Inspect project info
    project.info()

    # 3. Read current parameter values (always use name.ext keys)
    current = project.read_params_values(["CN2.mgt", "ALPHA_BF.gw", "ESCO.hru"])
    print(current)

    # 4. Explicitly apply parameters to TxtInOut (project.apply is the only
    #    facade call that modifies TxtInOut)
    project.apply(
        {"CN2.mgt": 75.0, "ALPHA_BF.gw": 0.05, "ESCO.hru": 0.1},
        methods={"CN2.mgt": "v", "ALPHA_BF.gw": "v", "ESCO.hru": "r"},
    )

    # 5. Run SWAT once
    project.run()

    # 6. Read simulated discharge at reach 1
    sim = project.Output.read_rch(
        columns=["RCH", "MON", "FLOW_OUTcms"],
        reach_id=1,
    )["FLOW_OUTcms"]
    print(f"Mean simulated flow: {sim.mean():.2f} m3/s")

    # 7. Evaluate against observations by period (pure: no SWAT run)
    obs = pd.read_csv(
        "D:/SWAT/observed_flow.csv",
        index_col="date",
        parse_dates=True,
    )["flow"]

    ev = project.evaluate(
        {("FLOW_OUTcms", 1): sim},
        {("FLOW_OUTcms", 1): obs},
        periods={
            "calib": ("2005-01-01", "2010-12-31"),
            "valid": ("2011-01-01", "2015-12-31"),
        },
        metrics=("nse", "kge", "pbias", "r2"),
    )
    print(ev.table)


if __name__ == "__main__":
    main()
