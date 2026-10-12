"""
test_sports_repository.py – Integration tests for sports repository and scrape run tracking.
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
from app.database.models import Sport
from app.database.repositories import ScrapeRunsRepository, SportsRepository
from app.scraper.sports.parser import SportsParser
from tests.fixtures.sports import SAMPLE_SPORT_DUPLICATES, SAMPLE_SPORT_NORMAL


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


class TestSportsRepositoryIntegration:
    def test_sport_upsert_idempotency(self, db_session: Session) -> None:
        repo = SportsRepository(db_session)
        s1 = SportsParser.parse_sport_dict(SAMPLE_SPORT_NORMAL)
        assert s1 is not None

        sport1 = repo.upsert(
            name=s1.name,
            slug=s1.slug,
            source_url=s1.source_url,
            external_id=s1.external_id,
            description=s1.description,
            image_url=s1.image_url,
        )
        orig_id = sport1.id

        # Upsert again with modified description
        sport2 = repo.upsert(
            name=s1.name,
            slug=s1.slug,
            source_url=s1.source_url,
            external_id=s1.external_id,
            description="Updated description",
        )

        assert sport2.id == orig_id
        assert sport2.description == "Updated description"

    def test_duplicate_sports_prevention(self, db_session: Session) -> None:
        repo = SportsRepository(db_session)
        s1 = SportsParser.parse_sport_dict(SAMPLE_SPORT_DUPLICATES[0])
        s2 = SportsParser.parse_sport_dict(SAMPLE_SPORT_DUPLICATES[1])
        assert s1 is not None and s2 is not None

        sport1 = repo.upsert(name=s1.name, slug=s1.slug, source_url=s1.source_url)
        sport2 = repo.upsert(name=s2.name, slug=s2.slug, source_url=s2.source_url)

        assert sport1.id == sport2.id
        all_sports = [s for s in db_session.query(Sport).filter_by(slug="basketball").all()]
        assert len(all_sports) == 1

    def test_sports_scrape_run_audit(self, db_session: Session) -> None:
        runs_repo = ScrapeRunsRepository(db_session)
        run = runs_repo.create_run(run_type="sports", metadata_json={"target": "fancode"})
        assert run.id is not None
        assert run.status == "running"

        finished = runs_repo.finish_run(run_id=run.id, status="success", records_processed=5, records_created=5)
        assert finished is not None
        assert finished.status == "success"
        assert finished.records_created == 5
