"""
test_match_detail_normalizer.py – Unit tests for Match Detail normalization.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.match_detail.normalizer import (
    derive_match_identity,
    normalize_venue_details,
)


class TestMatchDetailNormalizer:
    def test_derive_match_identity(self) -> None:
        # Priority 1: external_id
        id1 = derive_match_identity("match-999", "https://www.fancode.com/matches/mi-vs-csk")
        assert id1 == "match-999"

        # Priority 2: source_url
        id2 = derive_match_identity(None, "https://www.fancode.com/matches/mi-vs-csk?utm_source=fancode")
        assert id2 == "https://www.fancode.com/matches/mi-vs-csk"

    def test_normalize_venue_details(self) -> None:
        full, name, city, country = normalize_venue_details("Eden Gardens", "Kolkata", "India")
        assert full == "Eden Gardens"
        assert name == "Eden Gardens"
        assert city == "Kolkata"
        assert country == "India"

    def test_normalize_empty_venue(self) -> None:
        full, name, city, country = normalize_venue_details(None)
        assert full is None
        assert name is None
