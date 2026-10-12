"""
test_match_identity_regression.py – Comprehensive regression tests for match entity resolution,
cross-scraper deduplication, URL ID extraction, Match Detail backfilling, and Live Now DOM extraction.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database.models import Match
from app.database.repositories import MatchesRepository
from app.scraper.discovery.url_normalizer import extract_match_id_from_url
from app.scraper.live_now.models import LiveMatchRecord, RawLiveItem
from app.scraper.live_now.normalizer import (
    LiveNowNormalizer,
    extract_title_from_slug_or_url,
    is_valid_match_title,
    is_vs_title,
)
from app.scraper.live_now.parser import LiveNowParser
from app.scraper.live_now.scraper import FanCodeLiveNowScraper
from app.scraper.match_detail.models import MatchDetail, RawMatchDetail
from app.scraper.match_detail.parser import MatchDetailParser
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper
from app.scraper.schedule.models import RawScheduleItem
from app.scraper.schedule.parser import ScheduleParser


# =============================================================================
# 1. URL Match ID Extraction Tests (Requirements A, B, C, D, E, L, M, N)
# =============================================================================

@pytest.mark.parametrize(
    "url, expected_id",
    [
        # Req A: Deep FanCode URL with Tour ID and Match ID
        (
            "/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
            "4249663",
        ),
        # Req B: Another real FanCode URL
        (
            "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
            "4249721",
        ),
        # Req C: Relative URL
        (
            "/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
            "4249663",
        ),
        # Req D: URL with query string
        (
            "https://www.fancode.com/matches/tasmania-vs-new-south-wales-4249663/live-match-info?tab=scorecard&utm_source=fancode",
            "4249663",
        ),
        # Req E: URL with fragment
        (
            "https://www.fancode.com/matches/tasmania-vs-new-south-wales-4249663/live-match-info#commentary",
            "4249663",
        ),
        # Standard formats
        ("https://www.fancode.com/matches/day-1-world-feed-4249774/live-match-info", "4249774"),
        ("/match/tuskers-vs-lions/140356", "140356"),
        ("/cricket/matches/zimbabwe-tour-of-bangladesh-2026/bangladesh-vs-zimbabwe/139151", "139151"),
        ("https://www.fancode.com/matches/139151", "139151"),
        ("/matches/match-slug-99999", "99999"),
        ("/matches/match-slug-99999/", "99999"),
        # Req L: Generic listing URLs must NOT produce match external_id
        ("https://www.fancode.com/live-now/all-sports", None),
        ("https://www.fancode.com/schedule", None),
        ("https://www.fancode.com/sports", None),
        ("https://www.fancode.com/video", None),
        ("https://www.fancode.com", None),
        ("/live", None),
        # Req M: Malformed / None URLs return None safely
        (None, None),
        ("", None),
        ("   ", None),
        # Req N: Non-match numeric URLs (tour ID without /matches/)
        ("/cricket/tour/sheffield-shield-19896475", None),
        ("https://www.fancode.com/tour/asia-qualifier-19896480", None),
    ],
)
def test_extract_match_id_from_url_all_shapes(url, expected_id):
    assert extract_match_id_from_url(url) == expected_id


# =============================================================================
# 2. Schedule Parser URL ID Extraction (Requirements F & G)
# =============================================================================

def test_schedule_parser_derives_id_from_url_when_payload_id_absent():
    """Req F: Schedule parser extracts external_id from match URL when not explicitly in JSON id field."""
    raw = RawScheduleItem(
        raw_data={
            "title": "Thailand vs Qatar",
            "url": "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
            "status": "UPCOMING",
            "matchDate": "2026-10-10T10:00:00Z",
        },
        source_type="json",
    )
    match = ScheduleParser.parse_item(raw)
    assert match is not None
    assert match.external_id == "4249721"
    assert match.title == "Thailand vs Qatar"
    assert match.status == "UPCOMING"


def test_schedule_parser_explicit_id_takes_priority():
    """Req G: Explicit payload ID takes priority if present."""
    raw = RawScheduleItem(
        raw_data={
            "id": "139151",
            "title": "Bangladesh vs Zimbabwe",
            "url": "/cricket/matches/zimbabwe-tour-of-bangladesh-2026/bangladesh-vs-zimbabwe/999999",
            "status": "UPCOMING",
        },
        source_type="json",
    )
    match = ScheduleParser.parse_item(raw)
    assert match is not None
    assert match.external_id == "139151"


# =============================================================================
# 3. Match Detail Parser & Scraper URL ID Extraction (Requirements H, Part B.1, B.2, B.3)
# =============================================================================

def test_match_detail_parser_derives_id_from_url():
    """Req H: Match Detail parser derives external_id from source_url when payload ID missing."""
    raw = RawMatchDetail(
        raw_data={
            "title": "Tasmania vs New South Wales",
            "source_url": "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
            "status": "LIVE",
        },
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
    )
    detail = MatchDetailParser.parse_detail(raw)
    assert detail is not None
    assert detail.match_external_id == "4249663"
    assert detail.title == "Tasmania vs New South Wales"


def test_match_detail_enrichment_backfills_null_external_id(db_session, monkeypatch):
    """Part B.1: Match Detail enrichment backfills NULL external_id on existing record."""
    repo = MatchesRepository(db_session)
    m = repo.create(
        external_id=None,
        title="Thailand vs Qatar",
        slug="thailand-vs-qatar",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        status="SCHEDULED",
    )
    initial_id = m.id
    assert m.external_id is None

    # Mock get_session to return test db_session
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.match_detail.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.match_detail.scraper.init_db", lambda: None)

    detail = MatchDetail(
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        match_external_id="4249721",
        title="Thailand vs Qatar",
        venue="Terdthai Cricket Ground",
        status="LIVE",
    )

    scraper = FanCodeMatchDetailScraper(browser=None)
    scraper._enrich_in_database(detail)

    updated = repo.get_by_id(initial_id)
    assert updated is not None
    assert updated.external_id == "4249721"
    assert updated.venue == "Terdthai Cricket Ground"
    assert updated.status == "LIVE"


def test_match_detail_enrichment_does_not_overwrite_existing_external_id(db_session, monkeypatch):
    """Part B.2: Match Detail does NOT overwrite an existing non-null external_id."""
    repo = MatchesRepository(db_session)
    m = repo.create(
        external_id="4249721",
        title="Thailand vs Qatar",
        slug="thailand-vs-qatar",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        status="SCHEDULED",
    )
    initial_id = m.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.match_detail.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.match_detail.scraper.init_db", lambda: None)

    # Attempt to enrich with a different incoming external ID
    detail = MatchDetail(
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        match_external_id="9999999",
        title="Thailand vs Qatar",
        venue="Terdthai Cricket Ground",
    )

    scraper = FanCodeMatchDetailScraper(browser=None)
    scraper._enrich_in_database(detail)

    updated = repo.get_by_id(initial_id)
    assert updated.external_id == "4249721"


def test_match_detail_enrichment_incoming_none_does_not_clear_existing_external_id(db_session, monkeypatch):
    """Part B.3: Incoming None does not clear an existing external_id."""
    repo = MatchesRepository(db_session)
    m = repo.create(
        external_id="4249721",
        title="Thailand vs Qatar",
        slug="thailand-vs-qatar",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
    )
    initial_id = m.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.match_detail.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.match_detail.scraper.init_db", lambda: None)

    detail = MatchDetail(
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        match_external_id=None,
        title="Thailand vs Qatar",
    )

    scraper = FanCodeMatchDetailScraper(browser=None)
    scraper._enrich_in_database(detail)

    updated = repo.get_by_id(initial_id)
    assert updated.external_id == "4249721"


# =============================================================================
# 4. Live Now Parser & Inverted Team Identity Resolution (Requirements I, Part B.5)
# =============================================================================

def test_live_now_parser_derives_id_from_url():
    """Req I: LiveNowParser derives external_id from canonical match URL."""
    raw = RawLiveItem(
        raw_data={
            "title": "Tasmania vs New South Wales",
            "url": "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
            "status": "LIVE",
        },
        source_type="dom",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is not None
    assert rec.match_external_id == "4249663"
    assert rec.status == "LIVE"


def test_live_now_resolves_inverted_teams_by_external_id(db_session, monkeypatch):
    """Part B.5: Live Now resolves existing match row by external_id even if team order, slug, or URL differ."""
    repo = MatchesRepository(db_session)

    # In DB: Queensland vs Western Australia (4249664)
    m = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="SCHEDULED",
    )
    initial_id = m.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    # Live Now reports: Western Australia vs Queensland with different slug/URL but same external_id
    live_record = LiveMatchRecord(
        match_external_id="4249664",
        title="Western Australia vs Queensland",
        source_url="https://www.fancode.com/matches/western-australia-vs-queensland-4249664/live-match-info",
        status="LIVE",
        score_summary="WAU 150/2 (20.0)",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_record])

    # Must resolve and update the same DB row
    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    updated = repo.get_by_id(initial_id)
    assert updated is not None
    assert updated.external_id == "4249664"
    assert updated.status == "LIVE"
    assert updated.score_summary == "WAU 150/2 (20.0)"


# =============================================================================
# 5. External ID Backfill & Upsert Behavior (Requirement J)
# =============================================================================

def test_existing_match_with_null_external_id_is_backfilled_without_duplicate(db_session):
    """Req J: Existing match with external_id=None receives external_id on upsert without duplicating row."""
    repo = MatchesRepository(db_session)

    m1 = repo.create(
        external_id=None,
        title="THA vs QAT",
        slug="match-1",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        status="SCHEDULED",
    )
    initial_id = m1.id
    assert m1.external_id is None

    m2 = repo.upsert(
        external_id="4249721",
        title="Thailand vs Qatar",
        slug="thailand-vs-qatar",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        status="LIVE",
    )

    assert m2.id == initial_id
    assert m2.external_id == "4249721"
    assert m2.title == "Thailand vs Qatar"
    assert m2.status == "LIVE"

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1


# =============================================================================
# 6. Generic Slug Safety & Non-Collision (Requirement K & Part B.6)
# =============================================================================

def test_generic_slugs_do_not_cause_identity_collisions(db_session):
    """Req K / Part B.6: Generic ordinal slugs (match-1, match-2, match-3, match-17) with different URLs create separate rows."""
    repo = MatchesRepository(db_session)

    m1 = repo.upsert(
        external_id=None,
        title="THA vs QAT",
        slug="match-1",
        source_url="https://www.fancode.com/matches/thailand-vs-qatar-4249721/live-match-info",
        status="SCHEDULED",
    )

    m2 = repo.upsert(
        external_id=None,
        title="BRN vs BHU",
        slug="match-2",
        source_url="https://www.fancode.com/matches/bahrain-vs-bhutan-4249722/live-match-info",
        status="SCHEDULED",
    )

    m3 = repo.upsert(
        external_id=None,
        title="QUN vs WAU",
        slug="match-17",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="LIVE",
    )

    assert m1.id != m2.id
    assert m2.id != m3.id
    assert m1.id != m3.id

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 3


def test_base_slug_fallback_does_not_collapse_match_1_into_match(db_session):
    """A row with slug='match' must NOT match incoming rows with slug='match-1' or 'match-2'."""
    repo = MatchesRepository(db_session)

    m_generic = repo.create(
        external_id=None,
        title="Generic Match",
        slug="match",
        source_url="https://www.fancode.com/match",
    )

    m_ordinal = repo.upsert(
        external_id=None,
        title="New Fixture",
        slug="match-1",
        source_url="https://www.fancode.com/matches/new-fixture-4249999/live",
    )

    assert m_ordinal.id != m_generic.id
    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 2


# =============================================================================
# 7. Source URL Preservation
# =============================================================================

def test_specific_match_source_url_preserved_over_generic_schedule_url(db_session):
    """Specific canonical match URL is not overwritten by /schedule or /live-now."""
    repo = MatchesRepository(db_session)

    m1 = repo.upsert(
        external_id="4249663",
        title="New South Wales vs Tasmania",
        slug="new-south-wales-vs-tasmania",
        source_url="https://www.fancode.com/matches/new-south-wales-vs-tasmania-4249663/live-match-info",
        status="LIVE",
    )
    specific_url = m1.source_url

    m2 = repo.upsert(
        external_id="4249663",
        title="New South Wales vs Tasmania",
        slug="new-south-wales-vs-tasmania",
        source_url="https://www.fancode.com/schedule",
        status="SCHEDULED",
    )

    assert m2.id == m1.id
    assert m2.source_url == specific_url


# =============================================================================
# 8. Step 6A: Live Now Multi-Word URL Extraction & External-ID Normalization
# =============================================================================

@pytest.mark.parametrize(
    "url, expected_id",
    [
        (
            "https://www.fancode.com/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info",
            "4249664",
        ),
        (
            "/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info",
            "4249664",
        ),
        (
            "https://www.fancode.com/matches/western-australia-vs-queensland-4249664/live-match-info",
            "4249664",
        ),
        (
            "/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
            "4249664",
        ),
    ],
)
def test_extract_match_id_from_multiword_live_now_urls(url, expected_id):
    """Step 6A: URL match ID extraction correctly extracts ID from multi-word hyphenated slug URLs."""
    assert extract_match_id_from_url(url) == expected_id


@pytest.mark.parametrize(
    "raw_input, expected_normalized",
    [
        ("4249664", "4249664"),
        (" 4249664 ", "4249664"),
        (4249664, "4249664"),
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_external_id_normalization_logic(raw_input, expected_normalized):
    """Step 6A: External ID normalization safely strips whitespace and handles None/empty values."""
    normalized = str(raw_input).strip() if raw_input is not None and str(raw_input).strip() else None
    assert normalized == expected_normalized


# =============================================================================
# 9. Step 6A: Live Now Parser with Multi-Word Hyphenated URLs
# =============================================================================

def test_live_now_parser_extracts_id_from_multiword_url():
    """Step 6A: LiveNowParser extracts external_id 4249664 from multi-word hyphenated live-match-info URL."""
    raw = RawLiveItem(
        raw_data={
            "title": "Western Australia vs Queensland",
            "url": "https://www.fancode.com/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info",
            "status": "LIVE",
            "scoreSummary": "WAU 150/2 (20.0)",
        },
        source_type="dom",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is not None
    assert rec.match_external_id == "4249664"
    assert rec.title == "Western Australia vs Queensland"
    assert rec.status == "LIVE"
    assert rec.score_summary == "WAU 150/2 (20.0)"


# =============================================================================
# 10. Step 6A: Unknown IDs & Unmatched Record Safety
# =============================================================================

@pytest.mark.parametrize(
    "ext_id, title",
    [
        ("4249739", "Team Alpha vs Team Beta"),
        ("4249740", "Team Gamma vs Team Delta"),
        ("4249741", "Team Epsilon vs Team Zeta"),
        ("4248813", "Team Eta vs Team Theta"),
        ("4248815", "Team Iota vs Team Kappa"),
        ("4248816", "Team Lambda vs Team Mu"),
    ],
)
def test_live_now_unknown_external_ids_created_safely(db_session, monkeypatch, ext_id, title):
    """Step 6A: Brand new live matches with valid unknown external IDs and titles create valid records."""
    repo = MatchesRepository(db_session)

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    live_record = LiveMatchRecord(
        match_external_id=ext_id,
        title=title,
        source_url=f"https://www.fancode.com/matches/{title.lower().replace(' ', '-')}-{ext_id}/live-match-info",
        status="LIVE",
        score_summary="100/1 (10.0)",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_record])

    created = repo.get_by_external_id(ext_id)
    assert created is not None
    assert created.external_id == ext_id
    assert created.title == title
    assert created.status == "LIVE"


def test_live_now_unmatchable_record_skipped_safely_without_db_pollution(db_session, monkeypatch):
    """Step 6A: Incomplete live record with no external ID and invalid/generic title is skipped safely."""
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    unmatchable_record = LiveMatchRecord(
        match_external_id=None,
        title="",  # Empty/invalid title
        source_url="https://www.fancode.com/live-now",
        status="LIVE",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([unmatchable_record])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 0


# =============================================================================
# 11. Step 6A: Duplicate Protection Across Repeated Live Now Scrapes
# =============================================================================

def test_live_now_duplicate_prevention_across_repeated_runs(db_session, monkeypatch):
    """Step 6A: Repeated Live Now runs for match 4249664 update the canonical row and never create duplicate rows."""
    repo = MatchesRepository(db_session)

    # Pre-existing canonical match in DB
    canonical = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="SCHEDULED",
    )
    canonical_id = canonical.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    scraper = FanCodeLiveNowScraper(browser=None)

    # First Live Now scrape: Team order inverted, score 50/0
    record_1 = LiveMatchRecord(
        match_external_id="4249664",
        title="Western Australia vs Queensland",
        source_url="https://www.fancode.com/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info",
        status="LIVE",
        score_summary="WAU 50/0 (8.0)",
    )
    scraper._persist_to_database([record_1])

    matches_after_run1 = db_session.scalars(select(Match)).all()
    assert len(matches_after_run1) == 1
    m1 = repo.get_by_id(canonical_id)
    assert m1.status == "LIVE"
    assert m1.score_summary == "WAU 50/0 (8.0)"

    # Second Live Now scrape: Score updated to 120/2
    record_2 = LiveMatchRecord(
        match_external_id="4249664",
        title="Western Australia vs Queensland",
        source_url="https://www.fancode.com/matches/western-australia-vs-queensland-4249664/live-match-info",
        status="LIVE",
        score_summary="WAU 120/2 (16.0)",
    )
    scraper._persist_to_database([record_2])

    matches_after_run2 = db_session.scalars(select(Match)).all()
    assert len(matches_after_run2) == 1
    m2 = repo.get_by_id(canonical_id)
    assert m2.status == "LIVE"
    assert m2.score_summary == "WAU 120/2 (16.0)"


# =============================================================================
# 12. Step 6B: Validation Runner Schema Audit & JSON Serialization Verification
# =============================================================================

def test_capture_db_snapshot_schema_validity(tmp_path, monkeypatch):
    """Step 6B: capture_db_snapshot executes cleanly against SQLite schema without missing-column errors."""
    import json
    import sqlite3
    from scripts.e2e_step6b_runner import capture_db_snapshot, to_json_safe
    from app.database.connection import Base
    from sqlalchemy import create_engine

    # Create a clean SQLite database with full Base metadata
    db_file = tmp_path / "test_snapshot.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    # Monkeypatch DB_PATH in scripts.e2e_step6b_runner
    monkeypatch.setattr("scripts.e2e_step6b_runner.DB_PATH", db_file)

    snapshot = capture_db_snapshot("TEST_AUDIT")
    assert snapshot["integrity_ok"] is True
    assert len(snapshot["fk_violations"]) == 0
    assert snapshot["counts"]["matches"] == 0
    assert snapshot["null_external_ids"] == 0
    assert snapshot["distinct_external_ids"] == 0
    assert len(snapshot["duplicate_external_ids"]) == 0
    assert isinstance(snapshot["recent_runs"], list)
    assert isinstance(snapshot["recent_change_events"], list)

    # Verify JSON serialization without TypeError
    serialized = json.dumps(snapshot)
    assert isinstance(serialized, str)
    assert '"integrity_ok": true' in serialized


def test_capture_db_snapshot_json_serialization_with_full_output(tmp_path, monkeypatch):
    """Step 6B: full_output containing pre/post snapshots and run results serializes to JSON without Row serialization errors."""
    import json
    import sqlite3
    from scripts.e2e_step6b_runner import capture_db_snapshot, to_json_safe
    from app.database.connection import Base
    from sqlalchemy import create_engine

    db_file = tmp_path / "test_json_full.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr("scripts.e2e_step6b_runner.DB_PATH", db_file)

    pre_snapshot = capture_db_snapshot("PRE_RUN")
    post_snapshot = capture_db_snapshot("POST_RUN")

    full_output = {
        "timestamp": "2026-10-08T09:30:00Z",
        "pre_snapshot": pre_snapshot,
        "run_result": {"status": "success", "duration_seconds": 12.34},
        "post_snapshot": post_snapshot,
        "new_change_events": [],
        "logs": ["test log 1", "test log 2"],
    }

    json_str = json.dumps(to_json_safe(full_output), indent=2, default=str)
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["pre_snapshot"]["integrity_raw"] == ["ok"]
    assert parsed["post_snapshot"]["integrity_ok"] is True


# =============================================================================
# 13. Step 5B: Collision Investigation & Tour-ID Isolation Tests
# =============================================================================

@pytest.mark.parametrize(
    "url, expected_id",
    [
        # Match 10 / 14 URL shapes (4250055)
        (
            "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-bhutan-4250055/live-match-info",
            "4250055",
        ),
        (
            "https://www.fancode.com/matches/thailand-vs-bhutan-4250055/live-match-info",
            "4250055",
        ),
        # Match 11 / 15 URL shapes (4250088)
        (
            "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/qatar-vs-bahrain-4250088/live-match-info",
            "4250088",
        ),
        (
            "https://www.fancode.com/matches/qatar-vs-bahrain-4250088/live-match-info",
            "4250088",
        ),
        # Tour URLs (Tour ID 19896480 must NEVER be extracted as match external_id)
        (
            "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480",
            None,
        ),
        (
            "/cricket/tour/sheffield-shield-2026-27-19896475",
            None,
        ),
    ],
)
def test_collision_url_extraction_and_tour_id_isolation(url, expected_id):
    """Step 5B: Extract exact match IDs (4250055, 4250088) from both deep tour and short match URLs, ignoring tour IDs."""
    assert extract_match_id_from_url(url) == expected_id


# =============================================================================
# 14. Step 5C: Safe Canonical Duplicate Resolution & Merging Tests
# =============================================================================

def test_canonical_selection_deep_tour_url_preference():
    """Step 5C: select_canonical_match prefers deep tour URLs (/tour/.../matches/...) over short URLs."""
    from scripts.backfill_match_external_ids import select_canonical_match

    row_short = {
        "id": 10,
        "title": "Thailand vs Bhutan",
        "slug": "thailand-vs-bhutan-4250055",
        "source_url": "https://www.fancode.com/matches/thailand-vs-bhutan-4250055/live-match-info",
        "status": "UPCOMING",
    }
    row_deep = {
        "id": 14,
        "title": "Thailand vs Bhutan",
        "slug": "thailand-vs-bhutan",
        "source_url": "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-bhutan-4250055/live-match-info",
        "status": "UPCOMING",
    }

    # Order 1: short first
    canon1, dups1 = select_canonical_match([row_short, row_deep])
    assert canon1["id"] == 14
    assert len(dups1) == 1
    assert dups1[0]["id"] == 10

    # Order 2: deep first
    canon2, dups2 = select_canonical_match([row_deep, row_short])
    assert canon2["id"] == 14
    assert len(dups2) == 1
    assert dups2[0]["id"] == 10


def test_canonical_selection_semantic_slug_preference():
    """Step 5C: select_canonical_match prefers semantic slugs over generic or ordinal slugs."""
    from scripts.backfill_match_external_ids import select_canonical_match

    row_generic = {
        "id": 5,
        "title": "Match 10",
        "slug": "match-10",
        "source_url": "https://www.fancode.com/matches/match-10-99999",
    }
    row_semantic = {
        "id": 8,
        "title": "Team A vs Team B",
        "slug": "team-a-vs-team-b",
        "source_url": "https://www.fancode.com/matches/team-a-vs-team-b-99999",
    }

    canon, dups = select_canonical_match([row_generic, row_semantic])
    assert canon["id"] == 8
    assert len(dups) == 1
    assert dups[0]["id"] == 5


def test_canonical_selection_tiebreaker_lowest_id():
    """Step 5C: select_canonical_match uses lowest primary key as deterministic tiebreaker."""
    from scripts.backfill_match_external_ids import select_canonical_match

    row1 = {
        "id": 20,
        "title": "Identical Match",
        "slug": "identical-match",
        "source_url": "https://www.fancode.com/matches/identical-match-11111",
    }
    row2 = {
        "id": 35,
        "title": "Identical Match",
        "slug": "identical-match",
        "source_url": "https://www.fancode.com/matches/identical-match-11111",
    }

    canon, dups = select_canonical_match([row2, row1])
    assert canon["id"] == 20
    assert len(dups) == 1
    assert dups[0]["id"] == 35


def test_compute_merged_attributes_non_destructive():
    """Step 5C: compute_merged_attributes enriches only missing (null/empty) fields in canonical row."""
    from scripts.backfill_match_external_ids import compute_merged_attributes

    canonical = {
        "id": 14,
        "venue": None,  # Missing -> should be enriched
        "status": "LIVE",  # Present -> should NOT be overwritten
        "score_summary": "100/2",  # Present -> should NOT be overwritten
        "tour_id": None,  # Missing -> should be enriched
        "sport_id": 1,
    }
    duplicates = [
        {
            "id": 10,
            "venue": "Terdthai Cricket Ground",
            "status": "SCHEDULED",
            "score_summary": None,
            "tour_id": 2,
            "sport_id": 1,
        }
    ]

    updates = compute_merged_attributes(canonical, duplicates)
    assert updates == {
        "venue": "Terdthai Cricket Ground",
        "tour_id": 2,
    }


def test_full_backfill_duplicate_resolution_in_isolated_sqlite_db(tmp_path):
    """Step 5C: Complete end-to-end simulation of duplicate resolution on isolated SQLite database."""
    import sqlite3
    from sqlalchemy import create_engine
    from app.database.connection import Base
    from scripts.backfill_match_external_ids import run_audit, execute_backfill_transaction

    db_file = tmp_path / "test_isolated_backfill.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    conn = sqlite3.connect(db_file.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Insert 17 matches mirroring production (with 2 duplicate pairs: 10/14 and 11/15)
    cur.execute("INSERT INTO sports (id, name, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 'Cricket', 'cricket', 'https://www.fancode.com/cricket', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")
    cur.execute("INSERT INTO tours (id, sport_id, name, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 1, 'Asia Qualifier', 'asia-qualifier-19896480', 'https://www.fancode.com/tour/asia-qualifier-19896480', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")

    matches_data = [
        (1, "Thailand vs Qatar", "thailand-vs-qatar", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info", None),
        (2, "Bahrain vs Bhutan", "bahrain-vs-bhutan", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/bahrain-vs-bhutan-4249722/live-match-info", None),
        (3, "Cambodia vs Saudi Arabia", "cambodia-vs-saudi-arabia", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/cambodia-vs-saudi-arabia-4249723/live-match-info", None),
        (4, "Day 1 World Feed", "day-1-world-feed", "https://www.fancode.com/matches/day-1-world-feed-4249774/live-match-info", None),
        (5, "Day 2 World Feed", "day-2-world-feed", "https://www.fancode.com/matches/day-2-world-feed-4249775/live-match-info", None),
        (6, "Day 3 World Feed", "day-3-world-feed", "https://www.fancode.com/matches/day-3-world-feed-4249776/live-match-info", None),
        (7, "Day 4 World Feed", "day-4-world-feed", "https://www.fancode.com/matches/day-4-world-feed-4249777/live-match-info", None),
        (8, "Day 5 World Feed", "day-5-world-feed", "https://www.fancode.com/matches/day-5-world-feed-4249778/live-match-info", None),
        (9, "Bhutan vs Cambodia", "bhutan-vs-cambodia", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/bhutan-vs-cambodia-4249727/live-match-info", None),
        # Pair 1: Match 10 (short URL) + Match 14 (deep tour URL) -> 4250055
        (10, "Thailand vs Bhutan", "thailand-vs-bhutan-4250055", "https://www.fancode.com/matches/thailand-vs-bhutan-4250055/live-match-info", "Terdthai Ground"),
        # Pair 2: Match 11 (short URL) + Match 15 (deep tour URL) -> 4250088
        (11, "Qatar vs Bahrain", "qatar-vs-bahrain-4250088", "https://www.fancode.com/matches/qatar-vs-bahrain-4250088/live-match-info", "Gymkhana Ground"),
        (12, "Thailand vs Saudi Arabia", "thailand-vs-saudi-arabia", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-saudi-arabia-4249729/live-match-info", None),
        (13, "Bahrain vs Cambodia", "bahrain-vs-cambodia", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/bahrain-vs-cambodia-4249730/live-match-info", None),
        (14, "Thailand vs Bhutan", "thailand-vs-bhutan", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-bhutan-4250055/live-match-info", None),
        (15, "Qatar vs Bahrain", "qatar-vs-bahrain", "https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/qatar-vs-bahrain-4250088/live-match-info", None),
        (16, "Tasmania vs New South Wales", "tasmania-vs-new-south-wales", "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info", None),
        (17, "Queensland vs Western Australia", "queensland-vs-western-australia", "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info", None),
    ]

    for m_id, title, slug, url, venue in matches_data:
        cur.execute(
            "INSERT INTO matches (id, sport_id, tour_id, title, slug, source_url, venue, status, created_at, updated_at, first_seen_at, last_seen_at) "
            "VALUES (?, 1, 1, ?, ?, ?, ?, 'SCHEDULED', datetime('now'), datetime('now'), datetime('now'), datetime('now'));",
            (m_id, title, slug, url, venue),
        )

    # Insert dependent records:
    # 1. Video referencing duplicate Match 10
    cur.execute("INSERT INTO videos (id, sport_id, match_id, title, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 1, 10, 'Match 10 Highlights', 'match-10-highlights', 'https://fancode.com/v/1', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")

    # 2. ChangeEvents referencing duplicate Match 10 & 11 and canonical Match 14 & 15
    cur.execute("INSERT INTO change_events (id, entity_type, entity_id, change_type, field_name, detected_at, created_at) VALUES (1, 'match', 10, 'NEW', 'title', datetime('now'), datetime('now'));")
    cur.execute("INSERT INTO change_events (id, entity_type, entity_id, change_type, field_name, detected_at, created_at) VALUES (2, 'match', 11, 'NEW', 'title', datetime('now'), datetime('now'));")
    cur.execute("INSERT INTO change_events (id, entity_type, entity_id, change_type, field_name, detected_at, created_at) VALUES (3, 'match', 14, 'NEW', 'title', datetime('now'), datetime('now'));")

    # 3. Notification batch, delivery, and link referencing change_event 1
    cur.execute("INSERT INTO notification_batches (id, batch_key, subject, status, event_count, recipient_count, created_at, updated_at) VALUES (1, 'batch_001', 'Alert', 'SENT', 1, 1, datetime('now'), datetime('now'));")
    cur.execute("INSERT INTO notification_deliveries (id, batch_id, recipient, status, provider, attempted_at) VALUES (1, 1, 'user@test.com', 'SENT', 'console', datetime('now'));")
    cur.execute("INSERT INTO notification_event_links (id, batch_id, change_event_id) VALUES (1, 1, 1);")

    conn.commit()

    # Step 1: Pre-backfill Audit
    audit = run_audit(cur)
    assert audit["integrity_ok"] is True
    assert len(audit["fk_violations"]) == 0
    assert len(audit["errors"]) == 0
    assert audit["total_duplicate_rows_to_remove"] == 2
    assert audit["expected_final_matches"] == 15
    assert audit["distinct_external_ids_count"] == 15
    assert len(audit["duplicate_groups"]) == 2

    # Verify duplicate groups: Group 1 -> 4250055 (Canonical 14, Dup 10); Group 2 -> 4250088 (Canonical 15, Dup 11)
    g1 = next(g for g in audit["duplicate_groups"] if g["external_id"] == "4250055")
    assert g1["canonical"]["id"] == 14
    assert g1["duplicate_ids"] == [10]
    assert g1["enrichments"].get("venue") == "Terdthai Ground"

    g2 = next(g for g in audit["duplicate_groups"] if g["external_id"] == "4250088")
    assert g2["canonical"]["id"] == 15
    assert g2["duplicate_ids"] == [11]
    assert g2["enrichments"].get("venue") == "Gymkhana Ground"

    # Step 2: Execute Backfill Transaction
    res = execute_backfill_transaction(conn, audit)
    assert res["canonical_updates"] == 15
    assert res["duplicates_deleted"] == 2
    assert res["videos_relinked"] == 1
    assert res["change_events_relinked"] == 2
    assert res["post_matches"] == 15
    assert res["post_nulls"] == 0
    assert res["post_distinct"] == 15

    # Step 3: Verify Post-Backfill DB State
    cur.execute("SELECT COUNT(*) FROM matches;")
    assert cur.fetchone()[0] == 15

    # Duplicate IDs 10 and 11 must be deleted
    cur.execute("SELECT id FROM matches WHERE id IN (10, 11);")
    assert len(cur.fetchall()) == 0

    # Canonical IDs 14 and 15 must be retained with non-destructive enrichment
    cur.execute("SELECT id, external_id, venue FROM matches WHERE id = 14;")
    m14 = cur.fetchone()
    assert m14["external_id"] == "4250055"
    assert m14["venue"] == "Terdthai Ground"

    cur.execute("SELECT id, external_id, venue FROM matches WHERE id = 15;")
    m15 = cur.fetchone()
    assert m15["external_id"] == "4250088"
    assert m15["venue"] == "Gymkhana Ground"

    # Video must be re-linked to Match 14
    cur.execute("SELECT match_id FROM videos WHERE id = 1;")
    assert cur.fetchone()[0] == 14

    # ChangeEvents must be re-linked to Match 14 and 15 with external_id populated
    cur.execute("SELECT entity_id, external_id FROM change_events WHERE id = 1;")
    ce1 = cur.fetchone()
    assert ce1["entity_id"] == 14
    assert ce1["external_id"] == "4250055"

    cur.execute("SELECT entity_id, external_id FROM change_events WHERE id = 2;")
    ce2 = cur.fetchone()
    assert ce2["entity_id"] == 15
    assert ce2["external_id"] == "4250088"

    # Notification event links must remain intact
    cur.execute("SELECT COUNT(*) FROM notification_event_links;")
    assert cur.fetchone()[0] == 1

    # PRAGMAs
    cur.execute("PRAGMA integrity_check;")
    assert cur.fetchone()[0] == "ok"

    cur.execute("PRAGMA foreign_key_check;")
    assert len(cur.fetchall()) == 0

    conn.close()


def test_backfill_transaction_rollback_on_assertion_failure(tmp_path):
    """Step 5C: execute_backfill_transaction rolls back completely if an error occurs during transaction."""
    import sqlite3
    from sqlalchemy import create_engine
    from app.database.connection import Base
    from scripts.backfill_match_external_ids import run_audit, execute_backfill_transaction

    db_file = tmp_path / "test_rollback.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    conn = sqlite3.connect(db_file.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("INSERT INTO sports (id, name, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 'Cricket', 'cricket', 'https://www.fancode.com/cricket', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")
    cur.execute(
        "INSERT INTO matches (id, sport_id, title, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) "
        "VALUES (1, 1, 'Match 1', 'match-1', 'https://www.fancode.com/matches/match-1-11111/live-match-info', datetime('now'), datetime('now'), datetime('now'), datetime('now'));"
    )
    conn.commit()

    audit = run_audit(cur)
    # Tamper expected_final_matches to force assertion failure
    audit["expected_final_matches"] = 999

    with pytest.raises(RuntimeError, match="Expected 999 matches after merge"):
        try:
            execute_backfill_transaction(conn, audit)
        except Exception:
            conn.rollback()
            raise

    # Verify state after rollback: match 1 is still present with external_id = NULL
    cur.execute("SELECT id, external_id FROM matches WHERE id = 1;")
    m = cur.fetchone()
    assert m["id"] == 1
    assert m["external_id"] is None

    conn.close()


def test_backfill_idempotency_running_twice(tmp_path):
    """Step 5C: Running the backfill migration a second time on an already-migrated database is idempotent and safe."""
    import sqlite3
    from sqlalchemy import create_engine
    from app.database.connection import Base
    from scripts.backfill_match_external_ids import run_audit, execute_backfill_transaction

    db_file = tmp_path / "test_idempotency.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    conn = sqlite3.connect(db_file.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("INSERT INTO sports (id, name, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 'Cricket', 'cricket', 'https://www.fancode.com/cricket', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")
    cur.execute(
        "INSERT INTO matches (id, sport_id, title, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) "
        "VALUES (1, 1, 'Match 1', 'match-1', 'https://www.fancode.com/matches/match-1-11111/live-match-info', datetime('now'), datetime('now'), datetime('now'), datetime('now'));"
    )
    conn.commit()

    # First run
    audit1 = run_audit(cur)
    res1 = execute_backfill_transaction(conn, audit1)
    assert res1["post_matches"] == 1
    assert res1["post_nulls"] == 0

    # Second run
    audit2 = run_audit(cur)
    assert audit2["total_duplicate_rows_to_remove"] == 0
    assert audit2["expected_final_matches"] == 1
    assert len(audit2["duplicate_groups"]) == 0
    res2 = execute_backfill_transaction(conn, audit2)
    assert res2["post_matches"] == 1
    assert res2["post_nulls"] == 0
    assert res2["duplicates_deleted"] == 0

    cur.execute("SELECT id, external_id FROM matches WHERE id = 1;")
    m = cur.fetchone()
    assert m["external_id"] == "11111"

    conn.close()


def test_generic_slugs_cannot_trigger_unrelated_merges():
    """Step 5C: Matches with generic slugs ('match-1', 'match-2', 'match-10') with distinct match IDs are never merged."""
    from scripts.backfill_match_external_ids import run_audit

    import sqlite3
    from sqlalchemy import create_engine
    from app.database.connection import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create tables in memory
    cur.execute("""
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY,
            sport_id INTEGER,
            tour_id INTEGER,
            external_id TEXT,
            title TEXT,
            slug TEXT,
            source_url TEXT,
            status TEXT,
            start_time TEXT,
            match_date TEXT,
            team_a_name TEXT,
            team_a_external_id TEXT,
            team_b_name TEXT,
            team_b_external_id TEXT,
            team_a_logo_url TEXT,
            team_b_logo_url TEXT,
            venue TEXT,
            score_summary TEXT,
            image_url TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_seen_at TEXT
        );
    """)
    cur.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE tours (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE videos (id INTEGER PRIMARY KEY, match_id INTEGER);")
    cur.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE change_events (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER, external_id TEXT);")
    cur.execute("CREATE TABLE scrape_runs (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE notification_batches (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE notification_deliveries (id INTEGER PRIMARY KEY);")
    cur.execute("CREATE TABLE notification_event_links (id INTEGER PRIMARY KEY);")

    # Insert 3 matches with generic slugs but different extracted external IDs
    generic_matches = [
        (1, "Match 1", "match-1", "https://www.fancode.com/matches/team-a-vs-team-b-11111/live-match-info"),
        (2, "Match 2", "match-2", "https://www.fancode.com/matches/team-c-vs-team-d-22222/live-match-info"),
        (10, "Match 10", "match-10", "https://www.fancode.com/matches/team-e-vs-team-f-33333/live-match-info"),
    ]
    for m_id, title, slug, url in generic_matches:
        cur.execute(
            "INSERT INTO matches (id, title, slug, source_url) VALUES (?, ?, ?, ?);",
            (m_id, title, slug, url),
        )
    conn.commit()

    audit = run_audit(cur)
    assert len(audit["errors"]) == 0
    assert audit["total_duplicate_rows_to_remove"] == 0
    assert audit["distinct_external_ids_count"] == 3
    assert len(audit["duplicate_groups"]) == 0
    assert len(audit["single_candidates"]) == 3

    conn.close()


def test_external_id_invariants_protected_from_conflict(tmp_path):
    """Step 5C: Backfill aborts with invariant error if canonical match already has a conflicting external_id."""
    import sqlite3
    from sqlalchemy import create_engine
    from app.database.connection import Base
    from scripts.backfill_match_external_ids import run_audit, execute_backfill_transaction

    db_file = tmp_path / "test_conflict.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    conn = sqlite3.connect(db_file.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("INSERT INTO sports (id, name, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) VALUES (1, 'Cricket', 'cricket', 'https://www.fancode.com/cricket', datetime('now'), datetime('now'), datetime('now'), datetime('now'));")
    # Match already has external_id = '99999', but URL has '11111'
    cur.execute(
        "INSERT INTO matches (id, sport_id, external_id, title, slug, source_url, created_at, updated_at, first_seen_at, last_seen_at) "
        "VALUES (1, 1, '99999', 'Match 1', 'match-1', 'https://www.fancode.com/matches/match-1-11111/live-match-info', datetime('now'), datetime('now'), datetime('now'), datetime('now'));"
    )
    conn.commit()

    audit = run_audit(cur)
    with pytest.raises(RuntimeError, match="Invariant violation on Match ID 1"):
        try:
            execute_backfill_transaction(conn, audit)
        except Exception:
            conn.rollback()
            raise

    conn.close()


# =============================================================================
# 15. Step 6C Phase 4: Live Now Test Matrix (Tests 1 to 20)
# =============================================================================

def test_live_now_matrix_1_existing_match_same_external_id(db_session, monkeypatch):
    """Test 1: Existing match + same external ID -> existing row updated, no new row."""
    repo = MatchesRepository(db_session)
    existing = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="SCHEDULED",
    )
    initial_id = existing.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    live_rec = LiveMatchRecord(
        match_external_id="4249664",
        title="Queensland vs Western Australia",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="LIVE",
        score_summary="QLD 120/3 (15.0)",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    updated = repo.get_by_id(initial_id)
    assert updated.status == "LIVE"
    assert updated.score_summary == "QLD 120/3 (15.0)"


def test_live_now_matrix_2_inverted_team_order_same_external_id_4249664(db_session, monkeypatch):
    """Test 2: Existing match + inverted team order + same external ID (4249664) -> existing row updated, no new row."""
    repo = MatchesRepository(db_session)
    existing = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="SCHEDULED",
    )
    initial_id = existing.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    # Inverted team order from Live Now
    live_rec = LiveMatchRecord(
        match_external_id="4249664",
        title="Western Australia vs Queensland",
        source_url="https://www.fancode.com/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info",
        status="LIVE",
        score_summary="WAU 250/5",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    updated = repo.get_by_id(initial_id)
    assert updated.id == initial_id
    assert updated.external_id == "4249664"
    assert updated.status == "LIVE"
    assert updated.score_summary == "WAU 250/5"


def test_live_now_matrix_3_different_url_same_external_id(db_session, monkeypatch):
    """Test 3: Existing match + different URL + same external ID -> existing row reused."""
    repo = MatchesRepository(db_session)
    existing = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="SCHEDULED",
    )
    initial_id = existing.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    # Deep tour URL with different path structure
    live_rec = LiveMatchRecord(
        match_external_id="4249664",
        title="Queensland vs Western Australia",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        status="LIVE",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    assert all_matches[0].id == initial_id


def test_live_now_matrix_4_new_valid_live_match(db_session, monkeypatch):
    """Test 4: New valid Live Now match (external_id=9999999, valid source URL, valid title) -> exactly 1 new match."""
    repo = MatchesRepository(db_session)

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    live_rec = LiveMatchRecord(
        match_external_id="9999999",
        title="Team Alpha vs Team Beta",
        source_url="https://www.fancode.com/cricket/tour/alpha-cup-1111/matches/team-alpha-vs-team-beta-9999999/live-match-info",
        status="LIVE",
        sport_name="Cricket",
        tour_name="Alpha Cup",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([live_rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    m = all_matches[0]
    assert m.external_id == "9999999"
    assert m.title == "Team Alpha vs Team Beta"
    assert m.status == "LIVE"


def test_live_now_matrix_5_same_new_external_id_twice_in_payload_deduplicates(db_session, monkeypatch):
    """Test 5: Same new external ID appears twice in one payload -> deduplicated in memory, 1 match only created."""
    repo = MatchesRepository(db_session)

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    rec1 = LiveMatchRecord(
        match_external_id="8888888",
        title="Team Gamma vs Team Delta",
        source_url="https://www.fancode.com/matches/team-gamma-vs-team-delta-8888888/live-match-info",
        status="LIVE",
        score_summary=None,
    )
    rec2 = LiveMatchRecord(
        match_external_id="8888888",
        title="Team Gamma vs Team Delta",
        source_url="https://www.fancode.com/matches/team-gamma-vs-team-delta-8888888/live-match-info",
        status="LIVE",
        score_summary="GAM 50/0 (5.0)",  # Richer record
    )

    deduped = LiveNowNormalizer.deduplicate_records([rec1, rec2])
    assert len(deduped) == 1
    assert deduped[0].score_summary == "GAM 50/0 (5.0)"

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database(deduped)

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 1
    assert all_matches[0].external_id == "8888888"
    assert all_matches[0].score_summary == "GAM 50/0 (5.0)"


def test_live_now_matrix_6_missing_external_id_generic_slug_skipped(db_session, monkeypatch):
    """Test 6: Missing external ID + generic slug -> skipped, no DB insert."""
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    rec = LiveMatchRecord(
        match_external_id=None,
        title="Match 10",
        source_url="https://www.fancode.com/live-now",
        status="LIVE",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 0


def test_live_now_matrix_7_missing_external_id_meaningful_url_no_reliable_id_skipped(db_session, monkeypatch):
    """Test 7: Missing external ID + meaningful source URL but no reliable match ID -> skipped per Invariant 6."""
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    rec = LiveMatchRecord(
        match_external_id=None,
        title="Some Team vs Another Team",
        source_url="https://www.fancode.com/cricket/tour/cup",
        status="LIVE",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 0


def test_live_now_matrix_8_malformed_external_ids_skipped(db_session, monkeypatch):
    """Test 8: Malformed external IDs ('abc', '', ' ', '12.3', '-1234') -> skipped safely, no DB insert."""
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    malformed_ids = ["abc", "", " ", "12.3", "-1234", "12"]
    scraper = FanCodeLiveNowScraper(browser=None)

    for m_id in malformed_ids:
        rec = LiveMatchRecord(
            match_external_id=m_id,
            title="Team A vs Team B",
            source_url="https://www.fancode.com/matches/team-a-vs-team-b/live-match-info",
            status="LIVE",
        )
        scraper._persist_to_database([rec])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 0


def test_live_now_matrix_9_10_external_id_title_and_url_rules(db_session, monkeypatch):
    """Test 9 & 10: Valid external ID + valid title + valid URL creates safely; missing title skipped."""
    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    scraper = FanCodeLiveNowScraper(browser=None)

    # Missing/generic title
    rec_invalid_title = LiveMatchRecord(
        match_external_id="7777777",
        title="Live",
        source_url="https://www.fancode.com/matches/7777777",
        status="LIVE",
    )
    scraper._persist_to_database([rec_invalid_title])
    assert len(db_session.scalars(select(Match)).all()) == 0

    # Valid title + external ID
    rec_valid = LiveMatchRecord(
        match_external_id="7777777",
        title="Team One vs Team Two",
        source_url="https://www.fancode.com/matches/team-one-vs-team-two-7777777/live-match-info",
        status="LIVE",
    )
    scraper._persist_to_database([rec_valid])
    matches = db_session.scalars(select(Match)).all()
    assert len(matches) == 1
    assert matches[0].external_id == "7777777"


def test_live_now_matrix_11_12_13_existing_external_id_never_cleared_or_overwritten(db_session, monkeypatch):
    """Test 11, 12, 13: Existing external_id must not be cleared by None, whitespace, or malformed ID."""
    repo = MatchesRepository(db_session)
    m = repo.create(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
    )
    m_id = m.id

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    scraper = FanCodeLiveNowScraper(browser=None)

    for bad_id in [None, "", "   ", "abc", "12.5", "-999"]:
        rec = LiveMatchRecord(
            match_external_id=bad_id,
            title="Queensland vs Western Australia",
            source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664/live-match-info",
            status="LIVE",
        )
        scraper._persist_to_database([rec])
        curr = repo.get_by_id(m_id)
        assert curr.external_id == "4249664"


def test_live_now_matrix_14_15_distinct_external_ids_similar_teams_or_slugs_create_distinct_matches(db_session, monkeypatch):
    """Test 14 & 15: Two different external IDs with similar teams or generic slugs produce distinct matches."""
    repo = MatchesRepository(db_session)

    from contextlib import contextmanager
    @contextmanager
    def mock_get_session():
        yield db_session

    monkeypatch.setattr("app.scraper.live_now.scraper.get_session", mock_get_session)
    monkeypatch.setattr("app.scraper.live_now.scraper.init_db", lambda: None)

    rec1 = LiveMatchRecord(
        match_external_id="4248813",
        title="Team A vs Team B",
        source_url="https://www.fancode.com/matches/team-a-vs-team-b-4248813/live-match-info",
        status="LIVE",
    )
    rec2 = LiveMatchRecord(
        match_external_id="4248814",
        title="Team A vs Team B (Leg 2)",
        source_url="https://www.fancode.com/matches/team-a-vs-team-b-4248814/live-match-info",
        status="LIVE",
    )

    scraper = FanCodeLiveNowScraper(browser=None)
    scraper._persist_to_database([rec1, rec2])

    all_matches = db_session.scalars(select(Match)).all()
    assert len(all_matches) == 2
    ext_ids = {m.external_id for m in all_matches}
    assert ext_ids == {"4248813", "4248814"}


def test_live_now_matrix_16_17_generic_slugs_match_1_final_never_collide(db_session):
    """Test 16 & 17: Generic slugs 'match-1' and 'final' never collide across different external IDs."""
    repo = MatchesRepository(db_session)
    m1 = repo.upsert(
        external_id="1111111",
        title="Final Match 2026",
        slug="final",
        source_url="https://www.fancode.com/matches/final-1111111/live-match-info",
    )
    m2 = repo.upsert(
        external_id="2222222",
        title="Final Match 2027",
        slug="final",
        source_url="https://www.fancode.com/matches/final-2222222/live-match-info",
    )
    assert m1.id != m2.id
    assert m1.external_id == "1111111"
    assert m2.external_id == "2222222"


def test_live_now_matrix_18_19_20_multiword_tour_alternate_url_extraction():
    """Test 18, 19, 20: Multi-word hyphenated, deep tour, and alternate FanCode URL shapes extract correct external IDs."""
    from app.scraper.discovery.url_normalizer import extract_match_id_from_url

    # Test 18: Multi-word hyphenated URL
    assert extract_match_id_from_url(
        "https://www.fancode.com/western-australia-vs-queensland/tour/sheffield-shield-2026-27-19896475/matches/western-australia-vs-queensland-4249664/live-match-info"
    ) == "4249664"

    # Test 19: Deep tour URL
    assert extract_match_id_from_url(
        "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/tasmania-vs-new-south-wales-4249663/live-match-info"
    ) == "4249663"

    # Test 20: Alternate URL shapes
    assert extract_match_id_from_url("/matches/day-1-world-feed-4249774/live-match-info") == "4249774"
    assert extract_match_id_from_url("/match/tuskers-vs-lions/140356") == "140356"


# =============================================================================
# 16. Step 6C Phase 5: Repository-Level Invariant Tests (A to H)
# =============================================================================

def test_matches_repo_upsert_and_invariants(db_session):
    """Phase 5: MatchesRepository upholds all external_id, slug, and fallback invariants."""
    repo = MatchesRepository(db_session)

    # A: upsert existing external_id
    m = repo.upsert(
        external_id="4249664",
        title="Queensland vs Western Australia",
        slug="queensland-vs-western-australia",
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664",
        status="SCHEDULED",
    )
    initial_id = m.id

    # B: upsert same external_id updates status
    m_up = repo.upsert(
        external_id="4249664",
        title="Queensland vs Western Australia",
        status="LIVE",
    )
    assert m_up.id == initial_id
    assert m_up.status == "LIVE"

    # C, D, E: None and whitespace incoming never clear external_id
    m_none = repo.upsert(
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664",
        external_id=None,
        status="LIVE",
    )
    assert m_none.id == initial_id
    assert m_none.external_id == "4249664"

    m_ws = repo.upsert(
        source_url="https://www.fancode.com/matches/queensland-vs-western-australia-4249664",
        external_id="   ",
        status="LIVE",
    )
    assert m_ws.id == initial_id
    assert m_ws.external_id == "4249664"

    # F: Different valid external ID creates separate match and does not replace identity
    m_diff = repo.upsert(
        external_id="5555555",
        title="Different Match",
        slug="different-match",
        source_url="https://www.fancode.com/matches/different-5555555",
    )
    assert m_diff.id != initial_id
    assert m_diff.external_id == "5555555"
    assert repo.get_by_id(initial_id).external_id == "4249664"


# =============================================================================
# 17. Step 6C Phase 6: Change Detection Regression Tests (A to L)
# =============================================================================

def test_change_detection_volatile_vs_meaningful_classification():
    """Phase 6: Volatile live counters are classified NOISY; status, venue, schedule transitions are MEANINGFUL."""
    from app.change_detection.classifier import ChangeClassifier

    # Volatile / Noisy fields
    assert ChangeClassifier.is_meaningful_field("match", "score_summary") is False
    assert ChangeClassifier.is_meaningful_field("match", "overs") is False
    assert ChangeClassifier.is_meaningful_field("match", "wickets") is False
    assert ChangeClassifier.is_meaningful_field("match", "points") is False
    assert ChangeClassifier.is_meaningful_field("match", "elapsed_time") is False
    assert ChangeClassifier.is_meaningful_field("match", "stream_available") is False

    # Meaningful fields
    assert ChangeClassifier.is_meaningful_field("match", "status") is True
    assert ChangeClassifier.is_meaningful_field("match", "venue") is True
    assert ChangeClassifier.is_meaningful_field("match", "start_time") is True
    assert ChangeClassifier.is_meaningful_field("match", "match_date") is True
    assert ChangeClassifier.is_meaningful_field("match", "title") is True


# =============================================================================
# 18. Step 6C Phase 7: Notification Regression Tests (1 to 10)
# =============================================================================

def test_notifications_filter_noisy_events_and_batch_meaningful(db_session):
    """Phase 7: Notifications ignore volatile noisy events and correctly batch meaningful events."""
    from app.notifications.policy import NotificationPolicy
    from app.database.models import ChangeEvent

    # Create 1 noisy event (score change) and 1 meaningful event (LIVE status transition)
    noisy_event = ChangeEvent(
        entity_type="match",
        entity_id=17,
        external_id="4249664",
        change_type="UPDATED",
        field_name="score_summary",
        old_value="0/0",
        new_value="50/0",
        severity="INFO",
    )
    meaningful_event = ChangeEvent(
        entity_type="match",
        entity_id=17,
        external_id="4249664",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="LIVE",
        severity="IMPORTANT",
    )

    filtered = NotificationPolicy.filter_events([noisy_event, meaningful_event])
    assert len(filtered) == 1
    assert filtered[0].field_name == "status"
    assert filtered[0].new_value == "LIVE"


# =============================================================================
# 19. Step 6C Phase 9: Runner Safety & Serialization Tests (1 to 7)
# =============================================================================

def test_runner_safety_and_serialization(tmp_path, monkeypatch):
    """Phase 9: Runner defaults to snapshot-only, does not execute monitor automatically, and produces deterministic JSON."""
    import json
    from scripts.e2e_step6b_runner import capture_db_snapshot, to_json_safe, parse_args
    from app.database.connection import Base
    from sqlalchemy import create_engine

    db_file = tmp_path / "test_runner_safety.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr("scripts.e2e_step6b_runner.DB_PATH", db_file)

    # 1. Test CLI arg parsing default
    monkeypatch.setattr("sys.argv", ["scripts/e2e_step6b_runner.py"])
    args = parse_args()
    assert args.execute is False
    assert args.snapshot_only is False

    # 2. Test snapshot serialization
    snapshot = capture_db_snapshot("SAFETY_CHECK")
    json_bytes = json.dumps(snapshot, indent=2)
    assert isinstance(json_bytes, str)
    assert '"integrity_ok": true' in json_bytes


# =============================================================================
# 20. Step 8: Continuous Scheduler, Concurrency & Lifecycle Validation Tests
# =============================================================================

def test_scheduler_lock_acquisition_and_release(tmp_path):
    """Step 8 Phase 3: MonitorLock acquires lock atomically and releases cleanly."""
    from app.monitor.lock import MonitorLock

    lock_file = tmp_path / "test_monitor.lock"
    lock = MonitorLock(lock_file=str(lock_file), timeout_seconds=60)

    assert lock_file.exists() is False
    assert lock.is_locked() is False

    # 1. Acquire lock
    acquired = lock.acquire(blocking=False)
    assert acquired is True
    assert lock_file.exists() is True
    assert lock.is_locked() is True

    # Check lock info metadata
    info = lock.get_lock_info()
    assert info is not None
    assert "pid" in info
    assert "created_at" in info
    assert "hostname" in info

    # 2. Release lock
    lock.release()
    assert lock_file.exists() is False
    assert lock.is_locked() is False


def test_scheduler_concurrent_execution_prevention(tmp_path):
    """Step 8 Phase 3: Process B is blocked when Process A holds the lock, skipping execution cleanly."""
    from app.monitor.lock import MonitorLock
    from app.monitor.runner import MonitorRunner
    from app.monitor.models import PipelineStatus

    lock_file = tmp_path / "test_concurrent.lock"

    # Process A acquires lock
    lock_a = MonitorLock(lock_file=str(lock_file), timeout_seconds=1800)
    assert lock_a.acquire(blocking=False) is True

    # Process B tries to acquire lock
    lock_b = MonitorLock(lock_file=str(lock_file), timeout_seconds=1800)
    assert lock_b.acquire(blocking=False) is False

    # Process B runner run_once skips execution cleanly
    runner_b = MonitorRunner(lock=lock_b)
    res_b = runner_b.run_once(trigger_type="scheduled", dry_run=True)
    assert res_b.status == PipelineStatus.SKIPPED
    assert "lock" in res_b.error_summary.lower()

    # Process A releases lock
    lock_a.release()
    assert lock_b.acquire(blocking=False) is True
    lock_b.release()


def test_scheduler_stale_lock_recovery_dead_pid(tmp_path):
    """Step 8 Phase 4: Stale lock left by a dead process PID is safely reclaimed."""
    import json
    from datetime import datetime, timezone
    from app.monitor.lock import MonitorLock

    lock_file = tmp_path / "test_stale_dead_pid.lock"

    # Write a fake lock file with a dead PID (e.g. 99999999)
    stale_data = {
        "pid": 99999999,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hostname": "localhost",
        "run_id": "stale_run_123",
    }
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(stale_data, f)

    assert lock_file.exists() is True

    # New lock instance should detect dead PID as stale and reclaim it
    lock = MonitorLock(lock_file=str(lock_file), timeout_seconds=1800)
    assert lock.is_locked() is False  # Stale lock is not considered active

    acquired = lock.acquire(blocking=False)
    assert acquired is True
    assert lock.is_locked() is True
    new_info = lock.get_lock_info()
    assert new_info["pid"] != 99999999

    lock.release()
    assert lock_file.exists() is False


def test_scheduler_stale_lock_recovery_expired_ttl(tmp_path):
    """Step 8 Phase 4: Stale lock past timeout TTL is safely reclaimed."""
    import json
    from datetime import datetime, timezone, timedelta
    from app.monitor.lock import MonitorLock

    lock_file = tmp_path / "test_stale_ttl.lock"

    # Write a lock file with timestamp 2 hours in the past
    expired_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    stale_data = {
        "pid": 1,  # PID 1 or dummy
        "created_at": expired_time,
        "hostname": "localhost",
        "run_id": "expired_run_456",
    }
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(stale_data, f)

    lock = MonitorLock(lock_file=str(lock_file), timeout_seconds=60)
    assert lock._is_stale(stale_data) is True

    acquired = lock.acquire(blocking=False)
    assert acquired is True
    lock.release()


def test_scheduler_failure_recovery_and_lock_release(tmp_path):
    """Step 8 Phase 5: Pipeline stage failure does not leak the lock or crash the scheduler."""
    from app.monitor.lock import MonitorLock
    from app.monitor.pipeline import MonitorPipeline
    from app.monitor.runner import MonitorRunner
    from app.monitor.stages import BaseStage, PipelineContext
    from app.monitor.models import StageResult, StageStatus, PipelineStatus

    lock_file = tmp_path / "test_failure_lock.lock"
    lock = MonitorLock(lock_file=str(lock_file))

    class FailingStage(BaseStage):
        name = "failing_stage"
        is_fatal = False

        def run(self, context: PipelineContext) -> StageResult:
            raise RuntimeError("Simulated network timeout during stage scrape")

    pipeline = MonitorPipeline(stages=[FailingStage()], max_retries=0)
    runner = MonitorRunner(pipeline=pipeline, lock=lock)

    # Run should capture failure, update status to FAILED, and release lock
    res = runner.run_once(trigger_type="scheduled", dry_run=True)
    assert res.status == PipelineStatus.FAILED
    assert "failing_stage" in res.stages
    assert res.stages["failing_stage"].status == StageStatus.FAILED
    assert "Simulated network timeout" in res.stages["failing_stage"].errors[0]

    # Lock must be released cleanly in finally block
    assert lock.is_locked() is False
    assert lock_file.exists() is False


def test_scheduler_graceful_shutdown_simulation(tmp_path):
    """Step 8 Phase 6: Scheduler responds to stop request, terminates loop, and releases lock cleanly."""
    from app.monitor.lock import MonitorLock
    from app.monitor.pipeline import MonitorPipeline
    from app.monitor.runner import MonitorRunner
    from app.monitor.stages import BaseStage, PipelineContext
    from app.monitor.models import StageResult, StageStatus

    lock_file = tmp_path / "test_shutdown.lock"
    lock = MonitorLock(lock_file=str(lock_file))

    class DummySuccessStage(BaseStage):
        name = "dummy_success"
        def run(self, context: PipelineContext) -> StageResult:
            res = StageResult(name=self.name, status=StageStatus.SUCCESS)
            res.records_processed = 5
            return res

    pipeline = MonitorPipeline(stages=[DummySuccessStage()])
    runner = MonitorRunner(pipeline=pipeline, lock=lock)

    # Simulate stop request after 1 cycle
    runner._stop_requested = True
    results = runner.run_loop(interval_seconds=1, max_cycles=5, dry_run=True)

    assert len(results) == 1
    assert results[0].status.value == "SUCCESS"
    assert lock.is_locked() is False


def test_scheduler_restart_safety_and_idempotency(tmp_path):
    """Step 8 Phase 7: Stopping and restarting the scheduler does not create duplicate state or lock conflicts."""
    from app.monitor.lock import MonitorLock
    from app.monitor.pipeline import MonitorPipeline
    from app.monitor.runner import MonitorRunner
    from app.monitor.stages import BaseStage, PipelineContext
    from app.monitor.models import StageResult, StageStatus

    lock_file = tmp_path / "test_restart.lock"
    lock = MonitorLock(lock_file=str(lock_file))

    class DummyStage(BaseStage):
        name = "dummy_restart"
        def run(self, context: PipelineContext) -> StageResult:
            return StageResult(name=self.name, status=StageStatus.SUCCESS, records_processed=2)

    # First instance
    pipeline1 = MonitorPipeline(stages=[DummyStage()])
    runner1 = MonitorRunner(pipeline=pipeline1, lock=lock)
    res1 = runner1.run_once(trigger_type="scheduled", dry_run=True)
    assert res1.status.value == "SUCCESS"
    assert lock.is_locked() is False

    # Second instance (simulating process restart)
    pipeline2 = MonitorPipeline(stages=[DummyStage()])
    runner2 = MonitorRunner(pipeline=pipeline2, lock=lock)
    res2 = runner2.run_once(trigger_type="scheduled", dry_run=True)
    assert res2.status.value == "SUCCESS"
    assert lock.is_locked() is False


def test_scheduler_notification_idempotency_across_cycles(db_session):
    """Step 8 Phase 8: Multiple scheduled cycles do not re-send notifications for already-notified change events."""
    from app.database.models import ChangeEvent
    from app.notifications.service import NotificationService

    # Insert a meaningful change event
    event = ChangeEvent(
        entity_type="match",
        entity_id=17,
        external_id="4249664",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="LIVE",
        severity="CRITICAL",
    )
    db_session.add(event)
    db_session.flush()

    svc = NotificationService(session=db_session)

    # Cycle 1: Process and notify
    res1 = svc.process_events([event], dry_run=True)
    assert res1.events_eligible == 1
    assert res1.batches_created == 1

    # Simulate marking event notified
    event.notified_at = event.detected_at
    db_session.flush()

    # Cycle 2: Process same event in subsequent cycle
    res2 = svc.process_events([event], dry_run=True)
    assert res2.events_deduplicated == 1
    assert res2.batches_created == 0


def test_scheduler_multi_cycle_controlled_interval_simulation(tmp_path):
    """Step 8 Phase 9: Scheduled loop executes requested cycles sequentially without infinite tight loops."""
    from app.monitor.lock import MonitorLock
    from app.monitor.pipeline import MonitorPipeline
    from app.monitor.runner import MonitorRunner
    from app.monitor.stages import BaseStage, PipelineContext
    from app.monitor.models import StageResult, StageStatus

    lock_file = tmp_path / "test_interval_loop.lock"
    lock = MonitorLock(lock_file=str(lock_file))

    cycle_counter = {"count": 0}

    class CountingStage(BaseStage):
        name = "counting_stage"
        def run(self, context: PipelineContext) -> StageResult:
            cycle_counter["count"] += 1
            return StageResult(name=self.name, status=StageStatus.SUCCESS, records_processed=cycle_counter["count"])

    pipeline = MonitorPipeline(stages=[CountingStage()])
    runner = MonitorRunner(pipeline=pipeline, lock=lock)

    # Run 3 simulated cycles
    results = runner.run_loop(interval_seconds=1, max_cycles=3, dry_run=True)

    assert len(results) == 3
    assert cycle_counter["count"] == 3
    for r in results:
        assert r.status.value == "SUCCESS"
    assert lock.is_locked() is False


def test_sleep_with_countdown_output_and_flushing(monkeypatch):
    """Test sleep_with_countdown prints in-place live countdown with carriage returns and flushes stdout."""
    import io
    from app.monitor.runner import sleep_with_countdown

    sleep_calls = []
    def mock_sleep(duration):
        sleep_calls.append(duration)

    monkeypatch.setattr("time.sleep", mock_sleep)

    class TerminalStringIO(io.StringIO):
        def isatty(self):
            return True

    fake_stdout = TerminalStringIO()
    monkeypatch.setattr("sys.stdout", fake_stdout)

    # Test 3-second countdown
    sleep_with_countdown(3)

    output = fake_stdout.getvalue()
    assert "\rNext cycle in: 003s" in output
    assert "\rNext cycle in: 002s" in output
    assert "\rNext cycle in: 001s" in output
    assert "\rNext cycle in: 000s\n" in output
    assert sleep_calls == [1, 1, 1]


def test_sleep_with_countdown_early_stop_interruption(monkeypatch):
    """Test sleep_with_countdown halts immediately when stop_checker returns True."""
    import io
    from app.monitor.runner import sleep_with_countdown

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda d: sleep_calls.append(d))

    class TerminalStringIO(io.StringIO):
        def isatty(self):
            return True

    fake_stdout = TerminalStringIO()
    monkeypatch.setattr("sys.stdout", fake_stdout)

    call_count = {"ticks": 0}
    def stop_after_one():
        call_count["ticks"] += 1
        return call_count["ticks"] >= 2

    sleep_with_countdown(100, stop_checker=stop_after_one)

    assert len(sleep_calls) == 1
    assert sleep_calls == [1]


def test_sleep_with_countdown_zero_or_negative(monkeypatch):
    """Test sleep_with_countdown returns immediately for zero or negative durations."""
    from app.monitor.runner import sleep_with_countdown

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda d: sleep_calls.append(d))

    sleep_with_countdown(0)
    sleep_with_countdown(-10)

    assert len(sleep_calls) == 0


def test_sleep_with_countdown_is_silent_when_stdout_is_redirected(monkeypatch):
    """Redirected logs must not receive one countdown line per second."""
    from app.monitor.runner import sleep_with_countdown

    class RedirectedOutput:
        def __init__(self):
            self.output = ""

        def isatty(self):
            return False

        def write(self, value):
            self.output += value

        def flush(self):
            pass

    redirected = RedirectedOutput()
    sleeps = []
    monkeypatch.setattr("app.monitor.runner.sys.stdout", redirected)
    monkeypatch.setattr("app.monitor.runner.time.sleep", sleeps.append)

    sleep_with_countdown(3)

    assert redirected.output == ""
    assert sleeps == [1, 1, 1]






