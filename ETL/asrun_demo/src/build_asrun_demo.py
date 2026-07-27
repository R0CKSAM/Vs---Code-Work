"""Build a standalone ASRUN delivery demo from fixed-width broadcast logs."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


HERE = Path(__file__).resolve()
DEMO_ROOT = HERE.parents[1]
RAW_DIR = DEMO_ROOT / "data" / "raw"
PARSED_DIR = DEMO_ROOT / "data" / "parsed"
CONFIG_DIR = DEMO_ROOT / "config"
OUTPUT_DIR = DEMO_ROOT / "output"
# Reuse the exact processed mart that powers Audience Operations; the demo writes
# only ASRUN-date rows into its own parsed folder to stay light and portable.
DEFAULT_IDENTITY_MINUTE = DEMO_ROOT.parent / "output" / "watch_hours" / "concurrency" / "identity_minute.parquet"

# Positions come from the dash ruler in the ASRUN header, not from whitespace.
FIELD_SLICES = {
    # The first two fields start immediately after the one-character row margin.
    # Correct boundaries preserve 14:20 and 20:16 rather than dropping the first hour digit.
    "on_air_date": (1, 9),
    "on_air_time": (10, 21),
    "event_id": (22, 55),
    "s": (55, 58),
    "creative_title": (58, 91),
    "duration_text": (91, 103),
    "status": (103, 111),
    "device": (111, 131),
    "ch": (131, 134),
    "reconciliation_id": (134, 144),
    "event_type": (144, 152),
    "sec": (152, 157),
}
AD_TYPE_RULES = (("C00", "Spot"), ("LBD", "L-band"))
ASRUN_DAILY_FILENAME = re.compile(r"^ASRUN-\d{6}\.txt$", re.IGNORECASE)
ASRUN_EVENT_LINE = re.compile(r"^\s*\d{2}/\d{2}/\d{2}\s")
YOUTUBE_ROOT = Path(
    os.getenv("VG_ASRUN_YOUTUBE_ROOT", r"Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube")
)
AMAGI_ROOT = Path(
    os.getenv("VG_ASRUN_AMAGI_ROOT", r"Z:\Veto Logs Backup\DO NOT DELETE\source=amagi")
)
YOUTUBE_COLUMNS = ["date", "time", "video_id", "title", "concurrent_viewers", "status"]
CHARTJS_CACHE = DEMO_ROOT.parent / "output" / "cache" / "chartjs" / "chart.umd.min.js"
IST_ZONE = ZoneInfo("Asia/Kolkata")

# These labels have an explicit name match only; Samsung variants remain separate
# until a stakeholder confirms whether they are distinct linear feeds or aliases.
AMAGI_CHANNEL_MAP = {
    "India TV Live": "India TV",
    "India TV Speed News": "India TV SpeedNews",
    "IndiaTV AapkiAdalat": "India TV Adalat",
    "IndiaTV Yoga": "India TV Yoga",
}


def parse_duration_seconds(value: str) -> float | None:
    """Convert ASRUN HH:MM:SS.xx into seconds; blank/invalid values stay null."""
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,2}))?", value.strip())
    if not match:
        return None
    hours, minutes, seconds, fractions = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + float(f"0.{fractions or '0'}")


def classify_ad(event_id: str) -> str | None:
    cleaned = event_id.strip().upper()
    for prefix, ad_type in AD_TYPE_RULES:
        if cleaned.startswith(prefix):
            return ad_type
    return None


def parse_asrun(path: Path, channel: str) -> pd.DataFrame:
    """Parse one ASRUN file and preserve every valid fixed-width data event."""
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="latin-1").splitlines(), start=1):
        # A valid ASRUN event begins with the fixed MM/DD/YY on-air date.
        if not ASRUN_EVENT_LINE.match(raw_line):
            continue
        row = {name: raw_line[start:end].strip() for name, (start, end) in FIELD_SLICES.items()}
        try:
            on_air_start = datetime.strptime(
                f"{row['on_air_date']} {row['on_air_time']}", "%m/%d/%y %H:%M:%S.%f"
            )
        except ValueError as exc:
            raise ValueError(f"Invalid ASRUN timestamp in {path.name}, line {line_number}") from exc
        duration_seconds = parse_duration_seconds(row["duration_text"])
        ad_type = classify_ad(row["event_id"])
        rows.append(
            {
                "source_file": path.name,
                "source_line": line_number,
                "channel_name": channel,
                "on_air_start_ist": on_air_start,
                "on_air_end_ist": on_air_start + pd.to_timedelta(duration_seconds or 0, unit="s"),
                "on_air_date": on_air_start.date().isoformat(),
                "hour_ist": on_air_start.hour,
                "event_id": row["event_id"],
                "ad_type": ad_type,
                "is_ad": ad_type is not None,
                "creative_title": row["creative_title"],
                "actual_duration_seconds": duration_seconds,
                "status": row["status"],
                "device": row["device"],
                "channel_code": row["ch"],
                "reconciliation_id": row["reconciliation_id"],
                "event_type": row["event_type"],
                "sec": row["sec"],
            }
        )
    if not rows:
        raise ValueError(f"No fixed-width ASRUN data rows found in {path}")
    return pd.DataFrame(rows)


def apply_brand_map(events: pd.DataFrame) -> pd.DataFrame:
    """Join only explicit manual mappings; unknown creatives must stay visible."""
    map_path = CONFIG_DIR / "creative_brand_map.csv"
    if not map_path.exists() or map_path.stat().st_size == 0:
        events["brand"] = pd.NA
        events["campaign"] = pd.NA
        events["mapping_confidence"] = pd.NA
        return events
    mapping = pd.read_csv(map_path, dtype="string").dropna(how="all")
    required = {"creative_id", "creative_title", "brand", "campaign", "confidence"}
    if mapping.empty or not required.issubset(mapping.columns):
        events["brand"] = pd.NA
        events["campaign"] = pd.NA
        events["mapping_confidence"] = pd.NA
        return events
    mapping = mapping.rename(columns={"creative_id": "event_id", "confidence": "mapping_confidence"})
    mapping = mapping.drop_duplicates(["event_id", "creative_title"], keep="last")
    return events.merge(
        mapping[["event_id", "creative_title", "brand", "campaign", "mapping_confidence"]],
        how="left",
        on=["event_id", "creative_title"],
        validate="many_to_one",
    )


def load_viewer_minute_snapshot(events: pd.DataFrame, mart_path: Path) -> pd.DataFrame:
    """Load the ASRUN-date subset of the Audience Operations identity-minute mart."""
    columns = ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"]
    if not mart_path.is_file():
        raise FileNotFoundError(
            "Audience Operations identity-minute mart is missing: "
            f"{mart_path}. Run the normal ETL concurrency/identity-minute step first."
        )
    ads = events.loc[events["is_ad"]]
    if ads.empty:
        return pd.DataFrame(columns=columns)
    start_date = ads["on_air_start_ist"].min().date().isoformat()
    end_date = ads["on_air_end_ist"].max().date().isoformat()
    # Read only the six columns required for the ASRUN exposure view.
    viewer = pd.read_parquet(mart_path, columns=columns)
    viewer["log_date"] = viewer["log_date"].astype("string").str.slice(0, 10)
    viewer["source"] = viewer["source"].astype("string").str.lower()
    viewer = viewer[
        viewer["source"].isin(["fast", "stream"])
        & viewer["log_date"].between(start_date, end_date)
    ].copy()
    viewer["minute_ist"] = pd.to_datetime(viewer["minute_ist"], errors="coerce")
    viewer = viewer[viewer["minute_ist"].notna()].copy()
    viewer["platform_name"] = viewer["platform_name"].fillna("Unknown / NA").astype("string")
    viewer["channel_name"] = viewer["channel_name"].fillna("Unknown / NA").astype("string")
    viewer["distinct_cliips"] = pd.to_numeric(viewer["distinct_cliips"], errors="coerce").fillna(0)
    # Audience Operations sums matching minute rows after channel/platform filtering.
    # Aggregate hidden host/candidate rows here so the demo stores that same visible metric.
    visible_keys = ["log_date", "source", "minute_ist", "platform_name", "channel_name"]
    return (
        viewer.groupby(visible_keys, as_index=False, dropna=False)["distinct_cliips"]
        .sum()
        .sort_values(["source", "minute_ist", "platform_name", "channel_name"])
    )


def build_amagi_minute_mart(events: pd.DataFrame) -> dict[str, Any]:
    """Read Amagi's actual minute-level concurrency exports for ASRUN dates."""
    columns = ["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name", "concurrent_viewers"]
    empty = pd.DataFrame(columns=columns)
    ads = events.loc[events["is_ad"]]
    if ads.empty or not AMAGI_ROOT.is_dir():
        return {"available": False, "reason": "Amagi source folder is not available.", "minute": empty, "files": 0}

    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    # Amagi exports may later be organised into date folders; discover the
    # complete source tree rather than silently limiting a refresh to root CSVs.
    for csv_path in sorted(AMAGI_ROOT.rglob("*.csv")):
        try:
            frame = pd.read_csv(csv_path, dtype="string")
        except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            skipped.append(f"{csv_path.name}: {exc}")
            continue
        required = {"channel_name", "platform_name", "timestamp (UTC)", "No. of Concurrent Viewers"}
        if not required.issubset(frame.columns):
            skipped.append(f"{csv_path.name}: missing required columns")
            continue
        frames.append(frame.loc[:, list(required)].copy())

    if not frames:
        return {"available": False, "reason": "No readable Amagi concurrency CSV files were found.", "minute": empty, "files": 0, "skipped": skipped}

    amagi = pd.concat(frames, ignore_index=True)
    # CSV timestamps are UTC. Converting with a timezone-aware dtype prevents
    # accidental filename-based date assignment or an extra IST shift.
    amagi["minute_ist"] = pd.to_datetime(amagi["timestamp (UTC)"], errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    amagi["concurrent_viewers"] = pd.to_numeric(amagi["No. of Concurrent Viewers"], errors="coerce")
    amagi["channel_raw"] = amagi["channel_name"].fillna("Unknown / NA").astype("string").str.strip()
    amagi["channel_name"] = amagi["channel_raw"].replace(AMAGI_CHANNEL_MAP)
    amagi["platform_name"] = amagi["platform_name"].fillna("Unknown / NA").astype("string").str.strip()
    amagi = amagi[amagi["minute_ist"].notna() & amagi["concurrent_viewers"].notna()].copy()
    amagi = amagi[amagi["concurrent_viewers"].ge(0)]
    amagi["log_date"] = amagi["minute_ist"].dt.strftime("%Y-%m-%d")

    # Keep every available Amagi minute in the embedded mart. The dashboard
    # applies its ASRUN event-date filter when rendering delivered-ad context;
    # clipping here would silently discard newer Amagi source data.
    # A repeated export minute is a collector retry; use the latest source row.
    amagi = amagi.drop_duplicates(["minute_ist", "platform_name", "channel_raw"], keep="last")
    minute = (
        amagi.groupby(["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name"], as_index=False)["concurrent_viewers"]
        .sum()
        .sort_values(["minute_ist", "platform_name", "channel_raw"])
    )
    return {
        "available": not minute.empty,
        "reason": "" if not minute.empty else "No Amagi viewer minutes overlap the selected ASRUN dates.",
        "minute": minute,
        "files": len(frames),
        "skipped": skipped,
    }



def build_youtube_marts() -> dict[str, Any]:
    """Build compact, reusable YouTube concurrency marts for the ASRUN demo."""
    empty_minute = pd.DataFrame(
        columns=["timestamp_ist", "log_date", "total_concurrent_viewers", "live_videos", "peak_video_concurrent"]
    )
    empty_video_daily = pd.DataFrame(
        columns=["log_date", "video_id", "title", "peak_concurrent_viewers", "avg_concurrent_viewers", "viewer_minutes", "live_minutes"]
    )
    empty_video_5min = pd.DataFrame(
        columns=["bucket_ist", "log_date", "video_id", "avg_concurrent_viewers", "peak_concurrent_viewers"]
    )
    empty_video_minute = pd.DataFrame(
        columns=["timestamp_ist", "log_date", "video_id", "title", "concurrent_viewers"]
    )
    if not YOUTUBE_ROOT.is_dir():
        return {
            "available": False,
            "reason": f"YouTube source folder not found: {YOUTUBE_ROOT}",
            "completed_files": 0,
            "partial_files": 0,
            "minute": empty_minute,
            "video_daily": empty_video_daily,
            "video_5min": empty_video_5min,
            "video_minute": empty_video_minute,
            "true_start": "",
            "true_end": "",
            "full_start": "",
            "full_end": "",
        }

    completed_files = sorted(YOUTUBE_ROOT.rglob("*.parquet"))
    partial_files = list(YOUTUBE_ROOT.rglob("*.partial"))
    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    for parquet_path in completed_files:
        try:
            frame = pd.read_parquet(parquet_path, columns=YOUTUBE_COLUMNS)
        except (OSError, ValueError, KeyError) as exc:
            skipped.append(f"{parquet_path.name}: {exc}")
            continue
        frames.append(frame)

    if not frames:
        return {
            "available": False,
            "reason": "No readable completed YouTube Parquet files were found.",
            "completed_files": len(completed_files),
            "partial_files": len(partial_files),
            "skipped_files": skipped,
            "minute": empty_minute,
            "video_daily": empty_video_daily,
            "video_5min": empty_video_5min,
            "video_minute": empty_video_minute,
            "true_start": "",
            "true_end": "",
            "full_start": "",
            "full_end": "",
        }

    youtube = pd.concat(frames, ignore_index=True)
    youtube["timestamp_ist"] = pd.to_datetime(
        youtube["date"].astype("string") + " " + youtube["time"].astype("string"),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )
    youtube["video_id"] = youtube["video_id"].fillna("").astype("string").str.strip()
    youtube["title"] = youtube["title"].fillna("").astype("string").str.strip()
    youtube["status"] = youtube["status"].fillna("").astype("string").str.strip().str.casefold()
    youtube["concurrent_viewers"] = pd.to_numeric(youtube["concurrent_viewers"], errors="coerce")
    youtube = youtube[
        youtube["timestamp_ist"].notna()
        & youtube["video_id"].ne("")
        & youtube["concurrent_viewers"].notna()
    ].copy()
    youtube["concurrent_viewers"] = youtube["concurrent_viewers"].clip(lower=0)
    # A repeated timestamp/video is a collector retry. Keep its latest record.
    youtube = youtube.sort_values("timestamp_ist").drop_duplicates(
        ["timestamp_ist", "video_id"], keep="last"
    )
    live = youtube.loc[youtube["status"].eq("is_live")].copy()
    if live.empty:
        # Readable collector files without live rows are a valid degraded state,
        # not a NaT.strftime() failure while writing the manifest below.
        return {
            "available": False,
            "reason": "No live YouTube viewer minutes were found in readable completed files.",
            "completed_files": len(completed_files),
            "partial_files": len(partial_files),
            "skipped_files": skipped,
            "minute": empty_minute,
            "video_daily": empty_video_daily,
            "video_5min": empty_video_5min,
            "video_minute": empty_video_minute,
            "true_start": "",
            "true_end": "",
            "full_start": "",
            "full_end": "",
        }
    live["log_date"] = live["timestamp_ist"].dt.strftime("%Y-%m-%d")

    minute = (
        live.groupby("timestamp_ist", as_index=False)
        .agg(
            total_concurrent_viewers=("concurrent_viewers", "sum"),
            live_videos=("video_id", "nunique"),
            peak_video_concurrent=("concurrent_viewers", "max"),
        )
        .sort_values("timestamp_ist")
    )
    minute["log_date"] = minute["timestamp_ist"].dt.strftime("%Y-%m-%d")

    # Keep a meaningful title even when the collector emits a blank title later.
    title_daily = (
        live.loc[live["title"].ne("")]
        .sort_values("timestamp_ist")
        .drop_duplicates(["log_date", "video_id"], keep="last")
        [["log_date", "video_id", "title"]]
    )
    video_minute = (
        live[["timestamp_ist", "log_date", "video_id", "concurrent_viewers"]]
        .merge(title_daily, on=["log_date", "video_id"], how="left", validate="many_to_one")
        .sort_values(["timestamp_ist", "video_id"])
    )
    video_daily = (
        live.groupby(["log_date", "video_id"], as_index=False)
        .agg(
            peak_concurrent_viewers=("concurrent_viewers", "max"),
            avg_concurrent_viewers=("concurrent_viewers", "mean"),
            viewer_minutes=("concurrent_viewers", "sum"),
            live_minutes=("timestamp_ist", "size"),
        )
        .merge(title_daily, on=["log_date", "video_id"], how="left", validate="one_to_one")
        .sort_values(["log_date", "peak_concurrent_viewers"], ascending=[True, False])
    )
    video_5min = live.assign(bucket_ist=live["timestamp_ist"].dt.floor("5min"))
    video_5min = (
        video_5min.groupby(["bucket_ist", "log_date", "video_id"], as_index=False)
        .agg(
            avg_concurrent_viewers=("concurrent_viewers", "mean"),
            peak_concurrent_viewers=("concurrent_viewers", "max"),
        )
        .merge(title_daily, on=["log_date", "video_id"], how="left", validate="many_to_one")
        .sort_values(["bucket_ist", "video_id"])
    )

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    minute.to_parquet(PARSED_DIR / "youtube_minute_total.parquet", index=False)
    video_daily.to_parquet(PARSED_DIR / "youtube_video_daily.parquet", index=False)
    video_5min.to_parquet(PARSED_DIR / "youtube_video_5min.parquet", index=False)
    video_minute.to_parquet(PARSED_DIR / "youtube_video_minute.parquet", index=False)
    full_day_counts = minute.groupby("log_date")["timestamp_ist"].nunique()
    full_days = full_day_counts[full_day_counts.eq(1440)].index.tolist()
    manifest = {
        "source_root": str(YOUTUBE_ROOT),
        "completed_files": len(completed_files),
        "partial_files": len(partial_files),
        "skipped_files": skipped,
        "true_start": minute["timestamp_ist"].min().strftime("%Y-%m-%d %H:%M:%S"),
        "true_end": minute["timestamp_ist"].max().strftime("%Y-%m-%d %H:%M:%S"),
        "full_start": min(full_days) if full_days else "",
        "full_end": max(full_days) if full_days else "",
    }
    (PARSED_DIR / "youtube_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "available": True,
        "reason": "",
        "completed_files": len(completed_files),
        "partial_files": len(partial_files),
        "skipped_files": skipped,
        "minute": minute,
        "video_daily": video_daily,
        "video_5min": video_5min,
        "video_minute": video_minute,
        "true_start": manifest["true_start"],
        "true_end": manifest["true_end"],
        "full_start": manifest["full_start"],
        "full_end": manifest["full_end"],
    }

def records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    """Convert dashboard data to JSON-safe records without reparsing JSON text."""
    if frame.empty:
        return []
    clean = frame.loc[:, columns].copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3]
    clean = clean.astype("object").where(pd.notna(clean), None)
    return clean.to_dict(orient="records")


def build_payload(events: pd.DataFrame, viewer_minute: pd.DataFrame, youtube: dict[str, Any], amagi: dict[str, Any]) -> dict[str, Any]:
    ads = events.loc[events["is_ad"]].copy()
    ads["actual_duration_seconds"] = pd.to_numeric(ads["actual_duration_seconds"], errors="coerce")
    ads["actual_duration_seconds"] = ads["actual_duration_seconds"].fillna(0)
    ads["duration_minutes"] = ads["actual_duration_seconds"] / 60
    if ads.empty:
        creative = pd.DataFrame(columns=["ad_type", "event_id", "creative_title", "plays", "duration_seconds"])
        hourly = pd.DataFrame(columns=["on_air_date", "hour_ist", "plays", "duration_seconds"])
        ad_types = pd.DataFrame(columns=["ad_type", "plays", "duration_seconds"])
    else:
        grouped = (
            ads.groupby(
                ["ad_type", "event_id", "creative_title", "on_air_date", "hour_ist"],
                dropna=False,
                as_index=False,
            )
            .agg(plays=("event_id", "size"), duration_seconds=("actual_duration_seconds", "sum"))
        )
        creative = (
            grouped.groupby(["ad_type", "event_id", "creative_title"], dropna=False, as_index=False)
            .agg(plays=("plays", "sum"), duration_seconds=("duration_seconds", "sum"))
            .sort_values(["duration_seconds", "plays"], ascending=False)
        )
        hourly = (
            grouped.groupby(["on_air_date", "hour_ist"], dropna=False, as_index=False)
            .agg(plays=("plays", "sum"), duration_seconds=("duration_seconds", "sum"))
            .sort_values(["on_air_date", "hour_ist"])
        )
        ad_types = (
            grouped.groupby("ad_type", dropna=False, as_index=False)
            .agg(plays=("plays", "sum"), duration_seconds=("duration_seconds", "sum"))
            .sort_values("duration_seconds", ascending=False)
        )
    mapped_keys = events.loc[
        events["brand"].notna(), ["event_id", "creative_title"]
    ].drop_duplicates()
    unmapped = creative.merge(
        mapped_keys.assign(_mapped=True),
        on=["event_id", "creative_title"],
        how="left",
        validate="one_to_one",
    )
    unmapped = unmapped.loc[unmapped["_mapped"].isna()].drop(columns=["_mapped"])
    if ads.empty:
        true_range = {"start": "No classified ad events", "end": "No classified ad events"}
    else:
        true_range = {
            "start": ads["on_air_start_ist"].min().strftime("%d-%m-%y %I:%M:%S %p IST"),
            "end": ads["on_air_end_ist"].max().strftime("%d-%m-%y %I:%M:%S %p IST"),
        }
    return {
        # Never label host-local time as IST; the dashboard timestamp is an
        # operational datum and must be stable across machines.
        "generated_at_ist": datetime.now(IST_ZONE).strftime("%d/%m/%y %I:%M:%S %p IST"),
        "source_files": sorted(events["source_file"].dropna().unique().tolist()),
        "channels": sorted(events["channel_name"].dropna().unique().tolist()),
        # This is an ad-delivery dashboard, so coverage must exclude non-ad ASRUN control events.
        "true_range": true_range,
        "kpis": {
            "all_events": int(len(events)),
            "ad_plays": int(len(ads)),
            "ad_minutes": round(float(ads["duration_minutes"].sum()), 2),
            "unique_creatives": int(ads[["event_id", "creative_title"]].drop_duplicates().shape[0]),
            "unmapped_creatives": int(unmapped[["event_id", "creative_title"]].drop_duplicates().shape[0]),
        },
        "ad_types": records(ad_types, ["ad_type", "plays", "duration_seconds"]),
        "hourly": records(hourly, ["on_air_date", "hour_ist", "plays", "duration_seconds"]),
        "creatives": records(creative, ["ad_type", "event_id", "creative_title", "plays", "duration_seconds"]),
        "events": records(
            ads.sort_values("on_air_start_ist"),
            ["on_air_start_ist", "on_air_end_ist", "ad_type", "event_id", "creative_title",
             "actual_duration_seconds", "brand", "campaign"],
        ),
        "viewer_minute": records(
            viewer_minute,
            ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"],
        ),
        "amagi": {
            "available": bool(amagi["available"]),
            "reason": amagi["reason"],
            "files": amagi["files"],
            "skipped": amagi.get("skipped", []),
            "minute": records(amagi["minute"], ["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name", "concurrent_viewers"]),
        },
        "youtube": {
            "available": bool(youtube["available"]),
            "reason": youtube["reason"],
            "completed_files": youtube["completed_files"],
            "partial_files": youtube["partial_files"],
            "skipped_files": youtube.get("skipped_files", []),
            "true_start": youtube["true_start"],
            "true_end": youtube["true_end"],
            "full_start": youtube["full_start"],
            "full_end": youtube["full_end"],
            "minute": records(
                youtube["minute"],
                ["timestamp_ist", "log_date", "total_concurrent_viewers", "live_videos", "peak_video_concurrent"],
            ),
            "video_daily": records(
                youtube["video_daily"],
                ["log_date", "video_id", "title", "peak_concurrent_viewers", "avg_concurrent_viewers", "viewer_minutes", "live_minutes"],
            ),
            "video_5min": records(
                youtube["video_5min"],
                ["bucket_ist", "log_date", "video_id", "title", "avg_concurrent_viewers", "peak_concurrent_viewers"],
            ),
            "video_minute": records(
                youtube["video_minute"],
                # Titles repeat per minute; resolve them from video_daily in browser instead.
                ["timestamp_ist", "log_date", "video_id", "concurrent_viewers"],
            ),
        },
    }


def render_dashboard(payload: dict[str, Any]) -> str:
    """Render the standalone ASRUN delivery and audience-minute demo."""
    blob = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    if not CHARTJS_CACHE.is_file():
        raise FileNotFoundError(f"Chart.js cache is required for the ASRUN dashboard: {CHARTJS_CACHE}")
    chartjs = CHARTJS_CACHE.read_text(encoding="utf-8")
    title = html.escape(" / ".join(payload["channels"]))
    # Token replacement keeps the HTML/JS free of Python f-string brace escaping.
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veto ASRUN Delivery Demo</title><style>
:root {
  color-scheme: light;
  --ink: #162431;
  --muted: #5b6b7a;
  --line: #d7e0e8;
  --panel: #ffffff;
  --canvas: #f4f7fa;
  --blue: #1967d2;
  --fast: #1368ce;
  --stream: #17805b;
  --combined: #eab308;
}
* { box-sizing: border-box; }
html, body { max-width: 100%; overflow-x: hidden; }
body { margin: 0; background: var(--canvas); color: var(--ink); font: 14px/1.4 Arial, sans-serif; }
.wrap { width: min(100%, 1480px); margin: 0 auto; padding: 0 20px; }
.topbar { background: #ffffff; border-bottom: 1px solid var(--line); }
.topbar-inner { min-height: 52px; display: flex; align-items: center; gap: 16px; }
.title-group { display: flex; flex: 1 1 420px; align-items: baseline; gap: 9px; min-width: 0; }
.title-group h1 { margin: 0; font-size: 18px; white-space: nowrap; }
.source-label, .meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-label { color: var(--muted); font-size: 12px; }
.meta { display: flex; flex: 0 1 auto; justify-content: flex-end; gap: 14px; color: var(--muted); font-size: 11px; }
h2 { margin: 0; font-size: 17px; }
p { margin: 0; color: var(--muted); }
.filter-shell { position: sticky; top: 0; z-index: 10; min-height: 52px; background: #eef3f8; border-bottom: 1px solid #cbd5e1; box-shadow: 0 3px 8px rgba(22, 36, 49, .08); }
.filters { min-height: 52px; display: grid; grid-template-columns: 200px 200px 150px 180px minmax(230px, 1fr) auto; gap: 8px; align-items: center; }
.filter-label { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--muted); font-size: 11px; line-height: 1; white-space: nowrap; }
.filter-label input, .filter-label select { flex: 1 1 auto; min-width: 0; }
input, select { width: 100%; height: 30px; border: 1px solid #aebdca; border-radius: 4px; padding: 4px 7px; background: #ffffff; color: var(--ink); font-size: 12px; }
button { height: 30px; border: 0; border-radius: 4px; padding: 0 11px; background: var(--blue); color: #ffffff; cursor: pointer; font-size: 12px; white-space: nowrap; }
main { padding: 16px 0 24px; }
.grid { display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 12px; align-items: stretch; }
.card, .panel { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px; }
.card { min-height: 118px; display: flex; flex-direction: column; }
.label { color: var(--muted); font-size: 12px; }
.value { margin-top: 6px; font-size: 24px; font-weight: 700; line-height: 1.15; }
.card-note { margin-top: auto; padding-top: 8px; color: var(--muted); font-size: 12px; line-height: 1.25; }
.rank-grid, .audience-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; align-items: stretch; }
.rank-panel, .audience-panel { display: flex; flex-direction: column; min-width: 0; }
.panel-head { display: flex; min-height: 32px; gap: 10px; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.panel-head > div { min-width: 0; }
.panel-head small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; font-weight: 400; }
.panel-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 7px; }
.panel-actions button { border: 1px solid #9dbde7; background: #ffffff; color: var(--blue); }
.source-tag { display: inline-flex; flex: 0 0 auto; align-items: center; min-height: 22px; border-radius: 3px; padding: 2px 7px; color: #ffffff; font-size: 11px; font-weight: 700; }
.fast-tag { background: var(--fast); }
.stream-tag { background: var(--stream); }
.combined-tag { background: var(--combined); color: #2c2500; }
.rank-list, .audience-list, .combined-list { flex: 1 1 auto; max-height: 520px; overflow-y: auto; border-top: 1px solid var(--line); }
.rank-list { padding-top: 4px; }
.barrow { display: grid; grid-template-columns: minmax(180px, 1.2fr) minmax(80px, 2fr) 96px; gap: 10px; align-items: center; min-height: 42px; margin: 5px 0; }
.bar-label { display: grid; min-width: 0; gap: 2px; overflow-wrap: anywhere; line-height: 1.25; }
.bar-label strong { font-size: 12px; }
.bar-label small, .rank-meta { color: var(--muted); font-size: 11px; }
.rank-meta { text-align: right; white-space: nowrap; }
.bar { height: 8px; overflow: hidden; border-radius: 4px; background: #e5edf5; }
.bar i { display: block; height: 100%; background: var(--blue); }
.audience-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); min-height: 47px; gap: 10px; align-items: center; margin-bottom: 8px; padding: 8px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.stream-audience-controls { grid-template-columns: minmax(0, 1fr); }
.audience-controls .filter-label { height: 30px; font-size: 11px; }
.multi-select { position: relative; flex: 1 1 auto; min-width: 0; }
.multi-toggle { position: relative; width: 100%; padding-right: 24px; overflow: hidden; border: 1px solid #aebdca; background: #ffffff; color: var(--ink); text-align: left; text-overflow: ellipsis; }
.multi-toggle::after { content: "v"; position: absolute; right: 8px; color: var(--muted); }
.multi-menu { display: none; position: absolute; z-index: 30; top: calc(100% + 3px); right: 0; left: 0; max-height: 230px; overflow-y: auto; padding: 4px; border: 1px solid #aebdca; border-radius: 4px; background: #ffffff; box-shadow: 0 5px 14px rgba(22, 36, 49, .16); }
.multi-menu.open { display: block; }
.multi-option { display: flex; align-items: center; gap: 6px; padding: 5px 4px; cursor: pointer; font-size: 12px; line-height: 1.2; }
.multi-option:hover { background: #eef3f8; }
.multi-option input { width: 14px; height: 14px; flex: 0 0 auto; }.multi-search { width: 100%; margin: 2px 0 5px; padding: 6px 7px; border: 1px solid #aebdca; border-radius: 3px; font: inherit; }
.multi-all { border-bottom: 1px solid var(--line); font-weight: 700; }
.event-columns, .event-line { display: grid; grid-template-columns: 104px 88px minmax(125px, 1fr) 62px 116px; gap: 8px; align-items: center; }
.event-columns { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.event-columns > span, .combined-columns > span, .youtube-context-head > span { text-align: center; }
.event-line { min-height: 44px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }
.event-line > span, .combined-line > span { min-width: 0; overflow-wrap: anywhere; }
.event-line small, .combined-line small { display: block; color: var(--muted); font-size: 10px; }
.audience-value, .combined-value { font-weight: 700; text-align: right; }
.audience-empty { padding: 12px 2px; color: var(--muted); font-size: 12px; }
.audience-note:empty { display: none; }
.combined-panel { margin-top: 16px; }
.combined-columns, .combined-line { display: grid; grid-template-columns: 112px 92px minmax(190px, 1fr) 66px 112px 112px 112px 124px; gap: 8px; align-items: center; }
.combined-columns { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.combined-line { min-height: 44px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }

.youtube-panel { margin-top: 16px; }
.youtube-tag { background: #e62117; }
.youtube-meta { margin: -2px 0 10px; color: var(--muted); font-size: 11px; }
.youtube-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 12px; border: 1px solid var(--line); border-radius: 5px; }
.youtube-metric { min-width: 0; min-height: 78px; padding: 11px 12px; border-right: 1px solid var(--line); }
.youtube-metric:last-child { border-right: 0; }
.youtube-metric-label { color: var(--muted); font-size: 11px; }
.youtube-metric-value { margin-top: 4px; font-size: 21px; font-weight: 700; line-height: 1.15; }
.youtube-metric-note { margin-top: 3px; color: var(--muted); font-size: 10px; }
.youtube-filter-bar { display: grid; grid-template-columns: repeat(2, minmax(150px, 1fr)) minmax(260px, 1.5fr) auto; gap: 10px; align-items: end; padding: 10px; margin-bottom: 10px; border: 1px solid var(--line); border-radius: 5px; background: #fbfcfd; }
.youtube-filter-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.youtube-filter-actions button { white-space: nowrap; transition: background-color .16s ease, border-color .16s ease, color .16s ease; }
.youtube-filter-actions button:hover { background: #fee2e2; border-color: #e62117; color: #a61b14; }
.youtube-filter-actions button:focus-visible { outline: 3px solid #f8c9c6; outline-offset: 2px; }
.youtube-filter-actions button.active:hover { background: #b91c1c; border-color: #b91c1c; color: #fff; }
.youtube-filter-actions button.active { background: #e62117; border-color: #e62117; color: #fff; }
.youtube-controls { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; }
.youtube-data-details { margin-bottom: 16px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.youtube-data-details summary { padding: 10px 2px; cursor: pointer; color: var(--ink); font-size: 12px; font-weight: 700; }
.youtube-data-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.youtube-data-table th, .youtube-data-table td { padding: 7px 4px; border-top: 1px solid var(--line); text-align: left; }
.youtube-data-table th:last-child, .youtube-data-table td:last-child { text-align: right; }
.youtube-controls-note { color: var(--muted); font-size: 11px; text-align: right; }
.youtube-chart-shell { position: relative; height: 270px; margin-bottom: 16px; border: 1px solid var(--line); border-radius: 5px; background: #ffffff; }
.youtube-chart-shell canvas { display: block; width: 100%; height: 100%; }
.youtube-chart-empty { display: none; position: absolute; inset: 0; align-items: center; justify-content: center; color: var(--muted); font-size: 12px; }
.youtube-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr); gap: 16px; }
.youtube-subsection { min-width: 0; }
.youtube-subsection h3 { margin: 0 0 7px; font-size: 13px; }
.youtube-list { max-height: 360px; overflow-y: auto; border-top: 1px solid var(--line); }
.youtube-video-row { display: grid; grid-template-columns: minmax(150px, 1fr) minmax(80px, 1.4fr) 92px; gap: 8px; align-items: center; min-height: 46px; padding: 7px 2px; border-bottom: 1px solid var(--line); }
.youtube-video-label { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.youtube-video-label strong { font-size: 11px; }
.youtube-video-label small, .youtube-video-value small, .youtube-context-row small { color: var(--muted); font-size: 10px; }
.youtube-mini-bar { height: 7px; overflow: hidden; border-radius: 4px; background: #f2d7d5; }
.youtube-mini-bar i { display: block; height: 100%; background: #e62117; }
.youtube-video-value { text-align: right; font-size: 11px; font-weight: 700; }
.youtube-context-head, .youtube-context-row { display: grid; grid-template-columns: 104px 82px minmax(125px, 1fr) 104px 72px; gap: 8px; align-items: center; }
.youtube-context-head { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.youtube-context-row { min-height: 42px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }
.youtube-context-row > span { min-width: 0; overflow-wrap: anywhere; }
.youtube-context-value { text-align: right; font-weight: 700; }

@media (max-width: 1220px) {
  .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 6px 0; }
  .filter-shell { min-height: 76px; }
  .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 960px) {
  .topbar-inner { min-height: 60px; align-items: flex-start; flex-wrap: wrap; padding: 7px 0; gap: 3px 12px; }
  .meta { width: 100%; justify-content: flex-start; }
  .rank-grid, .audience-grid, .youtube-grid { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .wrap { padding: 0 12px; }
  .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .filter-shell { min-height: 116px; }
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-metric:nth-child(2) { border-right: 0; }
  .youtube-metric:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .youtube-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-filter-actions { grid-column: 1 / -1; }
  .youtube-controls { align-items: flex-start; flex-direction: column; }
  .youtube-controls-note { text-align: left; }
  .youtube-context-head, .youtube-context-row { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .youtube-context-head span:nth-child(4), .youtube-context-head span:nth-child(5), .youtube-context-row span:nth-child(4), .youtube-context-row span:nth-child(5) { grid-column: 3; text-align: left; }
  .event-columns, .event-line { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .event-columns .duration, .event-line .duration { display: none; }
  .audience-value, .event-columns .metric { grid-column: 3; text-align: left; }
  .combined-columns, .combined-line { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .combined-columns .duration, .combined-line .duration { display: none; }
  .combined-columns .fast-col, .combined-columns .stream-col, .combined-columns .youtube-col, .combined-columns .total-col, .combined-line .fast-col, .combined-line .stream-col, .combined-line .youtube-col, .combined-line .total-col { grid-column: 3; text-align: left; }
}
@media (max-width: 460px) {
  .title-group { display: block; }
  .source-label { display: block; margin-top: 2px; }
  .meta { display: grid; gap: 2px; }
  .filters { grid-template-columns: 1fr; }
  .filter-shell { min-height: 210px; }
  .grid { grid-template-columns: 1fr; }
  .youtube-metrics { grid-template-columns: 1fr; }
  .youtube-filter-bar { grid-template-columns: 1fr; }
  .youtube-metric, .youtube-metric:nth-child(2) { border-right: 0; border-bottom: 1px solid var(--line); }
  .youtube-metric:last-child { border-bottom: 0; }
  .audience-controls { grid-template-columns: 1fr; }
  .barrow { grid-template-columns: minmax(0, 1fr) 82px; }
  .bar { display: none; }
}
</style><script>__CHARTJS__</script></head><body><header class="topbar"><div class="wrap topbar-inner"><div class="title-group"><h1>Veto ASRUN Delivery Demo</h1><span class="source-label">__TITLE__ | ASRUN playout evidence</span></div><div class="meta"><span id="range"></span><span id="updated"></span></div></div></header><section class="filter-shell"><div class="wrap filters"><label class="filter-label">Date from<input id="from" type="date"></label><label class="filter-label">Date to<input id="to" type="date"></label><label class="filter-label">Ad type<span class="multi-select"><button id="typeToggle" class="multi-toggle" type="button">All ad types</button><span id="typeMenu" class="multi-menu"></span></span></label><label class="filter-label">Ad ID<span class="multi-select"><button id="adIdToggle" class="multi-toggle" type="button">All ad IDs</button><span id="adIdMenu" class="multi-menu"></span></span></label><label class="filter-label">Creative title<span class="multi-select"><button id="creativeToggle" class="multi-toggle" type="button">All creative titles</button><span id="creativeMenu" class="multi-menu"></span></span></label><button id="reset" type="button">Reset</button></div></section><main class="wrap"><section class="grid" id="kpis"></section><section class="rank-grid"><div class="panel rank-panel"><div class="panel-head"><h2>Spot Creative Delivery</h2><span class="source-tag fast-tag">SPOT</span></div><div class="rank-list" id="spotBars"></div></div><div class="panel rank-panel"><div class="panel-head"><h2>L-band Creative Delivery</h2><span class="source-tag stream-tag">L-BAND</span></div><div class="rank-list" id="lbandBars"></div></div></section><section class="audience-grid"><div class="panel audience-panel"><div class="panel-head"><div><h2>FAST Delivered Ad Events</h2></div><span class="source-tag fast-tag">FAST</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="fastPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="fastPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="fastChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="fastChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="fastRows"></div><div class="audience-note" id="fastNote"></div></div><div class="panel audience-panel"><div class="panel-head"><div><h2>STREAM Delivered Ad Events</h2></div><span class="source-tag stream-tag">STREAM</span></div><div class="audience-controls stream-audience-controls"><label class="filter-label">Channel<span class="multi-select"><button id="streamChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="streamChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="streamRows"></div><div class="audience-note" id="streamNote"></div></div></section><section class="panel combined-panel"><div class="panel-head"><div><h2>All Delivered Ad Events</h2><small>FAST + STREAM selected 5-minute concurrency | YouTube minute concurrency</small></div><div class="panel-actions"><button id="exportAllEvents" type="button">Export CSV</button><button id="exportAudienceBreakdown" type="button">Export platform/channel CSV</button><span class="source-tag combined-tag">FAST + STREAM</span></div></div><div class="combined-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="fast-col">FAST</span><span class="stream-col">STREAM</span><span class="youtube-col">YOUTUBE</span><span class="total-col">Combined</span></div><div class="combined-list" id="allRows"></div><div class="audience-note" id="allNote"></div></section><section class="panel youtube-panel" id="youtubePanel"><div class="panel-head"><div><h2>YouTube Live Audience Context</h2></div><span class="source-tag youtube-tag">YOUTUBE</span></div><div class="youtube-meta" id="youtubeMeta"></div><div class="youtube-filter-bar" aria-label="Independent YouTube filters"><label class="filter-label">YouTube date from<input id="youtubeFrom" type="date"></label><label class="filter-label">YouTube date to<input id="youtubeTo" type="date"></label><label class="filter-label">Videos<span class="multi-select"><button id="youtubeVideoToggle" class="multi-toggle" type="button">All live videos</button><span id="youtubeVideoMenu" class="multi-menu"></span></span></label><div class="youtube-filter-actions" role="group" aria-label="YouTube quick ranges"><button type="button" data-youtube-range="latest">Latest day</button><button type="button" data-youtube-range="7">7D</button><button type="button" data-youtube-range="30">30D</button><button type="button" data-youtube-range="all">All</button></div></div><div class="youtube-metrics" id="youtubeMetrics"></div><div class="youtube-controls"><span class="youtube-controls-note" id="youtubeSelectionNote" aria-live="polite"></span><div class="panel-actions"><label class="filter-label">CSV interval<select id="youtubeExportInterval"><option value="1">1 minute</option><option value="5" selected>5 minutes</option></select></label><button id="exportYoutubeCsv" type="button">Export minute CSV</button><button id="exportYoutubeReferenceCsv" type="button">Export stream reference</button></div></div><div class="youtube-chart-shell"><canvas id="youtubeTrend" aria-label="YouTube live concurrency trend"></canvas><div class="youtube-chart-empty" id="youtubeChartEmpty"></div></div><details class="youtube-data-details"><summary>View chart values as a table</summary><table class="youtube-data-table"><thead><tr><th>IST time</th><th>Live concurrency</th></tr></thead><tbody id="youtubeTrendTable"></tbody></table></details><div class="youtube-grid"><section class="youtube-subsection"><h3>Top Live Videos</h3><div class="youtube-list" id="youtubeVideoRanking"></div></section><section class="youtube-subsection"><h3>YouTube Audience at Delivered Ad Events</h3><div class="youtube-context-head"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span>YT concurrency</span><span>Live videos</span></div><div class="youtube-list" id="youtubeEventContext"></div></section></div></section></main><script>const DATA=__BLOB__;const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n),mins=s=>fmt(s/60)+' min',esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));const canonical=String((DATA.channels||[])[0]||'');const dates=DATA.events.map(x=>x.on_air_start_ist.slice(0,10)),minDate=[...dates].sort()[0],maxDate=[...dates].sort().at(-1);$('from').value=minDate;$('to').value=maxDate;$('from').min=minDate;$('from').max=maxDate;$('to').min=minDate;$('to').max=maxDate;$('range').textContent='Ad data range: '+DATA.true_range.start+' to '+DATA.true_range.end;$('updated').textContent='Dashboard created: '+DATA.generated_at_ist;
function option(value,label){return '<option value="'+esc(value)+'">'+esc(label)+'</option>'}function dateScope(){const from=$('from').value,to=$('to').value;return DATA.events.filter(e=>e.on_air_start_ist.slice(0,10)>=from&&e.on_air_start_ist.slice(0,10)<=to)}function selectedMulti(id){return new Set([...$(id+'Menu').querySelectorAll('input[data-value]:checked')].map(input=>input.dataset.value))}function scope(){const types=selectedMulti('type');return dateScope().filter(e=>!types.size||types.has(e.ad_type))}function filterKey(){return [$('from').value,$('to').value,[...selectedMulti('type')].sort().join('|'),[...selectedMulti('adId')].sort().join('|'),[...selectedMulti('creative')].sort().join('|')].join('\u0000')}function multiAllLabel(id,kind,allLabel){const values=[...selectedMulti(id)],count=$(id+'Menu').querySelectorAll('input[data-value]').length,button=$(id+'Toggle');if(!values.length||values.length===count){button.textContent=allLabel;return}button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected'}function buildHeaderMulti(id,items,kind,defaultValues,allLabel,onChange){const menu=$(id+'Menu'),old=selectedMulti(id),allowed=new Set(items.map(item=>item.value)),selected=new Set([...old].filter(value=>allowed.has(value)));if(!old.size&&!multiInitialized.has(id))for(const value of defaultValues)if(allowed.has(value))selected.add(value);multiInitialized.add(id);const allChecked=items.length>0&&selected.size===items.length;menu.innerHTML='<label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All '+kind+'</label>'+items.map(item=>'<label class="multi-option"><input type="checkbox" data-value="'+esc(item.value)+'" '+(selected.has(item.value)?'checked':'')+'>'+esc(item.label)+'</label>').join('');multiAllLabel(id,kind,allLabel);$(id+'Toggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus(id);menu.classList.toggle('open',open)};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-value]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-value]')].every(input=>input.checked);multiAllLabel(id,kind,allLabel);clearFilterCache();onChange()};}function countedOptions(rows,key){const counts=new Map();for(const row of rows){const value=String(row[key]||'').trim();if(value)counts.set(value,(counts.get(value)||0)+1)}return [...counts.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([value,count])=>({value,label:value+' ('+fmt(count)+')'}))}function refreshDependentOptions(){const base=dateScope(),typeCounts=new Map();for(const row of base)typeCounts.set(row.ad_type,(typeCounts.get(row.ad_type)||0)+1);const types=['Spot','L-band'].filter(type=>typeCounts.has(type)).map(type=>({value:type,label:type+' ('+fmt(typeCounts.get(type))+')'}));buildHeaderMulti('type',types,'ad types',types.map(item=>item.value),'All ad types ('+fmt(base.length)+')',()=>{refreshDependentOptions();refreshAudienceFilters();scheduleRender()});const eligible=scope(),ids=countedOptions(eligible,'event_id');buildHeaderMulti('adId',ids,'ad IDs',ids.map(item=>item.value),'All ad IDs ('+fmt(eligible.length)+')',()=>{refreshDependentOptions();scheduleRender()});const selectedIds=selectedMulti('adId'),titlesSource=eligible.filter(e=>!selectedIds.size||selectedIds.has(e.event_id)),titles=countedOptions(titlesSource,'creative_title');buildHeaderMulti('creative',titles,'creative titles',titles.map(item=>item.value),'All creative titles ('+fmt(titlesSource.length)+')',scheduleRender)}function filtered(){const key=filterKey();if(filterCache.key===key&&filterCache.value)return filterCache.value;const selectedIds=selectedMulti('adId'),creative=selectedMulti('creative'),result=scope().filter(e=>(!selectedIds.size||selectedIds.has(e.event_id))&&(!creative.size||creative.has(e.creative_title)));filterCache={key,value:result};return result}function formatIst(value){const normalized=String(value).replace(' ','T'),[datePart,timePart='00:00']=normalized.split('T'),[year,month,day]=datePart.split('-'),[rawHour='0',minute='00']=timePart.split(':');const hour=Number(rawHour),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return day+'-'+month+'-'+year.slice(-2)+' '+String(twelve).padStart(2,'0')+':'+minute+' '+suffix;}
function rankingBars(node,items){const max=Math.max(1,...items.map(x=>x.seconds));node.innerHTML=items.length?items.map(x=>'<div class="barrow"><span class="bar-label"><strong>'+esc(x.id)+'</strong><small>'+esc(x.title)+'</small></span><div class="bar"><i style="width:'+((x.seconds/max)*100)+'%"></i></div><span class="rank-meta">'+fmt(x.plays)+' plays<br>'+mins(x.seconds)+'</span></div>').join(''):'<p>No delivery events in this selection.</p>';}function minuteKey(value){return String(value).slice(0,16)+':00'}function viewerScope(source){const from=$('from').value,to=$('to').value;return (DATA.viewer_minute||[]).filter(r=>r.source===source&&String(r.minute_ist).slice(0,10)>=from&&String(r.minute_ist).slice(0,10)<=to)}const multiInitialized=new Set();let filterCache={key:null,value:null},renderTimer=null;function clearFilterCache(){filterCache={key:null,value:null}}function scheduleRender(){clearTimeout(renderTimer);renderTimer=setTimeout(render,160)}function closeMultiMenus(exceptId){for(const menu of document.querySelectorAll('.multi-menu'))if(menu.id!==exceptId+'Menu')menu.classList.remove('open')}function multiSummary(id,kind){const values=[...selectedMulti(id)],button=$(id+'Toggle');if(!values.length){button.textContent='Choose '+kind;return}const all=[...$(id+'Menu').querySelectorAll('input[data-value]')].map(input=>input.dataset.value);if(values.length===all.length){button.textContent='All '+kind;return}button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected'}function buildMulti(id,items,kind,defaultValues,onChange){const menu=$(id+'Menu'),old=selectedMulti(id),allowed=new Set(items),selected=new Set([...old].filter(value=>allowed.has(value)));if(!old.size&&!multiInitialized.has(id))for(const value of defaultValues)if(allowed.has(value))selected.add(value);multiInitialized.add(id);const allChecked=items.length>0&&selected.size===items.length;menu.innerHTML='<label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All '+kind+'</label>'+items.map(value=>'<label class="multi-option"><input type="checkbox" data-value="'+esc(value)+'" '+(selected.has(value)?'checked':'')+'>'+esc(value)+'</label>').join('');multiSummary(id,kind);$(id+'Toggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus(id);menu.classList.toggle('open',open)};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-value]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-value]')].every(input=>input.checked);multiSummary(id,kind);clearFilterCache();onChange()};}function refreshAudienceFilters(){const fast=viewerScope('fast'),platforms=[...new Set(fast.map(r=>String(r.platform_name)))].sort();buildMulti('fastPlatform',platforms,'platforms',platforms,()=>{refreshAudienceFilters();scheduleRender()});const selectedPlatforms=selectedMulti('fastPlatform'),fastChannels=[...new Set(fast.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('fastChannel',fastChannels,'channels',fastChannels,scheduleRender);const streamChannels=[...new Set(viewerScope('stream').map(r=>String(r.channel_name)))].sort();buildMulti('streamChannel',streamChannels,'channels',streamChannels,scheduleRender);}function audienceMinuteMap(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;if(!channels.size||(source==='fast'&&!platforms.size))return {message:'',map:new Map()};const rows=viewerScope(source).filter(r=>(source!=='fast'||platforms.has(String(r.platform_name)))&&channels.has(String(r.channel_name)));if(!rows.length)return {message:'',map:new Map()};const map=new Map();for(const r of rows){const key=minuteKey(r.minute_ist);map.set(key,(map.get(key)||0)+Number(r.distinct_cliips||0));}return {message:'',map};}function naiveMillis(value){const [d,t='00:00:00']=String(value).split('T'),[year,month,day]=d.split('-').map(Number),[hour=0,minute=0,seconds=0]=t.split(':').map(Number);return Date.UTC(year,month-1,day,hour,minute,seconds);}function fiveMinuteWindow(event){const bucket=Math.floor(naiveMillis(event.on_air_start_ist)/(5*60000))*(5*60000),keys=[];for(let offset=0;offset<5;offset++)keys.push(new Date(bucket+offset*60000).toISOString().slice(0,16)+':00');const start=new Date(bucket),end=new Date(bucket+4*60000),clock=d=>{const hour=d.getUTCHours(),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return String(twelve).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0')+' '+suffix;};return {keys,label:clock(start)+'-'+clock(end)+' IST'};}function audienceValue(event,state){const window=fiveMinuteWindow(event);if(!state.map)return {value:'0',window:window.label,total:0};let total=0,found=false;for(const key of window.keys){if(state.map.has(key)){found=true;total+=state.map.get(key);}}return {value:found?fmt(total):'0',window:window.label,total:found?total:0};}function audienceLines(events,state){if(!events.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const metric=audienceValue(e,state);return '<div class="event-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="audience-value">'+esc(metric.value)+'</span></div>';}).join('');}let youtubeDeliveryMinuteIndex=null;
function youtubeDeliveryDetails(event){const youtube=DATA.youtube||{},key=youtubeMinuteKey(event.on_air_start_ist);if(!youtubeDeliveryMinuteIndex){const totals=new Map((youtube.minute||[]).map(row=>[youtubeMinuteKey(row.timestamp_ist),row]));const videos=new Map();for(const row of youtube.video_minute||[]){const minuteKey=youtubeMinuteKey(row.timestamp_ist),list=videos.get(minuteKey)||[];list.push(row);videos.set(minuteKey,list)}youtubeDeliveryMinuteIndex={totals,videos}}const totalRow=youtubeDeliveryMinuteIndex.totals.get(key),videoRows=youtubeDeliveryMinuteIndex.videos.get(key)||[];if(!totalRow)return {value:'No YouTube data',total:null,live_videos:0,video_ids:'',video_titles:'',scope:'All live YouTube videos at the on-air minute'};const videoIds=[...new Set(videoRows.map(row=>String(row.video_id||'')).filter(Boolean))],titles=[...new Set(videoRows.map(row=>youtubeVideoTitle(youtube,row.video_id,row.log_date)).filter(Boolean))];return {value:fmt(Number(totalRow.total_concurrent_viewers||0)),total:Number(totalRow.total_concurrent_viewers||0),live_videos:Number(totalRow.live_videos||videoIds.length),video_ids:videoIds.join(' | '),video_titles:titles.join(' | '),scope:'All live YouTube videos at the on-air minute'}}
function youtubeFiveMinuteValue(event){return youtubeDeliveryDetails(event)}
function combinedRows(events,fast,stream){return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const fastMetric=audienceValue(e,fast),streamMetric=audienceValue(e,stream),youtubeMetric=youtubeFiveMinuteValue(e);return {event:e,fast:fastMetric,stream:streamMetric,youtube:youtubeMetric,total:fastMetric.total===null||streamMetric.total===null||youtubeMetric.total===null?null:fastMetric.total+streamMetric.total+youtubeMetric.total};});}function combinedLines(events,fast,stream){const rows=combinedRows(events,fast,stream);if(!rows.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return rows.map(row=>{const e=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="combined-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="combined-value fast-col">'+esc(row.fast.value)+'</span><span class="combined-value stream-col">'+esc(row.stream.value)+'</span><span class="combined-value youtube-col">'+esc(row.youtube.value)+'</span><span class="combined-value total-col">'+esc(total)+'</span></div>';}).join('');}function renderAudience(events){const fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream');$('fastRows').innerHTML=audienceLines(events,fast);$('streamRows').innerHTML=audienceLines(events,stream);$('allRows').innerHTML=combinedLines(events,fast,stream);$('fastNote').textContent='';$('streamNote').textContent='';$('allNote').textContent='';}function csvCell(value){const text=String(value??'');return text.includes(',')||text.includes('\"')||text.split(String.fromCharCode(10)).length>1?'\"'+text.replace(/\"/g,'\"\"')+'\"':text}function exportAllEventsCsv(){const events=filtered(),fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),fastPlatforms=[...selectedMulti('fastPlatform')].join(' | '),fastChannels=[...selectedMulti('fastChannel')].join(' | '),streamChannels=[...selectedMulti('streamChannel')].join(' | '),header=['On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency','YouTube Scope','YouTube Minute Concurrency','YouTube Active Live Videos','YouTube Active Video IDs','YouTube Active Video Titles','Combined 5-Minute Concurrency'],rows=combinedRows(events,fast,stream).map(row=>[formatIst(row.event.on_air_start_ist),row.event.ad_type,row.event.event_id,row.event.creative_title,row.event.actual_duration_seconds,row.fast.window,fastPlatforms,fastChannels,streamChannels,row.fast.value,row.stream.value,row.youtube.scope,row.youtube.value,row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,row.total===null?'No combined data':fmt(row.total)]),csv=[header,...rows].map(row=>row.map(csvCell).join(',')).join(String.fromCharCode(13,10)),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='asrun_all_delivered_events_'+$('from').value+'_to_'+$('to').value+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),0);}

function audienceBreakdownScopes(source){const rows=viewerScope(source),channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;if(!channels.size||(source==='fast'&&!platforms.size))return [];const seen=new Set(),scopes=[];for(const row of rows){const platform=source==='fast'?String(row.platform_name||'Unknown / NA'):'STREAM',channel=String(row.channel_name||'Unknown / NA');if(!channels.has(channel)||(source==='fast'&&!platforms.has(platform)))continue;const key=platform+'\u0000'+channel;if(!seen.has(key)){seen.add(key);scopes.push({source:source.toUpperCase(),platform,channel})}}return scopes.sort((a,b)=>a.platform.localeCompare(b.platform)||a.channel.localeCompare(b.channel));}function audienceScopeMap(scope){const map=new Map();for(const row of viewerScope(scope.source.toLowerCase())){const platform=scope.source==='FAST'?String(row.platform_name||'Unknown / NA'):'STREAM',channel=String(row.channel_name||'Unknown / NA');if(platform!==scope.platform||channel!==scope.channel)continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.distinct_cliips||0));}return map}function audienceScopeValue(event,map){const window=fiveMinuteWindow(event);let total=0;for(const key of window.keys)total+=Number(map.get(key)||0);return {window:window.label,total}}function exportAudienceBreakdownCsv(){const events=filtered(),scopes=[...audienceBreakdownScopes('fast'),...audienceBreakdownScopes('stream')],header=['On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','Source','Platform','Channel','5-Minute Window IST','Individual 5-Minute Concurrency'],rows=[];for(const scope of scopes){const map=audienceScopeMap(scope);for(const event of events){const metric=audienceScopeValue(event,map);rows.push([formatIst(event.on_air_start_ist),event.ad_type,event.event_id,event.creative_title,event.actual_duration_seconds,scope.source,scope.platform,scope.channel,metric.window,metric.total])}}downloadCsv('asrun_audience_platform_channel_breakdown_'+$('from').value+'_to_'+$('to').value+'.csv',header,rows)}function youtubeMinuteKey(value){return String(value||'').slice(0,16)+':00'}
function youtubeBounds(){const y=DATA.youtube||{};return {start:String(y.full_start||y.true_start||'').slice(0,10),end:String(y.full_end||y.true_end||'').slice(0,10)}}
function youtubeRangeEvents(from,to){return (DATA.events||[]).filter(e=>e.is_ad&&String(e.on_air_start_ist||'').slice(0,10)>=from&&String(e.on_air_start_ist||'').slice(0,10)<=to)}
function updateYoutubeRangeButtons(kind){document.querySelectorAll('[data-youtube-range]').forEach(button=>button.classList.toggle('active',button.dataset.youtubeRange===kind))}
function syncYoutubeDates(changed){const from=$('youtubeFrom'),to=$('youtubeTo');if(from.value>to.value){if(changed==='from')to.value=from.value;else from.value=to.value}to.min=from.value;from.max=to.value}
function setYoutubeRange(kind){const b=youtubeBounds(),end=new Date(b.end+'T00:00:00Z');if(kind==='all'){$('youtubeFrom').value=b.start;$('youtubeTo').value=b.end}else{const days=kind==='latest'?1:Number(kind);end.setUTCDate(end.getUTCDate()-(days-1));$('youtubeFrom').value=[end.toISOString().slice(0,10),b.start].sort().at(-1);$('youtubeTo').value=b.end}syncYoutubeDates('from');updateYoutubeRangeButtons(kind);renderYoutube()}
function youtubeRowsForDate(rows,from,to){return (rows||[]).filter(row=>String(row.log_date||'').slice(0,10)>=from&&String(row.log_date||'').slice(0,10)<=to)}
function youtubeVideoLabel(row){const id=String(row.video_id||'Unknown video'),title=String(row.title||'Untitled live video');return {id,title}}function youtubeSelectedVideoIds(){return new Set([...$('youtubeVideoMenu').querySelectorAll('input[data-video]:checked')].map(input=>input.dataset.video))}let youtubeVideoMultiInitialized=false;function youtubeSelectionIsAll(videoIds,selected){return videoIds.length>0&&selected.size===videoIds.length}function youtubeVideoSummary(videoIds,selected){const button=$('youtubeVideoToggle');if(!selected.size){button.textContent='No live videos selected';return}button.textContent=youtubeSelectionIsAll(videoIds,selected)?'All live videos':selected.size===1?'1 live video selected':selected.size+' live videos selected'}function buildYoutubeVideoMulti(videoIds,titles){const menu=$('youtubeVideoMenu'),old=youtubeSelectedVideoIds(),allowed=new Set(videoIds),selected=new Set([...old].filter(id=>allowed.has(id)));if(!youtubeVideoMultiInitialized){for(const id of videoIds)selected.add(id);youtubeVideoMultiInitialized=true}const allChecked=youtubeSelectionIsAll(videoIds,selected),items=videoIds.map(id=>({id,title:titles.get(id)||'Untitled live video'}));menu.innerHTML='<input id="youtubeVideoSearch" class="multi-search" type="search" placeholder="Search video ID or title..."><label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All live videos</label>'+items.map(item=>'<label class="multi-option" data-video-option data-search="'+esc((item.id+' '+item.title).toLowerCase())+'"><input type="checkbox" data-video="'+esc(item.id)+'" '+(selected.has(item.id)?'checked':'')+'><span><strong>'+esc(item.id)+'</strong><br><small>'+esc(item.title)+'</small></span></label>').join('');youtubeVideoSummary(videoIds,selected);$('youtubeVideoToggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus('youtubeVideo');menu.classList.toggle('open',open);if(open)$('youtubeVideoSearch').focus()};$('youtubeVideoSearch').oninput=event=>{const term=event.target.value.trim().toLowerCase();for(const option of menu.querySelectorAll('[data-video-option]'))option.style.display=!term||option.dataset.search.includes(term)?'flex':'none'};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-video]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-video]')].every(input=>input.checked);youtubeVideoSummary(videoIds,youtubeSelectedVideoIds());renderYoutube()}}function youtubePointsForSelection(minute,videoMinute,videoIds,selected){if(youtubeSelectionIsAll(videoIds,selected))return minute.map(row=>({label:youtubeMinuteKey(row.timestamp_ist),value:Number(row.total_concurrent_viewers||0)}));const totals=new Map();for(const row of videoMinute){if(!selected.has(String(row.video_id)))continue;const key=youtubeMinuteKey(row.timestamp_ist);totals.set(key,(totals.get(key)||0)+Number(row.concurrent_viewers||0))}return [...totals.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([label,value])=>({label,value}))}
let youtubeTrendChart=null;
function youtubeChartPoints(points){const maxPoints=900,step=Math.max(1,Math.ceil(points.length/maxPoints)),out=[];for(let i=0;i<points.length;i+=step){const bucket=points.slice(i,i+step);out.push({label:formatIst(bucket[0].label)+(bucket.length>1?' to '+formatIst(bucket.at(-1).label):''),value:bucket.reduce((sum,p)=>sum+Number(p.value||0),0)/bucket.length})}return out}
function renderYoutubeTrend(points,label){const canvas=$('youtubeTrend'),empty=$('youtubeChartEmpty');if(!points.length){canvas.style.display='none';empty.style.display='flex';empty.textContent='No YouTube live-concurrency data for the selected YouTube date range.';return}canvas.style.display='block';empty.style.display='none';const chartPoints=youtubeChartPoints(points),values=chartPoints.map(point=>Number(point.value||0)),average=values.reduce((sum,value)=>sum+value,0)/values.length,newData={labels:chartPoints.map(point=>point.label),datasets:[{label:label,data:values,borderColor:'#e62117',backgroundColor:'rgba(230,33,23,.10)',fill:true,tension:.18,pointRadius:0,pointHoverRadius:5,pointHitRadius:12,borderWidth:1.7},{label:'Average baseline',data:values.map(()=>average),borderColor:'#6b7280',borderDash:[5,4],pointRadius:0,pointHoverRadius:0,borderWidth:1.1,fill:false}]};if(youtubeTrendChart){youtubeTrendChart.data=newData;youtubeTrendChart.update('none');return}youtubeTrendChart=new Chart(canvas,{type:'line',data:newData,options:{responsive:true,maintainAspectRatio:false,normalized:true,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:true,position:'bottom',labels:{usePointStyle:true,pointStyle:'line',boxWidth:14,font:{size:10}}},tooltip:{backgroundColor:'#1f2937',borderColor:'#475569',borderWidth:1,titleColor:'#f8fafc',bodyColor:'#f8fafc',padding:10,displayColors:true,callbacks:{label:ctx=>ctx.dataset.label+': '+fmt(ctx.parsed.y)}}},scales:{x:{title:{display:true,text:'IST time',font:{size:11,weight:'700'}},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:18,font:{size:10},color:'#5b6b7a'},grid:{color:'#edf2f7'}},y:{title:{display:true,text:'Live concurrent viewers',font:{size:11,weight:'700'}},beginAtZero:true,ticks:{color:'#5b6b7a',callback:value=>fmt(value)},grid:{color:'#edf2f7'}}}}})}
function downloadCsv(filename,header,rows){const csv=[header,...rows].map(row=>row.map(csvCell).join(',')).join(String.fromCharCode(13,10)),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),0)}
function youtubeVideoTitle(youtube,videoId,logDate){const exact=(youtube.video_daily||[]).find(row=>String(row.video_id)===String(videoId)&&String(row.log_date)===String(logDate));const fallback=(youtube.video_daily||[]).find(row=>String(row.video_id)===String(videoId));return String((exact||fallback||{}).title||'')}
function exportYoutubeCsv(){const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value,interval=$('youtubeExportInterval').value,daily=youtubeRowsForDate(youtube.video_daily,from,to),videoIds=[...new Set(daily.map(row=>String(row.video_id)))],selected=youtubeSelectedVideoIds(),all=youtubeSelectionIsAll(videoIds,selected);let rows,header;if(interval==='1'){if(all){rows=youtubeRowsForDate(youtube.minute,from,to).sort((a,b)=>String(a.timestamp_ist).localeCompare(String(b.timestamp_ist))).map(row=>[formatIst(row.timestamp_ist),row.log_date,'All live videos','',Number(row.total_concurrent_viewers||0),Number(row.peak_video_concurrent||0),Number(row.live_videos||0),'Minute total across all live videos']);header=['IST Time','Date IST','Scope','Video ID','Live Concurrency','Peak Video Concurrency','Live Video Count','Metric Basis']}else{rows=youtubeRowsForDate(youtube.video_minute,from,to).filter(row=>selected.has(String(row.video_id))).sort((a,b)=>String(a.timestamp_ist).localeCompare(String(b.timestamp_ist))||String(a.video_id).localeCompare(String(b.video_id))).map(row=>[formatIst(row.timestamp_ist),row.log_date,'Selected live videos',row.video_id,youtubeVideoTitle(youtube,row.video_id,row.log_date),Number(row.concurrent_viewers||0),'Minute-level per-video concurrency']);header=['IST Time','Date IST','Scope','Video ID','Video Title','Live Concurrency','Metric Basis']}}else{rows=youtubeRowsForDate(youtube.video_5min,from,to).filter(row=>all||selected.has(String(row.video_id))).sort((a,b)=>String(a.bucket_ist).localeCompare(String(b.bucket_ist))||String(a.video_id).localeCompare(String(b.video_id))).map(row=>[formatIst(row.bucket_ist),row.log_date,all?'All live videos':'Selected live videos',row.video_id,row.title,Number(row.avg_concurrent_viewers||0),Number(row.peak_concurrent_viewers||0),'5-minute average and peak']);header=['IST Time (5-minute bucket)','Date IST','Scope','Video ID','Video Title','Average Live Concurrency','Peak Live Concurrency','Metric Basis']}downloadCsv('youtube_live_audience_'+interval+'min_'+from+'_to_'+to+(all?'_all_videos':'_selected_videos')+'.csv',header,rows)}function exportYoutubeReferenceCsv(){const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value,daily=youtubeRowsForDate(youtube.video_daily,from,to),videoIds=[...new Set(daily.map(row=>String(row.video_id)))],selected=youtubeSelectedVideoIds(),all=youtubeSelectionIsAll(videoIds,selected),grouped=new Map();for(const row of youtubeRowsForDate(youtube.video_5min,from,to).filter(row=>all||selected.has(String(row.video_id)))){const id=String(row.video_id),current=grouped.get(id)||{id,title:String(row.title||''),first:String(row.bucket_ist),last:String(row.bucket_ist),buckets:0,viewerMinutes:0,peak:0};current.title=String(row.title||current.title);current.first=String(row.bucket_ist)<current.first?String(row.bucket_ist):current.first;current.last=String(row.bucket_ist)>current.last?String(row.bucket_ist):current.last;current.buckets++;current.viewerMinutes+=Number(row.avg_concurrent_viewers||0)*5;current.peak=Math.max(current.peak,Number(row.peak_concurrent_viewers||0));grouped.set(id,current)}const rows=[...grouped.values()].sort((a,b)=>b.viewerMinutes-a.viewerMinutes).map(row=>[from+' to '+to,row.id,row.title,formatIst(row.first),formatIst(row.last),row.buckets,row.viewerMinutes,row.peak]);downloadCsv('youtube_live_stream_reference_'+from+'_to_'+to+(all?'_all_videos':'_selected_videos')+'.csv',['Selected YouTube Range','Video ID','Video Title','First Observed IST','Last Observed IST','5-Minute Live Buckets','Estimated Viewer-Minutes','Peak Live Concurrency'],rows)}function renderYoutube(){const youtube=DATA.youtube||{};if(!youtube.available){$('youtubeMeta').textContent=youtube.reason||'YouTube source data is not available.';$('youtubeMetrics').innerHTML='';$('youtubeVideoRanking').innerHTML='<div class="audience-empty">YouTube live-audience data is unavailable.</div>';$('youtubeEventContext').innerHTML='';$('youtubeSelectionNote').textContent='';renderYoutubeTrend([], '');return}const from=$('youtubeFrom').value,to=$('youtubeTo').value,minute=youtubeRowsForDate(youtube.minute,from,to),daily=youtubeRowsForDate(youtube.video_daily,from,to),videoIds=[...new Set(daily.map(row=>String(row.video_id)))].sort(),titles=new Map();for(const row of daily.sort((a,b)=>String(a.log_date).localeCompare(String(b.log_date))))titles.set(String(row.video_id),String(row.title||''));buildYoutubeVideoMulti(videoIds,titles);const selected=youtubeSelectedVideoIds(),all=youtubeSelectionIsAll(videoIds,selected),videoMinute=youtubeRowsForDate(youtube.video_minute,from,to),points=youtubePointsForSelection(minute,videoMinute,videoIds,selected),values=points.map(point=>point.value),peak=values.length?Math.max(...values):0,average=values.length?values.reduce((sum,value)=>sum+value,0)/values.length:0,viewerMinutes=values.reduce((sum,value)=>sum+value,0),minuteSelectedCounts=new Map();for(const row of videoMinute){if(!all&&!selected.has(String(row.video_id)))continue;const key=youtubeMinuteKey(row.timestamp_ist);minuteSelectedCounts.set(key,(minuteSelectedCounts.get(key)||0)+1)}const peakLiveVideos=minuteSelectedCounts.size?Math.max(...minuteSelectedCounts.values()):0,bounds=youtubeBounds(),scopeLabel=all?'All live videos':selected.size+' selected live video'+(selected.size===1?'':'s');$('youtubeMeta').textContent='Independent YouTube filter | completed data: '+bounds.start+' to '+bounds.end+' | '+fmt(youtube.completed_files||0)+' completed hourly files';$('youtubeMetrics').innerHTML=[['Peak live concurrency',fmt(peak),scopeLabel],['Average live concurrency',fmt(average),scopeLabel],['Estimated viewer-minutes',fmt(viewerMinutes),'Live concurrency summed by minute'],['Peak simultaneous live videos',fmt(peakLiveVideos),scopeLabel]].map(metric=>'<div class="youtube-metric"><div class="youtube-metric-label">'+metric[0]+'</div><div class="youtube-metric-value">'+metric[1]+'</div><div class="youtube-metric-note">'+metric[2]+'</div></div>').join('');$('youtubeSelectionNote').textContent=scopeLabel+' | '+from+' to '+to+' | independent from ASRUN filters';renderYoutubeTrend(points,all?'Total live YouTube concurrency':'Selected live-video concurrency');const table=points.length>500?points.filter((_,i)=>i%Math.ceil(points.length/500)===0):points;$('youtubeTrendTable').innerHTML=table.length?table.map(point=>'<tr><td>'+formatIst(point.label)+'</td><td>'+fmt(point.value)+'</td></tr>').join(''):'<tr><td colspan="2">No values for this selection.</td></tr>';const grouped=new Map();for(const row of daily){if(!all&&!selected.has(String(row.video_id)))continue;const key=String(row.video_id),current=grouped.get(key)||{id:key,title:String(row.title||''),viewerMinutes:0,peak:0,liveMinutes:0,lastDate:''};current.viewerMinutes+=Number(row.viewer_minutes||0);current.peak=Math.max(current.peak,Number(row.peak_concurrent_viewers||0));current.liveMinutes+=Number(row.live_minutes||0);if(String(row.log_date)>=current.lastDate){current.lastDate=String(row.log_date);current.title=String(row.title||current.title)}grouped.set(key,current)}const ranking=[...grouped.values()].sort((a,b)=>b.viewerMinutes-a.viewerMinutes).slice(0,20),maxRank=Math.max(1,...ranking.map(row=>row.viewerMinutes));$('youtubeVideoRanking').innerHTML=ranking.length?ranking.map(row=>'<div class="youtube-video-row"><span class="youtube-video-label"><strong>'+esc(row.id)+'</strong><small>'+esc(row.title)+'</small></span><div class="youtube-mini-bar"><i style="width:'+((row.viewerMinutes/maxRank)*100)+'%"></i></div><span class="youtube-video-value">'+fmt(row.viewerMinutes)+'<small>viewer-minutes<br>Peak '+fmt(row.peak)+'</small></span></div>').join(''):'<div class="audience-empty">No live YouTube videos for this range.</div>';const minuteMap=new Map(minute.map(row=>[youtubeMinuteKey(row.timestamp_ist),row])),events=youtubeRangeEvents(from,to);$('youtubeEventContext').innerHTML=events.length?events.slice().sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(event=>{const row=minuteMap.get(youtubeMinuteKey(event.on_air_start_ist)),viewers=row?fmt(row.total_concurrent_viewers||0):'No data',videos=row?fmt(row.live_videos||0):'-';return '<div class="youtube-context-row"><span>'+formatIst(event.on_air_start_ist)+'</span><span><strong>'+esc(event.event_id)+'</strong><small>'+esc(event.ad_type)+'</small></span><span>'+esc(event.creative_title)+'</span><span class="youtube-context-value">'+viewers+'</span><span class="youtube-context-value">'+videos+'</span></div>'}).join(''):'<div class="audience-empty">No delivered ad events in this selection.</div>'}

function render(){const ev=filtered(),seconds=ev.reduce((n,e)=>n+(+e.actual_duration_seconds||0),0),grouped=new Map();for(const e of ev){const k=e.ad_type+'\u0000'+e.event_id+'\u0000'+e.creative_title,g=grouped.get(k)||{type:e.ad_type,id:e.event_id,title:e.creative_title,plays:0,seconds:0};g.plays++;g.seconds+=+e.actual_duration_seconds||0;grouped.set(k,g);}const rankings=[...grouped.values()].sort((a,b)=>b.seconds-a.seconds),spot=rankings.filter(x=>x.type==='Spot'),lband=rankings.filter(x=>x.type==='L-band'),spotPlays=ev.filter(x=>x.ad_type==='Spot').length,lbandPlays=ev.filter(x=>x.ad_type==='L-band').length,cards=[{label:'Total delivered ad plays',value:fmt(ev.length),note:'All Spot and L-band playout events'},{label:'Total actual ad duration',value:mins(seconds),note:'Sum of ASRUN delivered durations'},{label:'Total unique creatives',value:fmt(rankings.length),note:'Distinct Ad ID + creative title combinations'},{label:'Spot delivery',value:fmt(spotPlays)+' plays',note:fmt(spot.length)+' unique Spot creatives'},{label:'L-band delivery',value:fmt(lbandPlays)+' plays',note:fmt(lband.length)+' unique L-band creatives'}];$('kpis').innerHTML=cards.map(c=>'<div class="card"><div class="label">'+c.label+'</div><div class="value">'+c.value+'</div><div class="card-note">'+c.note+'</div></div>').join('');rankingBars($('spotBars'),spot);rankingBars($('lbandBars'),lband);renderAudience(ev);}
['from','to'].forEach(id=>$(id).addEventListener('change',()=>{clearFilterCache();refreshDependentOptions();refreshAudienceFilters();scheduleRender()}));$('youtubeFrom').addEventListener('change',()=>{syncYoutubeDates('from');updateYoutubeRangeButtons('');renderYoutube()});$('youtubeTo').addEventListener('change',()=>{syncYoutubeDates('to');updateYoutubeRangeButtons('');renderYoutube()});document.querySelectorAll('[data-youtube-range]').forEach(button=>button.addEventListener('click',()=>setYoutubeRange(button.dataset.youtubeRange)));window.addEventListener('resize',renderYoutube);$('exportAllEvents').addEventListener('click',exportAllEventsCsv);$('exportAudienceBreakdown').addEventListener('click',exportAudienceBreakdownCsv);$('exportYoutubeCsv').addEventListener('click',exportYoutubeCsv);$('exportYoutubeReferenceCsv').addEventListener('click',exportYoutubeReferenceCsv);document.addEventListener('click',event=>{if(!event.target.closest('.multi-select'))closeMultiMenus('')});$('reset').onclick=()=>{$('from').value=minDate;$('to').value=maxDate;multiInitialized.clear();clearFilterCache();refreshDependentOptions();refreshAudienceFilters();scheduleRender()};const youtubeInitial=youtubeBounds();$('youtubeFrom').min=youtubeInitial.start;$('youtubeFrom').max=youtubeInitial.end;$('youtubeTo').min=youtubeInitial.start;$('youtubeTo').max=youtubeInitial.end;const initialYoutubeFrom=[minDate,youtubeInitial.start].sort().at(-1),initialYoutubeTo=[maxDate,youtubeInitial.end].sort()[0];$('youtubeFrom').value=initialYoutubeFrom<=initialYoutubeTo?initialYoutubeFrom:youtubeInitial.end;$('youtubeTo').value=initialYoutubeFrom<=initialYoutubeTo?initialYoutubeTo:youtubeInitial.end;syncYoutubeDates('from');refreshDependentOptions();refreshAudienceFilters();render();renderYoutube();</script></body></html>"""
    amagi_extension = r'''<style>
:root { --amagi: #d97706; }
.amagi-tag { background: var(--amagi); color: #ffffff; }
.amagi-panel { border-top: 3px solid var(--amagi); }
.combined-columns, .combined-line { grid-template-columns: 112px 92px minmax(190px, 1fr) 66px 96px 96px 96px 96px 124px; }
.scope-panel { margin: 16px 0 28px; }
.scope-panel .panel-head { align-items: flex-start; }
.scope-panel small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; font-weight: 400; }
.scope-table-wrap { overflow-x: auto; }
.scope-table { width: 100%; min-width: 780px; border-collapse: collapse; font-size: 11px; }
.scope-table th, .scope-table td { padding: 9px 8px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
.scope-table th { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .03em; }
.scope-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
.scope-muted { color: var(--muted); }
@media (max-width: 680px) { .combined-columns .amagi-col, .combined-line .amagi-col { grid-column: 3; text-align: left; } }
</style><script>
const AMAGI=DATA.amagi||{};
function refreshAmagiFilters(){const rows=(AMAGI.minute||[]).filter(r=>String(r.log_date)>=String($('from').value)&&String(r.log_date)<=String($('to').value)),platforms=[...new Set(rows.map(r=>String(r.platform_name)))].sort();buildMulti('amagiPlatform',platforms,'platforms',platforms,()=>{refreshAmagiFilters();render()});const selectedPlatforms=selectedMulti('amagiPlatform'),channels=[...new Set(rows.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('amagiChannel',channels,'channels',channels,render);}
function amagiMinuteMap(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),map=new Map();for(const row of (AMAGI.minute||[])){if(!platforms.has(String(row.platform_name))||!channels.has(String(row.channel_name)))continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return {map};}
function ensureAmagiPanel(){if($('amagiRows'))return;const grid=document.querySelector('.audience-grid');grid.insertAdjacentHTML('beforeend','<div class="panel audience-panel amagi-panel"><div class="panel-head"><div><h2>AMAGI Delivered Ad Events</h2><small>Actual platform-reported concurrent viewers</small></div><span class="source-tag amagi-tag">AMAGI</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="amagiPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="amagiPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="amagiChannelToggle" class="multi-toggle" type="button">All channels</button><span id="amagiChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="amagiRows"></div><div class="audience-note" id="amagiNote"></div></div>');const header=document.querySelector('.combined-columns');header.querySelector('.youtube-col').insertAdjacentHTML('beforebegin','<span class="amagi-col">AMAGI</span>');document.querySelector('.combined-panel .panel-head small').textContent='FAST + STREAM selected 5-minute concurrency | Amagi actual 5-minute concurrency | YouTube minute concurrency';document.querySelector('.combined-panel .combined-tag').textContent='FAST + STREAM + AMAGI';}
function amagiLines(events,state){if(!AMAGI.available)return '<div class="audience-empty">'+esc(AMAGI.reason||'Amagi concurrency data is unavailable.')+'</div>';return audienceLines(events,state);}
function combinedRows(events,fast,stream){const amagi=amagiMinuteMap();return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const fastMetric=audienceValue(e,fast),streamMetric=audienceValue(e,stream),amagiMetric=audienceValue(e,amagi),youtubeMetric=youtubeFiveMinuteValue(e),all=[fastMetric.total,streamMetric.total,amagiMetric.total,youtubeMetric.total];return {event:e,fast:fastMetric,stream:streamMetric,amagi:amagiMetric,youtube:youtubeMetric,total:all.some(v=>v===null)?null:all.reduce((sum,v)=>sum+v,0)};});}
function combinedLines(events,fast,stream){const rows=combinedRows(events,fast,stream);if(!rows.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return rows.map(row=>{const e=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="combined-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="combined-value fast-col">'+esc(row.fast.value)+'</span><span class="combined-value stream-col">'+esc(row.stream.value)+'</span><span class="combined-value amagi-col">'+esc(row.amagi.value)+'</span><span class="combined-value youtube-col">'+esc(row.youtube.value)+'</span><span class="combined-value total-col">'+esc(total)+'</span></div>';}).join('');}
function renderAudience(events){ensureAmagiPanel();refreshAmagiFilters();const fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),amagi=amagiMinuteMap();$('fastRows').innerHTML=audienceLines(events,fast);$('streamRows').innerHTML=audienceLines(events,stream);$('amagiRows').innerHTML=amagiLines(events,amagi);$('allRows').innerHTML=combinedLines(events,fast,stream);$('fastNote').textContent='';$('streamNote').textContent='';$('amagiNote').textContent='';$('allNote').textContent='';}
function exportAllEventsCsv(){const events=filtered(),fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),amagi=amagiMinuteMap(),fastPlatforms=[...selectedMulti('fastPlatform')].join(' | '),fastChannels=[...selectedMulti('fastChannel')].join(' | '),streamChannels=[...selectedMulti('streamChannel')].join(' | '),header=['On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency','AMAGI 5-Minute Actual Concurrency','YouTube Scope','YouTube Minute Concurrency','YouTube Active Live Videos','YouTube Active Video IDs','YouTube Active Video Titles','Combined Concurrency'],rows=combinedRows(events,fast,stream).map(row=>[formatIst(row.event.on_air_start_ist),row.event.ad_type,row.event.event_id,row.event.creative_title,row.event.actual_duration_seconds,row.fast.window,fastPlatforms,fastChannels,streamChannels,row.fast.value,row.stream.value,row.amagi.value,row.youtube.scope,row.youtube.value,row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,row.total===null?'No combined data':fmt(row.total)]),csv=[header,...rows].map(row=>row.map(csvCell).join(',')).join(String.fromCharCode(13,10)),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='asrun_all_delivered_events_'+$('from').value+'_to_'+$('to').value+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),0);}
function amagiBreakdownScopes(){const rows=selectedAmagiRows(),seen=new Set(),scopes=[];for(const row of rows){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA'),key=platform+'\u0000'+channel;if(!seen.has(key)){seen.add(key);scopes.push({source:'AMAGI',platform,channel})}}return scopes.sort((a,b)=>a.platform.localeCompare(b.platform)||a.channel.localeCompare(b.channel));}
function amagiScopeMap(scope){const map=new Map();for(const row of selectedAmagiRows()){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA');if(platform!==scope.platform||channel!==scope.channel)continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return map;}
function exportAudienceBreakdownCsv(){const events=filtered(),scopes=[...audienceBreakdownScopes('fast'),...audienceBreakdownScopes('stream'),...amagiBreakdownScopes()],header=['On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','Source','Platform','Channel','5-Minute Window IST','Individual 5-Minute Concurrency','Metric Basis'],rows=[];for(const scope of scopes){const map=scope.source==='AMAGI'?amagiScopeMap(scope):audienceScopeMap(scope),basis=scope.source==='AMAGI'?'Actual platform-reported concurrent viewers':'Unique IP minute sum';for(const event of events){const metric=audienceScopeValue(event,map);rows.push([formatIst(event.on_air_start_ist),event.ad_type,event.event_id,event.creative_title,event.actual_duration_seconds,scope.source,scope.platform,scope.channel,metric.window,metric.total,basis])}}downloadCsv('asrun_audience_platform_channel_breakdown_'+$('from').value+'_to_'+$('to').value+'.csv',header,rows)}
function replaceDownloadAction(id,handler){const button=$(id);if(!button)return;const replacement=button.cloneNode(true);button.replaceWith(replacement);replacement.addEventListener('click',handler);}
function ensureScopePanel(){if($('dataScopeRows'))return;$('youtubePanel').insertAdjacentHTML('afterend','<section class="panel scope-panel" id="dataScopePanel"><div class="panel-head"><div><h2>Data Scope And Validation</h2><small>True range is all data embedded in this dashboard run. Used range updates with the active filters.</small></div></div><div class="scope-table-wrap"><table class="scope-table"><thead><tr><th>Dataset</th><th>True range (IST)</th><th>Used range (IST)</th><th>Used rows / points</th><th>Applied scope</th></tr></thead><tbody id="dataScopeRows"></tbody></table></div></section>');}
function sourceBounds(rows,startKey,endKey){if(!rows.length)return null;const starts=rows.map(row=>String(row[startKey]||'')).filter(Boolean).sort(),ends=rows.map(row=>String(row[endKey||startKey]||'')).filter(Boolean).sort();return starts.length&&ends.length?{start:starts[0],end:ends[ends.length-1]}:null;}
function scopeRangeText(bounds){return bounds?formatIst(bounds.start)+' to '+formatIst(bounds.end):'No matching data';}
function selectedViewerRows(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;return viewerScope(source).filter(row=>(!platforms||platforms.has(String(row.platform_name)))&&channels.has(String(row.channel_name)));}
function selectedAmagiRows(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),from=$('from').value,to=$('to').value;return (AMAGI.minute||[]).filter(row=>String(row.log_date)>=from&&String(row.log_date)<=to&&platforms.has(String(row.platform_name))&&channels.has(String(row.channel_name)));}
function selectedYoutubeRows(){const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value,daily=youtubeRowsForDate(youtube.video_daily,from,to),ids=[...new Set(daily.map(row=>String(row.video_id)))],selected=youtubeSelectedVideoIds(),all=youtubeSelectionIsAll(ids,selected);return youtubeRowsForDate(youtube.video_minute,from,to).filter(row=>all||selected.has(String(row.video_id)));}
function renderScopeValidation(){ensureScopePanel();const asrunTrue=sourceBounds(DATA.events||[],'on_air_start_ist','on_air_end_ist'),asrunUsed=sourceBounds(filtered(),'on_air_start_ist','on_air_end_ist'),fastTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='fast'),'minute_ist'),fastUsed=selectedViewerRows('fast'),streamTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='stream'),'minute_ist'),streamUsed=selectedViewerRows('stream'),amagiTrue=sourceBounds(AMAGI.minute||[],'minute_ist'),amagiUsed=selectedAmagiRows(),youtube=DATA.youtube||{},youtubeTrue={start:youtube.true_start||'',end:youtube.true_end||''},youtubeUsed=selectedYoutubeRows(),rows=[['ASRUN delivered ad events',asrunTrue,asrunUsed,filtered().length,'Date, ad type, ad ID, creative title'],['FAST viewer-minute snapshot',fastTrue,sourceBounds(fastUsed,'minute_ist'),fastUsed.length,'ASRUN date + FAST platform/channel'],['STREAM viewer-minute snapshot',streamTrue,sourceBounds(streamUsed,'minute_ist'),streamUsed.length,'ASRUN date + STREAM channel'],['AMAGI actual viewer minutes',amagiTrue,sourceBounds(amagiUsed,'minute_ist'),amagiUsed.length,'ASRUN date + AMAGI platform/channel'],['YouTube live audience',youtubeTrue.start&&youtubeTrue.end?youtubeTrue:null,sourceBounds(youtubeUsed,'timestamp_ist'),youtubeUsed.length,'Independent YouTube date + video filter']];$('dataScopeRows').innerHTML=rows.map(row=>'<tr><td><strong>'+esc(row[0])+'</strong></td><td>'+esc(scopeRangeText(row[1]))+'</td><td>'+esc(scopeRangeText(row[2]))+'</td><td>'+fmt(row[3])+'</td><td class="scope-muted">'+esc(row[4])+'</td></tr>').join('');}
const asrunBaseRender=render;render=function(){asrunBaseRender();renderScopeValidation();};
const asrunBaseRenderYoutube=renderYoutube;renderYoutube=function(){asrunBaseRenderYoutube();renderScopeValidation();};
ensureAmagiPanel();ensureScopePanel();replaceDownloadAction('exportAllEvents',exportAllEventsCsv);replaceDownloadAction('exportAudienceBreakdown',exportAudienceBreakdownCsv);render();
</script>'''
    return (
        template.replace("__BLOB__", blob)
        .replace("__TITLE__", title)
        .replace("__CHARTJS__", chartjs)
        # The extension reuses elements created by the base script, so it must
        # run after the base document and its initial render have completed.
        .replace("</body>", amagi_extension + "</body>")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", help="One or more ASRUN .txt files. Defaults to data/raw/*.txt.")
    parser.add_argument("--channel", required=True, help="Canonical Veto channel for these ASRUN files.")
    parser.add_argument(
        "--identity-minute",
        type=Path,
        default=DEFAULT_IDENTITY_MINUTE,
        help="Audience Operations identity_minute.parquet used for FAST/STREAM Unique IP Minute Sum.",
    )
    args = parser.parse_args()
    input_paths = args.input or sorted(
        path for path in RAW_DIR.iterdir()
        if path.is_file() and ASRUN_DAILY_FILENAME.fullmatch(path.name)
    )
    if not input_paths:
        raise SystemExit(
            f"No daily ASRUN files found in {RAW_DIR}. Expected names like ASRUN-150726.txt."
        )
    missing = [path for path in input_paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing input file(s): " + ", ".join(str(path) for path in missing))
    invalid_names = [path.name for path in input_paths if not ASRUN_DAILY_FILENAME.fullmatch(path.name)]
    if invalid_names:
        raise SystemExit(
            "Invalid ASRUN filename(s): " + ", ".join(invalid_names)
            + ". Use ASRUN-DDMMYY.txt, for example ASRUN-150726.txt."
        )
    events = apply_brand_map(pd.concat([parse_asrun(path, args.channel) for path in input_paths], ignore_index=True))
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed_path = PARSED_DIR / "asrun_events.parquet"
    events.to_parquet(parsed_path, index=False)
    viewer_minute = load_viewer_minute_snapshot(events, args.identity_minute)
    youtube = build_youtube_marts()
    amagi = build_amagi_minute_mart(events)
    viewer_snapshot_path = PARSED_DIR / "audience_ops_identity_minute_asrun_dates.parquet"
    viewer_minute.to_parquet(viewer_snapshot_path, index=False)
    payload = build_payload(events, viewer_minute, youtube, amagi)
    (OUTPUT_DIR / "asrun_ad_events.csv").write_text(
        events.loc[events["is_ad"]].to_csv(index=False), encoding="utf-8-sig"
    )
    html_path = OUTPUT_DIR / "asrun_delivery_demo.html"
    html_path.write_text(render_dashboard(payload), encoding="utf-8")
    print(f"Parsed events : {len(events):,}")
    print(f"Ad events     : {payload['kpis']['ad_plays']:,}")
    print(f"Viewer rows   : {len(viewer_minute):,} (Audience Operations identity-minute snapshot)")
    print(f"YouTube files : {youtube['completed_files']:,} completed, {youtube['partial_files']:,} partial")
    print(f"Amagi rows    : {len(amagi['minute']):,} actual viewer minutes from {amagi['files']:,} file(s)")
    print(f"Parquet       : {parsed_path}")
    print(f"Viewer mart   : {viewer_snapshot_path}")
    print(f"Dashboard     : {html_path}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
