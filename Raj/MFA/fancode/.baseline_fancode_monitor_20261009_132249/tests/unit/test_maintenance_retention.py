"""
test_maintenance_retention.py – Unit tests for safe operational data retention cleanup (Phase 11).
"""

from __future__ import annotations

from datetime import timedelta
import pytest
from app.database.connection import utc_now
from app.database.models import (
    ChangeEvent,
    Match,
    NotificationBatch,
    NotificationDelivery,
    NotificationEventLink,
    Page,
    ScrapeRun,
    Sport,
    Tour,
    Video,
)
from app.maintenance.retention import DataRetentionCleaner


class TestDataRetentionCleanup:
    def test_dry_run_identifies_expired_records_without_deleting(self, db_session):
        old_time = utc_now() - timedelta(days=60)
        old_run = ScrapeRun(run_type="monitor", status="success", started_at=old_time)
        db_session.add(old_run)

        old_event = ChangeEvent(
            entity_type="MATCH",
            entity_id=1,
            change_type="CREATED",
            detected_at=utc_now() - timedelta(days=120),
        )
        db_session.add(old_event)
        db_session.commit()

        report = DataRetentionCleaner.clean(
            session=db_session,
            dry_run=True,
            scrape_run_days=30,
            change_event_days=90,
        )

        assert report["is_dry_run"] is True
        assert report["deleted_counts"]["scrape_runs"] == 1
        assert report["deleted_counts"]["change_events"] == 1

        # Verify records are NOT deleted
        assert db_session.get(ScrapeRun, old_run.id) is not None
        assert db_session.get(ChangeEvent, old_event.id) is not None

    def test_destructive_cleanup_deletes_expired_operational_data(self, db_session):
        old_time = utc_now() - timedelta(days=45)
        old_run = ScrapeRun(run_type="monitor", status="success", started_at=old_time)
        db_session.add(old_run)

        old_batch = NotificationBatch(
            batch_key="old-batch-001",
            subject="Old digest",
            status="SENT",
            created_at=utc_now() - timedelta(days=100),
        )
        db_session.add(old_batch)
        db_session.commit()

        deliv = NotificationDelivery(
            batch_id=old_batch.id,
            recipient="test@example.com",
            status="SENT",
            attempted_at=utc_now() - timedelta(days=100),
        )
        db_session.add(deliv)
        db_session.commit()

        old_run_id = old_run.id
        old_batch_id = old_batch.id
        deliv_id = deliv.id

        report = DataRetentionCleaner.clean(
            session=db_session,
            dry_run=False,
            scrape_run_days=30,
            notification_days=90,
        )

        assert report["is_dry_run"] is False
        assert report["deleted_counts"]["scrape_runs"] == 1
        assert report["deleted_counts"]["notification_batches"] == 1
        assert report["deleted_counts"]["notification_deliveries"] == 1

        # Verify records ARE deleted
        assert db_session.get(ScrapeRun, old_run_id) is None
        assert db_session.get(NotificationBatch, old_batch_id) is None
        assert db_session.get(NotificationDelivery, deliv_id) is None

    def test_core_entities_are_never_deleted_during_cleanup(self, db_session):
        old_time = utc_now() - timedelta(days=365)
        sport = Sport(name="Cricket", slug="cricket", source_url="https://fancode.com/cricket", first_seen_at=old_time)
        tour = Tour(name="IPL", slug="ipl", source_url="https://fancode.com/ipl", first_seen_at=old_time)
        match = Match(title="Match 1", slug="match-1", source_url="https://fancode.com/match-1", first_seen_at=old_time)
        video = Video(title="Highlight 1", slug="video-1", source_url="https://fancode.com/video-1", first_seen_at=old_time)
        page = Page(url="https://fancode.com/p", canonical_url="https://fancode.com/p", page_type="HOME", first_seen_at=old_time)

        db_session.add_all([sport, tour, match, video, page])
        db_session.commit()

        # Run aggressive 1-day retention purge
        report = DataRetentionCleaner.clean(session=db_session, dry_run=False, scrape_run_days=1)

        # Core entities must still exist untouched!
        assert db_session.get(Sport, sport.id) is not None
        assert db_session.get(Tour, tour.id) is not None
        assert db_session.get(Match, match.id) is not None
        assert db_session.get(Video, video.id) is not None
        assert db_session.get(Page, page.id) is not None
        assert "NOT MODIFIED" in report["core_entities_status"]
