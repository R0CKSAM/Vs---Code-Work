"""
test_sports_parser.py – Unit tests for sports parsing and safe traversal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.sports.parser import SportsParser
from tests.fixtures.sports import (
    SAMPLE_SPORT_MALFORMED,
    SAMPLE_SPORT_NO_ID,
    SAMPLE_SPORT_NO_IMAGE,
    SAMPLE_SPORT_NORMAL,
)


class TestSportsParser:
    def test_parse_normal_sport(self) -> None:
        record = SportsParser.parse_sport_dict(SAMPLE_SPORT_NORMAL)
        assert record is not None
        assert record.name == "Cricket"
        assert record.external_id == "sport-1"
        assert record.slug == "cricket"
        assert record.is_active is True
        assert record.image_url == "https://img.fancode.com/cricket.png"

    def test_parse_sport_no_image(self) -> None:
        record = SportsParser.parse_sport_dict(SAMPLE_SPORT_NO_IMAGE)
        assert record is not None
        assert record.name == "Football"
        assert record.external_id == "sport-2"
        assert record.image_url is None

    def test_parse_sport_no_id(self) -> None:
        record = SportsParser.parse_sport_dict(SAMPLE_SPORT_NO_ID)
        assert record is not None
        assert record.name == "Kabaddi"
        assert record.external_id is None
        assert record.slug == "kabaddi"

    def test_parse_malformed_sport_returns_none(self) -> None:
        record = SportsParser.parse_sport_dict(SAMPLE_SPORT_MALFORMED)
        assert record is None

    def test_extract_sports_from_nested_json(self) -> None:
        payload = {
            "data": {
                "navigation": {
                    "sports": [
                        SAMPLE_SPORT_NORMAL,
                        SAMPLE_SPORT_NO_IMAGE,
                    ]
                }
            }
        }
        extracted = SportsParser.extract_sports_from_json(payload)
        assert len(extracted) == 2
        assert extracted[0].name == "Cricket"
        assert extracted[1].name == "Football"
