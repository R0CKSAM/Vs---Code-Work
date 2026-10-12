"""
test_tours_normalizer.py – Unit tests for tours normalization.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.tours.normalizer import derive_tour_identity, derive_tour_slug


class TestToursNormalizer:
    def test_derive_tour_slug(self) -> None:
        assert derive_tour_slug("Caribbean Premier League 2026") == "caribbean-premier-league-2026"
        assert derive_tour_slug("UEFA Champions League (UCL)") == "uefa-champions-league-ucl"
        assert derive_tour_slug("", fallback_id="555") == "tour-555"

    def test_derive_tour_identity(self) -> None:
        # Priority 1: external_id
        id1 = derive_tour_identity("tour-99", "https://www.fancode.com/tours/ipl", "IPL")
        assert id1 == "tour-99"

        # Priority 2: source_url
        id2 = derive_tour_identity(None, "https://www.fancode.com/tours/ipl?utm_campaign=c1", "IPL")
        assert id2 == "https://www.fancode.com/tours/ipl"

        # Priority 3: slug from name
        id3 = derive_tour_identity(None, None, "World Cup 2026")
        assert id3 == "world-cup-2026"
