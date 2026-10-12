"""
test_videos_repository.py – Integration tests for Videos repository interactions and DB persistence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Base
from app.database.models import Match, ScrapeRun, Sport, Tour, Video
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
    VideosRepository,
)
from app.scraper.videos.models import VideoRecord
from app.scraper.videos.scraper import FanCodeVideosScraper


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


class TestVideosRepositoryIntegration:
    def test_insert_and_retrieve_video(self, db_session: Session) -> None:
        repo = VideosRepository(db_session)
        video = repo.create(
            external_id="vid-test-1",
            title="Test Highlight Video",
            slug="test-highlight-video",
            source_url="https://www.fancode.com/video/vid-test-1",
            video_type="HIGHLIGHT",
            duration_seconds=300,
        )
        assert video.id is not None
        assert video.title == "Test Highlight Video"

        by_ext = repo.get_by_external_id("vid-test-1")
        assert by_ext is not None
        assert by_ext.id == video.id

        by_url = repo.get_by_source_url("https://www.fancode.com/video/vid-test-1")
        assert by_url is not None
        assert by_url.id == video.id

    def test_upsert_and_duplicate_prevention(self, db_session: Session) -> None:
        repo = VideosRepository(db_session)
        v1 = repo.upsert(
            external_id="vid-dup-101",
            title="Initial Title",
            slug="initial-title",
            source_url="https://www.fancode.com/video/vid-dup-101",
            duration_seconds=120,
        )
        v2 = repo.upsert(
            external_id="vid-dup-101",
            title="Updated Title",
            slug="updated-title",
            source_url="https://www.fancode.com/video/vid-dup-101",
            duration_seconds=180,
        )
        assert v1.id == v2.id

        all_vids = db_session.query(Video).all()
        assert len(all_vids) == 1
        assert all_vids[0].title == "Updated Title"
        assert all_vids[0].duration_seconds == 180

    def test_non_destructive_update_preserves_existing_values(self, db_session: Session, monkeypatch) -> None:
        repo = VideosRepository(db_session)
        # Seed video with thumbnail and duration
        v = repo.create(
            external_id="vid-preserve-1",
            title="Title",
            slug="title",
            source_url="https://www.fancode.com/video/vid-preserve-1",
            thumbnail_url="https://img.fancode.com/poster.jpg",
            duration_seconds=450,
        )
        db_session.commit()

        # Update without thumbnail or duration
        repo.upsert(
            external_id="vid-preserve-1",
            title="New Title",
            thumbnail_url=None,
            duration_seconds=None,
        )
        db_session.expire_all()
        updated = repo.get_by_id(v.id)
        assert updated is not None
        assert updated.title == "New Title"
        # Preserved
        assert updated.thumbnail_url == "https://img.fancode.com/poster.jpg"
        assert updated.duration_seconds == 450

    def test_associations_with_match_tour_and_sport(self, db_session: Session, monkeypatch) -> None:
        # Pre-seed match, tour, and sport
        sports_repo = SportsRepository(db_session)
        sport = sports_repo.create(name="Cricket", slug="cricket", source_url="https://www.fancode.com/cricket")

        tours_repo = ToursRepository(db_session)
        tour = tours_repo.create(name="IPL 2026", slug="ipl-2026", source_url="https://www.fancode.com/tours/ipl-2026", sport_id=sport.id)

        matches_repo = MatchesRepository(db_session)
        match = matches_repo.create(
            external_id="m-match-99",
            title="MI vs CSK",
            slug="mi-vs-csk",
            source_url="https://www.fancode.com/matches/mi-vs-csk",
            sport_id=sport.id,
            tour_id=tour.id,
        )
        db_session.commit()

        from contextlib import contextmanager

        @contextmanager
        def mock_get_session():
            yield db_session

        monkeypatch.setattr("app.scraper.videos.scraper.get_session", mock_get_session)
        monkeypatch.setattr("app.scraper.videos.scraper.init_db", lambda: None)

        scraper = FanCodeVideosScraper(browser=None)

        rec = VideoRecord(
            external_id="vid-assoc-1",
            title="MI vs CSK Super Highlights",
            source_url="https://www.fancode.com/video/vid-assoc-1",
            video_type="HIGHLIGHT",
            match_external_id="m-match-99",
            tour_name="IPL 2026",
            sport_name="Cricket",
        )

        scraper._persist_to_database([rec])

        db_session.expire_all()
        videos_repo = VideosRepository(db_session)
        saved = videos_repo.get_by_external_id("vid-assoc-1")
        assert saved is not None
        assert saved.match_id == match.id
        assert saved.tour_id == tour.id
        assert saved.sport_id == sport.id

    def test_scrape_run_lifecycle(self, db_session: Session, monkeypatch) -> None:
        from contextlib import contextmanager

        @contextmanager
        def mock_get_session():
            yield db_session

        monkeypatch.setattr("app.scraper.videos.scraper.get_session", mock_get_session)
        monkeypatch.setattr("app.scraper.videos.scraper.init_db", lambda: None)

        scraper = FanCodeVideosScraper(browser=None)
        rec = VideoRecord(
            external_id="vid-run-1",
            title="Video for Run Audit",
            source_url="https://www.fancode.com/video/vid-run-1",
        )

        scraper._persist_to_database([rec])

        runs_repo = ScrapeRunsRepository(db_session)
        run = runs_repo.get_latest(run_type="videos")
        assert run is not None
        assert run.run_type == "videos"
        assert run.status == "success"
        assert run.records_processed == 1
        assert run.records_created == 1
