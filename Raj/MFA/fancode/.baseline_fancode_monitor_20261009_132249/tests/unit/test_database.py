"""
test_database.py – Unit test suite for Database & Persistence Layer (Phase 2).

Tests:
1. database engine creation
2. database initialization (tables created)
3. table creation verification
4. sports insert
5. sports retrieval by id, external_id, slug
6. sports upsert behavior
7. tour insert
8. tour/sport relationship
9. match insert
10. match/tour/sport relationships
11. match upsert behavior (by external_id and source_url)
12. video insert
13. video relationships (sport, tour, match)
14. page insert
15. page canonical URL uniqueness enforcement
16. page upsert behavior
17. page mark_checked behavior
18. change event insert
19. unnotified change retrieval & mark_notified
20. scrape run creation
21. scrape run completion & statistics
22. transaction rollback on error
23. duplicate prevention via upsert
24. timestamp behavior (UTC timezone awareness)
25. JSON metadata storage and retrieval
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Base, create_db_engine, init_db, utc_now
from app.database.migrations import get_existing_tables, verify_schema
from app.database.models import (
    ChangeEvent,
    Match,
    Page,
    ScrapeRun,
    Sport,
    Tour,
    Video,
)
from app.database.repositories import (
    ChangeEventsRepository,
    MatchesRepository,
    PagesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
    VideosRepository,
)
from tests.factories import (
    build_change_event_data,
    build_match_data,
    build_page_data,
    build_scrape_run_data,
    build_sport_data,
    build_tour_data,
    build_video_data,
)


@pytest.fixture
def test_engine():
    """Create an isolated, in-memory SQLite engine for each test."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Provide an isolated database session rolled back after test."""
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


class TestDatabaseFoundation:
    """Test engine, table creation, schema verification, and migrations."""

    def test_engine_creation(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        assert engine is not None
        assert engine.url.database == ":memory:"


    def test_database_initialization(self, test_engine) -> None:
        init_db(test_engine)
        tables = get_existing_tables(test_engine)
        assert len(tables) >= 7
        assert "sports" in tables
        assert "tours" in tables
        assert "matches" in tables
        assert "videos" in tables
        assert "pages" in tables
        assert "change_events" in tables
        assert "scrape_runs" in tables

    def test_verify_schema(self, test_engine) -> None:
        assert verify_schema(test_engine) is True


class TestSportsRepository:
    """Test sports repository operations."""

    def test_sports_insert_and_retrieval(self, db_session: Session) -> None:
        repo = SportsRepository(db_session)
        sport = repo.create(**build_sport_data())
        assert sport.id is not None
        assert sport.name == "Cricket"

        by_id = repo.get_by_id(sport.id)
        assert by_id is not None
        assert by_id.slug == "cricket"

        by_ext = repo.get_by_external_id("sport-101")
        assert by_ext is not None
        assert by_ext.id == sport.id

        by_slug = repo.get_by_slug("cricket")
        assert by_slug is not None
        assert by_slug.id == sport.id

    def test_sports_upsert_existing(self, db_session: Session) -> None:
        repo = SportsRepository(db_session)
        sport1 = repo.create(**build_sport_data(description="Old description"))
        orig_id = sport1.id

        # Upsert with new description
        sport2 = repo.upsert(
            external_id="sport-101",
            name="Cricket",
            slug="cricket",
            source_url="https://www.fancode.com/cricket",
            description="Updated description",
        )
        assert sport2.id == orig_id
        assert sport2.description == "Updated description"


class TestToursRepository:
    """Test tours repository and relationship with sport."""

    def test_tour_insert_and_sport_relationship(self, db_session: Session) -> None:
        sports_repo = SportsRepository(db_session)
        tours_repo = ToursRepository(db_session)

        sport = sports_repo.create(**build_sport_data())
        tour = tours_repo.create(**build_tour_data(sport_id=sport.id))

        assert tour.id is not None
        assert tour.sport_id == sport.id
        assert tour.sport.name == "Cricket"
        assert len(sport.tours) == 1

    def test_tour_upsert(self, db_session: Session) -> None:
        tours_repo = ToursRepository(db_session)
        t1 = tours_repo.create(**build_tour_data(status="UPCOMING"))
        orig_id = t1.id

        t2 = tours_repo.upsert(
            external_id="tour-202",
            name="IPL 2026",
            slug="ipl-2026",
            source_url="https://www.fancode.com/tours/ipl-2026",
            status="LIVE",
        )
        assert t2.id == orig_id
        assert t2.status == "LIVE"


class TestMatchesRepository:
    """Test matches repository, foreign keys, and upsert."""

    def test_match_insert_and_relationships(self, db_session: Session) -> None:
        sports_repo = SportsRepository(db_session)
        tours_repo = ToursRepository(db_session)
        matches_repo = MatchesRepository(db_session)

        sport = sports_repo.create(**build_sport_data())
        tour = tours_repo.create(**build_tour_data(sport_id=sport.id))
        match = matches_repo.create(**build_match_data(tour_id=tour.id, sport_id=sport.id))

        assert match.id is not None
        assert match.tour.name == "Indian Premier League 2026"
        assert match.sport.name == "Cricket"

    def test_match_upsert_by_external_id(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)
        m1 = matches_repo.create(**build_match_data(status="SCHEDULED"))
        orig_id = m1.id

        m2 = matches_repo.upsert(
            external_id="match-303",
            source_url="https://www.fancode.com/matches/mi-vs-csk-2026",
            title="MI vs CSK",
            slug="mi-vs-csk-2026",
            status="LIVE",
            score_summary="MI 150/2 (15.0)",
        )
        assert m2.id == orig_id
        assert m2.status == "LIVE"
        assert m2.score_summary == "MI 150/2 (15.0)"

    def test_match_upsert_fallback_to_source_url(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)
        m1 = matches_repo.create(**build_match_data(external_id=None, source_url="https://www.fancode.com/matches/test-match"))
        orig_id = m1.id

        m2 = matches_repo.upsert(
            external_id=None,
            source_url="https://www.fancode.com/matches/test-match",
            title="Updated Title",
            slug="test-match",
        )
        assert m2.id == orig_id
        assert m2.title == "Updated Title"


class TestVideosRepository:
    """Test videos repository and associations."""

    def test_video_insert_and_associations(self, db_session: Session) -> None:
        sports_repo = SportsRepository(db_session)
        tours_repo = ToursRepository(db_session)
        matches_repo = MatchesRepository(db_session)
        videos_repo = VideosRepository(db_session)

        sport = sports_repo.create(**build_sport_data())
        tour = tours_repo.create(**build_tour_data(sport_id=sport.id))
        match = matches_repo.create(**build_match_data(tour_id=tour.id, sport_id=sport.id))
        video = videos_repo.create(**build_video_data(tour_id=tour.id, match_id=match.id, sport_id=sport.id))

        assert video.id is not None
        assert video.match.title == "Mumbai Indians vs Chennai Super Kings"
        assert video.tour.name == "Indian Premier League 2026"
        assert video.sport.name == "Cricket"


class TestPagesRepository:
    """Test pages repository, canonical URL uniqueness, and upsert."""

    def test_page_insert_and_retrieval(self, db_session: Session) -> None:
        repo = PagesRepository(db_session)
        page = repo.create(**build_page_data())
        assert page.id is not None
        assert page.canonical_url == "https://www.fancode.com/cricket"

        by_canon = repo.get_by_canonical_url("https://www.fancode.com/cricket")
        assert by_canon is not None
        assert by_canon.id == page.id

    def test_page_canonical_url_uniqueness(self, db_session: Session) -> None:
        repo = PagesRepository(db_session)
        repo.create(**build_page_data(canonical_url="https://www.fancode.com/unique"))
        db_session.commit()

        # Second insert with same canonical URL must violate unique constraint
        with pytest.raises(IntegrityError):
            repo.create(**build_page_data(canonical_url="https://www.fancode.com/unique"))
            db_session.commit()
        db_session.rollback()

    def test_page_upsert(self, db_session: Session) -> None:
        repo = PagesRepository(db_session)
        p1 = repo.create(**build_page_data(title="Old Title"))
        orig_id = p1.id

        # Upsert with same canonical URL
        p2 = repo.upsert(
            url="https://www.fancode.com/cricket",
            canonical_url="https://www.fancode.com/cricket",
            title="Updated Title",
            http_status=200,
        )
        assert p2.id == orig_id
        assert p2.title == "Updated Title"

    def test_page_mark_checked(self, db_session: Session) -> None:
        repo = PagesRepository(db_session)
        p = repo.create(**build_page_data())
        assert p.last_checked_at is None

        repo.mark_checked("https://www.fancode.com/cricket")
        assert p.last_checked_at is not None


class TestChangeEventsRepository:
    """Test change events logging and unnotified retrieval."""

    def test_change_event_insert_and_unnotified_retrieval(self, db_session: Session) -> None:
        repo = ChangeEventsRepository(db_session)
        evt = repo.create(**build_change_event_data())
        assert evt.id is not None
        assert evt.notified_at is None

        unnotified = repo.get_unnotified()
        assert len(unnotified) >= 1
        assert unnotified[0].id == evt.id

        repo.mark_notified(evt.id)
        assert evt.notified_at is not None
        assert len(repo.get_unnotified()) == 0


class TestScrapeRunsRepository:
    """Test scrape run lifecycle and stats recording."""

    def test_scrape_run_creation_and_completion(self, db_session: Session) -> None:
        repo = ScrapeRunsRepository(db_session)
        run = repo.create_run(run_type="discovery", metadata_json={"worker": "test"})
        assert run.id is not None
        assert run.status == "running"
        assert run.finished_at is None

        finished = repo.finish_run(
            run_id=run.id,
            status="success",
            pages_discovered=10,
            records_created=5,
        )
        assert finished is not None
        assert finished.status == "success"
        assert finished.pages_discovered == 10
        assert finished.records_created == 5
        assert finished.finished_at is not None

        latest = repo.get_latest("discovery")
        assert latest is not None
        assert latest.id == run.id


class TestAdvancedDatabaseBehaviors:
    """Test transaction rollbacks, timestamp consistency, and JSON metadata."""

    def test_transaction_rollback(self, test_engine) -> None:
        TestingSessionLocal = sessionmaker(bind=test_engine)
        session = TestingSessionLocal()
        sports_repo = SportsRepository(session)

        try:
            sports_repo.create(**build_sport_data(slug="temp-sport"))
            # Trigger integrity failure or manual exception
            raise RuntimeError("Forced error to test rollback")
        except RuntimeError:
            session.rollback()
        finally:
            session.close()

        # Verify not saved in fresh session
        verify_sess = TestingSessionLocal()
        found = verify_sess.scalars(select(Sport).where(Sport.slug == "temp-sport")).first()
        verify_sess.close()
        assert found is None

    def test_timestamp_utc_timezone_aware(self, db_session: Session) -> None:
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

        repo = SportsRepository(db_session)
        sport = repo.create(**build_sport_data())
        assert sport.created_at is not None

    def test_json_metadata_storage_and_retrieval(self, db_session: Session) -> None:
        repo = PagesRepository(db_session)
        meta = {"tags": ["cricket", "ipl"], "count": 42, "nested": {"key": "val"}}
        page = repo.create(**build_page_data(canonical_url="https://www.fancode.com/meta", metadata_json=meta))

        retrieved = repo.get_by_canonical_url("https://www.fancode.com/meta")
        assert retrieved is not None
        assert retrieved.metadata_json == meta
        assert retrieved.metadata_json["nested"]["key"] == "val"
