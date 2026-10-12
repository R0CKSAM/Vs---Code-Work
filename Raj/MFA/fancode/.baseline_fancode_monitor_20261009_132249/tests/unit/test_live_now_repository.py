"""
test_live_now_repository.py – Integration tests for Live Now repository interactions and DB enrichment.
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
from app.database.models import Match, ScrapeRun
from app.database.repositories import MatchesRepository, ScrapeRunsRepository
from app.scraper.live_now.models import LiveMatchRecord
from app.scraper.live_now.scraper import FanCodeLiveNowScraper


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


class TestLiveNowRepositoryIntegration:
    def test_existing_match_enrichment_preserves_existing_values(self, db_session: Session, monkeypatch) -> None:
        matches_repo = MatchesRepository(db_session)

        # 1. Seed existing match with scheduled status and known venue
        existing = matches_repo.upsert(
            external_id="crick-live-101",
            title="Initial Title",
            slug="initial-title",
            source_url="https://www.fancode.com/matches/mi-vs-csk-live",
            venue="Wankhede Stadium",
            status="SCHEDULED",
        )
        orig_id = existing.id
        db_session.commit()

        # Mock get_session in scraper to use our db_session
        from contextlib import contextmanager

        @contextmanager
        def mock_get_session():
            yield db_session

        monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
        monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

        scraper = FanCodeLiveNowScraper(browser=None)

        # 2. Live record has status LIVE and score, but venue is None
        live_rec = LiveMatchRecord(
            match_external_id="crick-live-101",
            title="MI vs CSK Updated",
            source_url="https://www.fancode.com/matches/mi-vs-csk-live",
            status="LIVE",
            score_summary="MI 152/4 (16.2 ov)",
            venue=None,  # Live page omitted venue
        )

        scraper._persist_to_database([live_rec])

        db_session.expire_all()
        enriched = matches_repo.get_by_id(orig_id)
        assert enriched is not None
        assert enriched.id == orig_id
        # Status and score updated
        assert enriched.status == "LIVE"
        assert enriched.score_summary == "MI 152/4 (16.2 ov)"
        # Venue preserved!
        assert enriched.venue == "Wankhede Stadium"

    def test_no_duplicate_created_for_existing_match(self, db_session: Session, monkeypatch) -> None:
        matches_repo = MatchesRepository(db_session)
        existing = matches_repo.upsert(
            external_id="dup-check-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            source_url="https://www.fancode.com/matches/ars-vs-che",
            status="SCHEDULED",
        )
        db_session.commit()

        from contextlib import contextmanager

        @contextmanager
        def mock_get_session():
            yield db_session

        monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
        monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

        scraper = FanCodeLiveNowScraper(browser=None)

        rec = LiveMatchRecord(
            match_external_id="dup-check-1",
            title="Arsenal vs Chelsea",
            source_url="https://www.fancode.com/matches/ars-vs-che",
            status="LIVE",
            score_summary="1 - 0",
        )

        scraper._persist_to_database([rec])
        scraper._persist_to_database([rec])

        all_matches = db_session.query(Match).all()
        assert len(all_matches) == 1
        assert all_matches[0].status == "LIVE"
        assert all_matches[0].score_summary == "1 - 0"

    def test_scrape_run_lifecycle_and_unmatched_skipped(self, db_session: Session, monkeypatch) -> None:
        from contextlib import contextmanager

        @contextmanager
        def mock_get_session():
            yield db_session

        monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
        monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

        scraper = FanCodeLiveNowScraper(browser=None)

        # Unmatched record with NO external_id to verify skip to prevent DB pollution
        unmatched_rec = LiveMatchRecord(
            match_external_id=None,
            title="",  # incomplete
            source_url="",
            status="LIVE",
        )

        scraper._persist_to_database([unmatched_rec])

        runs_repo = ScrapeRunsRepository(db_session)
        run = runs_repo.get_latest(run_type="live_now")
        assert run is not None
        assert run.run_type == "live_now"
        assert run.status == "success"
        assert run.records_processed == 1
        assert run.records_created == 0
        assert run.records_updated == 0

