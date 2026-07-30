"""Regression coverage for ASRUN demo empty-data handling."""

from __future__ import annotations

import importlib.util
import json
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


def test_parse_nct_csv_validates_and_normalizes_story_segments(tmp_path: Path) -> None:
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
            "clip_start_time": ["06:01:00"],
            "clip_end_time": ["06:01:10"],
            "pgm_date": ["29/07/2026"],
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
        }
    )
    preamble = "\n".join(
        [
            "Content Diagnostics - Duration - By Story Details",
            "Selection Details:",
            "Channels: INDIA TV,ABP NEWS",
            "From Date: 29/07/2026",
            "To Date: 29/07/2026",
            "Start Time: 05:00:00",
            "End Time: 23:59:00",
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


def test_nct_missing_channels_ignores_display_case_differences() -> None:
    """NCT metadata casing must not create a false missing-channel warning."""
    missing = asrun.missing_channel_labels(
        ["ABP NEWS", "NDTV INDIA"],
        {"ABP News"},
    )

    assert missing == ["NDTV INDIA"]


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
    assert "Filters changed from the default view; click to restore defaults" in html


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
    assert "ensureScopePanel();ensureDashboardPages();initializeNctLazyLoad()" in html
    assert "await activateDashboardPageData(activeDashboardPage)" in html


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
    assert 'id="fctCaptionToggle"' in html
    assert 'id="fctProgramToggle"' in html
    assert "for(const [id,key,kind] of FCT_FILTER_SPECS)" in html
    assert "buildMulti(id,values,kind,values,()=>renderFctAndScope(false))" in html
    assert "selections.every(([key,values])=>values.has(fctValue(row,key)))" in html
    assert "'Selected FCT Captions','Selected FCT Programs'" in html
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
    assert ".nct-controls > .filter-label:has(.multi-menu.open) { z-index: 120; }" in html
    assert ".filter-label:has(.multi-menu.open) { position: relative; z-index: 120; }" in html
    assert ".multi-menu:has(.multi-search-shell) {" in html
    assert ".nct-panel .multi-search-actions {" in html
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in html
    assert ".nct-panel .multi-search-shell {" in html
    assert "width: calc(100% + 8px);" in html
    assert "box-shadow: 0 2px 4px rgba(15, 23, 42, .10);" in html
    assert "width: min(280px, calc(100vw - 24px));" in html
    assert ".nct-controls > .filter-label:nth-last-child(-n+2) .multi-menu {" in html
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


def test_render_dashboard_adds_concurrency_to_nct_top_stories(
    tmp_path: Path, monkeypatch
) -> None:
    """Top Stories must reuse the established audience calculations."""
    chartjs = tmp_path / "chart.umd.min.js"
    chartjs.write_text("window.Chart=function(){};", encoding="utf-8")
    monkeypatch.setattr(asrun, "CHARTJS_CACHE", chartjs)

    html = asrun.render_dashboard({"channels": ["Test Channel"]})

    assert 'id="exportNctStoryAudienceCsv"' in html
    assert "function nctStoryAudienceRows(rows){" in html
    assert "const fast=fctCoveredAudienceValue(anchor,states.fast);" in html
    assert "const stream=fctCoveredAudienceValue(anchor,states.stream);" in html
    assert "const amagi=fctCoveredAudienceValue(anchor,states.amagi);" in html
    assert "const youtube=youtubeFiveMinuteValue(anchor);" in html
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
    assert "India TV YouTube uses minute concurrency" in html
    assert ".nct-story-audience-columns > span:not(:first-child)," in html
    assert ".nct-story-audience-row > span:not(:first-child) {" in html
    assert "function exportNctStoryAudienceCsv(){" in html
    assert "Average FAST 5-Minute Concurrency" in html
    assert "loadAudienceDashboardData()," in html
    assert "loadYoutubeDashboardData()," in html


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
    assert (
        "Independent FCT date + "
        "class/feed/language/brand/caption/program/category/company"
    ) in html
    assert "function fctCoveredAudienceValue(event,state)" in html
    assert "value:'Not available'" in html
    assert "partial:available.length!==values.length" in html
    assert "'Coverage Status'" in html
