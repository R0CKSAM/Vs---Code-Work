"""Regression coverage for ASRUN demo empty-data handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "src" / "build_asrun_demo.py"
SPEC = importlib.util.spec_from_file_location("build_asrun_demo", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
asrun = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asrun)


def test_build_payload_handles_no_classified_ads() -> None:
    """A control-only ASRUN file must publish zero KPIs instead of crashing."""
    events = pd.DataFrame(
        {
            "is_ad": [False],
            "actual_duration_seconds": [0],
            "ad_type": [None],
            "event_id": ["CONTROL"],
            "creative_title": ["Control event"],
            "on_air_date": ["2026-07-24"],
            "hour_ist": [10],
            "on_air_start_ist": [pd.Timestamp("2026-07-24 10:00:00")],
            "on_air_end_ist": [pd.Timestamp("2026-07-24 10:00:00")],
            "brand": [pd.NA],
            "campaign": [pd.NA],
            "source_file": ["ASRUN-240726.txt"],
            "channel_name": ["Test Channel"],
        }
    )
    viewer = pd.DataFrame(
        columns=["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"]
    )
    empty_youtube = {
        "available": False,
        "reason": "No YouTube data",
        "completed_files": 0,
        "partial_files": 0,
        "minute": pd.DataFrame(columns=["timestamp_ist", "log_date", "total_concurrent_viewers", "live_videos", "peak_video_concurrent"]),
        "video_daily": pd.DataFrame(columns=["log_date", "video_id", "title", "peak_concurrent_viewers", "avg_concurrent_viewers", "viewer_minutes", "live_minutes"]),
        "video_5min": pd.DataFrame(columns=["bucket_ist", "log_date", "video_id", "title", "avg_concurrent_viewers", "peak_concurrent_viewers"]),
        "video_minute": pd.DataFrame(columns=["timestamp_ist", "log_date", "video_id", "concurrent_viewers"]),
        "true_start": "",
        "true_end": "",
        "full_start": "",
        "full_end": "",
    }
    empty_amagi = {
        "available": False,
        "reason": "No Amagi data",
        "files": 0,
        "minute": pd.DataFrame(columns=["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name", "concurrent_viewers"]),
    }

    payload = asrun.build_payload(events, viewer, empty_youtube, empty_amagi)

    assert payload["kpis"]["ad_plays"] == 0
    assert payload["true_range"] == {
        "start": "No classified ad events",
        "end": "No classified ad events",
    }
    assert payload["generated_at_ist"].endswith(" IST")


def test_build_youtube_marts_handles_no_live_rows(tmp_path: Path, monkeypatch) -> None:
    """Readable collector data without live rows is an unavailable state, not NaT."""
    youtube_root = tmp_path / "youtube"
    youtube_root.mkdir()
    pd.DataFrame(
        {
            "date": ["2026-07-24"],
            "time": ["10:00:00"],
            "video_id": ["video-1"],
            "title": ["Recorded video"],
            "concurrent_viewers": [25],
            "status": ["offline"],
        }
    ).to_parquet(youtube_root / "sample.parquet", index=False)
    monkeypatch.setattr(asrun, "YOUTUBE_ROOT", youtube_root)
    monkeypatch.setattr(asrun, "PARSED_DIR", tmp_path / "parsed")

    result = asrun.build_youtube_marts()

    assert result["available"] is False
    assert result["reason"] == "No live YouTube viewer minutes were found in readable completed files."
    assert result["minute"].empty
