"""
test_schedule_repository.py – Integration tests for schedule persistence and scrape run lifecycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Base
from app.database.models import Match, ScrapeRun, Sport, Tour
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.scraper.schedule.models import RawScheduleItem
from app.scraper.schedule.parser import ScheduleParser
from tests.fixtures.schedule import (
    SAMPLE_CRICKET_MATCH,
    SAMPLE_DUPLICATE_ITEMS,
    SAMPLE_FOOTBALL_MATCH,
)


@pytest.fixture
def test_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


class TestSchedulePersistence:
    def test_persist_match_with_sport_and_tour(self, db_session: Session) -> None:
        sports_repo = SportsRepository(db_session)
        tours_repo = ToursRepository(db_session)
        matches_repo = MatchesRepository(db_session)

        item = RawScheduleItem(raw_data=SAMPLE_CRICKET_MATCH)
        match_data = ScheduleParser.parse_item(item)
        assert match_data is not None

        # Upsert sport & tour
        sport = sports_repo.upsert(
            name=match_data.sport_name,
            slug=match_data.sport_slug or "cricket",
            external_id=match_data.sport_external_id,
            source_url="https://www.fancode.com/cricket",
        )
        tour = tours_repo.upsert(
            name=match_data.tour_name,
            slug=match_data.tour_slug or "tour",
            external_id=match_data.tour_external_id,
            sport_id=sport.id,
            source_url="https://www.fancode.com/tour",
        )

        match = matches_repo.upsert(
            external_id=match_data.external_id,
            tour_id=tour.id,
            sport_id=sport.id,
            title=match_data.title,
            slug=match_data.slug or "match",
            source_url=match_data.source_url,
            match_date=match_data.match_date,
            start_time=match_data.start_time,
            status=match_data.status,
            venue=match_data.venue,
            team_a_name=match_data.team_a_name,
            team_b_name=match_data.team_b_name,
        )

        assert match.id is not None
        assert match.sport.name == "Cricket"
        assert match.tour.name == "Australia Tour of India 2026"
        assert match.team_a_name == "India"
        assert match.team_b_name == "Australia"

    def test_duplicate_match_upsert_prevention(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)

        item1 = ScheduleParser.parse_item(RawScheduleItem(raw_data=SAMPLE_DUPLICATE_ITEMS[0]))
        assert item1 is not None
        m1 = matches_repo.upsert(
            external_id=item1.external_id,
            title=item1.title,
            slug=item1.slug or "slug",
            source_url=item1.source_url,
            status=item1.status,
        )
        orig_id = m1.id

        # Upsert second duplicate item with updated status
        item2 = ScheduleParser.parse_item(RawScheduleItem(raw_data=SAMPLE_DUPLICATE_ITEMS[1]))
        assert item2 is not None
        m2 = matches_repo.upsert(
            external_id=item2.external_id,
            title=item2.title,
            slug=item2.slug or "slug",
            source_url=item2.source_url,
            status=item2.status,
        )

        assert m2.id == orig_id
        assert m2.status == "COMPLETED"

    def test_scrape_run_audit_lifecycle(self, db_session: Session) -> None:
        runs_repo = ScrapeRunsRepository(db_session)
        run = runs_repo.create_run(run_type="schedule", metadata_json={"target": "fancode"})
        assert run.id is not None
        assert run.status == "running"

        finished = runs_repo.finish_run(
            run_id=run.id,
            status="success",
            records_processed=25,
            records_created=20,
            records_updated=5,
        )
        assert finished is not None
        assert finished.status == "success"
        assert finished.records_created == 20
        assert finished.finished_at is not None
