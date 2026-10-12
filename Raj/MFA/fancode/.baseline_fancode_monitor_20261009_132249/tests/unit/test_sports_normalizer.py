"""
test_sports_normalizer.py – Unit tests for sports normalization.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.sports.normalizer import derive_sport_identity, derive_sport_slug


class TestSportsNormalizer:
    def test_derive_sport_slug(self) -> None:
        assert derive_sport_slug("Formula 1 Racing") == "formula-1-racing"
        assert derive_sport_slug("Table Tennis (TT)") == "table-tennis-tt"
        assert derive_sport_slug("", fallback_id="99") == "sport-99"

    def test_derive_sport_identity(self) -> None:
        # Priority 1: external_id
        id1 = derive_sport_identity("sport-10", "https://www.fancode.com/cricket", "Cricket")
        assert id1 == "sport-10"

        # Priority 2: source_url
        id2 = derive_sport_identity(None, "https://www.fancode.com/football?utm_source=fancode", "Football")
        assert id2 == "https://www.fancode.com/football"

        # Priority 3: slug from name
        id3 = derive_sport_identity(None, None, "Basketball")
        assert id3 == "basketball"
