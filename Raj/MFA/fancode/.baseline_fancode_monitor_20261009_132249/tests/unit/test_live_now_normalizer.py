"""
test_live_now_normalizer.py – Unit tests for Live Now normalizer and deduplication.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.live_now.models import LiveMatchRecord
from app.scraper.live_now.normalizer import LiveNowNormalizer


class TestLiveNowNormalizer:
    def test_status_normalization(self) -> None:
        assert LiveNowNormalizer.normalize_live_status("live") == "LIVE"
        assert LiveNowNormalizer.normalize_live_status("in_progress") == "LIVE"
        assert LiveNowNormalizer.normalize_live_status("streaming") == "LIVE"
        assert LiveNowNormalizer.normalize_live_status("upcoming") == "UPCOMING"
        assert LiveNowNormalizer.normalize_live_status("completed") == "COMPLETED"
        assert LiveNowNormalizer.normalize_live_status("cancelled") == "CANCELLED"
        assert LiveNowNormalizer.normalize_live_status(None) == "LIVE"

    def test_derive_match_identity_priority(self) -> None:
        # 1. External ID takes precedence
        key1 = LiveNowNormalizer.derive_match_identity("ext-123", "https://www.fancode.com/matches/other")
        assert key1 == "ext:ext-123"

        # 2. Source URL fallback
        key2 = LiveNowNormalizer.derive_match_identity(None, "https://www.fancode.com/matches/ind-vs-pak?utm_source=fb")
        assert key2 == "url:https://www.fancode.com/matches/ind-vs-pak"

        # 3. Slug from title fallback
        key3 = LiveNowNormalizer.derive_match_identity(None, "", "India vs Pakistan T20")
        assert key3.startswith("slug:india-vs-pakistan-t20")

    def test_deduplication_keeps_richer_record(self) -> None:
        rec1 = LiveMatchRecord(
            match_external_id="dup-1",
            title="MI vs CSK",
            source_url="https://www.fancode.com/matches/mi-vs-csk",
            score_summary=None,
            venue=None,
        )
        rec2 = LiveMatchRecord(
            match_external_id="dup-1",
            title="MI vs CSK Live",
            source_url="https://www.fancode.com/matches/mi-vs-csk",
            score_summary="MI 120/2",
            venue="Wankhede",
        )
        deduped = LiveNowNormalizer.deduplicate_records([rec1, rec2])
        assert len(deduped) == 1
        assert deduped[0].score_summary == "MI 120/2"
        assert deduped[0].venue == "Wankhede"

    def test_empty_and_null_handling(self) -> None:
        empty_rec = LiveMatchRecord()
        deduped = LiveNowNormalizer.deduplicate_records([empty_rec])
        assert len(deduped) == 1
        assert LiveNowNormalizer.normalize_live_status("") == "LIVE"
