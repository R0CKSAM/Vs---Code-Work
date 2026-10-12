"""
test_videos_parser.py – Unit tests for Videos & Highlights parser and defensive extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.videos.models import RawVideoItem
from app.scraper.videos.parser import VideosParser, safe_get
from tests.fixtures.videos import (
    SAMPLE_NESTED_VIDEO_PAYLOAD,
    SAMPLE_UNRELATED_RESPONSE,
    SAMPLE_VIDEO_CLIP,
    SAMPLE_VIDEO_HIGHLIGHT,
    SAMPLE_VIDEO_MALFORMED,
    SAMPLE_VIDEO_MATCH,
    SAMPLE_VIDEO_MISSING_FIELDS,
)


class TestVideosParser:
    def test_safe_get_traversal(self) -> None:
        data = {"media": {"asset": {"id": "123"}}}
        assert safe_get(data, "media", "asset", "id") == "123"
        assert safe_get(data, "media", "missing") is None
        assert safe_get(None, "media") is None

    def test_parse_normal_highlight(self) -> None:
        raw = RawVideoItem(raw_data=SAMPLE_VIDEO_HIGHLIGHT)
        rec = VideosParser.parse_video_item(raw)
        assert rec is not None
        assert rec.external_id == "vid-high-101"
        assert rec.title == "IND vs AUS 1st ODI Match Highlights"
        assert rec.video_type == "MATCH_HIGHLIGHT"
        assert rec.duration_seconds == 480
        assert rec.thumbnail_url == "https://img.fancode.com/thumb-high-101.jpg"
        assert rec.video_url == "https://video.fancode.com/vod/high-101.mp4"
        assert rec.match_external_id == "match-901"
        assert rec.tour_name == "Australia Tour of India 2026"
        assert rec.sport_name == "Cricket"
        assert rec.language == "English"

    def test_parse_normal_match_video(self) -> None:
        raw = RawVideoItem(raw_data=SAMPLE_VIDEO_MATCH)
        rec = VideosParser.parse_video_item(raw)
        assert rec is not None
        assert rec.external_id == "vid-match-202"
        assert rec.title == "Arsenal vs Chelsea Full Replay"
        assert rec.video_type == "REPLAY"
        # "01:35:00" -> (1*3600 + 35*60) = 5700 seconds
        assert rec.duration_seconds == 5700
        assert rec.match_external_id == "fb-888"
        assert rec.tour_name == "Premier League"
        assert rec.sport_name == "Football"

    def test_parse_video_with_thumbnail_and_clip(self) -> None:
        raw = RawVideoItem(raw_data=SAMPLE_VIDEO_CLIP)
        rec = VideosParser.parse_video_item(raw)
        assert rec is not None
        assert rec.external_id == "vid-clip-303"
        assert rec.video_type == "CLIP"
        assert rec.duration_seconds == 45
        assert rec.thumbnail_url == "https://img.fancode.com/clip-six.jpg"
        assert rec.sport_name == "Cricket"

    def test_parse_video_missing_optional_fields(self) -> None:
        raw = RawVideoItem(raw_data=SAMPLE_VIDEO_MISSING_FIELDS)
        rec = VideosParser.parse_video_item(raw)
        assert rec is not None
        assert rec.external_id == "vid-sparse-404"
        assert rec.video_type == "POST_MATCH"
        assert rec.duration_seconds is None
        assert rec.thumbnail_url is None
        assert rec.match_external_id is None

    def test_parse_malformed_video_returns_none(self) -> None:
        raw = RawVideoItem(raw_data=SAMPLE_VIDEO_MALFORMED)
        rec = VideosParser.parse_video_item(raw)
        assert rec is None

    def test_extract_from_nested_json(self) -> None:
        items = VideosParser.extract_video_items_from_payload(SAMPLE_NESTED_VIDEO_PAYLOAD)
        assert len(items) == 2
        parsed = [VideosParser.parse_video_item(it) for it in items]
        valid = [p for p in parsed if p is not None]
        assert len(valid) == 2
        titles = {v.title for v in valid}
        assert "IND vs AUS 1st ODI Match Highlights" in titles
        assert "Spectacular Six by Rohit Sharma" in titles

    def test_unrelated_json_ignored(self) -> None:
        items = VideosParser.extract_video_items_from_payload(SAMPLE_UNRELATED_RESPONSE)
        assert len(items) == 0

    def test_extract_embedded_json(self) -> None:
        html = '<html><head><script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"videos": []}}}</script></head><body></body></html>'
        data = VideosParser.extract_embedded_json(html)
        assert data is not None
        assert "videos" in data["props"]["pageProps"]

        empty_html = "<html><body>No embedded data</body></html>"
        assert VideosParser.extract_embedded_json(empty_html) is None
