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


def test_build_fct_ad_mart_classifies_deduplicates_and_tracks_spillover(
    tmp_path: Path, monkeypatch
) -> None:
    """FCT publishes valid evidence only and keeps filename-range QA explicit."""
    fct_root = tmp_path / "fct"
    fct_root.mkdir()
    workbook = fct_root / "YT_NEWS_12072026 to 14072026.xlsx"
    rows = pd.DataFrame(
        {
            "Feed Name": ["CN INDIA TV"] * 5,
            "Pdate": [
                "12/07/2026",
                "12/07/2026",
                "15/07/2026",
                "13/07/2026",
                "14/07/2026",
            ],
            "Progname": ["News", "News", "Promo Show", "News", "Prime Time"],
            "Pgst": ["06:00:00"] * 5,
            "Pgdur": ["00:30:00"] * 5,
            "Adst": ["06:01:00", "06:01:00", "07:02:00", "", "20:05:00"],
            "Brandname": ["Brand A", "Brand A", "Channel Promo", "Invalid", "India TV"],
            "Aaddur": [10, 10, 15, 0, 20],
            "Caption": ["Creative A", "Creative A", "Promo A", "Invalid", "House Creative"],
            "Language": ["Hindi"] * 5,
            "Category": ["FMCG", "FMCG", "PROMO PROGRAM", "FMCG", "FMCG"],
            "Company": [
                "Company A",
                "Company A",
                "India TV",
                "Company A",
                "Independent News Service Pvt. Ltd.",
            ],
            "Adpos": [1, 1, 2, 3, 1],
            "TotAds": [3, 3, 3, 3, 1],
        }
    )
    rows.to_excel(workbook, index=False)
    monkeypatch.setattr(asrun, "FCT_ROOT", fct_root)
    monkeypatch.setattr(asrun, "PARSED_DIR", tmp_path / "parsed")

    result = asrun.build_fct_ad_mart()
    cached_result = asrun.build_fct_ad_mart()

    assert result["available"] is True
    assert len(result["events"]) == 3
    assert result["source_rows"] == 5
    assert result["excluded_rows"] == 1
    assert result["spillover_rows"] == 1
    assert set(result["events"]["event_class"]) == {
        "Commercial",
        "In-House",
        "Internal / Promo",
    }
    assert len(cached_result["events"]) == 3
    assert (tmp_path / "parsed" / "fct_ad_events.parquet").is_file()
    assert (tmp_path / "parsed" / "fct_manifest.json").is_file()


def test_fixed_five_minute_sum_preserves_filter_dimensions_and_totals() -> None:
    """Compaction must equal the exact sum of source minutes in each fixed bucket."""
    minute = pd.DataFrame(
        {
            "log_date": ["2026-07-28"] * 6,
            "source": ["fast"] * 6,
            "platform_name": ["Platform A"] * 5 + ["Platform B"],
            "channel_name": ["Channel A"] * 6,
            "minute_ist": pd.to_datetime(
                [
                    "2026-07-28 12:00:00",
                    "2026-07-28 12:01:00",
                    "2026-07-28 12:04:00",
                    "2026-07-28 12:05:00",
                    "2026-07-28 12:09:00",
                    "2026-07-28 12:01:00",
                ]
            ),
            "distinct_cliips": [10, 11, 14, 20, 24, 7],
        }
    )

    compact = asrun.fixed_five_minute_sum(
        minute,
        time_column="minute_ist",
        group_columns=["log_date", "source", "platform_name", "channel_name"],
        value_column="distinct_cliips",
    )

    platform_a = compact[compact["platform_name"].eq("Platform A")]
    assert platform_a["distinct_cliips"].tolist() == [35, 44]
    assert compact.loc[
        compact["platform_name"].eq("Platform B"), "distinct_cliips"
    ].tolist() == [7]
    assert compact["distinct_cliips"].sum() == minute["distinct_cliips"].sum()
