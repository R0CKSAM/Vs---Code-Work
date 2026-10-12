"""
run_change_detection.py – Standalone CLI runner for FanCode Change Detection Engine.

Usage:
    python run_change_detection.py [--dry-run] [--entity-type TYPE] [--complete-snapshot]
"""

import argparse
import logging
import sys
from typing import Optional

from app.change_detection.detector import ChangeDetector
from app.change_detection.models import EntityType
from app.database.connection import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_change_detection")


def main() -> int:
    parser = argparse.ArgumentParser(description="FanCode Change Detection Engine (Phase 8)")
    parser.add_argument("--dry-run", action="store_true", help="Preview detected changes without persisting")
    parser.add_argument(
        "--entity-type",
        choices=["MATCH", "SPORT", "TOUR", "VIDEO", "ALL"],
        default="ALL",
        help="Entity category to run detection against (default: ALL)",
    )
    parser.add_argument(
        "--complete-snapshot",
        action="store_true",
        help="Treat incoming dataset as authoritative complete snapshot (enables REMOVED events)",
    )
    parser.add_argument(
        "--scrape-run-id",
        type=int,
        default=None,
        help="Optional scrape_run_id to associate events with",
    )
    args = parser.parse_args()

    logger.info("Initializing FanCode Change Detection Engine...")
    logger.info(
        "Mode: dry_run=%s, entity_type=%s, complete_snapshot=%s, scrape_run_id=%s",
        args.dry_run,
        args.entity_type,
        args.complete_snapshot,
        args.scrape_run_id,
    )

    with get_session() as session:
        detector = ChangeDetector(session=session)

        # In standalone run, if comparing without new scrape input, compare existing
        # entities against themselves or report current event summary
        result = detector.detect_all(
            matches_data=[],
            sports_data=[],
            tours_data=[],
            videos_data=[],
            scrape_run_id=args.scrape_run_id,
            complete_snapshot=args.complete_snapshot,
            dry_run=args.dry_run,
        )

        logger.info("Change Detection Complete.")
        logger.info(
            "Checked: %d | Created: %d | Updated: %d | Status: %d | Removed: %d | Ignored: %d",
            result.entities_checked,
            result.created_events,
            result.updated_events,
            result.status_events,
            result.removed_events,
            result.ignored_changes,
        )
        if result.events:
            logger.info("Generated %d events:", len(result.events))
            for ev in result.events[:10]:
                logger.info(
                    "  [%s] %s (ID %s) %s -> %s (sev=%s)",
                    ev.change_type,
                    ev.entity_type,
                    ev.entity_id,
                    ev.field_name or "ALL",
                    ev.new_value,
                    ev.severity,
                )
            if len(result.events) > 10:
                logger.info("  ... and %d more events", len(result.events) - 10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
