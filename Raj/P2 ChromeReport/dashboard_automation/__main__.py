from __future__ import annotations

import argparse
from pathlib import Path

from .config import DashboardAutomationConfig
from .logging_utils import configure_logging
from .pipeline import process_new_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weekly TV dashboard data automation")
    parser.add_argument(
        "command",
        choices=("process", "watch"),
        nargs="?",
        default="process",
        help="Run one processing pass or keep watching the data folder",
    )
    parser.add_argument(
        "--base-dir",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Project root directory",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=[".xlsm"],
        help="Excel file extensions to process. Default: .xlsm",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = DashboardAutomationConfig(base_dir=args.base_dir, supported_extensions=tuple(args.extensions))
    logger = configure_logging(config)

    if args.command == "watch":
        from .watch import watch_data_folder

        process_new_files(config, logger=logger)
        watch_data_folder(config, logger)
        return

    process_new_files(config, logger=logger)


if __name__ == "__main__":
    main()
