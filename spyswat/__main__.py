import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        prog="spyswat",
        description="SpySWAT — SWAT model automatic calibration tool"
    )
    parser.add_argument("--txinout",   required=True, help="Path to TxtInOut directory")
    parser.add_argument("--workingF",   required=True, help="Path to workingFolder directory")
    parser.add_argument("--exe",       required=True, help="Path to SWAT executable")
    parser.add_argument("--params",    required=True, help="Path to swatParam.txt")
    parser.add_argument("--observed",  required=True, help="Path to observed flow CSV")
    parser.add_argument("--n_parallel",  required=True, help="Number of parallel runs")
    parser.add_argument("--reach",     type=int, default=1, help="Reach ID")
    args = parser.parse_args()

    from spyswat import SWATProject
    project = SWATProject(args.txinout,args.workingF, args.exe, args.params, args.n_parallel)
    project.run()

if __name__ == "__main__":
    main()