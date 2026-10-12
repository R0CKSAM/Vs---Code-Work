"""
test_match_detail_parser.py – Unit tests for Match Detail parser.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.match_detail.models import RawMatchDetail
from app.scraper.match_detail.parser import MatchDetailParser
from tests.fixtures.match_detail import (
    SAMPLE_MATCH_DETAIL_COMPLETED,
    SAMPLE_MATCH_DETAIL_INDIVIDUAL,
    SAMPLE_MATCH_DETAIL_MALFORMED,
    SAMPLE_MATCH_DETAIL_NO_VENUE,
    SAMPLE_MATCH_DETAIL_NORMAL,
)


class TestMatchDetailParser:
    def test_parse_normal_match_detail(self) -> None:
        raw = RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_NORMAL)
        detail = MatchDetailParser.parse_detail(raw)
        assert detail is not None
        assert detail.match_external_id == "match-501"
        assert detail.title == "Mumbai Indians vs Chennai Super Kings"
        assert detail.venue == "Wankhede Stadium"
        assert detail.venue_city == "Mumbai"
        assert detail.sport_name == "Cricket"
        assert detail.tour_name == "Indian Premier League 2026"
        assert detail.team_a_name == "Mumbai Indians"
        assert detail.team_a_logo_url == "https://img.fancode.com/mi.png"
        assert detail.streaming_available is True

    def test_parse_match_detail_no_venue(self) -> None:
        raw = RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_NO_VENUE)
        detail = MatchDetailParser.parse_detail(raw)
        assert detail is not None
        assert detail.venue is None
        assert detail.match_external_id == "match-502"
        assert detail.sport_name == "Football"

    def test_parse_completed_match_with_score(self) -> None:
        raw = RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_COMPLETED)
        detail = MatchDetailParser.parse_detail(raw)
        assert detail is not None
        assert detail.status == "COMPLETED"
        assert "IND won by 20 runs" in detail.score_summary

    def test_parse_individual_event_detail(self) -> None:
        raw = RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_INDIVIDUAL)
        detail = MatchDetailParser.parse_detail(raw)
        assert detail is not None
        assert detail.team_a_name is None
        assert detail.venue == "Bahrain International Circuit"

    def test_parse_malformed_detail(self) -> None:
        raw = RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_MALFORMED)
        detail = MatchDetailParser.parse_detail(raw)
        assert detail is not None
        assert detail.match_external_id is None
        assert detail.title is None

    def test_extract_embedded_next_data(self) -> None:
        html = '<html><body><script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"matchId": "123"}}}</script></body></html>'
        data = MatchDetailParser.extract_embedded_json(html)
        assert data is not None
        assert data["props"]["pageProps"]["matchId"] == "123"
