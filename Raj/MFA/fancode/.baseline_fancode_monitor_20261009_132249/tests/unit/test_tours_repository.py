"""
test_tours_repository.py – Integration tests for tours repository and match relationships.
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
from app.database.models import Match, Tour
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.scraper.tours.parser import ToursParser
from tests.fixtures.tours import SAMPLE_TOUR_DUPLICATES, SAMPLE_TOUR_NORMAL


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


class TestToursRepositoryIntegration:
    def test_tour_upsert_with_sport_association(self, db_session: Session) -> None:
        sports_repo = SportsRepository(db_session)
        tours_repo = ToursRepository(db_session)

        tour_data = ToursParser.parse_tour_dict(SAMPLE_TOUR_NORMAL)
        assert tour_data is not None

        sport = sports_repo.upsert(
            name=tour_data.sport_name,
            slug=tour_data.sport_slug or "cricket",
            source_url="https://www.fancode.com/cricket",
        )

        tour = tours_repo.upsert(
            name=tour_data.name,
            slug=tour_data.slug,
            source_url=tour_data.source_url,
            external_id=tour_data.external_id,
            sport_id=sport.id,
            status=tour_data.status,
            start_date=tour_data.start_date,
            end_date=tour_data.end_date,
        )

        assert tour.id is not None
        assert tour.sport.name == "Cricket"
        assert tour.status == "UPCOMING"

    def test_duplicate_tours_prevention(self, db_session: Session) -> None:
        tours_repo = ToursRepository(db_session)
        t1 = ToursParser.parse_tour_dict(SAMPLE_TOUR_DUPLICATES[0])
        t2 = ToursParser.parse_tour_dict(SAMPLE_TOUR_DUPLICATES[1])
        assert t1 is not None and t2 is not None

        tour1 = tours_repo.upsert(name=t1.name, slug=t1.slug, source_url=t1.source_url)
        tour2 = tours_repo.upsert(name=t2.name, slug=t2.slug, source_url=t2.source_url)

        assert tour1.id == tour2.id
        all_tours = [t for t in db_session.query(Tour).filter_by(slug="cpl-2026").all()]
        assert len(all_tours) == 1

    def test_tour_to_match_linkage(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)
        tours_repo = ToursRepository(db_session)

        # Create a match without a tour_id
        match = matches_repo.upsert(
            title="MI vs CSK IPL 2026",
            slug="mi-vs-csk-ipl-2026",
            source_url="https://www.fancode.com/matches/ipl-2026-mi-vs-csk",
            status="UPCOMING",
        )
        assert match.tour_id is None

        # Create tour with matching slug
        tour = tours_repo.upsert(
            name="IPL 2026",
            slug="ipl-2026",
            source_url="https://www.fancode.com/tours/ipl-2026",
        )

        # Link match
        if tour.slug in match.source_url:
            match.tour_id = tour.id
            db_session.flush()

        assert match.tour_id == tour.id
        assert match.tour.name == "IPL 2026"
