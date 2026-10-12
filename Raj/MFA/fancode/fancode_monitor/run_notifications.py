"""
run_notifications.py – Command-line interface for FanCode Alerting / Notification Engine (Phase 9).

Usage:
  python run_notifications.py [--dry-run]
  python run_notifications.py --entity-type MATCH --severity IMPORTANT
  python run_notifications.py --scrape-run-id 10 --limit 50
  python run_notifications.py --output-dir data/notifications --backend console
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.database.connection import get_session, init_db
from app.notifications.email_backend import (
    ConsoleEmailBackend,
    TestEmailBackend,
)
from app.notifications.service import NotificationService
from app.notifications.smtp_backend import SmtpEmailBackend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_notifications")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FanCode Notification / Alerting CLI (Phase 9)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate notification run and render digests without sending or updating notified status",
    )
    parser.add_argument(
        "--entity-type",
        type=str,
        default=None,
        help="Filter unnotified events by entity type (e.g. MATCH, VIDEO, TOUR, SPORT)",
    )
    parser.add_argument(
        "--severity",
        type=str,
        default=None,
        help="Filter unnotified events by severity (e.g. CRITICAL, IMPORTANT, INFO)",
    )
    parser.add_argument(
        "--change-type",
        type=str,
        default=None,
        help="Filter unnotified events by change type (e.g. CREATED, STATUS_CHANGED, UPDATED, REMOVED)",
    )
    parser.add_argument(
        "--scrape-run-id",
        type=int,
        default=None,
        help="Filter events belonging to a specific scrape_run_id",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum unnotified change events to process in this run",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["console", "test", "smtp"],
        default=None,
        help="Override configured notification email backend",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save rendered HTML and text digest files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print execution summary as machine-readable JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    init_db()

    with get_session() as session:
        # Resolve backend override if provided
        backend = None
        output_dir = args.output_dir or getattr(settings, "NOTIFICATION_OUTPUT_DIR", None)

        if args.backend == "console":
            backend = ConsoleEmailBackend(output_dir=output_dir)
        elif args.backend == "test":
            backend = TestEmailBackend()
        elif args.backend == "smtp":
            backend = SmtpEmailBackend(
                host=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_USE_TLS,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )
        elif output_dir:
            backend = ConsoleEmailBackend(output_dir=output_dir)

        service = NotificationService(session=session, backend=backend)

        logger.info(
            "Starting Notification Run (dry_run=%s, entity_type=%s, severity=%s, limit=%d)...",
            args.dry_run,
            args.entity_type,
            args.severity,
            args.limit,
        )

        result = service.run(
            limit=args.limit,
            entity_type=args.entity_type,
            severity=args.severity,
            change_type=args.change_type,
            scrape_run_id=args.scrape_run_id,
            dry_run=args.dry_run,
        )

        if args.json:
            summary = {
                "events_inspected": result.events_inspected,
                "events_eligible": result.events_eligible,
                "events_filtered_out": result.events_filtered_out,
                "events_deduplicated": result.events_deduplicated,
                "batches_created": result.batches_created,
                "emails_sent": result.emails_sent,
                "deliveries_failed": result.deliveries_failed,
                "is_dry_run": result.is_dry_run,
                "errors": result.errors,
            }
            print(json.dumps(summary, indent=2))
        else:
            if result.batches_created == 0 and result.events_eligible == 0:
                print("\nNo notification-worthy changes found.")
            else:
                print(f"\nNotification Run Summary (Dry-Run: {result.is_dry_run}):")
                print(f"  Events Inspected:   {result.events_inspected}")
                print(f"  Eligible Events:    {result.events_eligible}")
                print(f"  Filtered Out:       {result.events_filtered_out}")
                print(f"  Deduplicated:       {result.events_deduplicated}")
                print(f"  Batches Created:    {result.batches_created}")
                print(f"  Emails Dispatched:  {result.emails_sent}")
                print(f"  Failures / Errors:  {result.deliveries_failed}")

                if result.batches:
                    for i, b in enumerate(result.batches, 1):
                        print(f"\n  Batch #{i} [{b.status.value}]:")
                        print(f"    Subject: {b.subject}")
                        print(f"    Events:  {len(b.events)}")
                        print(f"    Entities: {len(b.grouped_entities)}")

        return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
