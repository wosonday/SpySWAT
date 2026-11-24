"""Parallel calibration, evaluation, and sensitivity using the 0.3.0 facade.

Placeholder Windows paths: edit them before running. Everything that runs SWAT
must stay under ``if __name__ == "__main__":`` because Windows spawns worker
processes that re-import this script.
"""
import pandas as pd
from spyswat import SWATProject


def main():
    # 1. Initialize project with parallel workers
    project = SWATProject(
        txinout_dir="D:/SWAT/TxtInOut",
        working_dir="D:/SWAT/working",
        swat_exe="D:/SWAT/swat_rev688.exe",
        param_file="D:/SWAT/params.txt",
        n_parallel=8,
    )

    # 2. Load observations and define parameter space (name.ext format)
    obs = pd.read_csv(
        "D:/SWAT/observed_flow.csv",
        index_col="date",
        parse_dates=True,
    )["flow"]
    observed = {("FLOW_OUTcms", 1): obs}

    param_ranges = {
        "CN2.mgt":     ((35.0, 98.0), "r"),
        "ALPHA_BF.gw": (0.0, 1.0),
        "GW_DELAY.gw": (30.0, 450.0),
        "ESCO.hru":    (0.01, 1.0),
        "SOL_AWC.sol": ((0.01, 0.5), "r"),
    }

    # 3. Run parallel GLUE calibration with calib/valid periods + regression sensitivity
    res = project.calibration(
        param_ranges,
        observed=observed,
        calib_period=("2005-01-01", "2010-12-31"),
        valid_period=("2011-01-01", "2015-12-31"),
        algorithm="glue",
        metric="nse",
        metrics=("nse", "kge", "pbias", "r2"),
        n_samples=1000,
        threshold=0.5,
        seed=42,
        sensitivity=True,
    )

    print(f"Best run #{res.best_run_id} | score (NSE): {res.best_score:.4f}")
    print("\nBest run metrics (calib + valid):")
    print(res.metrics)

    print("\nRegression sensitivity (from initial sample, 0 extra SWAT runs):")
    print(res.sensitivity)

    # 4. Inspect top 10 behavioral parameter sets and session outputs
    top10 = res.top(10)
    print(f"\nExtracted {len(top10)} top parameter sets for scenarios.")
    print(f"Session saved to: {res.session_dir}")

    # 5. Optional: recompute regression sensitivity later from the saved session
    sens_reloaded = project.sensitivity(from_session=res.session_dir)
    print(sens_reloaded)

    # 6. Optional: Morris sensitivity analysis (parallel)
    morris = project.sensitivity(
        param_ranges,
        observed=observed,
        method="morris",
        n_trajectories=10,
        metric="nse",
        calib_period=("2005-01-01", "2010-12-31"),
    )
    print("\nMorris indices:")
    print(morris["morris_indices"])


if __name__ == "__main__":
    main()
