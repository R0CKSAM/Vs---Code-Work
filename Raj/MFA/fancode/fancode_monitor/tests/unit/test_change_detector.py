"""
Unit tests for ChangeDetector engine (Phase 8).
"""

import pytest
from app.change_detection.detector import ChangeDetector
from app.change_detection.models import ChangeType, EntityType, Severity
from app.database.models import Match, Video
from tests.fixtures.change_detection import (
    SAMPLE_MATCH_A_RESCHEDULED,
    SAMPLE_MATCH_A_SCHEDULED,
    SAMPLE_MATCH_A_SCORE_NOISE,
    SAMPLE_MATCH_A_WENT_LIVE,
    SAMPLE_VIDEO_NEW,
)


class TestChangeDetector:
    def test_detect_new_match_created(self, db_session):
        detector = ChangeDetector(session=db_session)
        result = detector.detect_matches([SAMPLE_MATCH_A_SCHEDULED])

        assert result.entities_checked == 1
        assert result.created_events == 1
        assert len(result.events) == 1
        event = result.events[0]
        assert event.change_type == ChangeType.CREATED.value
        assert event.entity_type == EntityType.MATCH.value

    def test_detect_score_only_noise_produces_no_event(self, db_session):
        # 1. Pre-seed DB with initial match
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
            venue="Wankhede Stadium, Mumbai",
        )
        db_session.add(match)
        db_session.commit()

        # 2. Run detection with only score changed (120/3 -> 121/3)
        detector = ChangeDetector(session=db_session)
        result = detector.detect_matches([SAMPLE_MATCH_A_SCORE_NOISE])

        assert result.entities_checked == 1
        # CRITICAL PRINCIPLE: Score updates are never notification/change events!
        assert result.created_events == 0
        assert result.updated_events == 0
        assert result.status_events == 0
        assert len(result.events) == 0

    def test_detect_status_change_to_live(self, db_session):
        # 1. Pre-seed DB
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
            venue="Wankhede Stadium, Mumbai",
        )
        db_session.add(match)
        db_session.commit()

        # 2. Match goes live
        detector = ChangeDetector(session=db_session)
        result = detector.detect_matches([SAMPLE_MATCH_A_WENT_LIVE])

        assert result.status_events == 1
        assert len(result.events) == 1
        ev = result.events[0]
        assert ev.change_type == ChangeType.STATUS_CHANGED.value
        assert ev.field_name == "status"
        assert ev.old_value == "UPCOMING"
        assert ev.new_value == "LIVE"
        assert ev.severity == Severity.CRITICAL.value

    def test_detect_venue_rescheduled(self, db_session):
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
            venue="Wankhede Stadium, Mumbai",
        )
        db_session.add(match)
        db_session.commit()

        detector = ChangeDetector(session=db_session)
        result = detector.detect_matches([SAMPLE_MATCH_A_RESCHEDULED])

        assert result.updated_events == 1
        ev = result.events[0]
        assert ev.change_type == ChangeType.UPDATED.value
        assert ev.field_name == "venue"
        assert "DY Patil" in ev.new_value

    def test_event_deduplication_on_repeated_runs(self, db_session):
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
            venue="Wankhede Stadium, Mumbai",
        )
        db_session.add(match)
        db_session.commit()

        detector = ChangeDetector(session=db_session)

        # Run 1: Detects venue change and persists event
        res1 = detector.detect_matches([SAMPLE_MATCH_A_RESCHEDULED])
        assert res1.updated_events == 1
        assert len(res1.events) == 1

        # Run 2: Exact same incoming data -> Deduplicated, no new event created!
        res2 = detector.detect_matches([SAMPLE_MATCH_A_RESCHEDULED])
        assert res2.updated_events == 0
        assert res2.ignored_changes >= 1
        assert len(res2.events) == 0

    def test_dry_run_does_not_persist(self, db_session):
        detector = ChangeDetector(session=db_session)
        result = detector.detect_matches([SAMPLE_MATCH_A_SCHEDULED], dry_run=True)

        assert result.created_events == 1
        assert len(result.events) == 1

        # Check DB repository: no event persisted!
        from app.database.repositories import ChangeEventsRepository

        repo = ChangeEventsRepository(db_session)
        assert len(repo.get_recent()) == 0

    def test_removal_safety_incomplete_snapshot_never_removes(self, db_session):
        # Match exists in DB
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
        )
        db_session.add(match)
        db_session.commit()

        detector = ChangeDetector(session=db_session)

        # Scrape fails or returns empty / partial items with complete_snapshot=False
        result = detector.detect_matches([], complete_snapshot=False)
        assert result.removed_events == 0
        assert len(result.events) == 0

    def test_removal_with_complete_snapshot(self, db_session):
        match = Match(
            external_id="101",
            title="Mumbai Indians vs Chennai Super Kings",
            slug="mumbai-indians-vs-chennai-super-kings",
            source_url="https://www.fancode.com/match/101",
            status="UPCOMING",
        )
        db_session.add(match)
        db_session.commit()

        detector = ChangeDetector(session=db_session)

        # Complete snapshot provided with another match, omitting match-101
        other_match = {
            "match_id": "match-999",
            "title": "Delhi Capitals vs Punjab Kings",
            "source_url": "https://www.fancode.com/match/999",
            "status": "UPCOMING",
        }
        result = detector.detect_matches([other_match], complete_snapshot=True)

        assert result.removed_events == 1
        assert any(e.change_type == ChangeType.REMOVED.value and e.entity_id == match.id for e in result.events)

    def test_detect_new_video(self, db_session):
        detector = ChangeDetector(session=db_session)
        result = detector.detect_videos([SAMPLE_VIDEO_NEW])

        assert result.created_events == 1
        assert result.events[0].entity_type == EntityType.VIDEO.value
        assert result.events[0].change_type == ChangeType.CREATED.value
