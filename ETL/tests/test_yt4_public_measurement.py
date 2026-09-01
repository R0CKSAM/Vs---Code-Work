from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ETL" / "YT"))

import YT4  # noqa: E402


class FakeYoutubeDL:
    responses: dict[str, object] = {}

    def __init__(self, _options):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url: str, download: bool = False):
        assert download is False
        video_id = url.rsplit("=", 1)[-1]
        result = self.responses[video_id]
        if isinstance(result, Exception):
            raise result
        return result


def test_public_measurement_needs_no_api_key(monkeypatch):
    FakeYoutubeDL.responses = {
        "live-video": {
            "id": "live-video",
            "title": "India TV Live",
            "concurrent_view_count": "12345",
            "live_status": "is_live",
        },
        "ended-video": {
            "id": "ended-video",
            "title": "Completed bulletin",
            "concurrent_view_count": None,
            "live_status": "post_live",
        },
    }
    monkeypatch.setattr(YT4.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    api = YT4.PublicYouTubeApi("")
    results = api.get_videos(["live-video", "ended-video"])

    assert results["live-video"].viewers == 12345
    assert results["live-video"].status == "is_live"
    assert results["ended-video"].status == "post_live"
    assert "post_live" in YT4.ENDED_STATUSES
    assert "post_live" in YT4.DIRECT_STOP_STATUSES


def test_auto_mode_repairs_only_missing_public_results(monkeypatch):
    FakeYoutubeDL.responses = {
        "public-ok": {
            "id": "public-ok",
            "title": "Public result",
            "concurrent_view_count": 99,
            "live_status": "is_live",
        },
        "public-failed": RuntimeError("temporary public lookup failure"),
    }
    monkeypatch.setattr(YT4.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    class Fallback:
        def get_videos(self, ids):
            assert list(ids) == ["public-failed"]
            return {
                "public-failed": YT4.VideoLookup(
                    "public-failed", "API repair", 77, "is_live"
                )
            }

    api = YT4.PublicFirstYouTubeApi("")
    api.api_fallback = Fallback()
    results = api.get_videos(["public-ok", "public-failed"])

    assert results["public-ok"].title == "Public result"
    assert results["public-ok"].viewers == 99
    assert results["public-failed"].title == "API repair"
    assert results["public-failed"].viewers == 77


def test_auto_mode_keeps_public_result_when_fallback_also_fails(monkeypatch):
    FakeYoutubeDL.responses = {
        "live-no-count": {
            "id": "live-no-count",
            "title": "Known live stream",
            "concurrent_view_count": None,
            "live_status": "is_live",
        }
    }
    monkeypatch.setattr(YT4.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    class FailedFallback:
        def get_videos(self, ids):
            return {
                video_id: YT4.VideoLookup(
                    video_id, None, None, "lookup_error", "quota exceeded"
                )
                for video_id in ids
            }

    api = YT4.PublicFirstYouTubeApi("")
    api.api_fallback = FailedFallback()
    result = api.get_videos(["live-no-count"])["live-no-count"]

    assert result.title == "Known live stream"
    assert result.status == "is_live"
    assert result.viewers is None
