"""
test_tours_parser.py – Unit tests for tours / series parsing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.tours.parser import ToursParser
from tests.fixtures.tours import (
    SAMPLE_TOUR_MALFORMED,
    SAMPLE_TOUR_NO_DATES,
    SAMPLE_TOUR_NORMAL,
)


class TestToursParser:
    def test_parse_normal_tour(self) -> None:
        record = ToursParser.parse_tour_dict(SAMPLE_TOUR_NORMAL)
        assert record is not None
        assert record.name == "Indian Premier League 2026"
        assert record.external_id == "tour-101"
        assert record.slug == "ipl-2026"
        assert record.sport_name == "Cricket"
        assert record.status == "UPCOMING"
        assert record.start_date is not None
        assert record.end_date is not None

    def test_parse_tour_no_dates(self) -> None:
        record = ToursParser.parse_tour_dict(SAMPLE_TOUR_NO_DATES)
        assert record is not None
        assert record.name == "English Premier League"
        assert record.external_id == "tour-102"
        assert record.sport_name == "Football"
        assert record.start_date is None

    def test_parse_malformed_tour_returns_none(self) -> None:
        record = ToursParser.parse_tour_dict(SAMPLE_TOUR_MALFORMED)
        assert record is None

    def test_extract_tours_from_nested_json(self) -> None:
        payload = {
            "competitions": [
                SAMPLE_TOUR_NORMAL,
                SAMPLE_TOUR_NO_DATES,
            ]
        }
        extracted = ToursParser.extract_tours_from_json(payload)
        assert len(extracted) == 2
        assert extracted[0].name == "Indian Premier League 2026"
        assert extracted[1].name == "English Premier League"
