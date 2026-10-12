"""
test_videos_normalizer.py – Unit tests for Videos normalizer and deduplication.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.videos.models import VideoRecord
from app.scraper.videos.normalizer import VideosNormalizer


class TestVideosNormalizer:
    def test_video_type_normalization(self) -> None:
        assert VideosNormalizer.normalize_video_type("highlight") == "HIGHLIGHT"
        assert VideosNormalizer.normalize_video_type("match_highlight") == "MATCH_HIGHLIGHT"
        assert VideosNormalizer.normalize_video_type("clip") == "CLIP"
        assert VideosNormalizer.normalize_video_type("replay") == "REPLAY"
        assert VideosNormalizer.normalize_video_type("post_match") == "POST_MATCH"
        assert VideosNormalizer.normalize_video_type("pre_match") == "PRE_MATCH"
        assert VideosNormalizer.normalize_video_type("interview") == "INTERVIEW"
        assert VideosNormalizer.normalize_video_type(None, "India vs Pakistan Highlights") == "HIGHLIGHT"
        assert VideosNormalizer.normalize_video_type(None, "Post-Match Press Conference") == "POST_MATCH"
        assert VideosNormalizer.normalize_video_type(None, "Random Unknown Video") == "UNKNOWN"

    def test_duration_normalization(self) -> None:
        # Seconds integer
        assert VideosNormalizer.normalize_duration(120) == 120
        # Milliseconds
        assert VideosNormalizer.normalize_duration(120_000) == 120
        # MM:SS string
        assert VideosNormalizer.normalize_duration("05:30") == 330
        # HH:MM:SS string
        assert VideosNormalizer.normalize_duration("01:10:00") == 4200
        # Suffix string
        assert VideosNormalizer.normalize_duration("45s") == 45
        # None or invalid
        assert VideosNormalizer.normalize_duration(None) is None
        assert VideosNormalizer.normalize_duration("invalid") is None

    def test_derive_video_identity_priority(self) -> None:
        # 1. External ID takes precedence
        key1 = VideosNormalizer.derive_video_identity("vid-101", "https://www.fancode.com/video/vid-101")
        assert key1 == "ext:vid-101"

        # 2. Source URL fallback
        key2 = VideosNormalizer.derive_video_identity(None, "https://www.fancode.com/video/ind-vs-aus?utm_source=fb")
        assert key2 == "url:https://www.fancode.com/video/ind-vs-aus"

        # 3. Fallback slug
        key3 = VideosNormalizer.derive_video_identity(None, "", "ind-vs-aus-clip")
        assert key3 == "slug:ind-vs-aus-clip"

    def test_deduplication_keeps_richer_record(self) -> None:
        rec1 = VideoRecord(
            external_id="vid-dup-1",
            title="MI vs CSK Highlights",
            source_url="https://www.fancode.com/video/vid-dup-1",
            duration_seconds=None,
            thumbnail_url=None,
        )
        rec2 = VideoRecord(
            external_id="vid-dup-1",
            title="MI vs CSK Highlights Full",
            source_url="https://www.fancode.com/video/vid-dup-1",
            duration_seconds=360,
            thumbnail_url="https://img.fancode.com/thumb-dup.jpg",
        )
        deduped = VideosNormalizer.deduplicate_records([rec1, rec2])
        assert len(deduped) == 1
        assert deduped[0].duration_seconds == 360
        assert deduped[0].thumbnail_url == "https://img.fancode.com/thumb-dup.jpg"

    def test_null_handling(self) -> None:
        empty = VideoRecord()
        deduped = VideosNormalizer.deduplicate_records([empty])
        assert len(deduped) == 1
        assert VideosNormalizer.normalize_duration("") is None
