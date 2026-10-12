"""
test_schedule_normalizer.py – Unit tests for schedule normalization (status, dates, slugs, identity).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.schedule.normalizer import (
    derive_slug,
    derive_stable_identity,
    normalize_datetime,
    normalize_status,
)


class TestScheduleNormalizer:
    def test_normalize_status_mappings(self) -> None:
        assert normalize_status("live") == "LIVE"
        assert normalize_status("upcoming") == "UPCOMING"
        assert normalize_status("scheduled") == "SCHEDULED"
        assert normalize_status("completed") == "COMPLETED"
        assert normalize_status("finished") == "COMPLETED"
        assert normalize_status("postponed") == "POSTPONED"
        assert normalize_status("cancelled") == "CANCELLED"
        assert normalize_status("random_unmapped_status") == "UNKNOWN"
        assert normalize_status(None) == "UNKNOWN"

    def test_normalize_datetime_iso(self) -> None:
        dt, time_str = normalize_datetime("2026-04-15T09:30:00Z")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 15
        assert time_str == "09:30"

    def test_normalize_datetime_epoch(self) -> None:
        # 1776245400 is in 2026
        dt, time_str = normalize_datetime(1776245400)
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert isinstance(time_str, str)

    def test_normalize_datetime_invalid(self) -> None:
        dt, time_str = normalize_datetime("invalid-date-string")
        assert dt is None
        assert time_str is None
        assert normalize_datetime(None) == (None, None)

    def test_derive_slug(self) -> None:
        assert derive_slug("India vs Australia 1st ODI") == "india-vs-australia-1st-odi"
        assert derive_slug("Arsenal vs Chelsea (Live)") == "arsenal-vs-chelsea-live"
        assert derive_slug("", fallback_id="123") == "match-123"

    def test_derive_stable_identity_priority(self) -> None:
        # 1. external_id takes top priority
        id1 = derive_stable_identity("ext-123", "https://www.fancode.com/matches/test", "Match Title")
        assert id1 == "ext-123"

        # 2. normalized source_url if no external_id
        id2 = derive_stable_identity(None, "https://www.fancode.com/matches/test?utm_source=twitter", "Match Title")
        assert id2 == "https://www.fancode.com/matches/test"

        # 3. title fallback
        id3 = derive_stable_identity(None, None, "Match Title", "2026-04-15")
        assert "match-title-2026-04-15" in id3
