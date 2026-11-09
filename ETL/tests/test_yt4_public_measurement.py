from __future__ import annotations

import sys
import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ETL" / "YT"))

import YT4  # noqa: E402


def test_transient_network_and_storage_errors_retry_until_recovery(monkeypatch):
    sleeps = []
    attempts = []
    monkeypatch.setattr(YT4.time, "sleep", sleeps.append)
    def operation():
        attempts.append(1)
        if len(attempts) <= 7:
            if len(attempts) % 2:
                raise YT4.YouTubeApiError("connection timed out")
            raise OSError("network share disconnected")
    YT4.run_with_recovery(operation)
    assert len(attempts) == 8
    assert sleeps == [5, 10, 20, 40, 60, 60, 60]


@pytest.mark.parametrize("error,once", [
    (YT4.YouTubeApiError("bad key", status_code=403), False),
    (ValueError("bad configuration"), False),
    (YT4.YouTubeApiError("offline"), True),
    (KeyboardInterrupt(), False),
])
def test_permanent_errors_once_and_user_stop_do_not_retry(monkeypatch, error, once):
    def unexpected_sleep(_):
        raise AssertionError("must not retry")
    monkeypatch.setattr(YT4.time, "sleep", unexpected_sleep)
    def operation():
        raise error
    with pytest.raises(type(error)):
        YT4.run_with_recovery(operation, once=once)


def test_outage_retries_discovery_next_poll_and_resumes_collection(monkeypatch, tmp_path):
    class Api:
        official_measurement = False
        discovery_notice = "discovery {discovery_every}"
        def __init__(self, *_):
            self.discovery_calls = 0
        def list_live_videos(self, *_):
            self.discovery_calls += 1
            if self.discovery_calls == 1:
                raise YT4.YouTubeApiError("DNS offline")
            return [YT4.LiveCandidate("live", "Recovered stream")]
        def get_videos(self, ids):
            return {v: YT4.VideoLookup(v, "Recovered stream", 42, "is_live") for v in ids}
    rows = []
    sleeps = []
    class Logger:
        partial_path = "test.journal"
        def __init__(self, *_): pass
        def add_rows(self, values): rows.extend(values)
        def close(self): pass
    monkeypatch.setattr(YT4, "CrashSafeParquetLogger", Logger)
    monkeypatch.setattr(YT4, "recover_journals", lambda *_: [])
    monkeypatch.setattr(YT4, "resolve_source", lambda *_: YT4.ResolvedSource("url", "channel", "channel", "Test"))
    monkeypatch.setattr(YT4.time, "sleep", sleeps.append)
    def stop_after_recovery(_): raise KeyboardInterrupt()
    monkeypatch.setattr(YT4, "sleep_until_next_boundary", stop_after_recovery)
    YT4.track_many(["url"], out_dir=str(tmp_path), api_class=Api)
    assert sleeps == [5]
    assert [r[-1] for r in rows] == ["channel_discovery_error", "is_live"]
    assert rows[0][4] is None
    assert rows[1][4] == 42


def test_lookup_failure_keeps_existing_live_stream_without_end_confirmation():
    class Api:
        official_measurement = False
        def list_live_videos(self, *_): raise YT4.YouTubeApiError("offline")
        def get_videos(self, ids):
            return {v: YT4.VideoLookup(v, None, None, "lookup_error", "offline") for v in ids}
    state = YT4.ChannelState(active_ids={"live"})
    rows, *_ = YT4.poll_channel(Api(), "channel", datetime.datetime.now(YT4.IST), state, 10, 15, 2)
    assert state.active_ids == {"live"}
    assert not state.end_misses
    assert rows[0][-1] == "lookup_error"
    assert rows[0][4] is None


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
