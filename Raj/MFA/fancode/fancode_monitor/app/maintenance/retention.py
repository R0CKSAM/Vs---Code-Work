"""
retention.py – Operational Data Retention & Safe Cleanup for FanCode Monitor (Phase 11).

Provides policy-driven cleanup of historical operational audit records:
- scrape_runs
- change_events
- notification_batches (and associated deliveries and event links)

STRICT RULE: NEVER deletes or modifies core entity tables:
- sports
- tours
- matches
- videos
- pages
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.connection import utc_now
from app.database.models import (
    ChangeEvent,
    NotificationBatch,
    NotificationDelivery,
    NotificationEventLink,
    ScrapeRun,
)

logger = logging.getLogger(__name__)

CORE_TABLES_PRESERVED = ["sports", "tours", "matches", "videos", "pages"]


class DataRetentionCleaner:
    """Executes safe, transactional retention cleanup of operational audit tables."""

    @classmethod
    def clean(
        cls,
        session: Session,
        dry_run: bool = True,
        scrape_run_days: Optional[int] = None,
        change_event_days: Optional[int] = None,
        notification_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculates and optionally deletes expired operational rows.
        Returns a dictionary with row counts and cutoff details.
        """
        now = utc_now()
        s_days = scrape_run_days or getattr(settings, "SCRAPE_RUN_RETENTION_DAYS", 30)
        c_days = change_event_days or getattr(settings, "CHANGE_EVENT_RETENTION_DAYS", 90)
        n_days = notification_days or getattr(settings, "NOTIFICATION_RETENTION_DAYS", 90)

        s_cutoff = now - timedelta(days=s_days)
        c_cutoff = now - timedelta(days=c_days)
        n_cutoff = now - timedelta(days=n_days)

        report: Dict[str, Any] = {
            "is_dry_run": dry_run,
            "retention_policies": {
                "scrape_runs_days": s_days,
                "change_events_days": c_days,
                "notifications_days": n_days,
            },
            "cutoffs": {
                "scrape_runs": s_cutoff.isoformat(),
                "change_events": c_cutoff.isoformat(),
                "notifications": n_cutoff.isoformat(),
            },
            "deleted_counts": {
                "scrape_runs": 0,
                "change_events": 0,
                "notification_batches": 0,
                "notification_deliveries": 0,
                "notification_event_links": 0,
            },
            "core_entities_status": "NOT MODIFIED (sports, tours, matches, videos, pages preserved)",
        }

        # 1. Scrape Runs
        s_query = select(ScrapeRun.id).where(ScrapeRun.started_at < s_cutoff)
        s_ids = list(session.scalars(s_query).all())
        report["deleted_counts"]["scrape_runs"] = len(s_ids)

        # 2. Change Events
        c_query = select(ChangeEvent.id).where(ChangeEvent.detected_at < c_cutoff)
        c_ids = list(session.scalars(c_query).all())
        report["deleted_counts"]["change_events"] = len(c_ids)

        # 3. Notification Batches & Associated Records
        n_query = select(NotificationBatch.id).where(NotificationBatch.created_at < n_cutoff)
        n_batch_ids = list(session.scalars(n_query).all())
        report["deleted_counts"]["notification_batches"] = len(n_batch_ids)

        if n_batch_ids:
            del_query = select(NotificationDelivery.id).where(NotificationDelivery.batch_id.in_(n_batch_ids))
            report["deleted_counts"]["notification_deliveries"] = len(list(session.scalars(del_query).all()))

            link_query = select(NotificationEventLink.id).where(NotificationEventLink.batch_id.in_(n_batch_ids))
            report["deleted_counts"]["notification_event_links"] = len(list(session.scalars(link_query).all()))

        if not dry_run:
            logger.info("Executing retention cleanup: deleting expired records...")
            # Delete in child-to-parent order for clean FK handling
            if n_batch_ids:
                session.execute(delete(NotificationDelivery).where(NotificationDelivery.batch_id.in_(n_batch_ids)))
                session.execute(delete(NotificationEventLink).where(NotificationEventLink.batch_id.in_(n_batch_ids)))
                session.execute(delete(NotificationBatch).where(NotificationBatch.id.in_(n_batch_ids)))

            if c_ids:
                session.execute(delete(ChangeEvent).where(ChangeEvent.id.in_(c_ids)))

            if s_ids:
                session.execute(delete(ScrapeRun).where(ScrapeRun.id.in_(s_ids)))

            session.commit()
            logger.info("Retention cleanup committed successfully.")

        return report

    @classmethod
    def format_report_text(cls, report: Dict[str, Any]) -> str:
        """Formats the cleanup report into human-readable text."""
        mode_str = "[DRY-RUN] Simulation Only" if report.get("is_dry_run") else "[LIVE] Executed Deletion"
        counts = report.get("deleted_counts", {})
        policies = report.get("retention_policies", {})

        lines = [
            "===========================================================",
            f"   FanCode Monitor — Data Retention Cleanup {mode_str}",
            "===========================================================",
            f"  Retention Thresholds : scrape_runs={policies.get('scrape_runs_days')}d, change_events={policies.get('change_events_days')}d, notifications={policies.get('notifications_days')}d",
            "-----------------------------------------------------------",
            "  Records Identified for Purge:",
            f"    scrape_runs              : {counts.get('scrape_runs', 0)}",
            f"    change_events            : {counts.get('change_events', 0)}",
            f"    notification_batches     : {counts.get('notification_batches', 0)}",
            f"    notification_deliveries  : {counts.get('notification_deliveries', 0)}",
            f"    notification_event_links : {counts.get('notification_event_links', 0)}",
            "-----------------------------------------------------------",
            f"  Core Entity Tables       : {report.get('core_entities_status')}",
            "===========================================================",
        ]
        return "\n".join(lines)
