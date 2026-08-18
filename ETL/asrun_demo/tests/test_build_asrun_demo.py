"""Regression coverage for ASRUN demo empty-data handling."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


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
    assert payload["date_coverage"] == {
        "asrun": [],
        "fast": [],
        "stream": [],
        "amagi": [],
        "fct": [],
        "youtube": [],
        "nct": [],
    }


def test_distinct_iso_dates_reports_only_represented_calendar_dates() -> None:
    """Continuity indexes must be sorted, deduplicated, and ignore invalid timestamps."""
    frame = pd.DataFrame(
        {
            "minute_ist": [
                "2026-07-03 12:30:00",
                "2026-07-01 08:00:00",
                "2026-07-03 18:00:00",
                "invalid",
                None,
            ]
        }
    )

    assert asrun.distinct_iso_dates(frame, "minute_ist") == [
        "2026-07-01",
        "2026-07-03",
    ]
    assert asrun.distinct_iso_dates(frame, "missing") == []


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


def test_fct_workbook_uses_internal_dates_and_ignores_summary_tabs(
    tmp_path: Path,
) -> None:
    """Differently named FCT workbooks derive coverage from their valid data tab."""
    workbook = tmp_path / "CTV FCT.xlsx"
    data = pd.DataFrame(
        {
            "Feed Name": ["CN INDIA TV", "CN INDIA TV"],
            "Pdate": ["24/06/2026", "30/06/2026"],
            "Progname": ["News", "Prime Time"],
            "Pgst": ["06:00:00", "20:00:00"],
            "Pgdur": ["00:30:00", "00:30:00"],
            "Adst": ["06:01:00", "20:01:00"],
            "Brandname": ["Brand A", "Brand B"],
            "Aaddur": [10, 20],
            "Caption": ["Creative A", "Creative B"],
            "Language": ["Hindi", "Hindi"],
            "Category": ["FMCG", "FMCG"],
            "Company": ["Company A", "Company B"],
            "Adpos": [1, 1],
            "TotAds": [2, 2],
        }
    )
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame({"Category": ["Summary"]}).to_excel(
            writer, sheet_name="S1", index=False
        )
        data.to_excel(writer, sheet_name="Sheet1", index=False)

    events, metadata = asrun.parse_fct_workbook(workbook, workbook.name)

    assert len(events) == 2
    assert metadata["declared_start"] == "2026-06-24"
    assert metadata["declared_end"] == "2026-06-30"
    assert metadata["range_source"] == "Pdate"
    assert metadata["parsed_sheets"] == ["Sheet1"]
    assert metadata["ignored_sheets"] == ["S1"]
    assert events["is_filename_spillover"].eq(False).all()


def test_viewer_snapshot_includes_additional_fct_date_range(tmp_path: Path) -> None:
    """Historical FCT events must retain FAST/STREAM audience evidence."""
    mart_path = tmp_path / "identity_minute.parquet"
    pd.DataFrame(
        {
            "log_date": ["2026-06-30", "2026-07-10"],
            "source": ["fast", "stream"],
            "minute_ist": pd.to_datetime(
                ["2026-06-30 23:59:00", "2026-07-10 12:00:00"]
            ),
            "platform_name": ["Platform A", "STREAM"],
            "channel_name": ["India TV", "India TV"],
            "distinct_cliips": [125, 250],
        }
    ).to_parquet(mart_path, index=False)
    events = pd.DataFrame(
        {
            "is_ad": [True],
            "on_air_start_ist": [pd.Timestamp("2026-07-10 12:00:00")],
            "on_air_end_ist": [pd.Timestamp("2026-07-10 12:00:10")],
        }
    )

    snapshot = asrun.load_viewer_minute_snapshot(
        events,
        mart_path,
        [("2026-06-30", "2026-06-30")],
    )

    assert snapshot["log_date"].astype(str).tolist() == [
        "2026-06-30",
        "2026-07-10",
    ]
    assert snapshot["distinct_cliips"].tolist() == [125, 250]


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


def test_split_dashboard_payload_preserves_all_source_rows() -> None:
    """Startup compaction must relocate source rows, never truncate them."""
    payload = {
        "viewer_minute": [{"source": "fast"}, {"source": "stream"}],
        "amagi": {"available": True, "minute": [{"value": 1}]},
        "fct": {"available": True, "events": [{"event": 1}, {"event": 2}]},
        "youtube": {
            "available": True,
            "minute": [{"minute": 1}],
            "video_daily": [{"day": 1}],
            "video_5min": [{"bucket": 1}],
            "video_minute": [{"video": 1}, {"video": 2}],
        },
    }

    core, chunks = asrun.split_dashboard_payload(payload)

    assert core["viewer_minute"] == []
    assert core["amagi"]["minute"] == []
    assert core["fct"]["events"] == []
    assert all(core["youtube"][key] == [] for key in asrun.YOUTUBE_PAYLOAD_ARRAYS)
    assert chunks["viewer"] == payload["viewer_minute"]
    assert chunks["amagi"] == payload["amagi"]["minute"]
    assert chunks["fct"] == payload["fct"]["events"]
    assert chunks["youtube"]["video_minute"] == payload["youtube"]["video_minute"]
    assert payload["viewer_minute"]  # The full payload remains available to callers.


def test_youtube_mart_reuses_unchanged_source_files(
    tmp_path: Path, monkeypatch
) -> None:
    """An unchanged YouTube refresh should read marts, not every source Parquet."""
    youtube_root = tmp_path / "youtube"
    parsed = tmp_path / "parsed"
    youtube_root.mkdir()
    source = youtube_root / "indiatv_29-07-2026_12-00_complete.parquet"
    pd.DataFrame(
        {
            "date": ["2026-07-29", "2026-07-29"],
            "time": ["12:00:00", "12:01:00"],
            "video_id": ["video-1", "video-1"],
            "title": ["India TV Live", "India TV Live"],
            "concurrent_viewers": [100, 120],
            "status": ["is_live", "is_live"],
        }
    ).to_parquet(source, index=False)
    monkeypatch.setattr(asrun, "YOUTUBE_ROOT", youtube_root)
    monkeypatch.setattr(asrun, "PARSED_DIR", parsed)

    first = asrun.build_youtube_marts()
    original_read_parquet = pd.read_parquet
    source_reads: list[Path] = []

    def tracked_read_parquet(path, *args, **kwargs):
        resolved = Path(path).resolve()
        if resolved.parent == youtube_root.resolve():
            source_reads.append(resolved)
        return original_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", tracked_read_parquet)
    second = asrun.build_youtube_marts()

    assert first["available"] is True
    assert second["minute"]["total_concurrent_viewers"].tolist() == [100, 120]
    assert source_reads == []
    manifest = json.loads((parsed / "youtube_manifest.json").read_text())
    assert manifest["schema_version"] == asrun.YOUTUBE_MART_VERSION


def test_amagi_mart_reuses_unchanged_source_files(
    tmp_path: Path, monkeypatch
) -> None:
    """An unchanged Amagi refresh should use its normalized minute mart."""
    amagi_root = tmp_path / "amagi"
    parsed = tmp_path / "parsed"
    amagi_root.mkdir()
    pd.DataFrame(
        {
            "channel_name": ["India TV Live"],
            "platform_name": ["Samsung TV Plus - IN"],
            "timestamp (UTC)": ["2026-07-29 06:30:00+00:00"],
            "No. of Concurrent Viewers": [75],
        }
    ).to_csv(amagi_root / "concurrency.csv", index=False)
    events = pd.DataFrame({"is_ad": [True]})
    monkeypatch.setattr(asrun, "AMAGI_ROOT", amagi_root)
    monkeypatch.setattr(asrun, "PARSED_DIR", parsed)

    first = asrun.build_amagi_minute_mart(events)

    def unexpected_read_csv(*args, **kwargs):
        raise AssertionError("unchanged Amagi CSV was reopened")

    monkeypatch.setattr(pd, "read_csv", unexpected_read_csv)
    second = asrun.build_amagi_minute_mart(events)

    assert first["available"] is True
    assert second["minute"]["concurrent_viewers"].tolist() == [75]
    manifest = json.loads((parsed / "amagi_manifest.json").read_text())
    assert manifest["schema_version"] == asrun.AMAGI_MART_VERSION


@pytest.mark.parametrize(
    ("date_value", "start_time", "end_time", "duration_value"),
    [
        ("29/07/2026", "06:01:00", "06:01:10", "00:00:10"),
        ("29-07-26", "6.01.00", "6.01.10", "0.00.10"),
    ],
)
def test_parse_nct_csv_validates_and_normalizes_story_segments(
    tmp_path: Path,
    date_value: str,
    start_time: str,
    end_time: str,
    duration_value: str,
) -> None:
    """NCT preamble metadata and source-reported IST segments remain traceable."""
    source = tmp_path / "Detail_StoryTrack_Duration.CSV"
    row = pd.DataFrame(
        {
            "channel": ["INDIA TV"],
            "Story": ["TEST STORY"],
            "Sub_Story": ["TEST SUB-STORY"],
            "story_genre_1": ["POLITICS"],
            "story_genre_2": ["NO NEWS CONTENT"],
            "pgm_name": ["TEST PROGRAM"],
            "Pgm_Start_Time": ["06:00:00"],
            "Pgm_End_Time": ["06:30:00"],
            "clip_start_time": [start_time],
            "clip_end_time": [end_time],
            "pgm_date": [date_value],
            "week": [""],
            "geography": ["INDIAN"],
            "title": ["."],
            "grap_type": ["Duration"],
            "duration": [duration_value],
            "duration_seconds": [10],
            "personality": [""],
            "guest": [""],
            "anchor": ["TEST ANCHOR"],
            "reporter": [""],
            "logistics": ["IN STUDIO"],
            "telecast_format": ["HEADLINES"],
            "assist_used": ["FOOTAGE"],
            "split": ["NORMAL"],
            "Story_Format": ["REPORT"],
            "Start Half Hour": ["06:00:00"],
            "Dur in Mins": [1 / 6],
            "AMA": [1234],
            "UR": [5678],
        }
    )
    preamble = "\n".join(
        [
            "Content Diagnostics - Duration - By Story Details",
            "Selection Details:",
            "Channels: INDIA TV,ABP NEWS,,,,",
            "From Date: 29/07/2026,,,,",
            "To Date: 29/07/2026,,,,",
            "Start Time: 05:00:00,,,,",
            "End Time: 23:59:00,,,,",
            "Geography: ALL",
            "Story:",
            "Genre: Any",
            "Story Type: Story",
            "Downloaded On :29/7/2026 10:59",
            "",
            "",
        ]
    )
    source.write_text(preamble + row.to_csv(index=False), encoding="utf-8")

    segments, metadata = asrun.parse_nct_csv(source, source.name)

    assert len(segments) == 1
    assert segments.loc[0, "channel_name"] == "INDIA TV"
    assert segments.loc[0, "duration_seconds"] == 10
    assert pd.isna(segments.loc[0, "title"])
    assert metadata["declared_start"] == "2026-07-29"
    assert metadata["actual_channels"] == ["INDIA TV"]
    assert metadata["missing_selected_channels"] == ["ABP NEWS"]


def test_parse_nct_excel_accepts_split_data_genre_aliases(tmp_path: Path) -> None:
    source = tmp_path / "NCT Split Data.xlsx"
    pd.DataFrame(
        {
            "channel": ["INDIA TV"],
            "Story": ["TEST STORY"],
            "Sub_Story": ["TEST SUB-STORY"],
            "content_type_1": ["POLITICS"],
            "content_type_2": ["NO NEWS CONTENT"],
            "pgm_name": ["TEST PROGRAM"],
            "Pgm_Start_Time": ["06:00:00"],
            "Pgm_End_Time": ["06:30:00"],
            "clip_start_time": ["06:01:00"],
            "clip_end_time": ["06:01:10"],
            "pgm_date": ["01-08-2026"],
            "week": [""],
            "geography": ["INDIAN"],
            "title": ["."],
            "grap_type": ["Duration"],
            "duration": ["00:00:10"],
            "duration_seconds": [10],
            "personality": [""],
            "guest": [""],
            "anchor": ["TEST ANCHOR"],
            "reporter": [""],
            "logistics": ["IN STUDIO"],
            "telecast_format": ["HEADLINES"],
            "assist_used": ["FOOTAGE"],
            "split": ["NORMAL"],
            "Story_Format": ["REPORT"],
            "Start Half Hour": ["06:00:00"],
            "Dur in Mins": [1 / 6],
            "AMA": [1234],
            "UR": [5678],
        }
    ).to_excel(source, index=False)

    segments, metadata = asrun.parse_nct_csv(source, source.name)

    assert len(segments) == 1
    assert segments.loc[0, "primary_genre"] == "POLITICS"
    assert segments.loc[0, "secondary_genre"] == "NO NEWS CONTENT"
    assert segments.loc[0, "source_start_half_hour"] == "06:00:00"
    assert float(segments.loc[0, "source_duration_minutes"]) == pytest.approx(1 / 6)
    assert segments.loc[0, "source_ama"] == "1234"
    assert segments.loc[0, "source_ur"] == "5678"
    assert metadata["declared_start"] == "2026-08-01"
    assert metadata["declared_end"] == "2026-08-01"
    assert metadata["selected_channels"] == ["INDIA TV"]


def test_nct_missing_channels_ignores_display_case_differences() -> None:
    """NCT metadata casing must not create a false missing-channel warning."""
    missing = asrun.missing_channel_labels(
        ["ABP NEWS", "NDTV INDIA"],
        {"ABP News"},
    )

    assert missing == ["NDTV INDIA"]


def test_minute_counts_by_date_exposes_partial_days() -> None:
    frame = pd.DataFrame(
        {
            "minute_ist": [
                "2026-08-07 00:00:00",
                "2026-08-07 00:01:00",
                "2026-08-07 00:01:00",
                "2026-08-08 00:00:00",
            ]
        }
    )

    assert asrun.minute_counts_by_date(frame) == {
        "2026-08-07": 2,
        "2026-08-08": 1,
    }


def test_render_dashboard_wires_complete_reset_and_fatal_error(
    tmp_path: Path, monkeypatch
) -> None:
    """Generated HTML must expose filter state and never hide startup failures."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert "showFatalDashboardError('initial render',startupError)" in html
    assert "throw startupError" in html
    assert "SIGNATURE_MULTI_IDS" in html
    assert "youtubeVideoFilterSignature" in html
    assert "nctContextChannel" in html
    assert "function loadNctManifest(){" in html
    assert "function nctMissingPartitions(range){" in html
    assert "function loadNctPartition(dateValue,file){" in html
    assert "Filters changed from the default view; click to restore defaults" in html


def test_render_dashboard_exports_missing_asrun_audience_as_zero(
    tmp_path: Path, monkeypatch
) -> None:
    """ASRUN source cells and exports must remain numeric when no minute matches."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert "coverage=new Set(allRows.map(row=>minuteKey(row.minute_ist)))" not in html
    assert "window.keys.some(key=>!coverage.has(key))" not in html
    assert "map=state&&state.map instanceof Map?state.map:new Map()" in html
    assert "return {value:fmt(total),window:window.label,total,available:true}" in html
    assert "total+=Number(map.get(key)||0)" in html
    assert 'src="asrun_delivery_data.js?v=unversioned"' in html


def test_split_dashboard_payload_versions_lazy_sidecars() -> None:
    """Every rebuild must force local-file browsers to load the new source arrays."""
    payload = {
        "generated_at_ist": "18/08/26 12:24:33 PM IST",
        "viewer_minute": [],
        "amagi": {"minute": []},
        "fct": {"events": []},
        "youtube": {key: [] for key in asrun.YOUTUBE_PAYLOAD_ARRAYS},
    }

    core, _chunks = asrun.split_dashboard_payload(payload)

    assert {
        config["file"].split("?v=")[1]
        for config in core["sidecars"].values()
    } == {"180826122433PMIST"}


def test_delivery_filters_are_bidirectional_and_empty_multiselects_stay_empty(
    tmp_path: Path, monkeypatch
) -> None:
    """ID/title filters must adapt both ways without a redundant type toggle."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert "const DELIVERY_AD_TYPES=['Spot','L-band'];" in html
    assert "function selectedDeliveryAdTypes(){" in html
    assert 'id="deliveryTypeFilter"' not in html
    assert 'data-delivery-ad-type="' not in html
    assert "function multiSelectionState(id){" in html
    assert "const idRows=creativeState.restricted" in html
    assert "const creativeRows=idState.restricted" in html
    assert "creativeState.selected.has(event.creative_title)" in html
    assert "idState.selected.has(event.event_id)" in html
    assert "if(!ids.size||!creatives.size)return [];" in html
    assert "if(!values.length){button.textContent='No '+kind+' selected';return;}" in html
    assert "adTypes:deliveryAdTypeLabel()" in html
    assert "adIds:exportDeliverySelection('adIds')" in html
    assert "creatives:exportDeliverySelection('creatives')" in html
    assert "deliveryAdTypeFileToken()+'_'+filters.dateFrom" in html
    assert "parts.push('deliveryTypes:'" in html


def test_render_dashboard_groups_sections_into_three_pages(
    tmp_path: Path, monkeypatch
) -> None:
    """Large source sections must be navigable without duplicating their data."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert 'id="dashboardPageNav"' in html
    assert 'data-dashboard-page-target="audience"' in html
    assert 'data-dashboard-page-target="delivery"' in html
    assert 'data-dashboard-page-target="content"' in html
    assert 'id="dashboardPageAudience"' in html
    assert 'id="dashboardPageDelivery"' in html
    assert 'id="dashboardPageContent"' in html
    assert "filters.insertBefore($('dashboardPageNav'),filters.firstChild);" in html
    assert ".dashboard-page-nav { flex: 1 1 100%; order: -1; }" in html
    assert ".filter-shell .filters button," in html
    assert "height: 26px;" in html
    assert "$('dashboardPageAudience').append(" in html
    assert "$('dashboardPageDelivery').append(" in html
    assert "$('dashboardPageContent').append(nodes.nct,nodes.scope)" in html
    assert "nodes.combined.id='allDeliveredEventsPanel'" in html
    assert "nodes.fctAudience.id='allFctMonitoredEventsPanel'" in html
    assert "nodes.fct.id='fctSourceEventsPanel'" in html
    assert "function placeSharedContextSections(page)" not in html
    assert "content.insertBefore(combined,scope)" not in html
    assert "content.insertBefore(fctAudience,scope)" not in html
    assert (
        "ensureScopePanel();ensureGlobalAudienceFilters();"
        "ensureDashboardPages();initializeNctLazyLoad()"
    ) in html
    assert "nodes.audience.remove();" in html
    assert "await activateDashboardPageData(activeDashboardPage)" in html


def test_render_dashboard_uses_one_visible_date_scope_per_page(
    tmp_path: Path, monkeypatch
) -> None:
    """Page-specific date controls must not compete with the master range."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert ".filters.master-date-hidden [data-master-date-control]" in html
    assert ".youtube-filter-bar.follow-main .youtube-independent-date-control" in html
    assert "let youtubeDateMode='follow';" in html
    assert "function syncDateControlVisibility(){" in html
    assert "activeDashboardPage==='content'&&nctDateMode==='independent'" in html
    assert "activeDashboardPage==='audience'&&youtubeDateMode==='independent'" in html
    assert "setYoutubeDateMode('follow',false);" in html
    assert "syncDateControlVisibility();\n  closeMultiMenus('');" in html
    assert 'id="nctDateFields" hidden' in html
    assert 'id="nctApplyDate"' in html
    assert "function applyNctDateRange(){" in html
    assert "<strong>Available:</strong>" in html
    assert "<strong>Used:</strong>" in html


def test_write_javascript_assignment_is_atomic_and_script_safe(
    tmp_path: Path,
) -> None:
    """Published sidecars must never expose partial or script-breaking JSON."""
    target = tmp_path / "payload.js"

    asrun.write_javascript_assignment(
        target,
        "window.__TEST_DATA__",
        {"title": "safe </script> value", "event_id": "C0012345"},
    )

    output = target.read_text(encoding="utf-8")
    assert output.startswith("window.__TEST_DATA__=")
    assert "<\\/script>" in output
    assert '"event_id":"C0012345"' in output
    assert not target.with_name(f".{target.name}.tmp").exists()


def test_write_nct_payload_script_partitions_rows_by_date(tmp_path: Path) -> None:
    """The browser must be able to load only selected NCT dates."""
    columns = [
        "clip_start_ist",
        "clip_end_ist",
        "log_date",
        "channel_name",
        "program_name",
        "story",
        "sub_story",
        "primary_genre",
        "secondary_genre",
        "geography",
        "duration_seconds",
        "anchor",
        "reporter",
        "personality",
        "guest",
        "logistics",
        "telecast_format",
        "assist_used",
        "split",
        "story_format",
        "source_file",
        "source_row",
    ]
    rows = []
    for index, date_value in enumerate(["2026-07-28", "2026-07-29"]):
        row = {column: "" for column in columns}
        row.update(
            {
                "clip_start_ist": f"{date_value} 10:00:00",
                "clip_end_ist": f"{date_value} 10:00:10",
                "log_date": date_value,
                "channel_name": "INDIA TV",
                "story": f"Story {index}",
                "duration_seconds": 10,
                "source_row": index + 1,
            }
        )
        rows.append(row)
    target = tmp_path / "nct_story_data.js"
    viewer_minute = pd.DataFrame(
        [
            {
                "log_date": "2026-07-28",
                "minute_ist": pd.Timestamp("2026-07-28 10:00:00"),
                "source": "fast",
                "platform_name": "Samsung TV Plus",
                "channel_name": "India TV",
                "distinct_cliips": 125,
            }
        ]
    )
    amagi_minute = pd.DataFrame(
        [
            {
                "log_date": "2026-07-28",
                "minute_ist": pd.Timestamp("2026-07-28 10:00:00"),
                "platform_name": "Samsung TV Plus",
                "channel_name": "India TV",
                "concurrent_viewers": 75,
            }
        ]
    )

    asrun.write_nct_payload_script(
        target,
        {
            "available": True,
            "reason": "",
            "segments": pd.DataFrame(rows, columns=columns),
        },
        viewer_minute,
        amagi_minute,
    )

    manifest_text = target.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text.split("=", 1)[1].rstrip(";"))
    assert manifest["partitioned"] is True
    assert manifest["segment_count"] == 2
    assert manifest["segments"] == []
    assert manifest["audience_schema"]["viewer"][0] == "minute_ist"
    assert sorted(manifest["dates"]) == ["2026-07-28", "2026-07-29"]
    for date_value, relative_path in manifest["dates"].items():
        chunk_text = (tmp_path / relative_path).read_text(encoding="utf-8")
        marker = f'window.__NCT_STORY_PARTITIONS__["{date_value}"]='
        story_json = chunk_text.split(marker, 1)[1].split(
            ";window.__NCT_AUDIENCE_PARTITIONS__", 1
        )[0]
        chunk_rows = json.loads(story_json)
        assert [row["log_date"] for row in chunk_rows] == [date_value]
        audience_marker = f'window.__NCT_AUDIENCE_PARTITIONS__["{date_value}"]='
        audience = json.loads(chunk_text.split(audience_marker, 1)[1].rstrip(";"))
        if date_value == "2026-07-28":
            assert audience["viewer"][0][1:] == [
                "fast",
                "Samsung TV Plus",
                "India TV",
                125,
            ]
            assert audience["amagi"][0][1:] == [
                "Samsung TV Plus",
                "India TV",
                75,
            ]
        else:
            assert audience == {"viewer": [], "amagi": []}


def test_render_dashboard_keeps_fct_multiselects_independent(
    tmp_path: Path, monkeypatch
) -> None:
    """Clearing one FCT dropdown must not rebuild or clear neighboring filters."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert "const FCT_FILTER_SPECS=[" in html
    assert "['fctCaption','caption','captions']" in html
    assert "['fctProgram','program_name','programs']" in html
    assert "['fctWeekday','_weekday','weekdays']" in html
    assert "['fctAdPosition','ad_position','positions']" in html
    assert "['fctBreakSize','total_ads','break sizes']" in html
    assert "['fctCoverage','is_filename_spillover','coverage states']" in html
    assert "['fctSourceFile','source_file','workbooks']" in html
    assert "['fctSourceSheet','source_sheet','sheets']" in html
    assert 'id="fctCaptionToggle"' in html
    assert 'id="fctProgramToggle"' in html
    assert 'id="fctWeekdayToggle"' in html
    assert 'id="fctAdPositionToggle"' in html
    assert 'id="fctBreakSizeToggle"' in html
    assert 'id="fctCoverageToggle"' in html
    assert 'id="fctSourceFileToggle"' in html
    assert 'id="fctSourceSheetToggle"' in html
    assert 'id="fctTimeFrom"' in html
    assert 'id="fctTimeTo"' in html
    assert 'id="fctProgramTimeFrom"' in html
    assert 'id="fctProgramTimeTo"' in html
    assert 'id="fctDurationMin"' in html
    assert 'id="fctDurationMax"' in html
    assert 'id="fctProgramDurationMin"' in html
    assert 'id="fctProgramDurationMax"' in html
    assert "for(const [id,key,kind] of FCT_FILTER_SPECS)" in html
    assert "buildMulti(id,values,kind,values,()=>renderFctAndScope(false))" in html
    assert "selections.every(([key,values])=>values.has(fctValue(row,key)))" in html
    assert "&&fctAdvancedRangesMatch(row)" in html
    assert "function fctClockMatches(row,key,fromId,toId){" in html
    assert "function fctNumericMatches(row,key,minId,maxId){" in html
    assert "function syncFctNumericRange(changed,minId,maxId){" in html
    assert "let fctSelectionCache={key:null,value:null};" in html
    assert "'Selected FCT Captions','Selected FCT Programs'" in html
    assert "'Selected FCT Weekdays','Selected FCT Ad Positions'" in html
    assert "'Selected On-air Time From','Selected On-air Time To'" in html
    assert "const NCT_FILTER_SPECS=[" in html
    assert "for(const [id,key,kind] of NCT_FILTER_SPECS)" in html
    assert 'id="nctStoryToggle"' in html
    assert 'id="nctStoryLookup"' in html
    assert 'id="nctStoryOptions"' in html
    assert 'id="nctStorySearch"' not in html
    assert "const NCT_STORY_OPTION_LIMIT=100" in html
    assert "&&(!nctSelectedStory||nctText(row,'story')===nctSelectedStory)" in html
    assert ".nct-chart-empty[hidden] { display: none !important; }" in html
    assert ".nct-loading[hidden] { display: none !important; }" in html
    assert '.nct-panel .multi-option input[type="checkbox"] {' in html
    assert "function wrapNctOptionLabels(id){" in html
    assert "wrapNctOptionLabels(id);" in html
    assert ".nct-filter-grid > .filter-label:has(.multi-menu.open) { z-index: 120; }" in html
    assert ".filter-label:has(.multi-menu.open) { position: relative; z-index: 120; }" in html
    assert ".multi-menu:has(.multi-search-shell) {" in html
    assert ".nct-panel .multi-search-actions {" in html
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in html
    assert ".nct-panel .multi-search-shell {" in html
    assert "width: calc(100% + 8px);" in html
    assert "box-shadow: 0 2px 4px rgba(15, 23, 42, .10);" in html
    assert "width: min(280px, calc(100vw - 24px));" in html
    assert ".nct-filter-grid > .filter-label:nth-last-child(-n+2) .multi-menu {" in html
    assert "grid-column: 1 / -1;" in html
    assert "function clearMultiMenuSearch(menu){" in html
    assert "search.dispatchEvent(new Event('input',{bubbles:true}));" in html
    assert "function alignMultiMenu(menu){" in html
    assert "if(rect.right>window.innerWidth-edge){" in html
    assert "function closeMultiMenu(menu){" in html
    assert "if(id)multiSearchState.delete(id);" in html
    assert "if(!owner||!owner.contains(event.target))closeMultiMenu(menu);" in html
    assert "'placeholder=\"Search channel, video ID, or title...\" autocomplete=\"off\"></span>'" in html
    assert "const NCT_RANK_LIMIT=15" in html
    assert "function renderNctRank(kind,rows){" in html
    assert "button.textContent=expanded?'Show Top 15':'Expand All ('+fmt(ranked.length)+')'" in html
    assert "Monitored Content Trend" in html
    assert 'data-nct-chart-mode=' not in html
    assert "function setNctChartMode(" not in html
    assert "function nctRollingAverage(" not in html
    assert "buildMulti(id,values,kind,values" in html
    assert "zero-only series hidden" in html
    assert "pointRadius:0" in html
    assert "beginAtZero:false" in html
    assert "text:'Monitored content minutes'" in html
    assert (
        "buildMulti('fctFeed',feeds,'feeds',feeds,"
        "()=>{refreshFctFilters();renderFctAndScope(false)})"
    ) not in html


def test_render_dashboard_adds_interval_weighted_nct_story_performance(
    tmp_path: Path, monkeypatch
) -> None:
    """Story Performance must use interval-weighted minute audience metrics."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert 'id="exportNctStoryAudienceCsv"' in html
    assert 'id="nctStoryAudienceBasis"' in html
    assert 'id="nctStoryRankBy"' in html
    assert 'id="fastPlatformToggle"' in html
    assert 'id="fastChannelToggle"' in html
    assert 'id="streamChannelToggle"' in html
    assert 'id="amagiPlatformToggle"' in html
    assert 'id="amagiChannelToggle"' in html
    assert 'id="youtubeChannelToggle"' in html
    assert 'id="globalAudienceDetails"' in html
    assert 'id="nctYoutubeVideoToggle"' in html
    assert 'id="globalAudienceFilters"' in html
    assert "window.matchMedia('(max-width: 680px)').matches" in html
    assert "move('globalFastFilters','fastPlatform','fastChannel')" in html
    assert "move('globalYoutubeFilters','youtubeChannel')" in html
    assert 'id="globalAsrunFilters"' in html
    assert "$('globalAsrunFilters').append($('deliveryTypeFilter'));" not in html
    assert "'spotAdId','spotCreative','lbandAdId','lbandCreative'" in html
    assert "if(!controls.children.length)controls.remove();" in html
    assert "function refreshNctStorySourceFilters(){" in html
    assert "const channelId=source==='fast'?'fastChannel':'streamChannel';" in html
    assert "selectedMulti('fastPlatform')" in html
    assert "selectedMulti('amagiPlatform')" in html
    assert "selectedMulti('youtubeChannel')" in html
    assert "function isIndiaTvYoutubeChannel(value){" in html
    assert "youtubeDefaultChannels(channels)" in html
    assert "const channels=new Set(indiaTvYoutubeChannels());" in html
    assert "youtubeChannels=indiaTvYoutubeScopeLabel()" in html
    assert "column.textContent='INDIA TV YOUTUBE';" in html
    assert ".combined-columns .youtube-col," in html
    assert "background: #fef9c3;" in html
    assert "selectedMulti('nctYoutubeVideo')" in html
    assert "updateNctStorySourceControls();" in html
    assert "function nctStoryAudienceRows(rows){" in html
    assert "function nctPrepareAudienceState(state){" in html
    assert "function nctAudienceInterval(state,startMillis,endMillis){" in html
    assert "metric.viewerMinutes/metric.coveredMinutes" in html
    assert "metric.viewingShare/entry.airtimeShare*100" in html
    assert "value.youtube=nctPrepareAudienceState(nctYoutubeAudienceMinuteMap(range));" in html
    assert "value.combined=nctCombinedAudienceState(value);" in html
    assert "function renderNctStoryAudience(rows){" in html
    assert "const value=Number(seconds||0),hours=Math.round(value/3600);" in html
    assert "return hours?fmt(hours)+' h':fmt(Math.round(value/60))+' min';" in html
    assert ".nct-story-audience-table.expandable," in html
    assert "height: min(65vh, 620px);" in html
    assert 'id="nctStoryTable"' in html
    assert "table.classList.toggle('expanded',nctStoryAudienceExpanded);" in html
    assert "const NCT_SEGMENT_LIMIT=15;" in html
    assert "const NCT_SEGMENT_BATCH=200;" in html
    assert 'id="nctSegmentExpand"' in html
    assert 'id="nctSegmentTable"' in html
    assert 'id="exportNctAudienceCsv"' in html
    assert 'id="exportNctAudienceBreakdownCsv"' in html
    assert "Export platform/channel CSV" in html
    assert "exportNctCsv').addEventListener('click',()=>runWithDashboardSources(" in html
    assert "'Selected FAST Platforms','Selected FAST Channels','Selected STREAM Platforms'" in html
    assert "'FAST Viewer-Minutes','STREAM Viewer-Minutes','AMAGI Viewer-Minutes'" in html
    assert "integer(metric.youtube.total),integer(metric.combined.total)" in html
    assert "'Start Half Hour','Dur in Mins','AMA','UR','NCT Date From','NCT Date To'" in html
    assert "NCT Monitored Content Occurrences" in html
    assert "Full NCT clip duration" in html
    assert "FAST<br>Viewer-min" in html
    assert "function nctOccurrenceAudienceStates(){" in html
    assert "function nctOccurrenceMetric(state,startMillis,endMillis" in html
    assert "const states=nctOccurrenceAudienceStates();" in html
    assert "Viewer-minutes = sum of minute concurrency x overlapping seconds / 60." in html
    assert "'Selected YouTube Video IDs','FAST Viewer-Minutes','STREAM Viewer-Minutes'" in html
    assert "'FAST Coverage Percent'" not in html
    assert "function nctSegmentAudienceMetrics(row,states){" in html
    assert "function exportNctAudienceCsv(){" in html
    assert "function nctOccurrenceBreakdownStates(range){" in html
    assert "function exportNctAudienceBreakdownCsv(){" in html
    assert "'Audience Source','Audience Platform','Audience Channel'" in html
    assert "'nct_content_occurrence_platform_channel_'" in html
    assert "'YouTube Viewer-Minutes','Combined Viewer-Minutes',\n  ];" in html
    assert "'Combined Viewer-Minutes','Combined Available Sources'" not in html
    assert "function renderNctSegments(rows){" in html
    assert "function toggleNctSegments(){" in html
    assert "Scroll to load more; CSV exports the complete filtered result." in html
    assert ".nct-rank-list.expandable {" in html
    assert "html { scrollbar-gutter: stable; }" in html
    assert "body.nct-chart-expanded::before {" in html
    assert ".nct-panel .panel-actions > button," in html
    assert '.nct-panel button.nct-rank-toggle[aria-expanded="true"],' in html
    assert "$('expandNctChart').setAttribute('aria-expanded',String(expanded));" in html
    assert "const NCT_CONTEXT_LIMIT=15;" in html
    assert 'id="nctContextExpand"' in html
    assert 'id="nctContextTable"' in html
    assert "function toggleNctContext(){" in html
    assert "nctContextRowsCache.slice(0,NCT_CONTEXT_LIMIT)" in html
    assert "CSV exports the complete filtered result." in html
    assert "Performance Index = Viewing Share" in html
    assert "are summed and are not cross-source deduplicated." in html
    assert ".nct-story-audience-columns > span:not(:first-child)," in html
    assert ".nct-story-audience-row > span:not(:first-child) {" in html
    assert "function exportNctStoryAudienceCsv(){" in html
    assert "Selected Average Minute Audience" in html
    assert "Selected Performance Index" in html
    assert "Selected Audience Coverage Percent" not in html
    assert "FAST Coverage Percent" not in html
    assert "STREAM Coverage Percent" not in html
    assert "AMAGI Coverage Percent" not in html
    assert "YouTube Coverage Percent" not in html
    assert "Combined Coverage Percent" not in html
    assert "Selected FAST Platforms" in html
    assert "Selected YouTube Channels" in html
    assert "Selected YouTube Video IDs" in html
    assert "youtubeMetric=youtubeFiveMinuteValue(e)" in html
    assert "youtubeMetric=youtubeFiveMinuteValue(anchor)" in html
    assert "value:'0',total:0,live_videos:0" in html
    assert "scope:'No India TV YouTube collector'" in html
    assert "return 'No India TV YouTube minute record';" in html
    assert "return 'Outside India TV YouTube source range';" in html
    assert "value:'No India TV YouTube data'" not in html
    assert "row.fast.total,row.stream.total,row.amagi.total,row.youtube.scope,row.youtube.total" in html
    assert "row.fast.total??'',row.stream.total??'',row.amagi.total??''" in html
    assert "row.total??'',row.partial?'Partial source coverage'" in html
    assert "const zeroMissing=source==='youtube';" in html
    assert "const zeroSelected=basis==='youtube';" in html
    assert "loadAudienceDashboardData()," in html
    assert "loadYoutubeDashboardData()," in html
    assert "Date continuity checks source coverage inside the date window" in html
    assert "<th>Date continuity</th>" in html
    assert "function dateContinuity(dateValues,start,end)" in html
    assert "function usedDateContinuity(dateValues,start,end,trueBounds)" in html
    assert "outside source range" in html
    assert "function scopeContinuityHtml(dateValues,trueBounds,usedStart,usedEnd)" in html
    assert "(DATA.date_coverage||{}).nct" in html


def test_render_dashboard_gives_fct_an_independent_all_range(
    tmp_path: Path, monkeypatch
) -> None:
    """FCT rows and exports must use FCT dates instead of the ASRUN header range."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert 'id="fctFrom"' in html
    assert 'id="fctTo"' in html
    assert 'data-fct-range="all" class="active"' in html
    assert "function initializeFctDates()" in html
    assert "setFctRange('all',false)" in html
    assert "const from=$('fctFrom').value,to=$('fctTo').value" in html
    assert "filters=fctFilterContext()" in html
    assert "Independent FCT date + all selected FCT dimensions" in html
    assert "function fctCoveredAudienceValue(event,state)" in html
    assert "value:'Not available'" in html
    assert "partial:available.length!==values.length" in html
    assert "'Coverage Status'" in html
