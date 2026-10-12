"""
test_database_fresh_install.py – Phase 12 Fresh Database Installation & Integrity Validation.

Verifies:
- Clean initialization of a completely new SQLite database from scratch.
- Presence and correctness of all 10 core production tables.
- Foreign key constraints, relationships, and cascade behaviors.
- Successful initial monitoring cycle with mock data on the fresh database.
- Safe second monitoring cycle without data corruption or duplicates.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base, utc_now
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
from app.database.repositories import (
    ChangeEventsRepository,
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService


class TestDatabaseFreshInstallValidation:
    """Validates complete database bootstrap and schema integrity from an empty state."""

    @pytest.fixture
    def fresh_engine(self, tmp_path):
        """Creates a completely new SQLite database file."""
        db_file = tmp_path / "fresh_fancode.db"
        engine = create_engine(f"sqlite:///{db_file}", echo=False)
        Base.metadata.create_all(bind=engine)
        yield engine
        engine.dispose()

    @pytest.fixture
    def fresh_session(self, fresh_engine):
        """Yields an active session bound to the fresh engine."""
        session_factory = sessionmaker(bind=fresh_engine, expire_on_commit=False)
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def test_all_ten_core_tables_created(self, fresh_engine):
        """Verifies that all 10 required database tables are created upon initialization."""
        inspector = inspect(fresh_engine)
        table_names = set(inspector.get_table_names())

        expected_tables = {
            "sports",
            "tours",
            "matches",
            "videos",
            "pages",
            "change_events",
            "scrape_runs",
            "notification_batches",
            "notification_deliveries",
            "notification_event_links",
        }

        missing = expected_tables - table_names
        assert not missing, f"Missing required database tables on fresh installation: {missing}"

    def test_foreign_keys_and_cascade_constraints(self, fresh_session):
        """Verifies ORM cascade deletion behavior for notification batches and events."""
        # 1. Create a scrape run and change event
        scrape_run = ScrapeRun(run_type="monitor", status="success")
        fresh_session.add(scrape_run)
        fresh_session.commit()

        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=1,
            external_id="match-val-1",
            change_type="CREATED",
            new_value="India vs Australia",
            scrape_run_id=scrape_run.id,
        )
        fresh_session.add(event)
        fresh_session.commit()

        # 2. Create batch with delivery and link
        batch = NotificationBatch(
            batch_key="test-batch-cascade",
            subject="Alert Test",
            event_count=1,
            recipient_count=1,
        )
        fresh_session.add(batch)
        fresh_session.commit()

        delivery = NotificationDelivery(
            batch_id=batch.id,
            recipient="test@fancode.local",
            status="SENT",
            provider="test",
        )
        link = NotificationEventLink(
            batch_id=batch.id,
            change_event_id=event.id,
        )
        fresh_session.add_all([delivery, link])
        fresh_session.commit()

        assert len(batch.deliveries) == 1
        assert len(batch.event_links) == 1

        # 3. Deleting batch must cascade delete delivery and event link
        fresh_session.delete(batch)
        fresh_session.commit()

        remaining_deliveries = fresh_session.query(NotificationDelivery).filter_by(batch_id=batch.id).all()
        remaining_links = fresh_session.query(NotificationEventLink).filter_by(batch_id=batch.id).all()
        assert len(remaining_deliveries) == 0
        assert len(remaining_links) == 0

        # Change event itself should remain intact
        persisted_event = fresh_session.query(ChangeEvent).filter_by(id=event.id).first()
        assert persisted_event is not None

    def test_first_cycle_data_persistence_and_change_detection(self, fresh_session):
        """Verifies that an initial monitoring cycle on a fresh DB populates data, change events, and notifications."""
        sports_repo = SportsRepository(fresh_session)
        tours_repo = ToursRepository(fresh_session)
        matches_repo = MatchesRepository(fresh_session)
        events_repo = ChangeEventsRepository(fresh_session)
        runs_repo = ScrapeRunsRepository(fresh_session)

        # 1. Start run
        run = runs_repo.create_run(run_type="monitor")

        # 2. Persist core entities
        sport = sports_repo.upsert(name="Cricket", slug="cricket", source_url="https://fancode.com/cricket")
        tour = tours_repo.upsert(name="T20 Trophy", slug="t20-trophy", sport_id=sport.id, source_url="https://fancode.com/tour/t20")
        match = matches_repo.upsert(
            external_id="match-fresh-100",
            title="Team A vs Team B",
            slug="team-a-vs-team-b",
            status="UPCOMING",
            venue="Eden Gardens",
            sport_id=sport.id,
            tour_id=tour.id,
            source_url="https://fancode.com/match/100",
        )
        fresh_session.commit()

        # 3. Create change event
        event = events_repo.create(
            entity_type="MATCH",
            entity_id=match.id,
            external_id="match-fresh-100",
            change_type="CREATED",
            new_value="Team A vs Team B",
            severity="IMPORTANT",
            scrape_run_id=run.id,
        )
        fresh_session.commit()

        # 4. Dispatch notification
        backend = TestEmailBackend()
        service = NotificationService(session=fresh_session, backend=backend)
        result = service.run(scrape_run_id=run.id)

        assert result.emails_sent == 1
        assert len(backend.sent_messages) == 1
        assert "Team A vs Team B" in backend.sent_messages[0].subject or "change" in backend.sent_messages[0].subject.lower()

        # Finish run
        runs_repo.finish_run(run.id, status="success", records_processed=1, records_created=1)
        fresh_session.commit()

        # Assert DB state
        assert fresh_session.query(Match).count() == 1
        assert fresh_session.query(ChangeEvent).count() == 1
        assert fresh_session.query(NotificationBatch).count() == 1

    def test_second_cycle_idempotency_without_corruption(self, fresh_session):
        """Verifies that running an identical second cycle on the seeded DB causes zero duplicates or corrupted state."""
        matches_repo = MatchesRepository(fresh_session)
        events_repo = ChangeEventsRepository(fresh_session)
        runs_repo = ScrapeRunsRepository(fresh_session)

        # Pre-seed Cycle 1: initial run, match, and event
        run1 = runs_repo.create_run(run_type="monitor")
        match = matches_repo.upsert(
            external_id="match-fresh-100",
            title="Team A vs Team B",
            slug="team-a-vs-team-b",
            status="UPCOMING",
            venue="Eden Gardens",
            source_url="https://fancode.com/match/100",
        )
        event1 = events_repo.create(
            entity_type="MATCH",
            entity_id=match.id,
            external_id="match-fresh-100",
            change_type="CREATED",
            new_value="Team A vs Team B",
            severity="IMPORTANT",
            scrape_run_id=run1.id,
        )
        fresh_session.commit()

        # Cycle 2: Same match data
        run2 = runs_repo.create_run(run_type="monitor")
        match = matches_repo.upsert(
            external_id="match-fresh-100",
            title="Team A vs Team B",
            slug="team-a-vs-team-b",
            status="UPCOMING",
            venue="Eden Gardens",
            source_url="https://fancode.com/match/100",
        )
        fresh_session.commit()

        # Check existing event deduplication
        existing_ev = events_repo.find_existing_event(
            entity_type="MATCH",
            entity_id=match.id,
            change_type="CREATED",
            field_name=None,
            new_value="Team A vs Team B",
        )
        assert existing_ev is not None  # Correctly identifies duplicate

        # Notification service has nothing new to dispatch
        backend = TestEmailBackend()
        service = NotificationService(session=fresh_session, backend=backend)
        res = service.run(scrape_run_id=run2.id)
        assert res.emails_sent == 0
        assert len(backend.sent_messages) == 0

        runs_repo.finish_run(run2.id, status="success", records_processed=1, records_updated=0)
        fresh_session.commit()

        # Confirm count hasn't grown
        assert fresh_session.query(Match).count() == 1
        assert fresh_session.query(ChangeEvent).count() == 1
