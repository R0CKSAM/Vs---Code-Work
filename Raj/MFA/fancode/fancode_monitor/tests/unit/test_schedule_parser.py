"""
test_schedule_parser.py – Unit tests for schedule parsing and defensive extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.schedule.models import RawScheduleItem
from app.scraper.schedule.parser import ScheduleParser, safe_get
from tests.fixtures.schedule import (
    SAMPLE_CRICKET_MATCH,
    SAMPLE_FOOTBALL_MATCH,
    SAMPLE_INDIVIDUAL_EVENT,
    SAMPLE_MALFORMED_ITEM,
)


class TestScheduleParser:
    def test_safe_get_traversal(self) -> None:
        data = {"a": {"b": {"c": 42}}}
        assert safe_get(data, "a", "b", "c") == 42
        assert safe_get(data, "a", "nonexistent") is None
        assert safe_get(None, "a") is None

    def test_parse_normal_cricket_match(self) -> None:
        item = RawScheduleItem(raw_data=SAMPLE_CRICKET_MATCH)
        match = ScheduleParser.parse_item(item)
        assert match is not None
        assert match.external_id == "match-901"
        assert match.title == "India vs Australia 1st ODI"
        assert match.status == "UPCOMING"
        assert match.sport_name == "Cricket"
        assert match.tour_name == "Australia Tour of India 2026"
        assert match.team_a_name == "India"
        assert match.team_b_name == "Australia"
        assert match.team_a_logo_url == "https://img.fancode.com/ind.png"

    def test_parse_football_match(self) -> None:
        item = RawScheduleItem(raw_data=SAMPLE_FOOTBALL_MATCH)
        match = ScheduleParser.parse_item(item)
        assert match is not None
        assert match.external_id == "fb-888"
        assert match.title == "Arsenal vs Chelsea"
        assert match.status == "LIVE"
        assert match.sport_name == "Football"
        assert match.tour_name == "Premier League"
        assert match.team_a_name == "Arsenal"
        assert match.team_b_name == "Chelsea"

    def test_parse_individual_event(self) -> None:
        item = RawScheduleItem(raw_data=SAMPLE_INDIVIDUAL_EVENT)
        match = ScheduleParser.parse_item(item)
        assert match is not None
        assert match.external_id == "f1-100"
        assert match.title == "Monaco Grand Prix Qualifying"
        assert match.team_a_name is None
        assert match.team_b_name is None
        assert match.venue == "Circuit de Monaco"

    def test_parse_malformed_item_returns_none(self) -> None:
        item = RawScheduleItem(raw_data=SAMPLE_MALFORMED_ITEM)
        match = ScheduleParser.parse_item(item)
        assert match is None

    def test_extract_raw_items_from_nested_json(self) -> None:
        nested_payload = {
            "status": "success",
            "data": {
                "sections": [
                    {
                        "matches": [
                            SAMPLE_CRICKET_MATCH,
                            SAMPLE_FOOTBALL_MATCH,
                        ]
                    }
                ]
            }
        }
        items = ScheduleParser.extract_raw_items_from_json(nested_payload)
        assert len(items) == 2
        assert items[0].get("id") == "match-901"
        assert items[1].get("matchId") == "fb-888"
