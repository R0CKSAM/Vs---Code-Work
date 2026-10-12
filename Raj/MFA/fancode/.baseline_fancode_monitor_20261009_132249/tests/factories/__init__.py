"""
factories.py – Deterministic test data factories for Phase 2 database entities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def build_sport_data(**overrides: Any) -> Dict[str, Any]:
    data = {
        "name": "Cricket",
        "slug": "cricket",
        "external_id": "sport-101",
        "source_url": "https://www.fancode.com/cricket",
        "description": "Cricket matches and tournaments",
        "image_url": "https://images.fancode.com/cricket.png",
        "is_active": True,
    }
    data.update(overrides)
    return data


def build_tour_data(sport_id: int | None = None, **overrides: Any) -> Dict[str, Any]:
    data = {
        "name": "Indian Premier League 2026",
        "slug": "ipl-2026",
        "external_id": "tour-202",
        "sport_id": sport_id,
        "source_url": "https://www.fancode.com/tours/ipl-2026",
        "description": "T20 Cricket Tournament",
        "status": "UPCOMING",
        "start_date": datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return data


def build_match_data(tour_id: int | None = None, sport_id: int | None = None, **overrides: Any) -> Dict[str, Any]:
    data = {
        "title": "Mumbai Indians vs Chennai Super Kings",
        "slug": "mi-vs-csk-2026",
        "external_id": "match-303",
        "tour_id": tour_id,
        "sport_id": sport_id,
        "source_url": "https://www.fancode.com/matches/mi-vs-csk-2026",
        "status": "SCHEDULED",
        "venue": "Wankhede Stadium, Mumbai",
        "team_a_name": "Mumbai Indians",
        "team_a_external_id": "team-mi",
        "team_b_name": "Chennai Super Kings",
        "team_b_external_id": "team-csk",
        "match_date": datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return data


def build_video_data(tour_id: int | None = None, match_id: int | None = None, sport_id: int | None = None, **overrides: Any) -> Dict[str, Any]:
    data = {
        "title": "MI vs CSK Top Highlights",
        "slug": "mi-vs-csk-highlights",
        "external_id": "video-404",
        "tour_id": tour_id,
        "match_id": match_id,
        "sport_id": sport_id,
        "source_url": "https://www.fancode.com/video/mi-vs-csk-highlights",
        "duration_seconds": 600,
        "video_type": "HIGHLIGHT",
    }
    data.update(overrides)
    return data


def build_page_data(**overrides: Any) -> Dict[str, Any]:
    data = {
        "url": "https://www.fancode.com/cricket",
        "canonical_url": "https://www.fancode.com/cricket",
        "page_type": "SPORT",
        "title": "Live Cricket Streaming & Schedule",
        "http_status": 200,
        "content_type": "text/html",
        "is_json": False,
        "metadata_json": {"links_count": 25, "section": "cricket"},
    }
    data.update(overrides)
    return data


def build_change_event_data(**overrides: Any) -> Dict[str, Any]:
    data = {
        "entity_type": "match",
        "entity_id": 1,
        "external_id": "match-303",
        "change_type": "STATUS_CHANGED",
        "field_name": "status",
        "old_value": "SCHEDULED",
        "new_value": "LIVE",
        "source_url": "https://www.fancode.com/matches/mi-vs-csk-2026",
    }
    data.update(overrides)
    return data


def build_scrape_run_data(**overrides: Any) -> Dict[str, Any]:
    data = {
        "run_type": "discovery",
        "metadata_json": {"depth": 2, "seed": "https://www.fancode.com"},
    }
    data.update(overrides)
    return data
