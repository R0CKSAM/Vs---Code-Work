"""
Test fixtures for Alerting & Notification Engine (Phase 9).
"""

from __future__ import annotations

from datetime import datetime, timezone
from app.change_detection.models import ChangeType, EntityType, Severity


SAMPLE_EVENT_MATCH_CREATED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.CREATED.value,
    "field_name": None,
    "old_value": None,
    "new_value": "Mumbai Indians vs Chennai Super Kings",
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
        "venue": "Wankhede Stadium, Mumbai",
    },
}

SAMPLE_EVENT_MATCH_LIVE = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.STATUS_CHANGED.value,
    "field_name": "status",
    "old_value": "UPCOMING",
    "new_value": "LIVE",
    "severity": Severity.CRITICAL.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_MATCH_COMPLETED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.STATUS_CHANGED.value,
    "field_name": "status",
    "old_value": "LIVE",
    "new_value": "COMPLETED",
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_MATCH_CANCELLED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.STATUS_CHANGED.value,
    "field_name": "status",
    "old_value": "UPCOMING",
    "new_value": "CANCELLED",
    "severity": Severity.CRITICAL.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_MATCH_POSTPONED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.STATUS_CHANGED.value,
    "field_name": "status",
    "old_value": "UPCOMING",
    "new_value": "POSTPONED",
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_MATCH_VENUE_CHANGED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.UPDATED.value,
    "field_name": "venue",
    "old_value": "Wankhede Stadium, Mumbai",
    "new_value": "DY Patil Stadium, Navi Mumbai",
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_MATCH_START_TIME_CHANGED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.UPDATED.value,
    "field_name": "start_time",
    "old_value": "2026-05-10T14:00:00Z",
    "new_value": "2026-05-10T15:30:00Z",
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_VIDEO_CREATED = {
    "entity_type": EntityType.VIDEO.value,
    "entity_id": 201,
    "external_id": "vid-201",
    "change_type": ChangeType.CREATED.value,
    "field_name": None,
    "old_value": None,
    "new_value": "MI vs CSK Top Highlights 2026",
    "severity": Severity.INFO.value,
    "source_url": "https://www.fancode.com/video/vid-201",
    "metadata_json": {
        "title": "MI vs CSK Top Highlights 2026",
        "video_type": "HIGHLIGHTS",
    },
}

SAMPLE_EVENT_TOUR_CREATED = {
    "entity_type": EntityType.TOUR.value,
    "entity_id": 301,
    "external_id": "tour-301",
    "change_type": ChangeType.CREATED.value,
    "field_name": None,
    "old_value": None,
    "new_value": "IPL 2026",
    "severity": Severity.INFO.value,
    "source_url": "https://www.fancode.com/tour/ipl-2026",
    "metadata_json": {
        "name": "IPL 2026",
    },
}

SAMPLE_EVENT_SPORT_CREATED = {
    "entity_type": EntityType.SPORT.value,
    "entity_id": 401,
    "external_id": "sport-401",
    "change_type": ChangeType.CREATED.value,
    "field_name": None,
    "old_value": None,
    "new_value": "Cricket",
    "severity": Severity.INFO.value,
    "source_url": "https://www.fancode.com/cricket",
    "metadata_json": {
        "name": "Cricket",
    },
}

SAMPLE_EVENT_MATCH_REMOVED = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.REMOVED.value,
    "field_name": None,
    "old_value": "Mumbai Indians vs Chennai Super Kings",
    "new_value": None,
    "severity": Severity.IMPORTANT.value,
    "source_url": "https://www.fancode.com/match/101",
    "metadata_json": {
        "title": "Mumbai Indians vs Chennai Super Kings",
    },
}

SAMPLE_EVENT_NOISY_SCORE = {
    "entity_type": EntityType.MATCH.value,
    "entity_id": 101,
    "external_id": "101",
    "change_type": ChangeType.UPDATED.value,
    "field_name": "score_summary",
    "old_value": "120/3 in 15.0 ov",
    "new_value": "121/3 in 15.1 ov",
    "severity": "LOW",
    "source_url": "https://www.fancode.com/match/101",
}
