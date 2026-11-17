import argparse
from typing import Optional, Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spyswat",
        description="SpySWAT: run the SWAT executable once in the given TxtInOut directory."
    )
    parser.add_argument("--txinout",   required=True, help="Path to TxtInOut directory")
    parser.add_argument("--workingF",  required=True, help="Path to workingFolder directory")
    parser.add_argument("--exe",       required=True, help="Path to SWAT executable")
    parser.add_argument("--params",    default=None, help="Path to swatParam.txt (optional)")
    parser.add_argument("--observed",  default=None,
                        help="Path to observed flow CSV (reserved, currently unused)")
    parser.add_argument("--n_parallel", type=int, default=1, help="Number of parallel runs")
    parser.add_argument("--reach",     type=int, default=1,
                        help="Reach ID (reserved, currently unused)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    from spyswat import SWATProject
    project = SWATProject(args.txinout, args.workingF, args.exe, args.params, args.n_parallel)
    project.run()


if __name__ == "__main__":
    main()
