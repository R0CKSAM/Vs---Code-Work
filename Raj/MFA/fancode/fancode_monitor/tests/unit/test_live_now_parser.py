"""
test_live_now_parser.py – Unit tests for Live Now parser and defensive extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.live_now.models import RawLiveItem
from app.scraper.live_now.parser import LiveNowParser, safe_get
from tests.fixtures.live_now import (
    SAMPLE_LIVE_CRICKET,
    SAMPLE_LIVE_FOOTBALL,
    SAMPLE_LIVE_INDIVIDUAL_SPORT,
    SAMPLE_LIVE_MALFORMED,
    SAMPLE_LIVE_MISSING_SCORE,
    SAMPLE_LIVE_MISSING_TEAMS,
    SAMPLE_LIVE_MISSING_VENUE,
    SAMPLE_NESTED_LIVE_PAYLOAD,
)


class TestLiveNowParser:
    def test_safe_get_traversal(self) -> None:
        data = {"foo": {"bar": [10, 20, 30]}}
        assert safe_get(data, "foo", "bar", 1) == 20
        assert safe_get(data, "foo", "bar", 99) is None
        assert safe_get(data, "nonexistent") is None
        assert safe_get(None, "foo") is None

    def test_parse_normal_live_cricket(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_CRICKET)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.match_external_id == "crick-live-101"
        assert rec.title == "Mumbai Indians vs Chennai Super Kings"
        assert rec.status == "LIVE"
        assert rec.sport_name == "Cricket"
        assert rec.tour_name == "Indian Premier League 2026"
        assert rec.team_a_name == "Mumbai Indians"
        assert rec.team_b_name == "Chennai Super Kings"
        assert rec.score_summary == "MI 152/4 (16.2 ov)"
        assert rec.venue == "Wankhede Stadium, Mumbai"
        assert rec.stream_available is True
        assert rec.stream_language == "English"
        assert rec.metadata.get("overs") == "16.2"

    def test_parse_live_football(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_FOOTBALL)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.match_external_id == "fb-live-202"
        assert rec.title == "Arsenal vs Chelsea"
        assert rec.status == "LIVE"
        assert rec.sport_name == "Football"
        assert rec.tour_name == "Premier League"
        assert rec.team_a_name == "Arsenal"
        assert rec.team_b_name == "Chelsea"
        assert rec.score_summary == "ARS 2 - 1 CHE"
        assert rec.venue == "Emirates Stadium"

    def test_parse_individual_sport(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_INDIVIDUAL_SPORT)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.match_external_id == "f1-live-303"
        assert rec.title == "Monaco Grand Prix - Race"
        assert rec.sport_name == "Motorsport"
        assert rec.score_summary == "Lap 45/78"
        assert rec.team_a_name is None

    def test_parse_missing_score(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_MISSING_SCORE)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.score_summary is None
        assert rec.team_a_name == "KKR"

    def test_parse_missing_venue(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_MISSING_VENUE)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.venue is None
        assert rec.score_summary == "0 - 0 (HT)"

    def test_parse_missing_teams(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_MISSING_TEAMS)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is not None
        assert rec.team_a_name is None
        assert rec.title == "World Athletics Championship 100m Final"

    def test_parse_malformed_item(self) -> None:
        raw = RawLiveItem(raw_data=SAMPLE_LIVE_MALFORMED)
        rec = LiveNowParser.parse_live_item(raw)
        assert rec is None

    def test_extract_from_nested_json(self) -> None:
        items = LiveNowParser.extract_live_items_from_payload(SAMPLE_NESTED_LIVE_PAYLOAD)
        assert len(items) >= 2
        parsed = [LiveNowParser.parse_live_item(it) for it in items]
        valid = [p for p in parsed if p is not None]
        assert len(valid) == 2
        titles = {v.title for v in valid}
        assert "Mumbai Indians vs Chennai Super Kings" in titles
        assert "Arsenal vs Chelsea" in titles

    def test_unrelated_json_ignored(self) -> None:
        unrelated = {
            "nav": [{"label": "Home", "url": "/"}, {"label": "About", "url": "/about"}],
            "footer": {"copyright": "2026 FanCode"},
        }
        items = LiveNowParser.extract_live_items_from_payload(unrelated)
        assert len(items) == 0

    def test_extract_embedded_json(self) -> None:
        html = '<html><head><script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"live": true}}}</script></head><body></body></html>'
        data = LiveNowParser.extract_embedded_json(html)
        assert data is not None
        assert data["props"]["pageProps"]["live"] is True

        empty_html = "<html><body>No Next Data</body></html>"
        assert LiveNowParser.extract_embedded_json(empty_html) is None
