from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from db import build_file_outputs
from utils import iter_excel_files, parse_workbook


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_workbook_path(root: Path, workbook_arg: str | None) -> Path:
    if workbook_arg:
        workbook_path = Path(workbook_arg).expanduser()
        if not workbook_path.is_absolute():
            workbook_path = (root / workbook_path).resolve()
        if not workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {workbook_path}")
        return workbook_path

    candidates = list(iter_excel_files(root))
    if not candidates:
        raise FileNotFoundError(
            "No Excel workbook was found in either the 'data' or 'Data' directory."
        )

    if len(candidates) > 1:
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    return candidates[0]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import headend/channel Excel data and write CSV/JSON outputs."
    )
    parser.add_argument(
        "--workbook",
        help="Optional workbook path. Defaults to the newest .xlsx file in ./data or ./Data.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    configure_logging(verbose=args.verbose)

    logger = logging.getLogger(__name__)
    root = project_root()

    try:
        workbook_path = resolve_workbook_path(root=root, workbook_arg=args.workbook)
        parsed = parse_workbook(workbook_path)
        results = build_file_outputs(root=root, headends_df=parsed.headends, channels_df=parsed.channels)

        logger.info("Workbook imported successfully.")
        logger.info("Processed CSV directory: %s", results["processed_dir"])
        logger.info("Dashboard JSON directory: %s", results["dashboard_data_dir"])
        logger.info("Batch headends: %s", results["headend_rows_in_batch"])
        logger.info("Batch channels: %s", results["channel_rows_in_batch"])
        logger.info("New Headend_ID values created: %s", results["new_headend_ids_assigned"])
        logger.info("Total headends stored: %s", results["headend_rows_total"])
        logger.info("Total channels stored: %s", results["channel_rows_total"])
        logger.info("Total comparison rows generated: %s", results["comparison_rows_total"])
        return 0
    except Exception as exc:  # pragma: no cover - CLI safety path
        logger.exception("ETL import failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
