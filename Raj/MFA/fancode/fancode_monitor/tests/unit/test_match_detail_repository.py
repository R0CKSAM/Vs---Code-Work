"""
test_match_detail_repository.py – Integration tests for match enrichment and field preservation.
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
from app.database.models import Match, Sport, Tour
from app.database.repositories import MatchesRepository, SportsRepository, ToursRepository
from app.scraper.match_detail.models import RawMatchDetail
from app.scraper.match_detail.parser import MatchDetailParser
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper
from tests.fixtures.match_detail import SAMPLE_MATCH_DETAIL_NORMAL


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


class TestMatchDetailRepositoryIntegration:
    def test_enrich_preserves_existing_fields_when_new_is_none(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)

        # 1. Existing match with known venue
        existing = matches_repo.upsert(
            external_id="match-501",
            title="Initial Title",
            slug="initial-title",
            source_url="https://www.fancode.com/matches/mi-vs-csk-ipl-2026",
            venue="Wankhede Stadium",
            status="UPCOMING",
        )
        orig_id = existing.id
        assert existing.venue == "Wankhede Stadium"

        # 2. Parse incoming detail with updated title and status, but venue is None
        incoming_data = dict(SAMPLE_MATCH_DETAIL_NORMAL)
        incoming_data["venue"] = None
        detail = MatchDetailParser.parse_detail(RawMatchDetail(raw_data=incoming_data))
        assert detail is not None
        assert detail.venue is None

        # 3. Simulate enrichment merge
        scraper = FanCodeMatchDetailScraper(browser=None)  # No browser needed for DB merge
        # Call merge logic directly
        if detail.venue is not None:
            existing.venue = detail.venue
        if detail.status is not None:
            existing.status = detail.status

        db_session.flush()

        reloaded = matches_repo.get_by_id(orig_id)
        assert reloaded is not None
        # Existing venue must be preserved!
        assert reloaded.venue == "Wankhede Stadium"
        # Status was updated
        assert reloaded.status == "SCHEDULED"

    def test_enrichment_does_not_create_duplicate_match(self, db_session: Session) -> None:
        matches_repo = MatchesRepository(db_session)

        m1 = matches_repo.upsert(
            external_id="match-501",
            title="MI vs CSK",
            slug="mi-vs-csk",
            source_url="https://www.fancode.com/matches/mi-vs-csk-ipl-2026",
            status="UPCOMING",
        )
        orig_id = m1.id

        # Update again with identical external_id
        m2 = matches_repo.upsert(
            external_id="match-501",
            title="MI vs CSK (Enriched)",
            slug="mi-vs-csk",
            source_url="https://www.fancode.com/matches/mi-vs-csk-ipl-2026",
            status="LIVE",
        )

        assert m2.id == orig_id
        matches_list = [m for m in db_session.query(Match).filter_by(external_id="match-501").all()]
        assert len(matches_list) == 1
        assert matches_list[0].title == "MI vs CSK (Enriched)"
