"""Build a standalone ASRUN delivery demo from fixed-width broadcast logs."""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ETL.asrun_demo.src.io_utils import (
        atomic_write_json,
        atomic_write_parquet,
        atomic_write_text,
        read_json_object,
        source_file_fingerprint,
    )
except ModuleNotFoundError:
    # Direct script execution places this source directory on sys.path.
    from io_utils import (  # type: ignore[no-redef]
        atomic_write_json,
        atomic_write_parquet,
        atomic_write_text,
        read_json_object,
        source_file_fingerprint,
    )


LOGGER = logging.getLogger("veto.asrun")
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
FCT_ROOT = Path(
    os.getenv("VG_ASRUN_FCT_ROOT", r"Z:\Veto Logs Backup\DO NOT DELETE\source=FCT")
)
NCT_ROOT = Path(
    os.getenv("VG_ASRUN_NCT_ROOT", r"Z:\Veto Logs Backup\DO NOT DELETE\source=NCT")
)
YOUTUBE_COLUMNS = ["date", "time", "video_id", "title", "concurrent_viewers", "status"]
YOUTUBE_FILENAME = re.compile(
    r"^(?P<collector>.+?)_\d{2}-\d{2}-\d{4}_\d{2}-\d{2}_[^.]+\.parquet$",
    re.IGNORECASE,
)
YOUTUBE_CHANNEL_LABELS = {
    "aajtak": "Aaj Tak",
    "abpnews": "ABP News",
    "cnnnews18": "CNN-News18",
    "indiatv": "India TV",
    "ndtvindia": "NDTV India",
    "republicbharat": "Republic Bharat",
    "tv9bharatvarsh": "TV9 Bharatvarsh",
    "zeenews": "Zee News",
}
CHARTJS_CACHE = DEMO_ROOT.parent / "output" / "cache" / "chartjs" / "chart.umd.min.js"
IST_ZONE = ZoneInfo("Asia/Kolkata")
FCT_FILENAME_RANGE = re.compile(
    r"(?P<start>\d{8})\s+to\s+(?P<end>\d{8})", re.IGNORECASE
)
FCT_REQUIRED_COLUMNS = {
    "Feed Name",
    "Pdate",
    "Progname",
    "Pgst",
    "Pgdur",
    "Adst",
    "Brandname",
    "Aaddur",
    "Caption",
    "Language",
    "Category",
    "Company",
    "Adpos",
    "TotAds",
}
FCT_INTERNAL_CATEGORIES = frozenset(
    {
        "PROMO TAG",
        "PROMO PROGRAM",
        "CHANNEL IMAGERY",
        "SHORT PROGRAM",
        "PROMO CHANNEL/BRAND",
    }
)
FCT_MART_VERSION = 3
NCT_MART_VERSION = 3
YOUTUBE_MART_VERSION = 3
AMAGI_MART_VERSION = 1
CORE_PAYLOAD_FILENAME = "asrun_delivery_data.js"
DASHBOARD_SIDECARS = {
    "viewer": {
        "file": "asrun_viewer_minute_data.js",
        "global": "__ASRUN_VIEWER_MINUTE__",
    },
    "amagi": {
        "file": "asrun_amagi_minute_data.js",
        "global": "__ASRUN_AMAGI_MINUTE__",
    },
    "fct": {
        "file": "asrun_fct_event_data.js",
        "global": "__ASRUN_FCT_EVENTS__",
    },
    "youtube": {
        "file": "asrun_youtube_data.js",
        "global": "__ASRUN_YOUTUBE_DATA__",
    },
}
YOUTUBE_PAYLOAD_ARRAYS = (
    "minute",
    "video_daily",
    "video_5min",
    "video_minute",
)
NCT_PARTITION_DIR = Path("data") / "nct"
NCT_REQUIRED_COLUMNS = {
    "channel",
    "Story",
    "Sub_Story",
    "story_genre_1",
    "story_genre_2",
    "pgm_name",
    "Pgm_Start_Time",
    "Pgm_End_Time",
    "clip_start_time",
    "clip_end_time",
    "pgm_date",
    "geography",
    "title",
    "duration",
    "duration_seconds",
    "personality",
    "guest",
    "anchor",
    "reporter",
    "logistics",
    "telecast_format",
    "assist_used",
    "split",
    "Story_Format",
}

# These labels have an explicit name match only; Samsung variants remain separate
# until a stakeholder confirms whether they are distinct linear feeds or aliases.
AMAGI_CHANNEL_MAP = {
    "India TV Live": "India TV",
    "India TV Speed News": "India TV SpeedNews",
    "IndiaTV AapkiAdalat": "India TV Adalat",
    "IndiaTV Yoga": "India TV Yoga",
}


def configure_logging(verbose: bool) -> None:
    """Enable concise operator diagnostics without changing normal CLI output."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def timed_step(label: str, function: Any, *args: Any) -> Any:
    """Run one pipeline step and log elapsed time when verbose mode is enabled."""
    started = perf_counter()
    LOGGER.info("Starting %s", label)
    result = function(*args)
    LOGGER.info("Completed %s in %.2f seconds", label, perf_counter() - started)
    return result


def parse_duration_seconds(value: str) -> float | None:
    """Convert ASRUN HH:MM:SS.xx into seconds; blank/invalid values stay null."""
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,2}))?", value.strip())
    if not match:
        return None
    hours, minutes, seconds, fractions = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + float(f"0.{fractions or '0'}")


def classify_ad(event_id: str) -> str | None:
    """Map a supported ASRUN event-ID prefix to its stakeholder ad type."""
    cleaned = event_id.strip().upper()
    for prefix, ad_type in AD_TYPE_RULES:
        if cleaned.startswith(prefix):
            return ad_type
    return None


def categorise_repeated_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    """Use categorical storage for low-cardinality dimensions before grouping."""
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].astype("category")
    return frame


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


def load_viewer_minute_snapshot(
    events: pd.DataFrame,
    mart_path: Path,
    additional_ranges: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Load the ASRUN and related evidence dates from the identity-minute mart."""
    columns = ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"]
    if not mart_path.is_file():
        raise FileNotFoundError(
            "Audience Operations identity-minute mart is missing: "
            f"{mart_path}. Run the normal ETL concurrency/identity-minute step first."
        )
    date_ranges: list[tuple[str, str]] = []
    ads = events.loc[events["is_ad"]]
    if not ads.empty:
        date_ranges.append(
            (
                ads["on_air_start_ist"].min().date().isoformat(),
                ads["on_air_end_ist"].max().date().isoformat(),
            )
        )
    for start, end in additional_ranges or []:
        normalized_start = str(start).strip()[:10]
        normalized_end = str(end).strip()[:10]
        if normalized_start and normalized_end and normalized_start <= normalized_end:
            date_ranges.append((normalized_start, normalized_end))
    if not date_ranges:
        return pd.DataFrame(columns=columns)
    start_date = min(start for start, _end in date_ranges)
    end_date = max(end for _start, end in date_ranges)
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
    viewer = categorise_repeated_columns(
        viewer,
        ("source", "platform_name", "channel_name"),
    )
    # Audience Operations sums matching minute rows after channel/platform filtering.
    # Aggregate hidden host/candidate rows here so the demo stores that same visible metric.
    visible_keys = ["log_date", "source", "minute_ist", "platform_name", "channel_name"]
    return (
        viewer.groupby(
            visible_keys,
            as_index=False,
            dropna=False,
            observed=True,
        )["distinct_cliips"]
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

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    source_paths = sorted(AMAGI_ROOT.rglob("*.csv"))
    path_by_name = {
        str(path.relative_to(AMAGI_ROOT)): path for path in source_paths
    }
    fingerprints = {
        name: source_file_fingerprint(path) for name, path in path_by_name.items()
    }
    manifest_path = PARSED_DIR / "amagi_manifest.json"
    source_cache_path = PARSED_DIR / "amagi_source_rows.parquet"
    minute_path = PARSED_DIR / "amagi_minute.parquet"
    old_manifest = read_json_object(manifest_path)
    old_fingerprints = (
        old_manifest.get("fingerprints", {})
        if old_manifest.get("schema_version") == AMAGI_MART_VERSION
        else {}
    )
    if (
        fingerprints == old_fingerprints
        and minute_path.is_file()
        and bool(old_manifest.get("available"))
    ):
        try:
            minute = pd.read_parquet(minute_path)
        except (OSError, ValueError, KeyError):
            pass
        else:
            LOGGER.info("Amagi mart cache hit: %d unchanged file(s)", len(source_paths))
            return {
                "available": not minute.empty,
                "reason": "" if not minute.empty else "No valid Amagi viewer minutes were found.",
                "minute": minute,
                "files": int(old_manifest.get("files", len(source_paths))),
                "skipped": old_manifest.get("skipped", []),
            }

    old_readable = set(old_manifest.get("readable_files", []))
    unchanged = {
        name
        for name, fingerprint in fingerprints.items()
        if old_fingerprints.get(name) == fingerprint and name in old_readable
    }
    cached_source = pd.DataFrame()
    if unchanged and source_cache_path.is_file():
        try:
            cached_source = pd.read_parquet(source_cache_path)
            required_cache_columns = {
                "channel_name",
                "platform_name",
                "timestamp (UTC)",
                "No. of Concurrent Viewers",
                "source_file",
            }
            if required_cache_columns.difference(cached_source.columns):
                cached_source = pd.DataFrame()
                unchanged.clear()
            else:
                cached_source = cached_source[
                    cached_source["source_file"].isin(unchanged)
                ].copy()
        except (OSError, ValueError, KeyError):
            cached_source = pd.DataFrame()
            unchanged.clear()

    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    readable_files = set(unchanged)
    required = {
        "channel_name",
        "platform_name",
        "timestamp (UTC)",
        "No. of Concurrent Viewers",
    }
    for source_name in sorted(set(path_by_name).difference(unchanged)):
        csv_path = path_by_name[source_name]
        try:
            frame = pd.read_csv(csv_path, dtype="string")
        except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            skipped.append(f"{source_name}: {exc}")
            continue
        if not required.issubset(frame.columns):
            skipped.append(f"{source_name}: missing required columns")
            continue
        parsed = frame.loc[:, sorted(required)].copy()
        parsed["source_file"] = source_name
        frames.append(parsed)
        readable_files.add(source_name)
    LOGGER.info(
        "Amagi incremental refresh: %d cached, %d parsed, %d skipped",
        len(unchanged),
        len(frames),
        len(skipped),
    )

    source_parts = [
        frame for frame in [cached_source, *frames] if not frame.empty
    ]
    if not source_parts:
        return {"available": False, "reason": "No readable Amagi concurrency CSV files were found.", "minute": empty, "files": 0, "skipped": skipped}

    amagi = pd.concat(source_parts, ignore_index=True)
    atomic_write_parquet(source_cache_path, amagi)
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
    amagi = categorise_repeated_columns(
        amagi,
        ("platform_name", "channel_raw", "channel_name"),
    )

    # Keep every available Amagi minute in the embedded mart. The dashboard
    # applies its ASRUN event-date filter when rendering delivered-ad context;
    # clipping here would silently discard newer Amagi source data.
    # A repeated export minute is a collector retry; use the latest source row.
    amagi = amagi.drop_duplicates(["minute_ist", "platform_name", "channel_raw"], keep="last")
    minute = (
        amagi.groupby(
            ["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name"],
            as_index=False,
            observed=True,
        )["concurrent_viewers"]
        .sum()
        .sort_values(["minute_ist", "platform_name", "channel_raw"])
    )
    atomic_write_parquet(minute_path, minute)
    manifest = {
        "schema_version": AMAGI_MART_VERSION,
        "available": not minute.empty,
        "source_root": str(AMAGI_ROOT),
        "files": len(readable_files),
        "skipped": skipped,
        "fingerprints": fingerprints,
        "readable_files": sorted(readable_files),
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "available": not minute.empty,
        "reason": "" if not minute.empty else "No Amagi viewer minutes overlap the selected ASRUN dates.",
        "minute": minute,
        "files": len(readable_files),
        "skipped": skipped,
    }


def empty_fct_events() -> pd.DataFrame:
    """Return the stable FCT mart schema used by the dashboard and cache."""
    return pd.DataFrame(
        columns=[
            "event_key",
            "event_ist",
            "log_date",
            "feed_name",
            "brand_name",
            "caption",
            "program_name",
            "program_start_ist",
            "program_duration_seconds",
            "duration_seconds",
            "language",
            "category",
            "company",
            "ad_position",
            "total_ads",
            "event_class",
            "is_filename_spillover",
            "declared_start",
            "declared_end",
            "source_file",
            "source_sheet",
            "source_row",
        ]
    )


def fct_filename_range(path: Path) -> tuple[str, str]:
    """Read declared DDMMYYYY coverage from an FCT workbook filename."""
    match = FCT_FILENAME_RANGE.search(path.stem)
    if not match:
        raise ValueError(
            f"FCT filename does not contain DDMMYYYY to DDMMYYYY coverage: {path.name}"
        )
    start = datetime.strptime(match.group("start"), "%d%m%Y").date().isoformat()
    end = datetime.strptime(match.group("end"), "%d%m%Y").date().isoformat()
    if end < start:
        raise ValueError(f"FCT filename has an end date before its start date: {path.name}")
    return start, end


def fct_internal_range(
    path: Path, sheets: dict[str, pd.DataFrame]
) -> tuple[str, str]:
    """Derive FCT coverage from valid sheets when a filename has no date range."""
    parsed_dates: list[pd.Series] = []
    for raw in sheets.values():
        dates = pd.to_datetime(
            raw["Pdate"].astype("string").str.strip(),
            format="%d/%m/%Y",
            errors="coerce",
        ).dropna()
        if not dates.empty:
            parsed_dates.append(dates)
    if not parsed_dates:
        raise ValueError(
            f"FCT workbook has no valid Pdate values for coverage: {path.name}"
        )
    combined = pd.concat(parsed_dates, ignore_index=True)
    return combined.min().date().isoformat(), combined.max().date().isoformat()


def parse_fct_workbook(path: Path, source_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize one FCT workbook without changing its source-reported IST wall clock."""
    sheets = pd.read_excel(path, sheet_name=None, dtype=object)
    valid_sheets: dict[str, pd.DataFrame] = {}
    ignored_sheets: list[str] = []
    for sheet_name, raw in sheets.items():
        present = FCT_REQUIRED_COLUMNS.intersection(raw.columns)
        missing = sorted(FCT_REQUIRED_COLUMNS.difference(raw.columns))
        if not missing:
            valid_sheets[str(sheet_name)] = raw
            continue
        # Summary tabs often contain only Category or no FCT columns. A near
        # match is more likely a damaged data sheet and must stop publication.
        if len(present) >= len(FCT_REQUIRED_COLUMNS) // 2:
            raise ValueError(
                f"{path.name}/{sheet_name} is missing FCT column(s): "
                + ", ".join(missing)
            )
        ignored_sheets.append(str(sheet_name))
    if not valid_sheets:
        raise ValueError(f"{path.name} contains no sheet with the FCT data schema.")
    try:
        declared_start, declared_end = fct_filename_range(path)
        range_source = "filename"
    except ValueError:
        declared_start, declared_end = fct_internal_range(path, valid_sheets)
        range_source = "Pdate"

    normalized: list[pd.DataFrame] = []
    source_rows = 0
    excluded_rows = 0

    for sheet_name, raw in valid_sheets.items():
        source_rows += len(raw)
        frame = raw.loc[:, sorted(FCT_REQUIRED_COLUMNS)].copy()
        frame["source_row"] = pd.Series(range(2, len(frame) + 2), index=frame.index, dtype="Int64")

        source_date = pd.to_datetime(
            frame["Pdate"].astype("string").str.strip(),
            format="%d/%m/%Y",
            errors="coerce",
        )
        ad_time = frame["Adst"].astype("string").str.strip()
        program_time = frame["Pgst"].astype("string").str.strip()
        frame["event_ist"] = pd.to_datetime(
            source_date.dt.strftime("%Y-%m-%d") + " " + ad_time,
            format="%Y-%m-%d %H:%M:%S",
            errors="coerce",
        )
        frame["program_start_ist"] = pd.to_datetime(
            source_date.dt.strftime("%Y-%m-%d") + " " + program_time,
            format="%Y-%m-%d %H:%M:%S",
            errors="coerce",
        )
        frame["duration_seconds"] = pd.to_numeric(frame["Aaddur"], errors="coerce")
        valid = frame["event_ist"].notna() & frame["duration_seconds"].gt(0)
        excluded_rows += int((~valid).sum())
        frame = frame.loc[valid].copy()
        if frame.empty:
            continue

        text_columns = {
            "Feed Name": "feed_name",
            "Brandname": "brand_name",
            "Caption": "caption",
            "Progname": "program_name",
            "Language": "language",
            "Category": "category",
            "Company": "company",
        }
        for source_column, target_column in text_columns.items():
            frame[target_column] = (
                frame[source_column].fillna("").astype("string").str.strip()
            )
        frame["log_date"] = frame["event_ist"].dt.strftime("%Y-%m-%d")
        frame["program_duration_seconds"] = pd.to_timedelta(
            frame["Pgdur"].astype("string").str.strip(), errors="coerce"
        ).dt.total_seconds()
        frame["ad_position"] = pd.to_numeric(frame["Adpos"], errors="coerce").astype("Int64")
        frame["total_ads"] = pd.to_numeric(frame["TotAds"], errors="coerce").astype("Int64")
        category_key = frame["category"].str.upper()
        frame["event_class"] = "Commercial"
        frame.loc[category_key.isin(FCT_INTERNAL_CATEGORIES), "event_class"] = "Internal / Promo"
        frame.loc[category_key.eq(""), "event_class"] = "Unclassified"
        company_key = (
            frame["company"]
            .str.upper()
            .str.replace(r"[^A-Z0-9]+", " ", regex=True)
            .str.strip()
        )
        # Independent News Service is the India TV organisation in this source.
        # Company ownership takes precedence over ad/promo category so all of its
        # occurrences remain together under the stakeholder's In-House view.
        frame.loc[
            company_key.isin(
                {
                    "INDEPENDENT NEWS SERVICE PVT LTD",
                    "INDEPENDENT NEWS SERVICE PRIVATE LIMITED",
                }
            ),
            "event_class",
        ] = "In-House"
        frame["declared_start"] = declared_start
        frame["declared_end"] = declared_end
        frame["is_filename_spillover"] = ~frame["log_date"].between(
            declared_start, declared_end
        )
        frame["source_file"] = source_name
        frame["source_sheet"] = str(sheet_name)

        # The source has no stable creative identifier. This fingerprint removes
        # exact collector re-exports while retaining legitimate separate airings.
        event_identity = frame[
            [
                "feed_name",
                "event_ist",
                "brand_name",
                "caption",
                "duration_seconds",
                "program_name",
                "category",
            ]
        ].copy()
        event_identity["event_ist"] = event_identity["event_ist"].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        frame["event_key"] = pd.util.hash_pandas_object(
            event_identity.fillna("").astype("string"), index=False
        ).astype("uint64").astype("string")
        normalized.append(frame.loc[:, empty_fct_events().columns])

    events = (
        pd.concat(normalized, ignore_index=True)
        if normalized
        else empty_fct_events()
    )
    metadata = {
        "declared_start": declared_start,
        "declared_end": declared_end,
        "source_rows": int(source_rows),
        "valid_rows": int(len(events)),
        "excluded_rows": int(excluded_rows),
        "range_source": range_source,
        "parsed_sheets": sorted(valid_sheets),
        "ignored_sheets": sorted(ignored_sheets),
    }
    return events, metadata


def fct_result(
    events: pd.DataFrame,
    *,
    files: int,
    source_rows: int,
    excluded_rows: int,
    skipped: list[str],
    declared_start: str,
    declared_end: str,
) -> dict[str, Any]:
    """Build one consistent FCT result for fresh and cache-reused runs."""
    if events.empty:
        true_start = ""
        true_end = ""
    else:
        events = events.copy()
        events["event_ist"] = pd.to_datetime(events["event_ist"], errors="coerce")
        events["program_start_ist"] = pd.to_datetime(
            events["program_start_ist"], errors="coerce"
        )
        events = events[events["event_ist"].notna()].copy()
        true_start = events["event_ist"].min().strftime("%Y-%m-%d %H:%M:%S")
        true_end = events["event_ist"].max().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "available": not events.empty,
        "reason": "" if not events.empty else "No valid FCT ad occurrences were found.",
        "events": events.sort_values(["event_ist", "feed_name"]).reset_index(drop=True),
        "files": int(files),
        "source_rows": int(source_rows),
        "excluded_rows": int(excluded_rows),
        "spillover_rows": int(events["is_filename_spillover"].fillna(False).sum())
        if not events.empty
        else 0,
        "skipped": skipped,
        "true_start": true_start,
        "true_end": true_end,
        "declared_start": declared_start,
        "declared_end": declared_end,
    }


def build_fct_ad_mart() -> dict[str, Any]:
    """Incrementally normalize FCT workbooks into monitored ad occurrences."""
    empty = empty_fct_events()
    if not FCT_ROOT.is_dir():
        return fct_result(
            empty,
            files=0,
            source_rows=0,
            excluded_rows=0,
            skipped=[],
            declared_start="",
            declared_end="",
        ) | {"reason": f"FCT source folder not found: {FCT_ROOT}"}

    paths = sorted(
        path
        for path in FCT_ROOT.rglob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    )
    if not paths:
        return fct_result(
            empty,
            files=0,
            source_rows=0,
            excluded_rows=0,
            skipped=[],
            declared_start="",
            declared_end="",
        ) | {"reason": "No FCT .xlsx workbooks were found."}

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    mart_path = PARSED_DIR / "fct_ad_events.parquet"
    manifest_path = PARSED_DIR / "fct_manifest.json"
    fingerprints = {
        str(path.relative_to(FCT_ROOT)): source_file_fingerprint(path) for path in paths
    }
    old_manifest = read_json_object(manifest_path)

    old_fingerprints = (
        old_manifest.get("fingerprints", {})
        if old_manifest.get("schema_version") == FCT_MART_VERSION
        else {}
    )
    old_file_meta = old_manifest.get("file_metadata", {})
    unchanged = {
        name
        for name, fingerprint in fingerprints.items()
        if old_fingerprints.get(name) == fingerprint
    }
    cached = empty
    if unchanged and mart_path.is_file():
        try:
            cached = pd.read_parquet(mart_path)
            missing_columns = set(empty.columns).difference(cached.columns)
            if missing_columns:
                cached = empty
                unchanged.clear()
            else:
                cached = cached[cached["source_file"].isin(unchanged)].copy()
        except (OSError, ValueError, KeyError):
            cached = empty
            unchanged.clear()

    parsed_frames: list[pd.DataFrame] = []
    file_metadata = {
        name: old_file_meta[name]
        for name in unchanged
        if name in old_file_meta
    }
    failures: list[str] = []
    path_by_name = {str(path.relative_to(FCT_ROOT)): path for path in paths}
    for source_name in sorted(set(path_by_name).difference(unchanged)):
        try:
            frame, metadata = parse_fct_workbook(path_by_name[source_name], source_name)
        except (OSError, ValueError, ImportError) as exc:
            failures.append(f"{source_name}: {exc}")
            continue
        parsed_frames.append(frame)
        file_metadata[source_name] = metadata

    if failures:
        raise ValueError(
            "FCT refresh was stopped to avoid publishing partial workbook data: "
            + "; ".join(failures)
        )

    parts = [frame for frame in [cached, *parsed_frames] if not frame.empty]
    events = pd.concat(parts, ignore_index=True) if parts else empty
    events = (
        events.sort_values(["event_ist", "source_file", "source_row"])
        .drop_duplicates("event_key", keep="last")
        .reset_index(drop=True)
    )
    declared_starts = [
        str(meta.get("declared_start", ""))
        for meta in file_metadata.values()
        if meta.get("declared_start")
    ]
    declared_ends = [
        str(meta.get("declared_end", ""))
        for meta in file_metadata.values()
        if meta.get("declared_end")
    ]
    manifest = {
        "schema_version": FCT_MART_VERSION,
        "source_root": str(FCT_ROOT),
        "fingerprints": fingerprints,
        "file_metadata": file_metadata,
        "generated_at_ist": datetime.now(IST_ZONE).isoformat(),
    }

    atomic_write_parquet(mart_path, events)
    atomic_write_json(manifest_path, manifest)

    return fct_result(
        events,
        files=len(paths),
        source_rows=sum(int(meta.get("source_rows", 0)) for meta in file_metadata.values()),
        excluded_rows=sum(int(meta.get("excluded_rows", 0)) for meta in file_metadata.values()),
        skipped=[],
        declared_start=min(declared_starts) if declared_starts else "",
        declared_end=max(declared_ends) if declared_ends else "",
    )


def empty_nct_segments() -> pd.DataFrame:
    """Return the stable, source-traceable NCT story-segment schema."""
    return pd.DataFrame(
        columns=[
            "segment_key",
            "channel_name",
            "story",
            "sub_story",
            "primary_genre",
            "secondary_genre",
            "program_name",
            "program_start_ist",
            "program_end_ist",
            "clip_start_ist",
            "clip_end_ist",
            "log_date",
            "geography",
            "title",
            "duration_seconds",
            "personality",
            "guest",
            "anchor",
            "reporter",
            "logistics",
            "telecast_format",
            "assist_used",
            "split",
            "story_format",
            "source_file",
            "source_row",
        ]
    )


def read_nct_header(path: Path) -> tuple[int, str, dict[str, Any]]:
    """Locate the CSV header and parse the human-readable NCT selection preamble."""
    raw_prefix = path.read_bytes()[:262_144]
    encoding = "utf-8-sig"
    try:
        prefix = raw_prefix.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp1252"
        prefix = raw_prefix.decode(encoding)
    lines = prefix.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.lstrip("\ufeff").startswith("channel,Story,Sub_Story,")
        ),
        -1,
    )
    if header_index < 0:
        raise ValueError(f"NCT CSV header was not found in {path.name}")

    metadata: dict[str, Any] = {
        "selected_channels": [],
        "declared_start": "",
        "declared_end": "",
        "declared_start_time": "",
        "declared_end_time": "",
        "downloaded_on": "",
    }
    for raw_line in lines[:header_index]:
        # Some NCT exports serialize preamble rows to the full CSV width,
        # leaving dozens of empty trailing fields after the visible value.
        # Parse the row structurally so those delimiters never become date text.
        fields = [field.strip() for field in next(csv.reader([raw_line]))]
        line = ",".join(field for field in fields if field)
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key == "channels":
            metadata["selected_channels"] = [
                channel.strip() for channel in value.split(",") if channel.strip()
            ]
        elif key in {"from date", "to date"}:
            try:
                parsed = datetime.strptime(value, "%d/%m/%Y").date().isoformat()
            except ValueError as exc:
                raise ValueError(
                    f"Invalid NCT {key} in {path.name}: {value!r}"
                ) from exc
            metadata["declared_start" if key == "from date" else "declared_end"] = parsed
        elif key == "start time":
            metadata["declared_start_time"] = value
        elif key == "end time":
            metadata["declared_end_time"] = value
        elif key == "downloaded on":
            metadata["downloaded_on"] = value
    return header_index, encoding, metadata


def parse_nct_csv(path: Path, source_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize one NCT story-duration export and preserve its reported IST clock."""
    header_index, encoding, metadata = read_nct_header(path)
    raw = pd.read_csv(
        path,
        skiprows=header_index,
        encoding=encoding,
        dtype=object,
        low_memory=False,
    )
    raw.columns = [str(column).strip() for column in raw.columns]
    missing = sorted(NCT_REQUIRED_COLUMNS.difference(raw.columns))
    if missing:
        raise ValueError(
            f"{path.name} is missing NCT column(s): {', '.join(missing)}"
        )
    source_rows = len(raw)
    frame = raw.loc[:, sorted(NCT_REQUIRED_COLUMNS)].copy()
    frame["source_row"] = pd.Series(
        range(header_index + 2, header_index + 2 + len(frame)),
        index=frame.index,
        dtype="Int64",
    )

    date_values = frame["pgm_date"].astype("string").str.strip()
    source_date = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    # NCT exports have used both slash/four-digit-year and dash/two-digit-year
    # formats. Parse only those documented layouts so ambiguous dates never pass.
    for date_format in ("%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y"):
        missing_dates = source_date.isna()
        if not missing_dates.any():
            break
        source_date.loc[missing_dates] = pd.to_datetime(
            date_values.loc[missing_dates],
            format=date_format,
            errors="coerce",
        )

    def combine_time(column: str) -> pd.Series:
        values = (
            frame[column]
            .astype("string")
            .str.strip()
            .str.replace(".", ":", regex=False)
        )
        clock = values.str.extract(
            r"^(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})$"
        ).apply(pd.to_numeric, errors="coerce")
        valid_clock = (
            clock["hour"].between(0, 23)
            & clock["minute"].between(0, 59)
            & clock["second"].between(0, 59)
        )
        seconds = (
            clock["hour"] * 3600 + clock["minute"] * 60 + clock["second"]
        ).where(valid_clock)
        # Adding a validated offset preserves the source-reported IST clock and
        # avoids host-timezone interpretation by pandas.
        return source_date + pd.to_timedelta(seconds, unit="s")

    frame["program_start_ist"] = combine_time("Pgm_Start_Time")
    frame["program_end_ist"] = combine_time("Pgm_End_Time")
    frame["clip_start_ist"] = combine_time("clip_start_time")
    frame["clip_end_ist"] = combine_time("clip_end_time")
    for start_column, end_column in [
        ("program_start_ist", "program_end_ist"),
        ("clip_start_ist", "clip_end_ist"),
    ]:
        crosses_midnight = (
            frame[start_column].notna()
            & frame[end_column].notna()
            & frame[end_column].lt(frame[start_column])
        )
        frame.loc[crosses_midnight, end_column] += pd.Timedelta(days=1)

    frame["duration_seconds"] = pd.to_numeric(
        frame["duration_seconds"], errors="coerce"
    )
    duration_values = (
        frame["duration"]
        .astype("string")
        .str.strip()
        .str.replace(".", ":", regex=False)
    )
    duration_parts = duration_values.str.extract(
        r"^(?P<hour>\d+):(?P<minute>\d{2}):(?P<second>\d{2})$"
    ).apply(pd.to_numeric, errors="coerce")
    valid_duration = (
        duration_parts["hour"].ge(0)
        & duration_parts["minute"].between(0, 59)
        & duration_parts["second"].between(0, 59)
    )
    duration_text_seconds = (
        duration_parts["hour"] * 3600
        + duration_parts["minute"] * 60
        + duration_parts["second"]
    ).where(valid_duration)
    invalid_critical = (
        source_date.isna()
        | frame["program_start_ist"].isna()
        | frame["program_end_ist"].isna()
        | frame["clip_start_ist"].isna()
        | frame["clip_end_ist"].isna()
        | frame["duration_seconds"].isna()
        | duration_text_seconds.isna()
        | frame["duration_seconds"].lt(0)
    )
    if invalid_critical.any():
        bad_rows = frame.loc[invalid_critical, "source_row"].head(10).tolist()
        raise ValueError(
            f"{path.name} has {int(invalid_critical.sum()):,} invalid NCT row(s); "
            f"first source rows: {bad_rows}"
        )

    clip_duration = (
        frame["clip_end_ist"] - frame["clip_start_ist"]
    ).dt.total_seconds()
    duration_mismatch = clip_duration.sub(frame["duration_seconds"]).abs().gt(1)
    duration_mismatch |= duration_text_seconds.sub(
        frame["duration_seconds"]
    ).abs().gt(1)
    if duration_mismatch.any():
        bad_rows = frame.loc[duration_mismatch, "source_row"].head(10).tolist()
        raise ValueError(
            f"{path.name} has {int(duration_mismatch.sum()):,} NCT duration "
            f"mismatch(es) over one second; first source rows: {bad_rows}"
        )

    text_columns = {
        "channel": "channel_name",
        "Story": "story",
        "Sub_Story": "sub_story",
        "story_genre_1": "primary_genre",
        "story_genre_2": "secondary_genre",
        "pgm_name": "program_name",
        "geography": "geography",
        "title": "title",
        "personality": "personality",
        "guest": "guest",
        "anchor": "anchor",
        "reporter": "reporter",
        "logistics": "logistics",
        "telecast_format": "telecast_format",
        "assist_used": "assist_used",
        "split": "split",
        "Story_Format": "story_format",
    }
    for source_column, target_column in text_columns.items():
        values = frame[source_column].fillna("").astype("string").str.strip()
        frame[target_column] = values.mask(values.isin({"", "."}), pd.NA)
    if frame["channel_name"].isna().any():
        raise ValueError(f"{path.name} contains blank NCT channel values")

    frame["log_date"] = source_date.dt.strftime("%Y-%m-%d")
    frame["source_file"] = source_name
    identity = frame[
        [
            "channel_name",
            "story",
            "sub_story",
            "log_date",
            "clip_start_ist",
            "clip_end_ist",
            "program_name",
        ]
    ].copy()
    for column in ["clip_start_ist", "clip_end_ist"]:
        identity[column] = identity[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    frame["segment_key"] = (
        pd.util.hash_pandas_object(
            identity.fillna("").astype("string"), index=False
        )
        .astype("uint64")
        .astype("string")
    )
    segments = frame.loc[:, empty_nct_segments().columns].copy()
    duplicate_rows = int(segments.duplicated("segment_key", keep="last").sum())
    segments = segments.drop_duplicates("segment_key", keep="last").reset_index(drop=True)
    actual_channels = sorted(
        segments["channel_name"].dropna().astype(str).unique().tolist()
    )
    selected_channels = metadata["selected_channels"]
    metadata.update(
        {
            "source_rows": int(source_rows),
            "valid_rows": int(len(segments)),
            "duplicate_rows": duplicate_rows,
            "actual_channels": actual_channels,
            "missing_selected_channels": missing_channel_labels(
                selected_channels,
                actual_channels,
            ),
        }
    )
    return segments, metadata


def missing_channel_labels(
    selected_channels: list[str],
    actual_channels: list[str] | set[str],
) -> list[str]:
    """Return genuinely absent channels without treating display-case drift as missing."""
    actual_keys = {
        str(channel).strip().casefold()
        for channel in actual_channels
        if str(channel).strip()
    }
    return sorted(
        {
            str(channel).strip()
            for channel in selected_channels
            if str(channel).strip()
            and str(channel).strip().casefold() not in actual_keys
        }
    )


def nct_result(
    segments: pd.DataFrame,
    *,
    files: int,
    source_rows: int,
    duplicate_rows: int,
    selected_channels: list[str],
    missing_selected_channels: list[str],
    declared_start: str,
    declared_end: str,
) -> dict[str, Any]:
    """Build one stable NCT result for fresh and cache-reused runs."""
    if segments.empty:
        true_start = ""
        true_end = ""
        channels: list[str] = []
    else:
        segments = segments.copy()
        for column in [
            "program_start_ist",
            "program_end_ist",
            "clip_start_ist",
            "clip_end_ist",
        ]:
            segments[column] = pd.to_datetime(segments[column], errors="coerce")
        segments = segments[
            segments["clip_start_ist"].notna() & segments["clip_end_ist"].notna()
        ].copy()
        true_start = segments["clip_start_ist"].min().strftime("%Y-%m-%d %H:%M:%S")
        true_end = segments["clip_end_ist"].max().strftime("%Y-%m-%d %H:%M:%S")
        channels = sorted(
            segments["channel_name"].dropna().astype(str).unique().tolist()
        )
    return {
        "available": not segments.empty,
        "reason": "" if not segments.empty else "No valid NCT story segments were found.",
        "segments": segments.sort_values(
            ["clip_start_ist", "channel_name", "source_row"]
        ).reset_index(drop=True),
        "files": int(files),
        "source_rows": int(source_rows),
        "duplicate_rows": int(duplicate_rows),
        "true_start": true_start,
        "true_end": true_end,
        "declared_start": declared_start,
        "declared_end": declared_end,
        "channels": channels,
        "selected_channels": sorted(set(selected_channels)),
        "missing_selected_channels": sorted(set(missing_selected_channels)),
        "source_timezone": "Asia/Kolkata",
    }


def build_nct_story_mart() -> dict[str, Any]:
    """Incrementally normalize NCT story exports into one validated segment mart."""
    empty = empty_nct_segments()
    if not NCT_ROOT.is_dir():
        return nct_result(
            empty,
            files=0,
            source_rows=0,
            duplicate_rows=0,
            selected_channels=[],
            missing_selected_channels=[],
            declared_start="",
            declared_end="",
        ) | {"reason": f"NCT source folder not found: {NCT_ROOT}"}

    paths = sorted(
        path
        for path in NCT_ROOT.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".csv"
    )
    if not paths:
        return nct_result(
            empty,
            files=0,
            source_rows=0,
            duplicate_rows=0,
            selected_channels=[],
            missing_selected_channels=[],
            declared_start="",
            declared_end="",
        ) | {"reason": "No NCT .csv exports were found."}

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    mart_path = PARSED_DIR / "nct_story_segments.parquet"
    manifest_path = PARSED_DIR / "nct_manifest.json"
    fingerprints = {
        str(path.relative_to(NCT_ROOT)): source_file_fingerprint(path) for path in paths
    }
    old_manifest = read_json_object(manifest_path)
    old_fingerprints = (
        old_manifest.get("fingerprints", {})
        if old_manifest.get("schema_version") == NCT_MART_VERSION
        else {}
    )
    old_file_meta = old_manifest.get("file_metadata", {})
    unchanged = {
        name
        for name, fingerprint in fingerprints.items()
        if old_fingerprints.get(name) == fingerprint
    }
    cached = empty
    if unchanged and mart_path.is_file():
        try:
            cached = pd.read_parquet(mart_path)
            if set(empty.columns).difference(cached.columns):
                cached = empty
                unchanged.clear()
            else:
                cached = cached[cached["source_file"].isin(unchanged)].copy()
        except (OSError, ValueError, KeyError):
            cached = empty
            unchanged.clear()

    path_by_name = {str(path.relative_to(NCT_ROOT)): path for path in paths}
    parsed_frames: list[pd.DataFrame] = []
    file_metadata = {
        name: old_file_meta[name] for name in unchanged if name in old_file_meta
    }
    failures: list[str] = []
    for source_name in sorted(set(path_by_name).difference(unchanged)):
        try:
            frame, metadata = parse_nct_csv(path_by_name[source_name], source_name)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            failures.append(f"{source_name}: {exc}")
            continue
        parsed_frames.append(frame)
        file_metadata[source_name] = metadata
    if failures:
        raise ValueError(
            "NCT refresh was stopped to avoid publishing partial story data: "
            + "; ".join(failures)
        )

    parts = [frame for frame in [cached, *parsed_frames] if not frame.empty]
    segments = pd.concat(parts, ignore_index=True) if parts else empty
    duplicate_rows = int(segments.duplicated("segment_key", keep="last").sum())
    segments = (
        segments.sort_values(["clip_start_ist", "source_file", "source_row"])
        .drop_duplicates("segment_key", keep="last")
        .reset_index(drop=True)
    )
    selected_channels = sorted(
        {
            str(channel)
            for metadata in file_metadata.values()
            for channel in metadata.get("selected_channels", [])
        }
    )
    actual_channels = set(
        segments["channel_name"].dropna().astype(str).unique().tolist()
    )
    declared_starts = [
        str(metadata["declared_start"])
        for metadata in file_metadata.values()
        if metadata.get("declared_start")
    ]
    declared_ends = [
        str(metadata["declared_end"])
        for metadata in file_metadata.values()
        if metadata.get("declared_end")
    ]
    manifest = {
        "schema_version": NCT_MART_VERSION,
        "source_root": str(NCT_ROOT),
        "fingerprints": fingerprints,
        "file_metadata": file_metadata,
        "generated_at_ist": datetime.now(IST_ZONE).isoformat(),
    }
    atomic_write_parquet(mart_path, segments)
    atomic_write_json(manifest_path, manifest)

    return nct_result(
        segments,
        files=len(paths),
        source_rows=sum(
            int(metadata.get("source_rows", 0))
            for metadata in file_metadata.values()
        ),
        duplicate_rows=duplicate_rows
        + sum(
            int(metadata.get("duplicate_rows", 0))
            for metadata in file_metadata.values()
        ),
        selected_channels=selected_channels,
        missing_selected_channels=missing_channel_labels(
            selected_channels,
            actual_channels,
        ),
        declared_start=min(declared_starts) if declared_starts else "",
        declared_end=max(declared_ends) if declared_ends else "",
    )



def youtube_channel_from_path(parquet_path: Path) -> tuple[str, str]:
    """Return the stable collector key and stakeholder-facing channel name."""
    match = YOUTUBE_FILENAME.match(parquet_path.name)
    if match is None:
        return "unknown", "Unknown / NA"
    key = match.group("collector").strip()
    label = YOUTUBE_CHANNEL_LABELS.get(key.casefold())
    if label is None:
        # Preserve an unseen collector instead of silently attributing it to India TV.
        label = re.sub(r"[_-]+", " ", key).strip() or "Unknown / NA"
    return key, label


def build_youtube_marts() -> dict[str, Any]:
    """Build compact, reusable YouTube concurrency marts for the ASRUN demo."""
    empty_minute = pd.DataFrame(
        columns=[
            "timestamp_ist",
            "log_date",
            "total_concurrent_viewers",
            "live_channels",
            "live_videos",
            "peak_video_concurrent",
        ]
    )
    empty_video_daily = pd.DataFrame(
        columns=[
            "log_date",
            "youtube_channel",
            "video_id",
            "title",
            "peak_concurrent_viewers",
            "avg_concurrent_viewers",
            "viewer_minutes",
            "live_minutes",
        ]
    )
    empty_video_5min = pd.DataFrame(
        columns=[
            "bucket_ist",
            "log_date",
            "youtube_channel",
            "video_id",
            "avg_concurrent_viewers",
            "peak_concurrent_viewers",
        ]
    )
    empty_video_minute = pd.DataFrame(
        columns=[
            "timestamp_ist",
            "log_date",
            "youtube_channel",
            "video_id",
            "title",
            "concurrent_viewers",
        ]
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
            "channels": [],
            "true_start": "",
            "true_end": "",
            "full_start": "",
            "full_end": "",
        }

    completed_files = sorted(YOUTUBE_ROOT.rglob("*.parquet"))
    partial_files = list(YOUTUBE_ROOT.rglob("*.partial"))
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = PARSED_DIR / "youtube_manifest.json"
    source_cache_path = PARSED_DIR / "youtube_source_rows.parquet"
    mart_paths = {
        "minute": PARSED_DIR / "youtube_minute_total.parquet",
        "video_daily": PARSED_DIR / "youtube_video_daily.parquet",
        "video_5min": PARSED_DIR / "youtube_video_5min.parquet",
        "video_minute": PARSED_DIR / "youtube_video_minute.parquet",
    }
    path_by_name = {
        str(path.relative_to(YOUTUBE_ROOT)): path for path in completed_files
    }
    fingerprints = {
        name: source_file_fingerprint(path) for name, path in path_by_name.items()
    }
    old_manifest = read_json_object(manifest_path)

    old_fingerprints = (
        old_manifest.get("fingerprints", {})
        if old_manifest.get("schema_version") == YOUTUBE_MART_VERSION
        else {}
    )
    exact_cache_hit = (
        fingerprints == old_fingerprints
        and all(path.is_file() for path in mart_paths.values())
        and bool(old_manifest.get("available"))
    )
    if exact_cache_hit:
        try:
            cached_marts = {
                name: pd.read_parquet(path) for name, path in mart_paths.items()
            }
        except (OSError, ValueError, KeyError):
            exact_cache_hit = False
        else:
            LOGGER.info(
                "YouTube mart cache hit: %d unchanged file(s)",
                len(completed_files),
            )
            return {
                "available": True,
                "reason": "",
                "completed_files": len(completed_files),
                "partial_files": len(partial_files),
                "skipped_files": old_manifest.get("skipped_files", []),
                **cached_marts,
                "channels": old_manifest.get("channels", []),
                "true_start": old_manifest.get("true_start", ""),
                "true_end": old_manifest.get("true_end", ""),
                "full_start": old_manifest.get("full_start", ""),
                "full_end": old_manifest.get("full_end", ""),
            }

    unchanged = {
        name
        for name, fingerprint in fingerprints.items()
        if old_fingerprints.get(name) == fingerprint
        and name in set(old_manifest.get("readable_files", []))
    }
    cached_source = pd.DataFrame()
    if unchanged and source_cache_path.is_file():
        try:
            cached_source = pd.read_parquet(source_cache_path)
            required_cache_columns = {
                *YOUTUBE_COLUMNS,
                "youtube_collector_key",
                "youtube_channel",
                "source_file",
            }
            if required_cache_columns.difference(cached_source.columns):
                cached_source = pd.DataFrame()
                unchanged.clear()
            else:
                cached_source = cached_source[
                    cached_source["source_file"].isin(unchanged)
                ].copy()
        except (OSError, ValueError, KeyError):
            cached_source = pd.DataFrame()
            unchanged.clear()

    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    readable_files = set(unchanged)
    for source_name in sorted(set(path_by_name).difference(unchanged)):
        parquet_path = path_by_name[source_name]
        try:
            frame = pd.read_parquet(parquet_path, columns=YOUTUBE_COLUMNS)
        except (OSError, ValueError, KeyError) as exc:
            skipped.append(f"{source_name}: {exc}")
            continue
        collector_key, youtube_channel = youtube_channel_from_path(parquet_path)
        frame["youtube_collector_key"] = collector_key
        frame["youtube_channel"] = youtube_channel
        frame["source_file"] = source_name
        frames.append(frame)
        readable_files.add(source_name)
    LOGGER.info(
        "YouTube incremental refresh: %d cached, %d parsed, %d skipped",
        len(unchanged),
        len(frames),
        len(skipped),
    )

    source_parts = [
        frame for frame in [cached_source, *frames] if not frame.empty
    ]
    if not source_parts:
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
            "channels": [],
            "true_start": "",
            "true_end": "",
            "full_start": "",
            "full_end": "",
        }

    youtube = pd.concat(source_parts, ignore_index=True)
    atomic_write_parquet(source_cache_path, youtube)
    youtube["timestamp_ist"] = pd.to_datetime(
        youtube["date"].astype("string") + " " + youtube["time"].astype("string"),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    ).dt.floor("min")
    youtube["youtube_collector_key"] = (
        youtube["youtube_collector_key"].fillna("unknown").astype("string").str.strip()
    )
    youtube["youtube_channel"] = (
        youtube["youtube_channel"].fillna("Unknown / NA").astype("string").str.strip()
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
    # Collectors begin at different seconds; minute-normalization above aligns
    # simultaneous channel observations before aggregation.
    youtube = youtube.sort_values("timestamp_ist").drop_duplicates(
        ["timestamp_ist", "youtube_collector_key", "video_id"], keep="last"
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
            "channels": [],
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
            live_channels=("youtube_channel", "nunique"),
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
        .drop_duplicates(["log_date", "youtube_channel", "video_id"], keep="last")
        [["log_date", "youtube_channel", "video_id", "title"]]
    )
    video_minute = (
        live[
            [
                "timestamp_ist",
                "log_date",
                "youtube_channel",
                "video_id",
                "concurrent_viewers",
            ]
        ]
        .merge(
            title_daily,
            on=["log_date", "youtube_channel", "video_id"],
            how="left",
            validate="many_to_one",
        )
        .sort_values(["timestamp_ist", "youtube_channel", "video_id"])
    )
    video_daily = (
        live.groupby(["log_date", "youtube_channel", "video_id"], as_index=False)
        .agg(
            peak_concurrent_viewers=("concurrent_viewers", "max"),
            avg_concurrent_viewers=("concurrent_viewers", "mean"),
            viewer_minutes=("concurrent_viewers", "sum"),
            live_minutes=("timestamp_ist", "size"),
        )
        .merge(
            title_daily,
            on=["log_date", "youtube_channel", "video_id"],
            how="left",
            validate="one_to_one",
        )
        .sort_values(
            ["log_date", "peak_concurrent_viewers", "youtube_channel"],
            ascending=[True, False, True],
        )
    )
    video_5min = live.assign(bucket_ist=live["timestamp_ist"].dt.floor("5min"))
    video_5min = (
        video_5min.groupby(
            ["bucket_ist", "log_date", "youtube_channel", "video_id"],
            as_index=False,
        )
        .agg(
            avg_concurrent_viewers=("concurrent_viewers", "mean"),
            peak_concurrent_viewers=("concurrent_viewers", "max"),
        )
        .merge(
            title_daily,
            on=["log_date", "youtube_channel", "video_id"],
            how="left",
            validate="many_to_one",
        )
        .sort_values(["bucket_ist", "youtube_channel", "video_id"])
    )

    atomic_write_parquet(mart_paths["minute"], minute)
    atomic_write_parquet(mart_paths["video_daily"], video_daily)
    atomic_write_parquet(mart_paths["video_5min"], video_5min)
    atomic_write_parquet(mart_paths["video_minute"], video_minute)
    full_day_counts = minute.groupby("log_date")["timestamp_ist"].nunique()
    full_days = full_day_counts[full_day_counts.eq(1440)].index.tolist()
    manifest = {
        "schema_version": YOUTUBE_MART_VERSION,
        "available": True,
        "source_root": str(YOUTUBE_ROOT),
        "completed_files": len(completed_files),
        "partial_files": len(partial_files),
        "skipped_files": skipped,
        "fingerprints": fingerprints,
        "readable_files": sorted(readable_files),
        "channels": sorted(live["youtube_channel"].dropna().unique().tolist()),
        "true_start": minute["timestamp_ist"].min().strftime("%Y-%m-%d %H:%M:%S"),
        "true_end": minute["timestamp_ist"].max().strftime("%Y-%m-%d %H:%M:%S"),
        "full_start": min(full_days) if full_days else "",
        "full_end": max(full_days) if full_days else "",
    }
    atomic_write_json(manifest_path, manifest)
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
        "channels": manifest["channels"],
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


def distinct_iso_dates(frame: pd.DataFrame, column: str) -> list[str]:
    """Return sorted calendar dates represented by valid source rows."""
    if frame.empty or column not in frame.columns:
        return []
    values = pd.to_datetime(frame[column], errors="coerce")
    return sorted(values.dropna().dt.strftime("%Y-%m-%d").unique().tolist())


def fixed_five_minute_sum(
    frame: pd.DataFrame,
    *,
    time_column: str,
    group_columns: list[str],
    value_column: str,
) -> pd.DataFrame:
    """Collapse minute rows into fixed five-minute sums without losing filter dimensions."""
    if frame.empty:
        return frame.loc[:, [*group_columns, time_column, value_column]].copy()
    compact = frame.loc[:, [*group_columns, time_column, value_column]].copy()
    compact[time_column] = pd.to_datetime(compact[time_column], errors="coerce").dt.floor(
        "5min"
    )
    compact[value_column] = pd.to_numeric(compact[value_column], errors="coerce")
    compact = compact[
        compact[time_column].notna() & compact[value_column].notna()
    ].copy()
    return (
        compact.groupby(
            [*group_columns, time_column],
            as_index=False,
            dropna=False,
            sort=False,
        )[value_column]
        .sum()
        .sort_values([time_column, *group_columns])
        .reset_index(drop=True)
    )


def build_payload(
    events: pd.DataFrame,
    viewer_minute: pd.DataFrame,
    youtube: dict[str, Any],
    amagi: dict[str, Any],
    fct: dict[str, Any] | None = None,
    nct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the complete dashboard payload before it is split into sidecars."""
    if fct is None:
        fct = fct_result(
            empty_fct_events(),
            files=0,
            source_rows=0,
            excluded_rows=0,
            skipped=[],
            declared_start="",
            declared_end="",
        )
    if nct is None:
        nct = nct_result(
            empty_nct_segments(),
            files=0,
            source_rows=0,
            duplicate_rows=0,
            selected_channels=[],
            missing_selected_channels=[],
            declared_start="",
            declared_end="",
        )
    # The UI always uses fixed HH:00-04 / HH:05-09 five-minute sums. Keeping
    # filter dimensions while collapsing minute rows preserves every displayed
    # value and removes most repeated JSON records from the static dashboard.
    viewer_payload = fixed_five_minute_sum(
        viewer_minute,
        time_column="minute_ist",
        group_columns=[
            "log_date",
            "source",
            "platform_name",
            "channel_name",
        ],
        value_column="distinct_cliips",
    )
    amagi_payload = fixed_five_minute_sum(
        amagi["minute"],
        time_column="minute_ist",
        group_columns=[
            "log_date",
            "platform_name",
            "channel_raw",
            "channel_name",
        ],
        value_column="concurrent_viewers",
    )
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
        # Compact date indexes let the browser identify internal calendar gaps
        # without repeatedly scanning the large event/minute payloads.
        "date_coverage": {
            "asrun": distinct_iso_dates(ads, "on_air_start_ist"),
            "fast": distinct_iso_dates(
                viewer_payload.loc[viewer_payload["source"].eq("fast")], "log_date"
            ),
            "stream": distinct_iso_dates(
                viewer_payload.loc[viewer_payload["source"].eq("stream")], "log_date"
            ),
            "amagi": distinct_iso_dates(amagi_payload, "log_date"),
            "fct": distinct_iso_dates(fct["events"], "log_date"),
            "youtube": distinct_iso_dates(youtube["minute"], "log_date"),
            "nct": distinct_iso_dates(nct["segments"], "log_date"),
        },
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
            viewer_payload,
            ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"],
        ),
        "amagi": {
            "available": bool(amagi["available"]),
            "reason": amagi["reason"],
            "files": amagi["files"],
            "skipped": amagi.get("skipped", []),
            "minute": records(amagi_payload, ["minute_ist", "log_date", "platform_name", "channel_raw", "channel_name", "concurrent_viewers"]),
        },
        "fct": {
            "available": bool(fct["available"]),
            "reason": fct["reason"],
            "files": fct["files"],
            "source_rows": fct["source_rows"],
            "excluded_rows": fct["excluded_rows"],
            "spillover_rows": fct["spillover_rows"],
            "skipped": fct.get("skipped", []),
            "true_start": fct["true_start"],
            "true_end": fct["true_end"],
            "declared_start": fct["declared_start"],
            "declared_end": fct["declared_end"],
            "events": records(
                fct["events"],
                [
                    "event_ist",
                    "log_date",
                    "feed_name",
                    "brand_name",
                    "caption",
                    "program_name",
                    "program_start_ist",
                    "program_duration_seconds",
                    "duration_seconds",
                    "language",
                    "category",
                    "company",
                    "ad_position",
                    "total_ads",
                    "event_class",
                    "is_filename_spillover",
                    "declared_start",
                    "declared_end",
                    "source_file",
                    "source_sheet",
                    "source_row",
                ],
            ),
        },
        # Segment-level NCT rows live in a lazy-loaded sidecar. Keeping only
        # scope metadata here avoids inflating the already large core payload.
        "nct": {
            "available": bool(nct["available"]),
            "reason": nct["reason"],
            "files": nct["files"],
            "source_rows": nct["source_rows"],
            "duplicate_rows": nct["duplicate_rows"],
            "true_start": nct["true_start"],
            "true_end": nct["true_end"],
            "declared_start": nct["declared_start"],
            "declared_end": nct["declared_end"],
            "channels": nct["channels"],
            "selected_channels": nct["selected_channels"],
            "missing_selected_channels": nct["missing_selected_channels"],
            "source_timezone": nct["source_timezone"],
            "sidecar": "nct_story_data.js",
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
            "channels": youtube.get("channels", []),
            "minute": records(
                youtube["minute"],
                [
                    "timestamp_ist",
                    "log_date",
                    "total_concurrent_viewers",
                    "live_channels",
                    "live_videos",
                    "peak_video_concurrent",
                ],
            ),
            "video_daily": records(
                youtube["video_daily"],
                [
                    "log_date",
                    "youtube_channel",
                    "video_id",
                    "title",
                    "peak_concurrent_viewers",
                    "avg_concurrent_viewers",
                    "viewer_minutes",
                    "live_minutes",
                ],
            ),
            "video_5min": records(
                youtube["video_5min"],
                [
                    "bucket_ist",
                    "log_date",
                    "youtube_channel",
                    "video_id",
                    "title",
                    "avg_concurrent_viewers",
                    "peak_concurrent_viewers",
                ],
            ),
            "video_minute": records(
                youtube["video_minute"],
                # Titles repeat per minute; resolve them from video_daily in browser instead.
                [
                    "timestamp_ist",
                    "log_date",
                    "youtube_channel",
                    "video_id",
                    "concurrent_viewers",
                ],
            ),
        },
    }


def write_payload_script(path: Path, payload: dict[str, Any]) -> None:
    """Atomically publish compact dashboard data as a local JavaScript sidecar."""
    write_javascript_assignment(path, "window.__ASRUN_DATA__", payload)


def write_javascript_assignment(path: Path, target: str, value: Any) -> None:
    """Atomically publish one JSON-safe value as a JavaScript global assignment."""
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    atomic_write_text(path, f"{target}={encoded};")


def split_dashboard_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move large source arrays out of the startup payload without changing their data."""
    core = payload.copy()
    chunks: dict[str, Any] = {
        "viewer": payload["viewer_minute"],
        "amagi": payload["amagi"]["minute"],
        "fct": payload["fct"]["events"],
        "youtube": {
            key: payload["youtube"][key] for key in YOUTUBE_PAYLOAD_ARRAYS
        },
    }

    core["viewer_minute"] = []
    core["amagi"] = payload["amagi"].copy()
    core["amagi"]["minute"] = []
    core["fct"] = payload["fct"].copy()
    core["fct"]["events"] = []
    core["youtube"] = payload["youtube"].copy()
    for key in YOUTUBE_PAYLOAD_ARRAYS:
        core["youtube"][key] = []
    core["sidecars"] = {
        name: dict(config) for name, config in DASHBOARD_SIDECARS.items()
    }
    return core, chunks


def write_dashboard_sidecars(chunks: dict[str, Any]) -> dict[str, Path]:
    """Publish source-specific payloads so the browser can load them independently."""
    paths: dict[str, Path] = {}
    for name, config in DASHBOARD_SIDECARS.items():
        path = OUTPUT_DIR / config["file"]
        write_javascript_assignment(
            path,
            f"window.{config['global']}",
            chunks[name],
        )
        paths[name] = path
    return paths


def write_nct_payload_script(path: Path, nct: dict[str, Any]) -> None:
    """Publish a lightweight NCT manifest plus independently loadable daily rows."""
    segment_columns = [
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
    segments = nct["segments"]
    partitions: dict[str, str] = {}
    if not segments.empty:
        for log_date, daily in segments.groupby("log_date", sort=True, dropna=False):
            date_value = str(log_date).strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                raise ValueError(f"NCT segment has an invalid log_date: {date_value!r}")
            relative_path = NCT_PARTITION_DIR / f"{date_value}.js"
            chunk_path = path.parent / relative_path
            rows = records(daily, segment_columns)
            encoded = json.dumps(
                rows,
                ensure_ascii=True,
                separators=(",", ":"),
            ).replace("</", "<\\/")
            atomic_write_text(
                chunk_path,
                "window.__NCT_STORY_PARTITIONS__="
                "window.__NCT_STORY_PARTITIONS__||{};"
                f"window.__NCT_STORY_PARTITIONS__[{json.dumps(date_value)}]={encoded};",
            )
            partitions[date_value] = relative_path.as_posix()

    payload = {
        "available": bool(nct["available"]),
        "reason": nct["reason"],
        "partitioned": True,
        "segment_count": int(len(segments)),
        "dates": partitions,
        # Retain this key so older dashboard code degrades to an empty dataset
        # instead of failing if the manifest and HTML are briefly out of sync.
        "segments": [],
    }
    write_javascript_assignment(path, "window.__NCT_STORY_DATA__", payload)


def render_dashboard(payload: dict[str, Any]) -> str:
    """Render the lightweight ASRUN shell that loads its generated data sidecar."""
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
  --spot: #1565c0;
  --lband: #15803d;
  --fast: #6d28d9;
  --stream: #be185d;
  --combined: #ca8a04;
  --ui-font: "Segoe UI Variable Text", "Segoe UI", Arial, sans-serif;
  --display-font: "Segoe UI Variable Display", "Segoe UI", Arial, sans-serif;
}
* { box-sizing: border-box; }
html { scrollbar-gutter: stable; }
html, body { max-width: 100%; overflow-x: hidden; }
body { margin: 0; background: var(--canvas); color: var(--ink); font-family: var(--ui-font); font-size: 14px; line-height: 1.4; letter-spacing: 0; }
.wrap { width: 100%; margin: 0; padding: 0; }
.topbar { background: #ffffff; border-bottom: 1px solid var(--line); }
.topbar-inner { min-height: 52px; display: flex; align-items: center; gap: 16px; }
.title-group { display: flex; flex: 1 1 420px; align-items: baseline; gap: 9px; min-width: 0; }
.title-group h1 { margin: 0; font-family: var(--display-font); font-size: 18px; white-space: nowrap; }
.source-label, .meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-label { color: var(--muted); font-size: 12px; }
.meta { display: flex; flex: 0 1 auto; justify-content: flex-end; gap: 14px; color: var(--muted); font-size: 11px; }
h2, h3 { font-family: var(--display-font); }
h2 { margin: 0; font-size: 17px; }
p { margin: 0; color: var(--muted); }
.filter-shell { position: sticky; top: 0; z-index: 30; min-height: 40px; background: #eef3f8; border-bottom: 1px solid #cbd5e1; box-shadow: 0 3px 8px rgba(22, 36, 49, .08); }
.filters {
  display: flex;
  flex-wrap: wrap;
  min-height: 40px;
  gap: 5px;
  align-items: center;
  padding: 5px 4px;
}
.date-mode-group {
  display: grid;
  flex: 0 1 300px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 3px;
  min-width: 230px;
}
.date-mode-group button {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #93b4df;
  background: #f8fbff;
  color: #1557a8;
  text-overflow: ellipsis;
  transition: border-color .15s ease, background-color .15s ease, color .15s ease;
}
.date-mode-group button:hover {
  border-color: #2563eb;
  background: #dbeafe;
  color: #123d73;
}
.date-mode-group button.active {
  border-color: #1d4ed8;
  background: #2563eb;
  color: #ffffff;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .12);
}
.period-field[hidden] { display: none; }
.filters .period-field { flex: 0 1 190px; min-width: 150px; }
.filter-label { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--muted); font-size: 11px; line-height: 1; white-space: nowrap; }
.filter-label input, .filter-label select { flex: 1 1 auto; min-width: 0; }
input, select { width: 100%; height: 30px; border: 1px solid #aebdca; border-radius: 4px; padding: 4px 7px; background: #ffffff; color: var(--ink); font-family: inherit; font-size: 12px; letter-spacing: 0; }
button { height: 30px; border: 0; border-radius: 4px; padding: 0 11px; background: var(--blue); color: #ffffff; cursor: pointer; font-family: var(--display-font); font-size: 12px; letter-spacing: 0; white-space: nowrap; }
#reset { background: #16a34a; transition: background-color .16s ease; }
#reset:hover { background: #15803d; }
#reset.is-dirty { background: #dc2626; }
#reset.is-dirty:hover { background: #b91c1c; }
.filter-shell .filters button,
.filter-shell .filters input,
.filter-shell .filters select {
  height: 26px;
  min-height: 26px;
  font-size: 10px;
}
.filter-shell .filters button { padding: 0 8px; }
.filter-shell :is(button, input, select):focus-visible {
  outline: 2px solid #f59e0b;
  outline-offset: 1px;
}
.loading-toast { position: fixed; right: 18px; bottom: 18px; z-index: 2000; display: flex; align-items: center; gap: 9px; min-width: 210px; max-width: min(360px, calc(100vw - 24px)); min-height: 44px; padding: 10px 13px; border: 1px solid #b8c6d3; border-radius: 6px; background: #ffffff; box-shadow: 0 8px 24px rgba(22, 36, 49, .2); color: var(--ink); font-size: 12px; transition: opacity .18s ease, transform .18s ease; }
.loading-toast.hidden { opacity: 0; pointer-events: none; transform: translateY(8px); }
.loading-toast.error { border-color: #dc2626; color: #991b1b; }
.loading-spinner { width: 17px; height: 17px; flex: 0 0 auto; border: 2px solid #cbd5e1; border-top-color: var(--blue); border-radius: 50%; animation: loading-spin .8s linear infinite; }
.loading-toast.error .loading-spinner { display: none; }
@keyframes loading-spin { to { transform: rotate(360deg); } }
main { padding: 16px 0 24px; }
.grid { display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 12px; align-items: stretch; }
.card, .panel { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px; }
.card { min-height: 118px; display: flex; flex-direction: column; }
.label { color: var(--muted); font-size: 12px; }
.value { margin-top: 6px; font-size: 24px; font-weight: 700; line-height: 1.15; }
.card-note { margin-top: auto; padding-top: 8px; color: var(--muted); font-size: 12px; line-height: 1.25; }
.rank-grid, .audience-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; align-items: stretch; }
.rank-panel, .audience-panel { display: flex; flex-direction: column; min-width: 0; }
.rank-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); min-height: 47px; gap: 10px; align-items: center; margin-bottom: 8px; padding: 8px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.rank-controls .filter-label { height: 30px; }
.panel-head { display: flex; min-height: 32px; gap: 10px; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.panel-head > div { min-width: 0; }
.panel-head small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; font-weight: 400; }
.panel-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 7px; }
.panel-actions button { border: 1px solid #9dbde7; background: #ffffff; color: var(--blue); }
.source-tag { display: inline-flex; flex: 0 0 auto; align-items: center; min-height: 22px; border-radius: 3px; padding: 2px 7px; color: #ffffff; font-size: 11px; font-weight: 700; }
.fast-tag { background: var(--fast); }
.stream-tag { background: var(--stream); }
.combined-tag { background: var(--combined); color: #2c2500; }
.rank-grid > .rank-panel:first-child { border-top: 3px solid var(--spot); }
.rank-grid > .rank-panel:nth-child(2) { border-top: 3px solid var(--lband); }
.rank-grid > .rank-panel:first-child .source-tag { background: var(--spot); }
.rank-grid > .rank-panel:nth-child(2) .source-tag { background: var(--lband); }
.rank-grid > .rank-panel:first-child .bar i { background: var(--spot); }
.rank-grid > .rank-panel:nth-child(2) .bar i { background: var(--lband); }
.audience-grid > .audience-panel:first-child { border-top: 3px solid var(--fast); }
.audience-grid > .audience-panel:nth-child(2) { border-top: 3px solid var(--stream); }
.combined-panel { border-top: 3px solid var(--combined); }
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
.audience-note {
  margin-top: 6px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.35;
}
.audience-note:empty { display: none; }
.combined-panel { margin-top: 16px; }
.combined-columns, .combined-line { display: grid; grid-template-columns: 112px 92px minmax(190px, 1fr) 66px 112px 112px 112px 124px; gap: 8px; align-items: center; }
.combined-columns { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.combined-line { min-height: 44px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }
.combined-columns .fast-col,
.fct-audience-columns .fast-col {
  border-bottom: 2px solid var(--fast);
  color: var(--fast);
}
.combined-columns .stream-col,
.fct-audience-columns .stream-col {
  border-bottom: 2px solid var(--stream);
  color: var(--stream);
}
.combined-columns .amagi-col,
.fct-audience-columns .amagi-col {
  border-bottom: 2px solid var(--amagi);
  color: var(--amagi);
}
.combined-line .fast-col,
.fct-audience-line .fast-col {
  border-left: 3px solid var(--fast);
  background: #f3efff;
  color: #4c1d95;
}
.combined-line .stream-col,
.fct-audience-line .stream-col {
  border-left: 3px solid var(--stream);
  background: #fff0f6;
  color: #9d174d;
}
.combined-line .amagi-col,
.fct-audience-line .amagi-col {
  border-left: 3px solid var(--amagi);
  background: #fff4ed;
  color: #9a3412;
}
.combined-line :is(.fast-col, .stream-col, .amagi-col),
.fct-audience-line :is(.fast-col, .stream-col, .amagi-col) {
  min-height: 28px;
  padding: 6px;
  border-radius: 3px;
}

.youtube-panel { margin-top: 16px; border-top: 3px solid #eab308; }
.youtube-tag { background: #facc15; color: #422006; }
.combined-columns .youtube-col,
.fct-audience-columns .youtube-col {
  border-bottom: 2px solid #eab308;
  color: #713f12;
}
.combined-line .youtube-col,
.fct-audience-line .youtube-col {
  min-height: 28px;
  padding: 6px;
  border-left: 3px solid #eab308;
  border-radius: 3px;
  background: #fef9c3;
  color: #713f12;
}
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
body.youtube-chart-expanded { overflow: hidden; }
.youtube-chart-modal[hidden] { display: none; }
.youtube-chart-modal {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: grid;
  place-items: center;
  padding: 14px;
  background: rgba(15, 23, 42, .68);
}
.youtube-chart-dialog {
  display: flex;
  flex-direction: column;
  width: min(1500px, 100%);
  height: min(94vh, 980px);
  overflow: hidden;
  border: 1px solid #aebdca;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 24px 70px rgba(15, 23, 42, .35);
}
.youtube-chart-modal-head {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
}
.youtube-chart-modal-head h2 { margin: 0; font-size: 16px; }
.youtube-chart-modal-body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.youtube-chart-modal-body .youtube-filter-bar,
.youtube-chart-modal-body .youtube-controls {
  flex: 0 0 auto;
  margin: 0;
}
.youtube-chart-modal-body .youtube-chart-shell {
  flex: 1 1 auto;
  min-height: 420px;
  height: auto;
  margin: 0;
}
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
  .filters { gap: 4px; }
  .filters .period-field { min-width: 138px; }
  .date-mode-group { min-width: 210px; }
  .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 960px) {
  .topbar-inner { min-height: 60px; align-items: flex-start; flex-wrap: wrap; padding: 7px 0; gap: 3px 12px; }
  .meta { width: 100%; justify-content: flex-start; }
  .filters { flex-wrap: wrap; }
  .dashboard-page-nav { flex: 1 1 100%; order: -1; }
  .rank-grid, .audience-grid, .youtube-grid { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .wrap { padding: 0; }
  .filters { align-items: stretch; }
  .date-mode-group { flex: 1 1 100%; }
  .filters .period-field { flex: 1 1 calc(50% - 32px); }
  #reset { flex: 0 0 58px; }
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-metric:nth-child(2) { border-right: 0; }
  .youtube-metric:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .youtube-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-filter-actions { grid-column: 1 / -1; }
  .youtube-controls { align-items: flex-start; flex-direction: column; }
  .youtube-controls .panel-actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
  }
  .youtube-controls .filter-label {
    flex: 1 1 110px;
    min-width: 0;
  }
  .youtube-controls-note { text-align: left; }
  .youtube-context-head, .youtube-context-row { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .youtube-context-head span:nth-child(4), .youtube-context-head span:nth-child(5), .youtube-context-row span:nth-child(4), .youtube-context-row span:nth-child(5) { grid-column: 3; text-align: left; }
  .event-columns, .event-line { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .event-columns .duration, .event-line .duration { display: none; }
  .audience-value, .event-columns .metric { grid-column: 3; text-align: left; }
  .combined-columns, .combined-line { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .combined-columns .duration, .combined-line .duration { display: none; }
  .combined-columns .fast-col, .combined-columns .stream-col, .combined-columns .youtube-col, .combined-columns .total-col, .combined-line .fast-col, .combined-line .stream-col, .combined-line .youtube-col, .combined-line .total-col { grid-column: 3; text-align: left; }
  .youtube-chart-modal { padding: 0; }
  .youtube-chart-dialog {
    width: 100%;
    height: 100dvh;
    border: 0;
    border-radius: 0;
  }
  .youtube-chart-modal-head { padding: 10px; }
  .youtube-chart-modal-body { padding: 8px; }
  .youtube-chart-modal-body .youtube-chart-shell { min-height: 360px; }
}
@media (max-width: 460px) {
  .title-group { display: block; }
  .source-label { display: block; margin-top: 2px; }
  .meta { display: grid; gap: 2px; }
  .filters .period-field { flex-basis: calc(50% - 32px); }
  .grid { grid-template-columns: 1fr; }
  .youtube-metrics { grid-template-columns: 1fr; }
  .youtube-filter-bar { grid-template-columns: 1fr; }
  .youtube-metric, .youtube-metric:nth-child(2) { border-right: 0; border-bottom: 1px solid var(--line); }
  .youtube-metric:last-child { border-bottom: 0; }
  .audience-controls { grid-template-columns: 1fr; }
  .rank-controls { grid-template-columns: 1fr; }
  .barrow { grid-template-columns: minmax(0, 1fr) 82px; }
  .bar { display: none; }
}
</style><script>__CHARTJS__</script></head><body><header class="topbar"><div class="wrap topbar-inner"><div class="title-group"><h1>Veto ASRUN Delivery Demo</h1><span class="source-label">__TITLE__ | ASRUN playout evidence</span></div><div class="meta"><span id="range"></span><span id="updated"></span></div></div></header><section class="filter-shell"><div class="wrap filters"><label class="filter-label">Date from<input id="from" type="date"></label><label class="filter-label">Date to<input id="to" type="date"></label><label class="filter-label">Ad type<span class="multi-select"><button id="typeToggle" class="multi-toggle" type="button">All ad types</button><span id="typeMenu" class="multi-menu"></span></span></label><label class="filter-label">Ad ID<span class="multi-select"><button id="adIdToggle" class="multi-toggle" type="button">All ad IDs</button><span id="adIdMenu" class="multi-menu"></span></span></label><label class="filter-label">Creative title<span class="multi-select"><button id="creativeToggle" class="multi-toggle" type="button">All creative titles</button><span id="creativeMenu" class="multi-menu"></span></span></label><button id="reset" type="button">Reset</button></div></section><main class="wrap"><section class="grid" id="kpis"></section><section class="rank-grid"><div class="panel rank-panel"><div class="panel-head"><h2>Spot Creative Delivery</h2><span class="source-tag fast-tag">SPOT</span></div><div class="rank-list" id="spotBars"></div></div><div class="panel rank-panel"><div class="panel-head"><h2>L-band Creative Delivery</h2><span class="source-tag stream-tag">L-BAND</span></div><div class="rank-list" id="lbandBars"></div></div></section><section class="audience-grid"><div class="panel audience-panel"><div class="panel-head"><div><h2>FAST Delivered Ad Events</h2></div><span class="source-tag fast-tag">FAST</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="fastPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="fastPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="fastChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="fastChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="fastRows"></div><div class="audience-note" id="fastNote"></div></div><div class="panel audience-panel"><div class="panel-head"><div><h2>STREAM Delivered Ad Events</h2></div><span class="source-tag stream-tag">STREAM</span></div><div class="audience-controls stream-audience-controls"><label class="filter-label">Channel<span class="multi-select"><button id="streamChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="streamChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="streamRows"></div><div class="audience-note" id="streamNote"></div></div></section><section class="panel combined-panel"><div class="panel-head"><div><h2>All Delivered Ad Events</h2><small>FAST + STREAM selected 5-minute concurrency | YouTube minute concurrency</small></div><div class="panel-actions"><button id="exportAllEvents" type="button">Export CSV</button><button id="exportAudienceBreakdown" type="button">Export platform/channel CSV</button><span class="source-tag combined-tag">FAST + STREAM</span></div></div><div class="combined-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="fast-col">FAST</span><span class="stream-col">STREAM</span><span class="youtube-col">YOUTUBE</span><span class="total-col">Combined</span></div><div class="combined-list" id="allRows"></div><div class="audience-note" id="allNote"></div></section><section class="panel youtube-panel" id="youtubePanel"><div class="panel-head"><div><h2>YouTube Live Audience Context</h2></div><span class="source-tag youtube-tag">YOUTUBE</span></div><div class="youtube-meta" id="youtubeMeta"></div><div class="youtube-filter-bar" aria-label="Independent YouTube filters"><label class="filter-label">YouTube date from<input id="youtubeFrom" type="date"></label><label class="filter-label">YouTube date to<input id="youtubeTo" type="date"></label><label class="filter-label">Videos<span class="multi-select"><button id="youtubeVideoToggle" class="multi-toggle" type="button">All live videos</button><span id="youtubeVideoMenu" class="multi-menu"></span></span></label><div class="youtube-filter-actions" role="group" aria-label="YouTube quick ranges"><button type="button" data-youtube-range="latest">Latest day</button><button type="button" data-youtube-range="7">7D</button><button type="button" data-youtube-range="30">30D</button><button type="button" data-youtube-range="all">All</button></div></div><div class="youtube-metrics" id="youtubeMetrics"></div><div class="youtube-controls"><span class="youtube-controls-note" id="youtubeSelectionNote" aria-live="polite"></span><div class="panel-actions"><label class="filter-label">CSV interval<select id="youtubeExportInterval"><option value="1">1 minute</option><option value="5" selected>5 minutes</option></select></label><button id="exportYoutubeCsv" type="button">Export minute CSV</button><button id="exportYoutubeReferenceCsv" type="button">Export stream reference</button></div></div><div class="youtube-chart-shell"><canvas id="youtubeTrend" aria-label="YouTube live concurrency trend"></canvas><div class="youtube-chart-empty" id="youtubeChartEmpty"></div></div><details class="youtube-data-details"><summary>View chart values as a table</summary><table class="youtube-data-table"><thead><tr><th>IST time</th><th>Live concurrency</th></tr></thead><tbody id="youtubeTrendTable"></tbody></table></details><div class="youtube-grid"><section class="youtube-subsection"><h3>Top Live Videos</h3><div class="youtube-list" id="youtubeVideoRanking"></div></section><section class="youtube-subsection"><h3>YouTube Audience at Delivered Ad Events</h3><div class="youtube-context-head"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span>YT concurrency</span><span>Live videos</span></div><div class="youtube-list" id="youtubeEventContext"></div></section></div></section></main><script>const DATA=__BLOB__;const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n),mins=s=>fmt(s/60)+' min',esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));const canonical=String((DATA.channels||[])[0]||'');const dates=DATA.events.map(x=>x.on_air_start_ist.slice(0,10)),minDate=[...dates].sort()[0],maxDate=[...dates].sort().at(-1);$('from').value=minDate;$('to').value=maxDate;$('from').min=minDate;$('from').max=maxDate;$('to').min=minDate;$('to').max=maxDate;$('range').textContent='Ad data range: '+DATA.true_range.start+' to '+DATA.true_range.end;$('updated').textContent='Dashboard created: '+DATA.generated_at_ist;
function option(value,label){return '<option value="'+esc(value)+'">'+esc(label)+'</option>'}function dateScope(){const from=$('from').value,to=$('to').value;return DATA.events.filter(e=>e.on_air_start_ist.slice(0,10)>=from&&e.on_air_start_ist.slice(0,10)<=to)}function selectedMulti(id){return new Set([...$(id+'Menu').querySelectorAll('input[data-value]:checked')].map(input=>input.dataset.value))}function scope(){const types=selectedMulti('type');return dateScope().filter(e=>!types.size||types.has(e.ad_type))}function filterKey(){return [$('from').value,$('to').value,[...selectedMulti('type')].sort().join('|'),[...selectedMulti('adId')].sort().join('|'),[...selectedMulti('creative')].sort().join('|')].join('\u0000')}function multiAllLabel(id,kind,allLabel){const values=[...selectedMulti(id)],count=$(id+'Menu').querySelectorAll('input[data-value]').length,button=$(id+'Toggle');if(!values.length||values.length===count){button.textContent=allLabel;return}button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected'}function buildHeaderMulti(id,items,kind,defaultValues,allLabel,onChange){const menu=$(id+'Menu'),old=selectedMulti(id),allowed=new Set(items.map(item=>item.value)),selected=new Set([...old].filter(value=>allowed.has(value)));if(!old.size&&!multiInitialized.has(id))for(const value of defaultValues)if(allowed.has(value))selected.add(value);multiInitialized.add(id);const allChecked=items.length>0&&selected.size===items.length;menu.innerHTML='<label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All '+kind+'</label>'+items.map(item=>'<label class="multi-option"><input type="checkbox" data-value="'+esc(item.value)+'" '+(selected.has(item.value)?'checked':'')+'>'+esc(item.label)+'</label>').join('');multiAllLabel(id,kind,allLabel);$(id+'Toggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus(id);menu.classList.toggle('open',open)};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-value]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-value]')].every(input=>input.checked);multiAllLabel(id,kind,allLabel);clearFilterCache();onChange()};}function countedOptions(rows,key){const counts=new Map();for(const row of rows){const value=String(row[key]||'').trim();if(value)counts.set(value,(counts.get(value)||0)+1)}return [...counts.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([value,count])=>({value,label:value+' ('+fmt(count)+')'}))}function refreshDependentOptions(){const base=dateScope(),typeCounts=new Map();for(const row of base)typeCounts.set(row.ad_type,(typeCounts.get(row.ad_type)||0)+1);const types=['Spot','L-band'].filter(type=>typeCounts.has(type)).map(type=>({value:type,label:type+' ('+fmt(typeCounts.get(type))+')'}));buildHeaderMulti('type',types,'ad types',types.map(item=>item.value),'All ad types ('+fmt(base.length)+')',()=>{refreshDependentOptions();refreshAudienceFilters();scheduleRender()});const eligible=scope(),ids=countedOptions(eligible,'event_id');buildHeaderMulti('adId',ids,'ad IDs',ids.map(item=>item.value),'All ad IDs ('+fmt(eligible.length)+')',()=>{refreshDependentOptions();scheduleRender()});const selectedIds=selectedMulti('adId'),titlesSource=eligible.filter(e=>!selectedIds.size||selectedIds.has(e.event_id)),titles=countedOptions(titlesSource,'creative_title');buildHeaderMulti('creative',titles,'creative titles',titles.map(item=>item.value),'All creative titles ('+fmt(titlesSource.length)+')',scheduleRender)}function filtered(){const key=filterKey();if(filterCache.key===key&&filterCache.value)return filterCache.value;const selectedIds=selectedMulti('adId'),creative=selectedMulti('creative'),result=scope().filter(e=>(!selectedIds.size||selectedIds.has(e.event_id))&&(!creative.size||creative.has(e.creative_title)));filterCache={key,value:result};return result}function formatIst(value){const normalized=String(value).replace(' ','T'),[datePart,timePart='00:00']=normalized.split('T'),[year,month,day]=datePart.split('-'),[rawHour='0',minute='00']=timePart.split(':');const hour=Number(rawHour),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return day+'-'+month+'-'+year.slice(-2)+' '+String(twelve).padStart(2,'0')+':'+minute+' '+suffix;}
function rankingBars(node,items){const visible=items.slice(0,50),max=Math.max(1,...visible.map(x=>x.seconds));node.innerHTML=visible.length?visible.map(x=>'<div class="barrow"><span class="bar-label"><strong>'+esc(x.id)+'</strong><small>'+esc(x.title)+'</small></span><div class="bar"><i style="width:'+((x.seconds/max)*100)+'%"></i></div><span class="rank-meta">'+fmt(x.plays)+' plays<br>'+mins(x.seconds)+'</span></div>').join(''):'<p>No delivery events in this selection.</p>';}function minuteKey(value){return String(value).slice(0,16)+':00'}function viewerScope(source){const from=$('from').value,to=$('to').value;return (DATA.viewer_minute||[]).filter(r=>r.source===source&&String(r.minute_ist).slice(0,10)>=from&&String(r.minute_ist).slice(0,10)<=to)}const multiInitialized=new Set();let filterCache={key:null,value:null},renderTimer=null;function clearFilterCache(){filterCache={key:null,value:null}}function scheduleRender(){clearTimeout(renderTimer);renderTimer=setTimeout(render,160)}function closeMultiMenus(exceptId){for(const menu of document.querySelectorAll('.multi-menu'))if(menu.id!==exceptId+'Menu')menu.classList.remove('open')}function multiSummary(id,kind){const values=[...selectedMulti(id)],button=$(id+'Toggle');if(!values.length){button.textContent='Choose '+kind;return}const all=[...$(id+'Menu').querySelectorAll('input[data-value]')].map(input=>input.dataset.value);if(values.length===all.length){button.textContent='All '+kind;return}button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected'}function buildMulti(id,items,kind,defaultValues,onChange){const menu=$(id+'Menu'),old=selectedMulti(id),allowed=new Set(items),selected=new Set([...old].filter(value=>allowed.has(value)));if(!old.size&&!multiInitialized.has(id))for(const value of defaultValues)if(allowed.has(value))selected.add(value);multiInitialized.add(id);const allChecked=items.length>0&&selected.size===items.length;menu.innerHTML='<label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All '+kind+'</label>'+items.map(value=>'<label class="multi-option"><input type="checkbox" data-value="'+esc(value)+'" '+(selected.has(value)?'checked':'')+'>'+esc(value)+'</label>').join('');multiSummary(id,kind);$(id+'Toggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus(id);menu.classList.toggle('open',open)};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-value]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-value]')].every(input=>input.checked);multiSummary(id,kind);clearFilterCache();onChange()};}function refreshAudienceFilters(){const fast=viewerScope('fast'),platforms=[...new Set(fast.map(r=>String(r.platform_name)))].sort();buildMulti('fastPlatform',platforms,'platforms',platforms,()=>{refreshAudienceFilters();scheduleRender()});const selectedPlatforms=selectedMulti('fastPlatform'),fastChannels=[...new Set(fast.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('fastChannel',fastChannels,'channels',fastChannels,scheduleRender);const streamChannels=[...new Set(viewerScope('stream').map(r=>String(r.channel_name)))].sort();buildMulti('streamChannel',streamChannels,'channels',streamChannels,scheduleRender);}function audienceMinuteMap(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;if(!channels.size||(source==='fast'&&!platforms.size))return {message:'',map:new Map()};const rows=viewerScope(source).filter(r=>(source!=='fast'||platforms.has(String(r.platform_name)))&&channels.has(String(r.channel_name)));if(!rows.length)return {message:'',map:new Map()};const map=new Map();for(const r of rows){const key=minuteKey(r.minute_ist);map.set(key,(map.get(key)||0)+Number(r.distinct_cliips||0));}return {message:'',map};}function naiveMillis(value){const [d,t='00:00:00']=String(value).split('T'),[year,month,day]=d.split('-').map(Number),[hour=0,minute=0,seconds=0]=t.split(':').map(Number);return Date.UTC(year,month-1,day,hour,minute,seconds);}function fiveMinuteWindow(event){const bucket=Math.floor(naiveMillis(event.on_air_start_ist)/(5*60000))*(5*60000),keys=[];for(let offset=0;offset<5;offset++)keys.push(new Date(bucket+offset*60000).toISOString().slice(0,16)+':00');const start=new Date(bucket),end=new Date(bucket+4*60000),clock=d=>{const hour=d.getUTCHours(),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return String(twelve).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0')+' '+suffix;};return {keys,label:clock(start)+'-'+clock(end)+' IST'};}function audienceValue(event,state){const window=fiveMinuteWindow(event);if(!state.map)return {value:'0',window:window.label,total:0};let total=0,found=false;for(const key of window.keys){if(state.map.has(key)){found=true;total+=state.map.get(key);}}return {value:found?fmt(total):'0',window:window.label,total:found?total:0};}function audienceLines(events,state){if(!events.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const metric=audienceValue(e,state);return '<div class="event-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="audience-value">'+esc(metric.value)+'</span></div>';}).join('');}let youtubeDeliveryMinuteIndex=null;
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
['from','to'].forEach(id=>$(id).addEventListener('change',()=>{clearFilterCache();refreshDependentOptions();refreshAudienceFilters();scheduleRender()}));$('youtubeFrom').addEventListener('change',()=>{syncYoutubeDates('from');updateYoutubeRangeButtons('');renderYoutube()});$('youtubeTo').addEventListener('change',()=>{syncYoutubeDates('to');updateYoutubeRangeButtons('');renderYoutube()});document.querySelectorAll('[data-youtube-range]').forEach(button=>button.addEventListener('click',()=>setYoutubeRange(button.dataset.youtubeRange)));window.addEventListener('resize',renderYoutube);$('exportAllEvents').addEventListener('click',exportAllEventsCsv);$('exportAudienceBreakdown').addEventListener('click',exportAudienceBreakdownCsv);$('exportYoutubeCsv').addEventListener('click',exportYoutubeCsv);$('exportYoutubeReferenceCsv').addEventListener('click',exportYoutubeReferenceCsv);document.addEventListener('click',event=>{if(!event.target.closest('.multi-select'))closeMultiMenus('')});$('reset').onclick=()=>{$('from').value=minDate;$('to').value=maxDate;if(typeof fctClassMode!=='undefined')fctClassMode='Commercial';multiInitialized.clear();clearFilterCache();refreshDependentOptions();refreshAudienceFilters();scheduleRender()};const youtubeInitial=youtubeBounds();$('youtubeFrom').min=youtubeInitial.start;$('youtubeFrom').max=youtubeInitial.end;$('youtubeTo').min=youtubeInitial.start;$('youtubeTo').max=youtubeInitial.end;const initialYoutubeFrom=[minDate,youtubeInitial.start].sort().at(-1),initialYoutubeTo=[maxDate,youtubeInitial.end].sort()[0];$('youtubeFrom').value=initialYoutubeFrom<=initialYoutubeTo?initialYoutubeFrom:youtubeInitial.end;$('youtubeTo').value=initialYoutubeFrom<=initialYoutubeTo?initialYoutubeTo:youtubeInitial.end;syncYoutubeDates('from');refreshDependentOptions();refreshAudienceFilters();render();renderYoutube();</script></body></html>"""
    loading_markup = (
        '<div id="loadingToast" class="loading-toast" role="status" aria-live="polite">'
        '<span class="loading-spinner" aria-hidden="true"></span>'
        '<span id="loadingText">Loading dashboard data...</span></div>'
    )
    data_marker = "<script>const DATA=__BLOB__;"
    if data_marker not in template:
        raise RuntimeError("ASRUN template data marker is missing.")
    template = template.replace("<body>", "<body>" + loading_markup, 1)
    template = template.replace(
        data_marker,
        '<script src="asrun_delivery_data.js"></script><script>'
        "const DATA=window.__ASRUN_DATA__;"
        "if(!DATA){const toast=document.getElementById('loadingToast');"
        "toast.classList.add('error');"
        "document.getElementById('loadingText').textContent="
        "'Dashboard data file is missing or unreadable.';"
        "throw new Error('asrun_delivery_data.js did not load');}"
        "if(typeof Chart!=='undefined'){Chart.defaults.font.family="
        "\"'Segoe UI Variable Text', 'Segoe UI', Arial, sans-serif\";}",
        1,
    )
    startup_marker = (
        "syncYoutubeDates('from');refreshDependentOptions();"
        "refreshAudienceFilters();render();renderYoutube();"
        "</script></body></html>"
    )
    if startup_marker not in template:
        raise RuntimeError("ASRUN template startup marker is missing.")
    # The extension performs the one authoritative initial render after all
    # optimized overrides exist, avoiding a full duplicate DOM build.
    template = template.replace(
        startup_marker,
        "syncYoutubeDates('from');refreshAudienceFilters();"
        "</script></body></html>",
        1,
    )
    youtube_context_marker = (
        "const minuteMap=new Map(minute.map(row=>"
        "[youtubeMinuteKey(row.timestamp_ist),row])),"
        "events=youtubeRangeEvents(from,to);"
        "$('youtubeEventContext').innerHTML=events.length?"
        "events.slice().sort((a,b)=>"
        "a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(event=>"
    )
    if youtube_context_marker not in template:
        raise RuntimeError("YouTube event-context marker is missing.")
    # Keep all matching events in memory for exports, but only build DOM nodes
    # for the latest 50 rows shown in the dashboard.
    template = template.replace(
        youtube_context_marker,
        "const minuteMap=new Map(minute.map(row=>"
        "[youtubeMinuteKey(row.timestamp_ist),row])),"
        "events=youtubeRangeEvents(from,to),"
        "eventPreview=events.slice().sort((a,b)=>"
        "a.on_air_start_ist.localeCompare(b.on_air_start_ist))"
        ".slice(-50).reverse();"
        "$('youtubeEventContext').innerHTML=eventPreview.length?"
        "eventPreview.map(event=>",
        1,
    )

    amagi_extension = r'''<style>
:root { --amagi: #c2410c; }
.amagi-tag { background: var(--amagi); color: #ffffff; }
.amagi-panel { border-top: 3px solid var(--amagi); }
.youtube-filter-bar {
  grid-template-columns:
    minmax(190px, .9fr)
    repeat(2, minmax(142px, .65fr))
    minmax(185px, .9fr)
    minmax(245px, 1.35fr)
    auto;
}
.filters.master-date-hidden [data-master-date-control] {
  display: none !important;
}
.youtube-filter-bar.follow-main {
  grid-template-columns: minmax(190px, .7fr) minmax(260px, 1.3fr);
}
.youtube-filter-bar.follow-main .youtube-independent-date-control {
  display: none !important;
}
.youtube-date-mode {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.youtube-date-mode-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
}
.youtube-date-mode-buttons button {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #f0a5a0;
  background: #ffffff;
  color: #9f1d17;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.youtube-date-mode-buttons button.active {
  border-color: #b91c1c;
  background: #b91c1c;
  color: #ffffff;
}
.youtube-filter-bar input:disabled {
  border-color: #d8dee6;
  background: #f1f5f9;
  color: #475569;
  opacity: 1;
}
.youtube-date-help {
  grid-column: 1 / -1;
  min-height: 15px;
  margin: -4px 0 0;
  color: var(--muted);
  font-size: 10px;
}
.youtube-date-help.error { color: #b91c1c; font-weight: 700; }
.youtube-chart-interval-controls {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: end;
}
.youtube-chart-interval-controls .filter-label[hidden] { display: none; }
.youtube-chart-interval-controls .filter-label { min-width: 130px; }
.youtube-chart-interval-controls input { width: 105px; }
.youtube-channel-label {
  display: block;
  color: #b91c1c;
  font-weight: 700;
}
:root { --fct: #374151; }
.fct-tag { background: var(--fct); color: #ffffff; }
.fct-panel { border-top: 3px solid var(--fct); }
.fct-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.fct-controls .filter-label:last-child { grid-column: 1 / -1; }
.fct-advanced {
  margin: -1px 0 8px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #fbfcfd;
}
.fct-advanced summary {
  padding: 6px 8px;
  color: var(--fct);
  cursor: pointer;
  font-size: 10px;
  font-weight: 700;
}
.fct-advanced[open] summary { border-bottom: 1px solid var(--line); }
.fct-advanced-controls {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  padding: 8px;
}
.fct-advanced-controls .filter-label {
  display: grid;
  grid-template-columns: 1fr;
  gap: 4px;
  white-space: normal;
}
.fct-advanced-controls input,
.fct-advanced-controls .multi-toggle { width: 100%; }
.fct-date-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-bottom: 8px; }
.fct-date-controls input { width: 100%; min-width: 0; }
.fct-range-actions { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; }
.fct-range-actions button { border: 1px solid #aeb8c4; background: #ffffff; color: #374151; }
.fct-range-actions button.active { border-color: var(--fct); background: var(--fct); color: #ffffff; }
.fct-date-meta { grid-column: 1 / -1; color: var(--muted); font-size: 9px; line-height: 1.35; }
.fct-class-filter { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; margin-bottom: 8px; }
.fct-class-filter button { overflow: hidden; border: 1px solid #99bcb8; background: #ffffff; color: #315d59; text-overflow: ellipsis; }
.fct-class-filter button.active { border-color: var(--fct); background: var(--fct); color: #ffffff; }
.fct-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 8px; border: 1px solid var(--line); border-radius: 4px; }
.fct-kpi { min-width: 0; padding: 7px 8px; border-right: 1px solid var(--line); }
.fct-kpi:last-child { border-right: 0; }
.fct-kpi strong { display: block; font-size: 15px; line-height: 1.15; }
.fct-kpi small { display: block; margin-top: 2px; color: var(--muted); font-size: 9px; }
.fct-columns, .fct-line { display: grid; grid-template-columns: 96px 100px minmax(140px, 1.2fr) minmax(125px, 1fr) 58px 92px; gap: 7px; align-items: center; }
.fct-columns { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.fct-line { min-height: 48px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }
.fct-line > span { min-width: 0; overflow-wrap: anywhere; }
.fct-line small { display: block; color: var(--muted); font-size: 9px; }
.fct-duration, .fct-class { text-align: right; }
.fct-preview-note {
  margin-top: 6px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.35;
}
.fct-preview-note:empty { display: none; }
.fct-panel .panel-actions button { border-color: #99bcb8; color: var(--fct); }
.fct-audience-panel { margin-top: 16px; border-top: 3px solid var(--fct); }
.fct-audience-panel .panel-actions button { border-color: #aeb5bf; color: var(--fct); }
.fct-audience-columns, .fct-audience-line { display: grid; grid-template-columns: 112px 100px minmax(190px, 1fr) 66px 92px 92px 92px 92px 112px; gap: 8px; align-items: center; }
.fct-audience-columns { padding: 0 2px 6px; color: var(--muted); font-size: 10px; font-weight: 700; }
.fct-audience-columns > span { text-align: center; }
.fct-audience-line { min-height: 46px; padding: 7px 2px; border-bottom: 1px solid var(--line); font-size: 11px; }
.fct-audience-line > span { min-width: 0; overflow-wrap: anywhere; }
.fct-audience-line small { display: block; color: var(--muted); font-size: 9px; }
.fct-audience-value { text-align: right; font-weight: 700; }
.combined-columns, .combined-line { grid-template-columns: 112px 92px minmax(190px, 1fr) 66px 96px 96px 96px 96px 124px; }
.scope-panel { margin: 16px 0 28px; }
.scope-panel .panel-head { align-items: flex-start; }
.scope-panel small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; font-weight: 400; }
.scope-table-wrap { overflow-x: auto; }
.scope-table { width: 100%; min-width: 920px; border-collapse: collapse; font-size: 11px; }
.scope-table th, .scope-table td { padding: 9px 8px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
.scope-table th { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .03em; }
.scope-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
.scope-muted { color: var(--muted); }
.scope-continuity { display: grid; gap: 3px; min-width: 150px; }
.scope-continuity-line { color: var(--muted); line-height: 1.25; }
.scope-continuity-line strong { color: var(--ink); }
.scope-continuity-line.complete strong { color: #047857; }
.scope-continuity-line.gap strong { color: #b45309; }
.multi-search-shell {
  display: block;
  position: sticky;
  z-index: 20;
  top: -4px;
  width: calc(100% + 8px);
  margin: -4px -4px 4px;
  padding: 6px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
  box-shadow: 0 2px 4px rgba(15, 23, 42, .10);
}
.multi-search-shell .multi-search { margin: 0 0 4px; }
.multi-search-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  align-items: center;
}
.multi-search-count {
  grid-column: 1 / -1;
  overflow: visible;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.2;
  white-space: normal;
}
.multi-search-actions button {
  width: 100%;
  min-width: 0;
  min-height: 22px;
  padding: 3px 6px;
  border-color: #c7d2dc;
  background: #f7f9fb;
  color: var(--ink);
  font-size: 10px;
}
.multi-search-actions button:hover { background: #eaf0f5; }
.multi-search-actions button:disabled { cursor: default; opacity: .45; }
.filter-label:has(.multi-menu.open) { position: relative; z-index: 120; }
.multi-select:has(.multi-menu.open) { z-index: 121; }
.multi-menu.open { z-index: 122; }
.multi-menu:has(.multi-search-shell) {
  width: min(280px, calc(100vw - 24px));
  max-width: calc(100vw - 24px);
}
.multi-menu .multi-option[hidden] { display: none !important; }
:root { --nct: #0f766e; }
.nct-panel {
  position: relative;
  margin-top: 16px;
  border-top: 3px solid var(--nct);
  box-shadow: 0 3px 12px rgba(15, 118, 110, .07);
}
.nct-panel > .panel-head { align-items: flex-start; flex-wrap: wrap; }
.nct-panel > .panel-head .panel-actions { flex-wrap: wrap; }
.nct-tag { background: var(--nct); color: #ffffff; }
.nct-mode { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3px; padding: 2px; border: 1px solid #b7d9d4; border-radius: 4px; background: #f0fdfa; }
.nct-mode button {
  border: 1px solid transparent;
  background: transparent;
  color: #0b5f59;
  transition: border-color .15s ease, background-color .15s ease, color .15s ease;
}
.nct-mode button:hover { border-color: #84c5bc; background: #d8f3ee; color: #064e3b; }
.nct-mode button.active {
  border-color: var(--nct);
  background: var(--nct);
  color: #ffffff;
}
.nct-panel .panel-actions > button,
.nct-rank-toggle,
#expandNctChart,
#exportNctContextCsv {
  min-width: 92px;
  height: 26px;
  border: 1px solid #6bb5aa;
  background: #ecfdf9;
  color: #0b5f59;
  font-size: 9px;
  font-weight: 700;
  transition: border-color .15s ease, background-color .15s ease, color .15s ease;
}
.nct-panel .panel-actions > button:hover,
.nct-rank-toggle:hover,
#expandNctChart:hover,
#exportNctContextCsv:hover {
  border-color: var(--nct);
  background: #ccfbf1;
  color: #064e3b;
}
.nct-panel button.nct-rank-toggle[aria-expanded="true"],
.nct-panel button#expandNctChart[aria-expanded="true"] {
  border-color: #064e3b;
  background: var(--nct);
  color: #ffffff;
}
.nct-panel button.nct-rank-toggle[aria-expanded="true"]:hover,
.nct-panel button#expandNctChart[aria-expanded="true"]:hover {
  border-color: #042f2e;
  background: #0b5f59;
  color: #ffffff;
}
.nct-panel :is(button, input, select):focus-visible {
  outline: 2px solid #f59e0b;
  outline-offset: 1px;
}
.nct-controls {
  position: relative;
  z-index: 20;
  display: block;
  margin-bottom: 8px;
}
.nct-scope-row {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(410px, 560px) minmax(240px, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  padding: 6px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.nct-date-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(145px, 1fr)) auto;
  gap: 7px;
  align-items: center;
}
.nct-date-fields[hidden] { display: none; }
.nct-date-fields .filter-label { min-width: 0; }
.nct-apply-date {
  border: 1px solid var(--nct);
  background: var(--nct);
  color: #ffffff;
  font-weight: 700;
}
.nct-apply-date:disabled { cursor: not-allowed; opacity: .48; }
.nct-apply-date.pending { background: #b45309; border-color: #b45309; }
.nct-status { min-width: 0; color: var(--muted); font-size: 10px; line-height: 1.35; }
.nct-status strong { color: var(--ink); }
.nct-qa-note {
  display: inline-flex;
  margin-left: 5px;
  border-radius: 3px;
  padding: 2px 5px;
  background: #fff7ed;
  color: #9a3412;
  font-weight: 700;
}
.nct-filter-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(145px, 1fr));
  gap: 8px;
  padding-top: 8px;
  align-items: end;
}
.nct-filter-grid > .filter-label {
  position: relative;
  display: grid;
  gap: 4px;
  min-width: 0;
  align-items: stretch;
  line-height: 1.2;
}
.nct-filter-grid > .filter-label:has(.multi-menu.open) { z-index: 120; }
.nct-controls .multi-select:has(.multi-menu.open) { z-index: 121; }
.nct-panel .multi-menu.open { z-index: 122; }
.nct-controls .nct-mode-label { min-width: 0; }
.nct-story-filter {
  grid-column: span 2;
  min-width: 0;
}
.nct-controls input:not([type="checkbox"]), .nct-controls .multi-toggle {
  min-width: 0;
  width: 100%;
}
.nct-panel .multi-option { align-items: flex-start; overflow-wrap: anywhere; }
.nct-panel .multi-option input[type="checkbox"] {
  width: 14px;
  min-width: 14px;
  height: 14px;
  flex: 0 0 14px;
}
.nct-option-label {
  min-width: 0;
  flex: 1 1 auto;
  color: var(--ink);
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}
.nct-panel .multi-menu {
  width: min(280px, calc(100vw - 24px));
  max-width: calc(100vw - 24px);
  scrollbar-width: thin;
}
.nct-filter-grid > .filter-label:nth-last-child(-n+2) .multi-menu {
  right: 0;
  left: auto;
}
.nct-panel .multi-search-actions {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.nct-panel .multi-search-shell {
  display: block;
  z-index: 20;
  width: calc(100% + 8px);
  margin: -4px -4px 4px;
  padding: 6px;
  box-sizing: border-box;
  background: #ffffff;
  box-shadow: 0 2px 4px rgba(15, 23, 42, .10);
}
.nct-panel .multi-search-count {
  grid-column: 1 / -1;
  overflow: visible;
  line-height: 1.2;
  white-space: normal;
}
.nct-panel .multi-search-actions button {
  width: 100%;
  min-width: 0;
}
.nct-panel .multi-option { position: relative; z-index: 1; }
.nct-story-menu {
  width: min(520px, calc(100vw - 32px));
  min-width: min(520px, calc(100vw - 32px));
  max-height: 320px;
}
.nct-story-options { display: grid; }
.nct-story-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  padding: 6px 7px;
  border: 0;
  border-bottom: 1px solid #edf1f5;
  border-radius: 0;
  background: #ffffff;
  color: var(--ink);
  text-align: left;
}
.nct-story-option:hover, .nct-story-option.active { background: #e8f4f2; }
.nct-story-option span { min-width: 0; overflow-wrap: anywhere; }
.nct-story-option small { color: var(--muted); white-space: nowrap; }
.nct-help { min-height: 16px; color: var(--muted); font-size: 10px; }
.nct-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--line); border-radius: 4px; }
.nct-kpi { min-width: 0; padding: 8px; border-right: 1px solid var(--line); }
.nct-kpi:last-child { border-right: 0; }
.nct-kpi strong { display: block; font-size: 16px; line-height: 1.15; }
.nct-kpi small { display: block; margin-top: 2px; color: var(--muted); font-size: 9px; }
.nct-analytics { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 10px; }
.nct-chart-card, .nct-rank-card, .nct-context {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #cbdedb;
  border-radius: 4px;
  background: #ffffff;
}
.nct-chart-head, .nct-rank-head, .nct-context-head {
  display: flex;
  min-height: 44px;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  padding: 8px 9px;
  border-bottom: 1px solid #d8e8e5;
  background: #fbfefd;
}
.nct-chart-head h3, .nct-rank-head h3, .nct-context-head h3 { margin: 0; font-size: 13px; }
.nct-chart-title small, .nct-rank-head small { display: block; margin-top: 2px; color: var(--muted); font-size: 9px; }
.nct-chart-actions { display: flex; align-items: center; gap: 6px; }
#expandNctChart { min-width: 88px; }
.nct-chart-wrap { position: relative; height: 300px; padding: 8px; }
.nct-chart-empty, .nct-loading { display: flex; min-height: 180px; align-items: center; justify-content: center; color: var(--muted); text-align: center; }
.nct-chart-empty[hidden] { display: none !important; }
.nct-loading[hidden] { display: none !important; }
.nct-ranks { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.nct-rank-list { max-height: 240px; overflow-y: auto; padding: 4px 8px 8px; }
.nct-rank-list.expandable {
  height: 240px;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}
.nct-rank-list.expanded { max-height: 240px; overflow-y: auto; }
.nct-rank-toggle { min-width: 116px; padding: 0 7px; white-space: nowrap; }
.nct-rank-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 7px; padding: 6px 0; border-bottom: 1px solid #edf1f5; font-size: 10px; }
.nct-rank-row span { min-width: 0; overflow-wrap: anywhere; }
.nct-rank-row strong { font-variant-numeric: tabular-nums; white-space: nowrap; }
.nct-mini-bar { grid-column: 1 / -1; height: 3px; overflow: hidden; border-radius: 2px; background: #e4eceb; }
.nct-mini-bar i { display: block; height: 100%; background: var(--nct); }
.nct-story-audience { margin-top: 10px; }
.nct-story-audience .nct-rank-head > div:first-child { min-width: 0; }
.nct-story-audience .nct-rank-head small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 9px;
}
.nct-story-audience-columns, .nct-story-audience-row {
  display: grid;
  grid-template-columns:
    minmax(230px, 1.65fr) 78px 58px repeat(6, minmax(76px, .62fr));
  gap: 8px;
  align-items: center;
}
.nct-story-audience-columns {
  padding: 8px 9px 5px;
  color: var(--muted);
  font-size: 9px;
  font-weight: 700;
}
.nct-story-audience-columns > span:not(:first-child),
.nct-story-audience-row > span:not(:first-child) {
  text-align: right;
}
.nct-story-audience-row {
  min-height: 42px;
  padding: 6px 9px;
  border-top: 1px solid var(--line);
  font-size: 10px;
}
.nct-story-audience-row > span { min-width: 0; overflow-wrap: anywhere; }
.nct-story-audience-row .story-label strong { display: block; }
.nct-story-audience-row .story-label small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 9px;
}
.nct-story-audience-row .audience-number {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  text-align: right;
}
.nct-story-audience-row .audience-unavailable {
  color: var(--muted);
  font-weight: 500;
}
.nct-story-performance-controls {
  display: flex;
  align-items: end;
  gap: 6px;
}
.nct-story-performance-controls .filter-label { min-width: 128px; }
.nct-story-performance-controls select {
  width: 100%;
  min-width: 0;
  height: 28px;
}
.nct-story-source-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 7px 9px;
  border-bottom: 1px solid #d8e8e5;
  background: #f7fbfa;
}
.nct-story-source-group {
  display: flex;
  min-width: 0;
  align-items: end;
  gap: 6px;
}
.nct-story-source-group[hidden] { display: none !important; }
.nct-story-source-group .source-tag { flex: 0 0 auto; margin-bottom: 2px; }
.nct-story-source-group .filter-label { min-width: 0; flex: 1 1 0; }
.nct-story-source-note {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 9px;
}
.global-audience-details {
  flex: 1 0 100%;
  order: 2;
  min-width: 0;
}
.global-audience-details > summary {
  display: none;
}
.global-audience-filters {
  display: grid;
  grid-template-columns: auto repeat(4, minmax(150px, 1fr));
  gap: 5px;
  align-items: end;
  width: 100%;
  min-width: 0;
  padding: 4px 5px;
  border: 1px solid #c5d2de;
  border-radius: 4px;
  background: #ffffff;
}
.global-audience-heading {
  align-self: center;
  min-width: 92px;
}
.global-audience-heading strong { display: block; font-size: 10px; }
.global-audience-heading small {
  display: block;
  color: var(--muted);
  font-size: 8px;
  line-height: 1.2;
}
.global-source-group {
  display: flex;
  min-width: 0;
  align-items: end;
  gap: 4px;
}
.global-source-group .source-tag {
  min-height: 20px;
  margin-bottom: 3px;
  padding: 1px 5px;
  font-size: 9px;
}
.global-source-group .filter-label {
  min-width: 0;
  flex: 1 1 0;
  font-size: 9px;
}
.global-source-group .multi-toggle { height: 25px; font-size: 10px; }
.global-asrun-group {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: auto repeat(4, minmax(145px, 1fr));
  align-items: end;
  gap: 5px;
  padding-top: 4px;
  border-top: 1px solid var(--line);
}
.rank-controls:empty { display: none; }
.audience-controls:empty { display: none; }
.nct-story-audience-table.expandable,
.nct-segment-table.expandable,
.nct-context-table.expandable {
  height: min(65vh, 620px);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.nct-story-audience-table .nct-story-audience-columns,
.nct-segment-table .nct-segment-columns,
.nct-context-table .nct-context-columns {
  position: sticky;
  z-index: 2;
  top: 0;
  background: #f7fbfa;
  border-bottom: 1px solid #d8e8e5;
}
.nct-story-audience-note { padding: 7px 9px 9px; }
.nct-segment-section { margin-top: 10px; }
.nct-segment-columns, .nct-segment-row {
  display: grid;
  grid-template-columns: 120px 92px minmax(150px, .85fr) minmax(190px, 1.2fr) minmax(120px, .7fr) 65px;
  gap: 8px;
  align-items: center;
}
.nct-segment-columns { padding: 9px 2px 5px; color: var(--muted); font-size: 10px; font-weight: 700; }
.nct-segment-row { min-height: 45px; padding: 6px 2px; border-bottom: 1px solid var(--line); font-size: 10px; }
.nct-segment-row > span { min-width: 0; overflow-wrap: anywhere; }
.nct-segment-row small { display: block; color: var(--muted); font-size: 9px; }
.nct-segment-columns span:last-child, .nct-segment-row span:last-child {
  text-align: right;
}
.nct-preview-note { margin-top: 6px; color: var(--muted); font-size: 10px; }
.nct-context { margin-top: 10px; }
.nct-context-control { min-width: 190px; }
.nct-context-columns, .nct-context-row {
  display: grid;
  grid-template-columns: 122px 100px 105px minmax(160px, .8fr) minmax(200px, 1.2fr) 82px;
  gap: 8px;
  align-items: center;
}
.nct-context-columns { padding: 8px 9px 5px; color: var(--muted); font-size: 10px; font-weight: 700; }
.nct-context-row { min-height: 46px; padding: 6px 9px; border-top: 1px solid var(--line); font-size: 10px; }
.nct-context-row > span { min-width: 0; overflow-wrap: anywhere; }
.nct-context-row small { display: block; color: var(--muted); font-size: 9px; }
.nct-load-error { color: #b91c1c; }
.nct-chart-card.expanded {
  position: fixed;
  z-index: 1001;
  inset: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 18px 50px rgba(15, 23, 42, .28);
}
.nct-chart-card.expanded .nct-chart-wrap { flex: 1 1 auto; height: auto; min-height: 0; }
body.nct-chart-expanded { overflow: hidden; }
body.nct-chart-expanded::before {
  position: fixed;
  z-index: 1000;
  inset: 0;
  background: rgba(15, 23, 42, .42);
  content: "";
}
@media (max-width: 840px) {
  .nct-chart-head { align-items: flex-start; flex-direction: column; }
  .nct-chart-actions { width: 100%; flex-wrap: wrap; }
  .nct-chart-mode { flex: 1 1 auto; }
  .nct-chart-mode button { flex: 1 1 auto; }
}
.dashboard-page-nav {
  position: static;
  display: grid;
  flex: 1 1 430px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
  min-width: 360px;
  margin: 0;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #ffffff;
}
.dashboard-page-nav button {
  min-width: 0;
  min-height: 24px;
  overflow: hidden;
  border: 1px solid transparent;
  background: #f1f5f9;
  color: #334155;
  font-size: 10px;
  font-weight: 700;
  text-overflow: ellipsis;
  transition: border-color .15s ease, background-color .15s ease, color .15s ease;
  white-space: nowrap;
}
.dashboard-page-nav button:hover {
  border-color: #64748b;
  background: #dfe7ef;
  color: #172334;
}
.dashboard-page-nav button.active {
  border-color: #162431;
  background: #162431;
  color: #ffffff;
}
.dashboard-page[hidden] { display: none !important; }
.dashboard-page {
  min-width: 0;
  animation: dashboard-page-enter .16s ease-out;
}
.dashboard-page > :first-child { margin-top: 0; }
.dashboard-page[data-dashboard-page="delivery"] > .fct-panel { margin-top: 16px; }
@keyframes dashboard-page-enter {
  from { opacity: .35; transform: translateY(3px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (max-width: 1220px) {
  .global-audience-filters {
    grid-template-columns: auto repeat(2, minmax(0, 1fr));
  }
  .global-audience-heading { grid-row: span 2; }
  .global-asrun-group {
    grid-template-columns: auto repeat(2, minmax(145px, 1fr));
  }
  .global-asrun-group .source-tag { grid-row: span 2; align-self: center; }
  .youtube-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-filter-actions { grid-column: 1 / -1; }
  .nct-scope-row { grid-template-columns: minmax(280px, .8fr) minmax(390px, 1.2fr); }
  .nct-status { grid-column: 1 / -1; }
  .nct-filter-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .nct-story-filter { grid-column: span 2; }
}
@media (max-width: 680px) {
  .global-audience-details > summary {
    display: flex;
    min-height: 28px;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 5px 7px;
    border: 1px solid #c5d2de;
    border-radius: 4px;
    background: #ffffff;
    color: var(--ink);
    cursor: pointer;
    font-size: 10px;
    font-weight: 700;
    list-style-position: inside;
  }
  .global-audience-details > summary small {
    min-width: 0;
    overflow: hidden;
    color: var(--muted);
    font-size: 8px;
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .global-audience-details[open] > summary {
    border-bottom-right-radius: 0;
    border-bottom-left-radius: 0;
  }
  .global-audience-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-top: 0;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
  }
  .global-audience-heading { display: none; }
  .global-source-group { flex-wrap: wrap; }
  .global-source-group .source-tag { width: 100%; }
  .global-asrun-group {
    display: grid;
    grid-template-columns: 1fr;
  }
  .global-asrun-group .source-tag,
  .global-asrun-group .filter-label { grid-column: auto; }
  .global-asrun-group .source-tag { grid-row: auto; }
  .global-audience-filters > .nct-story-source-note { display: none; }
  .dashboard-page-nav {
    gap: 3px;
    min-width: 0;
    padding: 2px;
  }
  .dashboard-page-nav button {
    min-height: 28px;
    padding: 3px;
    font-size: 10px;
    line-height: 1.15;
    white-space: normal;
  }
  .youtube-filter-bar { grid-template-columns: 1fr; }
  .youtube-filter-bar.follow-main { grid-template-columns: 1fr; }
  .youtube-chart-interval-controls {
    width: 100%;
    flex-wrap: wrap;
  }
  .combined-columns, .combined-line {
    grid-template-columns: 88px 78px minmax(0, 1fr);
    gap: 6px;
  }
  .combined-panel .panel-head { align-items: flex-start; }
  .combined-panel .panel-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
  .combined-columns .amagi-col, .combined-line .amagi-col { grid-column: 3; text-align: left; }
  .fct-class-filter { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fct-date-controls { grid-template-columns: 1fr; }
  .fct-date-controls .filter-label, .fct-range-actions, .fct-date-meta { grid-column: 1; }
  .fct-range-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fct-advanced-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fct-controls, .fct-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fct-kpi:nth-child(2) { border-right: 0; }
  .fct-kpi:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .fct-columns, .fct-line { grid-template-columns: 88px minmax(0, 1fr) 72px; }
  .fct-columns span:nth-child(4), .fct-line span:nth-child(4),
  .fct-columns span:nth-child(6), .fct-line span:nth-child(6) { display: none; }
  .fct-audience-columns, .fct-audience-line { grid-template-columns: 88px 78px minmax(0, 1fr); gap: 6px; }
  .fct-audience-columns .duration, .fct-audience-line .duration { display: none; }
  .fct-audience-columns .fast-col, .fct-audience-columns .stream-col,
  .fct-audience-columns .amagi-col, .fct-audience-columns .youtube-col,
  .fct-audience-columns .total-col, .fct-audience-line .fast-col,
  .fct-audience-line .stream-col, .fct-audience-line .amagi-col,
  .fct-audience-line .youtube-col, .fct-audience-line .total-col {
    grid-column: 3;
    text-align: left;
  }
  .nct-scope-row, .nct-filter-grid, .nct-kpis, .nct-analytics, .nct-ranks { grid-template-columns: 1fr; }
  .nct-date-fields { grid-template-columns: 1fr; }
  .nct-story-filter { grid-column: 1; }
  .nct-story-menu { right: auto; width: min(520px, calc(100vw - 24px)); }
  .nct-kpi { border-right: 0; border-bottom: 1px solid var(--line); }
  .nct-kpi:last-child { border-bottom: 0; }
  .nct-story-audience .nct-rank-head { align-items: flex-start; flex-direction: column; }
  .nct-story-performance-controls { width: 100%; flex-wrap: wrap; }
  .nct-story-performance-controls .filter-label { flex: 1 1 145px; }
  .nct-story-source-filters { grid-template-columns: 1fr; }
  .nct-story-source-group { flex-wrap: wrap; }
  .nct-story-source-group .source-tag { width: 100%; }
  .nct-story-audience-columns { display: none; }
  .nct-story-audience-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px 10px;
    padding: 9px;
  }
  .nct-story-audience-row > span::before {
    display: block;
    margin-bottom: 2px;
    color: var(--muted);
    content: attr(data-label);
    font-size: 8px;
    font-weight: 700;
    text-transform: uppercase;
  }
  .nct-story-audience-row .story-label { grid-column: 1 / -1; }
  .nct-story-audience-row > span:not(:first-child) { text-align: left; }
  .nct-segment-columns, .nct-segment-row { grid-template-columns: 94px minmax(0, 1fr) 62px; }
  .nct-segment-columns span:nth-child(2), .nct-segment-row span:nth-child(2),
  .nct-segment-columns span:nth-child(5), .nct-segment-row span:nth-child(5) { display: none; }
  .nct-context-head { align-items: flex-start; flex-direction: column; }
  .nct-context-columns, .nct-context-row { grid-template-columns: 94px 86px minmax(0, 1fr); }
  .nct-context-columns span:nth-child(3), .nct-context-row span:nth-child(3),
  .nct-context-columns span:nth-child(6), .nct-context-row span:nth-child(6) { display: none; }
}
</style><script>
const AMAGI=DATA.amagi||{};
const FCT=DATA.fct||{};
const DASHBOARD_SOURCE_SIDECARS=DATA.sidecars||{};
const dashboardSourceState=new Map(
  Object.keys(DASHBOARD_SOURCE_SIDECARS).map(name=>[name,'pending'])
);
const dashboardSourcePromises=new Map();
function dashboardSourceLoaded(name){
  return !DASHBOARD_SOURCE_SIDECARS[name]
    ||dashboardSourceState.get(name)==='loaded';
}
function dashboardSourceError(name){
  return dashboardSourceState.get(name)==='failed'
    ?'The '+name.toUpperCase()+' dashboard data file could not be loaded.'
    :'';
}
function installDashboardSource(name,value){
  if(name==='viewer'){
    DATA.viewer_minute=Array.isArray(value)?value:[];
  }else if(name==='amagi'){
    AMAGI.minute=Array.isArray(value)?value:[];
  }else if(name==='fct'){
    FCT.events=Array.isArray(value)?value:[];
  }else if(name==='youtube'){
    Object.assign(DATA.youtube||{},value||{});
    youtubeDeliveryMinuteIndex=null;
  }else{
    throw new Error('Unsupported dashboard sidecar: '+name);
  }
}
function loadDashboardSource(name){
  if(dashboardSourceLoaded(name))return Promise.resolve();
  if(dashboardSourcePromises.has(name))return dashboardSourcePromises.get(name);
  const config=DASHBOARD_SOURCE_SIDECARS[name];
  if(!config){
    dashboardSourceState.set(name,'loaded');
    return Promise.resolve();
  }
  const promise=new Promise((resolve,reject)=>{
    const finish=()=>{
      const value=window[config.global];
      if(value===undefined){
        const error=new Error(config.file+' did not publish '+config.global);
        dashboardSourceState.set(name,'failed');
        reject(error);
        return;
      }
      installDashboardSource(name,value);
      try{delete window[config.global]}catch(_error){window[config.global]=undefined}
      dashboardSourceState.set(name,'loaded');
      resolve();
    };
    if(window[config.global]!==undefined){
      finish();
      return;
    }
    const script=document.createElement('script');
    script.src=config.file;
    script.async=true;
    script.onload=finish;
    script.onerror=()=>{
      const error=new Error('Unable to load '+config.file);
      dashboardSourceState.set(name,'failed');
      reject(error);
    };
    document.head.appendChild(script);
  });
  dashboardSourcePromises.set(name,promise);
  return promise;
}
function loadDashboardSources(names){
  return Promise.all(names.map(loadDashboardSource));
}
let fctClassMode='Commercial';
let fctRangeMode='all';
const FCT_SCALAR_FILTER_IDS=[
  'fctTimeFrom','fctTimeTo','fctProgramTimeFrom','fctProgramTimeTo',
  'fctDurationMin','fctDurationMax',
  'fctProgramDurationMin','fctProgramDurationMax',
];
const FCT_NUMERIC_FILTER_PAIRS=[
  ['fctDurationMin','fctDurationMax'],
  ['fctProgramDurationMin','fctProgramDurationMax'],
];
const multiSearchState=new Map();
const multiSelectControllers=new Map();
function normalizeMultiSearch(value){
  return String(value??'')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g,'')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g,' ')
    .trim();
}
class DashboardMultiSelect{
  constructor(id,kind){
    this.id=id;
    this.kind=kind;
    this.menu=$(id+'Menu');
    this.toggle=$(id+'Toggle');
  }
  mount(){
    if(!this.menu||!this.toggle||this.menu.querySelector('[data-multi-search-shell]')){
      return;
    }
    const query=multiSearchState.get(this.id)||'';
    this.menu.insertAdjacentHTML(
      'afterbegin',
      '<span class="multi-search-shell" data-multi-search-shell>'
        +'<input class="multi-search" type="search" data-multi-search '
        +'placeholder="Search '+esc(this.kind)+'..." autocomplete="off">'
        +'<span class="multi-search-actions">'
          +'<span class="multi-search-count" data-multi-search-count></span>'
          +'<button type="button" data-multi-match-action="select" '
          +'title="Select matching options">Select</button>'
          +'<button type="button" data-multi-match-action="clear" '
          +'title="Clear matching options">Clear</button>'
        +'</span>'
      +'</span>',
    );
    const search=this.menu.querySelector('[data-multi-search]');
    search.value=query;
    search.addEventListener('input',event=>{
      multiSearchState.set(this.id,event.target.value);
      this.applySearch();
    });
    // Search blur emits change; never route it through the checkbox handler.
    search.addEventListener('change',event=>event.stopPropagation());
    search.addEventListener('keydown',event=>{
      if(event.key==='Escape'){
        closeMultiMenu(this.menu);
        this.toggle.focus();
      }
    });
    for(const button of this.menu.querySelectorAll('[data-multi-match-action]')){
      button.addEventListener('click',event=>this.applyVisibleAction(event,button));
    }
    const originalToggle=this.toggle.onclick;
    this.toggle.onclick=event=>{
      const opening=!this.menu.classList.contains('open');
      originalToggle.call(this.toggle,event);
      if(!opening)clearMultiMenuSearch(this.menu);
      if(opening)requestAnimationFrame(()=>{
        alignMultiMenu(this.menu);
        const current=this.menu.querySelector('[data-multi-search]');
        if(current){
          current.focus();
          current.select();
        }
      });
    };
    this.applySearch();
  }
  optionInputs(visibleOnly=false){
    return [...this.menu.querySelectorAll('.multi-option:not(.multi-all)')]
      .filter(option=>!visibleOnly||!option.hidden)
      .map(option=>option.querySelector('input[data-value]'))
      .filter(Boolean);
  }
  applySearch(){
    const search=this.menu.querySelector('[data-multi-search]');
    if(!search)return;
    const terms=normalizeMultiSearch(search.value).split(/\s+/).filter(Boolean);
    let visible=0,total=0;
    for(const option of this.menu.querySelectorAll('.multi-option:not(.multi-all)')){
      const input=option.querySelector('input[data-value]');
      if(!input)continue;
      total++;
      const haystack=normalizeMultiSearch(option.textContent+' '+input.dataset.value);
      const words=haystack.split(/\s+/).filter(Boolean);
      const matches=terms.every(term=>words.some(word=>
        word.startsWith(term)||(term.length>=4&&word.includes(term))
      ));
      option.hidden=!matches;
      if(matches)visible++;
    }
    const count=this.menu.querySelector('[data-multi-search-count]');
    if(count)count.textContent=fmt(visible)+' of '+fmt(total)+' matches';
    for(const button of this.menu.querySelectorAll('[data-multi-match-action]')){
      button.disabled=visible===0;
    }
  }
  applyVisibleAction(event,button){
    event.preventDefault();
    event.stopPropagation();
    const inputs=this.optionInputs(true);
    if(!inputs.length)return;
    const checked=button.dataset.multiMatchAction==='select';
    for(const input of inputs)input.checked=checked;
    // Reuse the established checkbox change path for labels, cache, and charts.
    inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
  }
}
function clearMultiMenuSearch(menu){
  if(!menu)return;
  const search=menu.querySelector('input[type="search"]');
  if(!search)return;
  search.value='';
  search.dispatchEvent(new Event('input',{bubbles:true}));
  const id=menu.id.endsWith('Menu')?menu.id.slice(0,-4):'';
  if(id)multiSearchState.delete(id);
  if(id==='nctStory')renderNctStoryOptions();
  else if(id)multiSelectControllers.get(id)?.applySearch();
}
function alignMultiMenu(menu){
  if(!menu)return;
  menu.style.left='0';
  menu.style.right='auto';
  const rect=menu.getBoundingClientRect(),edge=8;
  if(rect.right>window.innerWidth-edge){
    menu.style.left='auto';
    menu.style.right='0';
  }
}
function closeMultiMenu(menu){
  if(!menu)return;
  menu.classList.remove('open');
  clearMultiMenuSearch(menu);
}
// All close paths share one cleanup rule so a stale search cannot reappear.
closeMultiMenus=function(exceptId){
  for(const menu of document.querySelectorAll('.multi-menu')){
    if(menu.id!==exceptId+'Menu')closeMultiMenu(menu);
  }
};
function applyMultiSearch(id){
  multiSelectControllers.get(id)?.applySearch();
}
function enhanceMultiSearch(id,kind){
  const controller=new DashboardMultiSelect(id,kind);
  multiSelectControllers.set(id,controller);
  controller.mount();
}
const buildMultiWithoutSearch=buildMulti;
buildMulti=function(id,items,kind,defaultValues,onChange){
  buildMultiWithoutSearch(id,items,kind,defaultValues,onChange);
  enhanceMultiSearch(id,kind);
};
const buildHeaderMultiWithoutSearch=buildHeaderMulti;
buildHeaderMulti=function(id,items,kind,defaultValues,allLabel,onChange){
  buildHeaderMultiWithoutSearch(id,items,kind,defaultValues,allLabel,onChange);
  enhanceMultiSearch(id,kind);
};
// An empty multi-select is an explicit zero-result selection. The original
// label treated both zero and all selected values as "All", which made exports
// look correctly filtered while silently including every row.
multiAllLabel=function(id,kind,allLabel){
  const values=[...selectedMulti(id)];
  const count=$(id+'Menu').querySelectorAll('input[data-value]').length;
  const button=$(id+'Toggle');
  if(!count){button.textContent='No '+kind+' available';return;}
  if(values.length===count){button.textContent=allLabel;return;}
  if(!values.length){button.textContent='No '+kind+' selected';return;}
  button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected';
};
multiSummary=function(id,kind){
  const values=[...selectedMulti(id)];
  const count=$(id+'Menu').querySelectorAll('input[data-value]').length;
  const button=$(id+'Toggle');
  if(!count){button.textContent='No '+kind+' available';return;}
  if(values.length===count){button.textContent='All '+fmt(count)+' '+kind;return;}
  if(!values.length){button.textContent='No '+kind+' selected';return;}
  button.textContent=values.length===1?values[0]:fmt(values.length)+' '+kind+' selected';
};
// FAST and STREAM menus were populated by the base script before this extension
// loaded, so rebuild them once through the searchable wrapper.
refreshAudienceFilters();
// Close an open menu when the pointer lands outside that menu's own control.
// The base handler only checked whether the click was inside any multi-select,
// which left the previous menu open when users clicked another filter area.
document.addEventListener('pointerdown',event=>{
  for(const menu of document.querySelectorAll('.multi-menu.open')){
    const owner=menu.closest('.multi-select');
    if(!owner||!owner.contains(event.target))closeMultiMenu(menu);
  }
},true);
document.addEventListener('keydown',event=>{
  if(event.key==='Escape')closeMultiMenus('');
});
function showLoading(message='Updating dashboard...'){const toast=$('loadingToast');if(!toast)return;toast.classList.remove('hidden','error');$('loadingText').textContent=message;}
function hideLoading(){const toast=$('loadingToast');if(toast)toast.classList.add('hidden');}
function showFatalDashboardError(stage,error){
  const message=error instanceof Error?error.message:String(error);
  const toast=$('loadingToast');
  if(toast){
    toast.classList.remove('hidden');
    toast.classList.add('error');
    $('loadingText').textContent='Dashboard failed during '+stage+': '+message;
  }
  document.body.dataset.dashboardError='true';
  console.error('Dashboard failed during '+stage,error);
}
let dateMode='range';
function isoUtc(date){return date.toISOString().slice(0,10);}
function utcDay(value){return new Date(String(value)+'T00:00:00Z');}
function shortDate(value){const [year,month,day]=String(value).split('-');return day+'/'+month+'/'+year.slice(-2);}
function firstSaturday(year){const date=new Date(Date.UTC(year,0,1)),offset=(6-date.getUTCDay()+7)%7;date.setUTCDate(date.getUTCDate()+offset);return date;}
function barcYearWeek(value){const date=typeof value==='string'?utcDay(value):value;let year=date.getUTCFullYear(),start=firstSaturday(year);if(date<start){year--;start=firstSaturday(year)}return {year,week:Math.floor((date-start)/604800000)+1};}
function fiscalStartYear(value){const date=typeof value==='string'?utcDay(value):value;return date.getUTCMonth()>=3?date.getUTCFullYear():date.getUTCFullYear()-1;}
function fillSelect(select,items,value){select.innerHTML=items.map(item=>'<option value="'+esc(item.value)+'">'+esc(item.label)+'</option>').join('');if(items.some(item=>String(item.value)===String(value)))select.value=String(value);}
function populateBarcWeeks(){const year=Number($('barcYear').value),start=firstSaturday(year),next=firstSaturday(year+1),count=Math.round((next-start)/604800000),items=[{value:'all',label:'All BARC weeks'}];for(let week=1;week<=count;week++){const weekStart=new Date(start.getTime()+(week-1)*604800000),weekEnd=new Date(weekStart.getTime()+6*86400000);if(isoUtc(weekEnd)<minDate||isoUtc(weekStart)>maxDate)continue;items.push({value:String(week),label:'BW '+String(week).padStart(2,'0')+' · '+shortDate(isoUtc(weekStart))+'-'+shortDate(isoUtc(weekEnd))})}fillSelect($('barcWeek'),items,$('barcWeek').value||'all');}
function updatePeriodMeta(){$('range').textContent='True range: '+DATA.true_range.start+' to '+DATA.true_range.end+' | Used: '+shortDate($('from').value)+' to '+shortDate($('to').value);}
function applyPeriodRange(start,end){$('from').value=start<minDate?minDate:start;$('to').value=end>maxDate?maxDate:end;clearFilterCache();refreshDependentOptions();refreshAudienceFilters();updatePeriodMeta();scheduleRender();}
function applyCalendarYear(){const year=Number($('calendarYear').value);applyPeriodRange(year+'-01-01',year+'-12-31');}
function applyFinancialYear(){const year=Number($('financialYear').value);applyPeriodRange(year+'-04-01',(year+1)+'-03-31');}
function applyBarcPeriod(){const year=Number($('barcYear').value),week=$('barcWeek').value,start=firstSaturday(year);if(week==='all'){const end=new Date(firstSaturday(year+1).getTime()-86400000);applyPeriodRange(isoUtc(start),isoUtc(end));return}const weekStart=new Date(start.getTime()+(Number(week)-1)*604800000),weekEnd=new Date(weekStart.getTime()+6*86400000);applyPeriodRange(isoUtc(weekStart),isoUtc(weekEnd));}
function setDateMode(mode,apply=true){dateMode=mode;for(const button of document.querySelectorAll('[data-date-mode]'))button.classList.toggle('active',button.dataset.dateMode===mode);for(const field of document.querySelectorAll('.period-field'))field.hidden=true;if(mode==='range'){$('dateFromLabel').hidden=false;$('dateToLabel').hidden=false}else if(mode==='cy')$('calendarYearLabel').hidden=false;else if(mode==='fy')$('financialYearLabel').hidden=false;else{$('barcYearLabel').hidden=false;$('barcWeekLabel').hidden=false}if(!apply){updatePeriodMeta();return}if(mode==='cy')applyCalendarYear();else if(mode==='fy')applyFinancialYear();else if(mode==='barc')applyBarcPeriod();else{updatePeriodMeta();hideLoading();}}
function ensurePeriodControls(){if($('dateModeGroup'))return;const filters=document.querySelector('.filters'),fromLabel=$('from').closest('.filter-label'),toLabel=$('to').closest('.filter-label');fromLabel.id='dateFromLabel';toLabel.id='dateToLabel';fromLabel.classList.add('period-field');toLabel.classList.add('period-field');fromLabel.dataset.masterDateControl='';toLabel.dataset.masterDateControl='';filters.insertAdjacentHTML('afterbegin','<div class="date-mode-group" id="dateModeGroup" data-master-date-control role="group" aria-label="Date period"><button type="button" data-date-mode="range" title="Custom date range">Range</button><button type="button" data-date-mode="cy" title="Calendar Year, January to December">CY</button><button type="button" data-date-mode="fy" title="Indian Financial Year, April to March">FY</button><button type="button" data-date-mode="barc" title="BARC Year and Week, Saturday to Friday">BY/BW</button></div><label class="filter-label period-field" id="calendarYearLabel" data-master-date-control hidden>Calendar Year<select id="calendarYear"></select></label><label class="filter-label period-field" id="financialYearLabel" data-master-date-control hidden>Financial Year<select id="financialYear"></select></label><label class="filter-label period-field" id="barcYearLabel" data-master-date-control hidden>BARC Year<select id="barcYear"></select></label><label class="filter-label period-field" id="barcWeekLabel" data-master-date-control hidden>BARC Week<select id="barcWeek"></select></label>');const minYear=utcDay(minDate).getUTCFullYear(),maxYear=utcDay(maxDate).getUTCFullYear(),calendarYears=[];for(let year=minYear;year<=maxYear;year++)calendarYears.push({value:String(year),label:'CY '+year});fillSelect($('calendarYear'),calendarYears,String(maxYear));const minFy=fiscalStartYear(minDate),maxFy=fiscalStartYear(maxDate),financialYears=[];for(let year=minFy;year<=maxFy;year++)financialYears.push({value:String(year),label:'FY '+year+'-'+String(year+1).slice(-2)});fillSelect($('financialYear'),financialYears,String(maxFy));const minBarc=barcYearWeek(minDate).year,maxBarc=barcYearWeek(maxDate).year,barcYears=[];for(let year=minBarc;year<=maxBarc;year++)barcYears.push({value:String(year),label:'BY '+year});fillSelect($('barcYear'),barcYears,String(maxBarc));populateBarcWeeks();document.querySelectorAll('[data-date-mode]').forEach(button=>button.addEventListener('click',()=>setDateMode(button.dataset.dateMode)));$('calendarYear').addEventListener('change',applyCalendarYear);$('financialYear').addEventListener('change',applyFinancialYear);$('barcYear').addEventListener('change',()=>{populateBarcWeeks();applyBarcPeriod()});$('barcWeek').addEventListener('change',applyBarcPeriod);for(const id of ['from','to'])$(id).addEventListener('change',()=>{setDateMode('range',false);updatePeriodMeta()});setDateMode('range',false);}
const DELIVERY_AD_TYPES=['Spot','L-band'];
function selectedDeliveryAdTypes(){
  return new Set(DELIVERY_AD_TYPES);
}
function deliveryAdTypeLabel(){
  return DELIVERY_AD_TYPES.join(' | ');
}
function deliveryAdTypeFileToken(){
  return DELIVERY_AD_TYPES.map(value=>
    value.toLowerCase().replace(/[^a-z0-9]+/g,'_')
  ).join('_');
}
function ensureCreativeFilters(){if($('spotAdIdToggle'))return;for(const id of ['typeToggle','adIdToggle','creativeToggle']){const control=$(id);if(control)control.closest('.filter-label').remove()}const panels=document.querySelectorAll('.rank-panel'),controls=(prefix,type)=>'<div class="rank-controls" aria-label="'+type+' creative filters"><label class="filter-label">'+type+' Ad ID<span class="multi-select"><button id="'+prefix+'AdIdToggle" class="multi-toggle" type="button">All ad IDs</button><span id="'+prefix+'AdIdMenu" class="multi-menu"></span></span></label><label class="filter-label">'+type+' Creative title<span class="multi-select"><button id="'+prefix+'CreativeToggle" class="multi-toggle" type="button">All creative titles</button><span id="'+prefix+'CreativeMenu" class="multi-menu"></span></span></label></div>';panels[0].querySelector('.panel-head').insertAdjacentHTML('afterend',controls('spot','Spot'));panels[1].querySelector('.panel-head').insertAdjacentHTML('afterend',controls('lband','L-band'));}
function sectionDateRows(type){return dateScope().filter(event=>event.ad_type===type);}
function sectionFilteredRows(type,prefix){const ids=selectedMulti(prefix+'AdId'),creatives=selectedMulti(prefix+'Creative');if(!ids.size||!creatives.size)return [];return sectionDateRows(type).filter(event=>ids.has(event.event_id)&&creatives.has(event.creative_title));}
function multiSelectionState(id){
  const menu=$(id+'Menu');
  const inputs=menu?[...menu.querySelectorAll('input[data-value]')]:[];
  const selected=selectedMulti(id);
  return {selected,restricted:inputs.length>0&&selected.size<inputs.length};
}
function refreshSectionOptions(type,prefix){
  const rows=sectionDateRows(type),idKey=prefix+'AdId',creativeKey=prefix+'Creative';
  const idState=multiSelectionState(idKey),creativeState=multiSelectionState(creativeKey);
  const idRows=creativeState.restricted
    ?rows.filter(event=>creativeState.selected.has(event.creative_title))
    :rows;
  const creativeRows=idState.restricted
    ?rows.filter(event=>idState.selected.has(event.event_id))
    :rows;
  const refresh=()=>{
    refreshSectionOptions(type,prefix);
    refreshAudienceFilters();
    scheduleRender();
  };
  const ids=countedOptions(idRows,'event_id');
  buildHeaderMulti(
    idKey,ids,'ad IDs',ids.map(item=>item.value),
    'All '+type+' ad IDs ('+fmt(idRows.length)+')',refresh,
  );
  const titles=countedOptions(creativeRows,'creative_title');
  buildHeaderMulti(
    creativeKey,titles,'creative titles',titles.map(item=>item.value),
    'All '+type+' creative titles ('+fmt(creativeRows.length)+')',refresh,
  );
}
function refreshDependentOptions(){ensureCreativeFilters();refreshSectionOptions('Spot','spot');refreshSectionOptions('L-band','lband');}
function scope(){const types=selectedDeliveryAdTypes();return DELIVERY_AD_TYPES.flatMap(type=>types.has(type)?sectionDateRows(type):[]);}
function filterKey(){return [$('from').value,$('to').value,[...selectedDeliveryAdTypes()].sort().join('|'),[...selectedMulti('spotAdId')].sort().join('|'),[...selectedMulti('spotCreative')].sort().join('|'),[...selectedMulti('lbandAdId')].sort().join('|'),[...selectedMulti('lbandCreative')].sort().join('|')].join('\u0000');}
function filtered(){const key=filterKey();if(filterCache.key===key&&filterCache.value)return filterCache.value;const types=selectedDeliveryAdTypes(),result=[...(types.has('Spot')?sectionFilteredRows('Spot','spot'):[]),...(types.has('L-band')?sectionFilteredRows('L-band','lband'):[])].sort((a,b)=>String(a.on_air_start_ist).localeCompare(String(b.on_air_start_ist)));filterCache={key,value:result};return result;}
// Multi-selects restored by Reset. The signature also covers independently
// rendered YouTube/NCT controls so a clean button always means a clean dashboard.
const RESET_SCOPE_IDS=[
  'spotAdId','spotCreative','lbandAdId','lbandCreative',
  'fastPlatform','fastChannel','streamChannel','amagiPlatform','amagiChannel',
  'fctFeed','fctLanguage','fctBrand','fctCaption','fctProgram','fctCategory',
  'fctCompany','fctWeekday','fctAdPosition','fctBreakSize','fctCoverage',
  'fctSourceFile','fctSourceSheet',
];
const SIGNATURE_MULTI_IDS=[
  ...RESET_SCOPE_IDS,'youtubeChannel','nctChannel','nctProgram','nctGenre','nctGeo',
  'nctYoutubeVideo',
];
let defaultFilterSignature=null;
function multiFilterSignature(id){
  const menu=$(id+'Menu');
  if(!menu)return 'ALL';
  const inputs=[...menu.querySelectorAll('input[data-value]')];
  if(!inputs.length)return 'ALL';
  const selected=inputs.filter(input=>input.checked).map(input=>input.dataset.value).sort();
  if(selected.length===inputs.length)return 'ALL';
  return selected.length?selected.join(','):'NONE';
}
function youtubeVideoFilterSignature(){
  const menu=$('youtubeVideoMenu');
  if(!menu)return 'ALL';
  const inputs=[...menu.querySelectorAll('input[data-video]')];
  if(!inputs.length)return 'ALL';
  const selected=inputs.filter(input=>input.checked).map(input=>input.dataset.video).sort();
  if(selected.length===inputs.length)return 'ALL';
  return selected.length?selected.join(','):'NONE';
}
function computeFilterSignature(){
  const parts=[$('from').value,$('to').value,dateMode,fctClassMode];
  parts.push('deliveryTypes:'+[...selectedDeliveryAdTypes()].sort().join(','));
  parts.push('fctRangeMode:'+fctRangeMode);
  if(fctRangeMode==='custom'){
    parts.push(
      'fctFrom:'+($('fctFrom')?.value||''),
      'fctTo:'+($('fctTo')?.value||''),
    );
  }
  for(const id of FCT_SCALAR_FILTER_IDS){
    parts.push(id+':'+($(id)?.value||''));
  }
  for(const id of SIGNATURE_MULTI_IDS)parts.push(id+':'+multiFilterSignature(id));
  const nctDefaultChannel=(NCT.channels||[]).includes('INDIA TV')
    ?'INDIA TV'
    :String((NCT.channels||[])[0]||'');
  parts.push(
    'youtubeDateMode:'+youtubeDateMode,
    'youtubeFrom:'+($('youtubeFrom')?.value||''),
    'youtubeTo:'+($('youtubeTo')?.value||''),
    'youtubeVideos:'+youtubeVideoFilterSignature(),
    'youtubeChartInterval:'+($('youtubeChartInterval')?.value||'5'),
    'youtubeCustomInterval:'+($('youtubeCustomInterval')?.value||'120'),
    'youtubeExportInterval:'+($('youtubeExportInterval')?.value||'5'),
    'nctDateMode:'+nctDateMode,
    'nctFrom:'+($('nctFrom')?.value||''),
    'nctTo:'+($('nctTo')?.value||''),
    'nctStory:'+nctSelectedStory,
    'nctContextChannel:'+($('nctContextChannel')?.value||nctDefaultChannel),
  );
  return parts.join('|');
}
function captureDefaultFilterSignature(){defaultFilterSignature=computeFilterSignature();updateResetState();}
function updateResetState(){
  const btn=$('reset');
  if(!btn||defaultFilterSignature===null)return;
  const dirty=computeFilterSignature()!==defaultFilterSignature;
  btn.classList.toggle('is-dirty',dirty);
  btn.title=dirty?'Filters changed from the default view; click to restore defaults':'Dashboard is showing the default view';
}
function resetDashboardFilters(){
  showLoading('Resetting dashboard...');
  $('from').value=minDate;
  $('to').value=maxDate;
  setDateMode('range',false);
  fctClassMode='Commercial';
  fctRangeMode='all';
  for(const id of RESET_SCOPE_IDS){
    const menu=$(id+'Menu');
    if(menu)menu.innerHTML='';
  }
  for(const id of FCT_SCALAR_FILTER_IDS){
    if($(id))$(id).value='';
  }
  multiInitialized.clear();
  if(dashboardSourceLoaded('fct'))setFctRange('all',false);
  clearFilterCache();
  refreshDependentOptions();
  refreshAudienceFilters();
  updatePeriodMeta();
  scheduleRender();
}
document.addEventListener('change',event=>{
  if(event.target.closest(
    '.filters,.rank-controls,.audience-controls,.fct-class-filter,'
    +'.fct-date-controls,.youtube-filter-bar,.youtube-controls'
  ))showLoading('Updating dashboard...');
},true);
document.addEventListener('click',event=>{
  if(event.target.closest(
    '[data-date-mode],[data-youtube-date-mode],[data-fct-class],'
    +'[data-fct-range],[data-youtube-range],#reset'
  ))showLoading('Updating dashboard...');
},true);
function refreshAmagiFilters(){const rows=(AMAGI.minute||[]).filter(r=>String(r.log_date)>=String($('from').value)&&String(r.log_date)<=String($('to').value)),platforms=[...new Set(rows.map(r=>String(r.platform_name)))].sort();buildMulti('amagiPlatform',platforms,'platforms',platforms,()=>{refreshAmagiFilters();render()});const selectedPlatforms=selectedMulti('amagiPlatform'),channels=[...new Set(rows.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('amagiChannel',channels,'channels',channels,render);}
function amagiMinuteMap(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),map=new Map();for(const row of (AMAGI.minute||[])){if(!platforms.has(String(row.platform_name))||!channels.has(String(row.channel_name)))continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return {map};}
function ensureAmagiPanel(){if($('amagiRows'))return;const grid=document.querySelector('.audience-grid');grid.insertAdjacentHTML('beforeend','<div class="panel audience-panel amagi-panel"><div class="panel-head"><div><h2>AMAGI Delivered Ad Events</h2><small>Actual platform-reported concurrent viewers</small></div><span class="source-tag amagi-tag">AMAGI</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="amagiPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="amagiPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="amagiChannelToggle" class="multi-toggle" type="button">All channels</button><span id="amagiChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="amagiRows"></div><div class="audience-note" id="amagiNote"></div></div>');const header=document.querySelector('.combined-columns');header.querySelector('.youtube-col').insertAdjacentHTML('beforebegin','<span class="amagi-col">AMAGI</span>');document.querySelector('.combined-panel .panel-head small').textContent='FAST + STREAM selected 5-minute concurrency | Amagi actual 5-minute concurrency | YouTube minute concurrency';document.querySelector('.combined-panel .combined-tag').textContent='FAST + STREAM + AMAGI';}
function ensureFctPanel(){
  if($('fctRows'))return;
  ensureAmagiPanel();
  document.querySelector('.amagi-panel').insertAdjacentHTML(
    'afterend',
    '<div class="panel audience-panel fct-panel">'
    +'<div class="panel-head"><div><h2>FCT Monitored Ad Occurrences</h2>'
    +'<small>External feed-monitoring evidence</small></div>'
    +'<div class="panel-actions"><button id="exportFctCsv" type="button">Export CSV</button>'
    +'<span class="source-tag fct-tag">FCT</span></div></div>'
    +'<div class="fct-date-controls" aria-label="Independent FCT date filters">'
    +'<label class="filter-label">FCT date from<input id="fctFrom" type="date" disabled></label>'
    +'<label class="filter-label">FCT date to<input id="fctTo" type="date" disabled></label>'
    +'<div class="fct-range-actions" role="group" aria-label="FCT quick ranges">'
    +'<button type="button" data-fct-range="latest">Latest day</button>'
    +'<button type="button" data-fct-range="7">7D</button>'
    +'<button type="button" data-fct-range="30">30D</button>'
    +'<button type="button" data-fct-range="all" class="active">All</button></div>'
    +'<div class="fct-date-meta" id="fctDateMeta">Loading FCT date coverage...</div></div>'
    +'<div class="fct-class-filter" role="group" aria-label="FCT occurrence classification">'
    +'<button type="button" data-fct-class="Commercial" class="active">Commercial</button>'
    +'<button type="button" data-fct-class="In-House">In-House</button>'
    +'<button type="button" data-fct-class="All">All</button>'
    +'<button type="button" data-fct-class="Internal / Promo">Internal &amp; Promo</button></div>'
    +'<div class="audience-controls fct-controls">'
    +'<label class="filter-label">Feed<span class="multi-select"><button id="fctFeedToggle" '
    +'class="multi-toggle" type="button">All feeds</button><span id="fctFeedMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Language<span class="multi-select"><button id="fctLanguageToggle" '
    +'class="multi-toggle" type="button">All languages</button><span id="fctLanguageMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Brand<span class="multi-select"><button id="fctBrandToggle" '
    +'class="multi-toggle" type="button">All brands</button><span id="fctBrandMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Caption<span class="multi-select"><button id="fctCaptionToggle" '
    +'class="multi-toggle" type="button">All captions</button><span id="fctCaptionMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Program Name<span class="multi-select"><button id="fctProgramToggle" '
    +'class="multi-toggle" type="button">All programs</button><span id="fctProgramMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Category<span class="multi-select"><button id="fctCategoryToggle" '
    +'class="multi-toggle" type="button">All categories</button><span id="fctCategoryMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Company<span class="multi-select"><button id="fctCompanyToggle" '
    +'class="multi-toggle" type="button">All companies</button><span id="fctCompanyMenu" '
    +'class="multi-menu"></span></span></label></div>'
    +'<details class="fct-advanced"><summary>More FCT Filters</summary>'
    +'<div class="fct-advanced-controls">'
    +'<label class="filter-label">Day of week<span class="multi-select">'
    +'<button id="fctWeekdayToggle" class="multi-toggle" type="button">All weekdays</button>'
    +'<span id="fctWeekdayMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Ad position<span class="multi-select">'
    +'<button id="fctAdPositionToggle" class="multi-toggle" type="button">All positions</button>'
    +'<span id="fctAdPositionMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Ads in break<span class="multi-select">'
    +'<button id="fctBreakSizeToggle" class="multi-toggle" type="button">All break sizes</button>'
    +'<span id="fctBreakSizeMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Coverage status<span class="multi-select">'
    +'<button id="fctCoverageToggle" class="multi-toggle" type="button">'
    +'All coverage states</button><span id="fctCoverageMenu" '
    +'class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Source workbook<span class="multi-select">'
    +'<button id="fctSourceFileToggle" class="multi-toggle" type="button">All workbooks</button>'
    +'<span id="fctSourceFileMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Source sheet<span class="multi-select">'
    +'<button id="fctSourceSheetToggle" class="multi-toggle" type="button">All sheets</button>'
    +'<span id="fctSourceSheetMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">On-air from<input id="fctTimeFrom" type="time"></label>'
    +'<label class="filter-label">On-air to<input id="fctTimeTo" type="time"></label>'
    +'<label class="filter-label">Program starts from'
    +'<input id="fctProgramTimeFrom" type="time"></label>'
    +'<label class="filter-label">Program starts to'
    +'<input id="fctProgramTimeTo" type="time"></label>'
    +'<label class="filter-label">Ad duration min (sec)'
    +'<input id="fctDurationMin" type="number" min="0" step="1" '
    +'placeholder="No minimum"></label>'
    +'<label class="filter-label">Ad duration max (sec)'
    +'<input id="fctDurationMax" type="number" min="0" step="1" '
    +'placeholder="No maximum"></label>'
    +'<label class="filter-label">Program duration min (sec)'
    +'<input id="fctProgramDurationMin" type="number" min="0" step="1" '
    +'placeholder="No minimum"></label>'
    +'<label class="filter-label">Program duration max (sec)'
    +'<input id="fctProgramDurationMax" type="number" min="0" step="1" '
    +'placeholder="No maximum"></label>'
    +'</div></details>'
    +'<div class="fct-kpis" id="fctKpis"></div>'
    +'<div class="fct-columns"><span>On-air IST</span><span>Feed</span>'
    +'<span>Brand / Caption</span><span>Program</span><span>Duration</span>'
    +'<span>Classification</span></div><div class="audience-list" id="fctRows"></div>'
    +'<div class="fct-preview-note" id="fctNote"></div></div>'
  );
  for(const button of document.querySelectorAll('[data-fct-class]')){
    button.addEventListener('click',()=>{
      fctClassMode=button.dataset.fctClass;
      if(['latest','7','30'].includes(fctRangeMode)){
        setFctRange(fctRangeMode,false);
      }
      for(const [id] of FCT_FILTER_SPECS){
        $(id+'Menu').innerHTML='';
        multiInitialized.delete(id);
      }
      renderFctAndScope();
    });
  }
  for(const button of document.querySelectorAll('[data-fct-range]')){
    button.addEventListener('click',()=>setFctRange(button.dataset.fctRange));
  }
  $('fctFrom').addEventListener('change',()=>syncFctDates('from'));
  $('fctTo').addEventListener('change',()=>syncFctDates('to'));
  for(const id of FCT_SCALAR_FILTER_IDS){
    $(id).addEventListener('change',()=>{
      const pair=FCT_NUMERIC_FILTER_PAIRS.find(ids=>ids.includes(id));
      if(pair)syncFctNumericRange(id,...pair);
      renderFctAndScope(false);
    });
  }
  $('exportFctCsv').addEventListener('click',exportFctCsv);
}
function ensureFctAudiencePanel(){if($('fctAllRows'))return;document.querySelector('.combined-panel').insertAdjacentHTML('afterend','<section class="panel fct-audience-panel"><div class="panel-head"><div><h2>All FCT Monitored Ad Occurrences</h2><small>FCT-selected occurrences | FAST + STREAM + AMAGI 5-minute concurrency | YouTube minute concurrency</small></div><div class="panel-actions"><button id="exportFctAudienceCsv" type="button">Export CSV</button><span class="source-tag fct-tag">FCT ANCHORED</span></div></div><div class="fct-audience-columns"><span>On-air IST</span><span>Feed</span><span>Brand / Caption</span><span class="duration">Duration</span><span class="fast-col">FAST</span><span class="stream-col">STREAM</span><span class="amagi-col">AMAGI</span><span class="youtube-col">YOUTUBE</span><span class="total-col">Combined</span></div><div class="combined-list" id="fctAllRows"></div><div class="fct-preview-note" id="fctAllNote"></div></section>');$('exportFctAudienceCsv').addEventListener('click',exportFctAudienceCsv);}
const FCT_WEEKDAYS=[
  'Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday',
];
function fctValue(row,key){
  if(key==='_weekday'){
    const [year,month,day]=String(row.log_date||'').split('-').map(Number);
    if(!year||!month||!day)return 'Unknown / NA';
    return FCT_WEEKDAYS[new Date(Date.UTC(year,month-1,day)).getUTCDay()];
  }
  if(key==='is_filename_spillover'){
    return row.is_filename_spillover===true
      ?'Filename spillover'
      :'Within declared range';
  }
  const value=String(row[key]??'').trim();
  return value||'Unknown / NA';
}
function formatIstSeconds(value){const normalized=String(value).replace(' ','T'),[datePart,timePart='00:00:00']=normalized.split('T'),[year,month,day]=datePart.split('-'),[rawHour='0',minute='00',second='00']=timePart.split(':'),hour=Number(rawHour),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return day+'-'+month+'-'+year.slice(-2)+' '+String(twelve).padStart(2,'0')+':'+minute+':'+second.slice(0,2)+' '+suffix;}
function fctBounds(){
  const dates=(FCT.events||[])
    .map(row=>String(row.log_date||'').slice(0,10))
    .filter(Boolean)
    .sort();
  return {
    start:dates[0]||String(FCT.true_start||'').slice(0,10),
    end:dates.at(-1)||String(FCT.true_end||'').slice(0,10),
  };
}
function fctClassBounds(){
  const dates=(FCT.events||[])
    .filter(row=>fctClassMode==='All'||String(row.event_class)===fctClassMode)
    .map(row=>String(row.log_date||'').slice(0,10))
    .filter(Boolean)
    .sort();
  return {start:dates[0]||'',end:dates.at(-1)||''};
}
function fctDateLabel(value){
  const [year='',month='',day='']=String(value||'').split('-');
  return year&&month&&day?day+'/'+month+'/'+year.slice(-2):'Not available';
}
function updateFctDateControls(){
  const bounds=fctBounds(),from=$('fctFrom'),to=$('fctTo');
  for(const input of [from,to]){
    input.min=bounds.start;
    input.max=bounds.end;
    input.disabled=!bounds.start||!bounds.end;
  }
  for(const button of document.querySelectorAll('[data-fct-range]')){
    button.classList.toggle('active',button.dataset.fctRange===fctRangeMode);
  }
  $('fctDateMeta').textContent=bounds.start&&bounds.end
    ?'Available: '+fctDateLabel(bounds.start)+' to '+fctDateLabel(bounds.end)
      +' | Used: '+fctDateLabel(from.value)+' to '+fctDateLabel(to.value)
    :'No FCT date coverage is available.';
}
function preserveFctAllSelections(){
  for(const [id] of FCT_FILTER_SPECS){
    const menu=$(id+'Menu');
    if(!menu)continue;
    const inputs=[...menu.querySelectorAll('input[data-value]')];
    if(!inputs.length||inputs.every(input=>input.checked)){
      menu.innerHTML='';
      multiInitialized.delete(id);
    }
  }
}
function syncFctDates(changed){
  const from=$('fctFrom'),to=$('fctTo');
  if(from.value>to.value){
    if(changed==='from')to.value=from.value;
    else from.value=to.value;
  }
  fctRangeMode='custom';
  preserveFctAllSelections();
  updateFctDateControls();
  renderFctAndScope(true);
}
function setFctRange(kind,renderNow=true){
  const bounds=fctBounds();
  if(!bounds.start||!bounds.end)return;
  const classBounds=fctClassBounds();
  const rangeEnd=kind==='all'?bounds.end:(classBounds.end||bounds.end);
  const end=new Date(rangeEnd+'T00:00:00Z');
  if(kind==='all'){
    $('fctFrom').value=bounds.start;
    $('fctTo').value=bounds.end;
  }else{
    const days=kind==='latest'?1:Number(kind);
    end.setUTCDate(end.getUTCDate()-(days-1));
    $('fctFrom').value=[end.toISOString().slice(0,10),bounds.start].sort().at(-1);
    $('fctTo').value=rangeEnd;
  }
  fctRangeMode=kind;
  preserveFctAllSelections();
  updateFctDateControls();
  if(renderNow)renderFctAndScope(true);
}
function initializeFctDates(){
  setFctRange('all',false);
}
function fctDateRows(){
  const bounds=fctBounds(),from=$('fctFrom')?.value||bounds.start,to=$('fctTo')?.value||bounds.end;
  return (FCT.events||[]).filter(
    row=>String(row.log_date)>=from&&String(row.log_date)<=to
  );
}
function fctClassRows(){return fctDateRows().filter(row=>fctClassMode==='All'||String(row.event_class)===fctClassMode);}
const FCT_FILTER_SPECS=[
  ['fctFeed','feed_name','feeds'],
  ['fctLanguage','language','languages'],
  ['fctBrand','brand_name','brands'],
  ['fctCaption','caption','captions'],
  ['fctProgram','program_name','programs'],
  ['fctCategory','category','categories'],
  ['fctCompany','company','companies'],
  ['fctWeekday','_weekday','weekdays'],
  ['fctAdPosition','ad_position','positions'],
  ['fctBreakSize','total_ads','break sizes'],
  ['fctCoverage','is_filename_spillover','coverage states'],
  ['fctSourceFile','source_file','workbooks'],
  ['fctSourceSheet','source_sheet','sheets'],
];
function fctOptionSort(key,left,right){
  if(key==='ad_position'||key==='total_ads'){
    return Number(left)-Number(right);
  }
  if(key==='_weekday'){
    return FCT_WEEKDAYS.indexOf(left)-FCT_WEEKDAYS.indexOf(right);
  }
  return left.localeCompare(right);
}
function refreshFctFilters(){
  if(!FCT.available)return;
  const base=fctClassRows();
  // Each FCT dropdown owns only its selection. Building every option list from
  // the same date/class scope prevents Clear in one control from erasing the
  // valid choices or current selections in neighboring controls.
  for(const [id,key,kind] of FCT_FILTER_SPECS){
    const values=[...new Set(base.map(row=>fctValue(row,key)))]
      .sort((left,right)=>fctOptionSort(key,left,right));
    buildMulti(id,values,kind,values,()=>renderFctAndScope(false));
  }
}
function fctClockMinutes(value){
  const match=/(\d{2}):(\d{2})/.exec(String(value||''));
  return match?Number(match[1])*60+Number(match[2]):null;
}
function fctClockMatches(row,key,fromId,toId){
  const from=fctClockMinutes($(fromId)?.value);
  const to=fctClockMinutes($(toId)?.value);
  if(from===null&&to===null)return true;
  const value=fctClockMinutes(String(row[key]||'').slice(11,16));
  if(value===null)return false;
  if(from!==null&&to!==null){
    return from<=to
      ?value>=from&&value<=to
      :value>=from||value<=to;
  }
  return from!==null?value>=from:value<=to;
}
function fctNumericMatches(row,key,minId,maxId){
  const minText=String($(minId)?.value||'').trim();
  const maxText=String($(maxId)?.value||'').trim();
  if(!minText&&!maxText)return true;
  const value=Number(row[key]);
  if(!Number.isFinite(value))return false;
  const min=minText?Number(minText):null,max=maxText?Number(maxText):null;
  return (min===null||value>=min)&&(max===null||value<=max);
}
function syncFctNumericRange(changed,minId,maxId){
  const minInput=$(minId),maxInput=$(maxId);
  if(!minInput.value||!maxInput.value)return;
  if(Number(minInput.value)<=Number(maxInput.value))return;
  if(changed===minId)maxInput.value=minInput.value;
  else minInput.value=maxInput.value;
}
function fctAdvancedRangesMatch(row){
  return fctClockMatches(row,'event_ist','fctTimeFrom','fctTimeTo')
    &&fctClockMatches(
      row,'program_start_ist','fctProgramTimeFrom','fctProgramTimeTo'
    )
    &&fctNumericMatches(
      row,'duration_seconds','fctDurationMin','fctDurationMax'
    )
    &&fctNumericMatches(
      row,'program_duration_seconds',
      'fctProgramDurationMin','fctProgramDurationMax'
    );
}
let fctSelectionCache={key:null,value:null};
function fctSelectionKey(){
  return [
    $('fctFrom')?.value||'',$('fctTo')?.value||'',fctClassMode,
    ...FCT_FILTER_SPECS.map(([id])=>
      [...selectedMulti(id)].sort().join('\u0001')
    ),
    ...FCT_SCALAR_FILTER_IDS.map(id=>$(id)?.value||''),
  ].join('\u0000');
}
function selectedFctRows(){
  if(!FCT.available)return [];
  const cacheKey=fctSelectionKey();
  if(fctSelectionCache.key===cacheKey&&fctSelectionCache.value){
    return fctSelectionCache.value;
  }
  const selections=FCT_FILTER_SPECS.map(([id,key])=>[
    key,selectedMulti(id),
  ]);
  if(selections.some(([_key,values])=>!values.size))return [];
  const value=fctClassRows().filter(row=>
    selections.every(([key,values])=>values.has(fctValue(row,key)))
    &&fctAdvancedRangesMatch(row)
  );
  fctSelectionCache={key:cacheKey,value};
  return value;
}
function multiSelectionIsAll(id){
  const inputs=[...$(id+'Menu').querySelectorAll('input[data-value]')];
  return inputs.length>0&&inputs.every(input=>input.checked);
}
function fctAudienceMinuteMap(source){
  const channelId=source==='fast'?'fastChannel':'streamChannel';
  const channels=selectedMulti(channelId),allChannels=multiSelectionIsAll(channelId);
  const platforms=source==='fast'?selectedMulti('fastPlatform'):null;
  const allPlatforms=source!=='fast'||multiSelectionIsAll('fastPlatform');
  const from=$('fctFrom').value,to=$('fctTo').value,map=new Map();
  let boundStart='',boundEnd='';
  for(const row of (DATA.viewer_minute||[])){
    if(row.source!==source)continue;
    const key=minuteKey(row.minute_ist);
    if(!boundStart||key<boundStart)boundStart=key;
    if(!boundEnd||key>boundEnd)boundEnd=key;
    if(String(row.log_date)<from||String(row.log_date)>to)continue;
    if(source==='fast'&&!allPlatforms&&!platforms.has(String(row.platform_name)))continue;
    if(!allChannels&&!channels.has(String(row.channel_name)))continue;
    map.set(key,(map.get(key)||0)+Number(row.distinct_cliips||0));
  }
  return {map,bounds:boundStart&&boundEnd?{start:boundStart,end:boundEnd}:null};
}
function fctAmagiMinuteMap(){
  const state=amagiMinuteMap(),bounds=sourceBounds(AMAGI.minute||[],'minute_ist');
  return {...state,bounds};
}
function fctCoveredAudienceValue(event,state){
  const window=fiveMinuteWindow(event),key=window.keys[0],bounds=state.bounds;
  if(!bounds||key<minuteKey(bounds.start)||key>minuteKey(bounds.end)){
    return {value:'Not available',window:window.label,total:null};
  }
  return audienceValue(event,state);
}
function fctAudienceRows(events,fast,stream){
  const amagi=fctAmagiMinuteMap();
  return events.slice()
    .sort((a,b)=>String(a.event_ist).localeCompare(String(b.event_ist)))
    .map(event=>{
      const anchor={on_air_start_ist:event.event_ist};
      const fastMetric=fctCoveredAudienceValue(anchor,fast);
      const streamMetric=fctCoveredAudienceValue(anchor,stream);
      const amagiMetric=fctCoveredAudienceValue(anchor,amagi);
      const youtubeMetric=youtubeFiveMinuteValue(anchor);
      const values=[
        fastMetric.total,streamMetric.total,amagiMetric.total,youtubeMetric.total,
      ];
      const available=values.filter(value=>value!==null);
      const total=available.length
        ?available.reduce((sum,value)=>sum+Number(value),0)
        :null;
      return {
        event,
        fast:fastMetric,
        stream:streamMetric,
        amagi:amagiMetric,
        youtube:youtubeMetric,
        total,
        partial:available.length!==values.length,
      };
    });
}
function fctAudienceLines(events){
  const rows=fctAudienceRows(
    events,fctAudienceMinuteMap('fast'),fctAudienceMinuteMap('stream')
  );
  const preview=rows.slice(-50).reverse();
  if(!preview.length){
    return '<div class="audience-empty">'
      +'No FCT occurrences match the selected date and FCT filters.</div>';
  }
  return preview.map(row=>{
    const event=row.event;
    const total=row.total===null
      ?'Not available'
      :fmt(row.total)+(row.partial?' (partial)':'');
    return '<div class="fct-audience-line"><span>'
      +formatIstSeconds(event.event_ist)+'</span><span><strong>'
      +esc(fctValue(event,'feed_name'))+'</strong><small>'
      +esc(event.event_class)+'</small></span><span><strong>'
      +esc(fctValue(event,'brand_name'))+'</strong><small>'
      +esc(fctValue(event,'caption'))+'</small></span><span class="duration">'
      +fmt(event.duration_seconds||0)+' sec</span>'
      +'<span class="fct-audience-value fast-col">'+esc(row.fast.value)+'</span>'
      +'<span class="fct-audience-value stream-col">'+esc(row.stream.value)+'</span>'
      +'<span class="fct-audience-value amagi-col">'+esc(row.amagi.value)+'</span>'
      +'<span class="fct-audience-value youtube-col">'+esc(row.youtube.value)+'</span>'
      +'<span class="fct-audience-value total-col">'+esc(total)+'</span></div>';
  }).join('');
}
function renderFctAudience(rows){ensureFctAudiencePanel();$('fctAllRows').innerHTML=fctAudienceLines(rows);$('fctAllNote').textContent='Showing latest '+fmt(Math.min(rows.length,50))+' of '+fmt(rows.length)+' matching FCT occurrences. CSV exports the complete filtered result. Not available means that source has no data for the event minute; partial combined values use the available sources only.';}
function renderFct(refresh=true){
  ensureFctPanel();
  ensureFctAudiencePanel();
  for(const button of document.querySelectorAll('[data-fct-class]')){
    button.classList.toggle('active',button.dataset.fctClass===fctClassMode);
  }
  for(const button of document.querySelectorAll('[data-fct-range]')){
    button.classList.toggle('active',button.dataset.fctRange===fctRangeMode);
  }
  if(!FCT.available){
    $('fctKpis').innerHTML='';
    $('fctRows').innerHTML='<div class="audience-empty">'
      +esc(FCT.reason||'FCT monitoring data is unavailable.')+'</div>';
    $('fctNote').textContent='';
    $('fctAllRows').innerHTML='<div class="audience-empty">'
      +esc(FCT.reason||'FCT monitoring data is unavailable.')+'</div>';
    $('fctAllNote').textContent='';
    return;
  }
  if(!dashboardSourceLoaded('fct')){
    const message=dashboardSourceError('fct')||'Loading FCT monitoring data...';
    $('fctKpis').innerHTML='';
    $('fctRows').innerHTML='<div class="audience-empty">'+esc(message)+'</div>';
    $('fctAllRows').innerHTML='<div class="audience-empty">'+esc(message)+'</div>';
    $('fctNote').textContent='';
    $('fctAllNote').textContent='';
    for(const [id] of FCT_FILTER_SPECS){
      $(id+'Toggle').disabled=true;
    }
    for(const id of FCT_SCALAR_FILTER_IDS)$(id).disabled=true;
    return;
  }
  updateFctDateControls();
  for(const [id] of FCT_FILTER_SPECS){
    $(id+'Toggle').disabled=false;
  }
  for(const id of FCT_SCALAR_FILTER_IDS)$(id).disabled=false;
  if(refresh)refreshFctFilters();
  const rows=selectedFctRows();
  const duration=rows.reduce((sum,row)=>sum+Number(row.duration_seconds||0),0);
  const brands=new Set(
    rows.map(row=>fctValue(row,'brand_name')).filter(value=>value!=='Unknown / NA')
  );
  const feeds=new Set(rows.map(row=>fctValue(row,'feed_name')));
  const spillovers=rows.filter(row=>row.is_filename_spillover===true).length;
  $('fctKpis').innerHTML=[
    [fmt(rows.length),'Detected events'],
    [mins(duration),'Detected duration'],
    [fmt(brands.size),'Brands'],
    [fmt(feeds.size),'Feeds'],
  ].map(item=>
    '<div class="fct-kpi"><strong>'+item[0]+'</strong><small>'+item[1]+'</small></div>'
  ).join('');
  const preview=rows.slice()
    .sort((a,b)=>String(b.event_ist).localeCompare(String(a.event_ist)))
    .slice(0,50);
  $('fctRows').innerHTML=preview.length?preview.map(row=>
    '<div class="fct-line"><span>'+formatIstSeconds(row.event_ist)+'</span>'
    +'<span><strong>'+esc(fctValue(row,'feed_name'))+'</strong>'
    +'<small>Ad '+fmt(row.ad_position||0)+' of '+fmt(row.total_ads||0)+'</small></span>'
    +'<span><strong>'+esc(fctValue(row,'brand_name'))+'</strong>'
    +'<small>'+esc(fctValue(row,'caption'))+'</small></span>'
    +'<span>'+esc(fctValue(row,'program_name'))+'<small>'
    +esc(fctValue(row,'category'))+'</small></span>'
    +'<span class="fct-duration">'+fmt(row.duration_seconds||0)+' sec</span>'
    +'<span class="fct-class">'+esc(row.event_class)
    +(row.is_filename_spillover===true?'<small>Filename spillover</small>':'')
    +'</span></div>'
  ).join(''):'<div class="audience-empty">'
    +'No FCT occurrences match the selected date and FCT filters.</div>';
  $('fctNote').textContent='Showing '+fmt(preview.length)+' of '+fmt(rows.length)
    +' matching occurrences'
    +(spillovers?' | '+fmt(spillovers)+' source-file spillover row(s)':'')
    +'. CSV exports the complete filtered result.';
  renderFctAudience(rows);
}
function renderFctAndScope(refresh=true){renderFct(refresh);if(typeof renderScopeValidation==='function')renderScopeValidation();updateResetState();hideLoading();}
function fctFilterContext(){
  return {
    dateFrom:$('fctFrom').value,dateTo:$('fctTo').value,
    timeFrom:$('fctTimeFrom').value,timeTo:$('fctTimeTo').value,
    programTimeFrom:$('fctProgramTimeFrom').value,
    programTimeTo:$('fctProgramTimeTo').value,
    durationMin:$('fctDurationMin').value,durationMax:$('fctDurationMax').value,
    programDurationMin:$('fctProgramDurationMin').value,
    programDurationMax:$('fctProgramDurationMax').value,
  };
}
function fctExportSelections(){
  return {
    feeds:exportSelection('fctFeed','All FCT feeds'),
    languages:exportSelection('fctLanguage','All FCT languages'),
    brands:exportSelection('fctBrand','All FCT brands'),
    captions:exportSelection('fctCaption','All FCT captions'),
    programs:exportSelection('fctProgram','All FCT programs'),
    categories:exportSelection('fctCategory','All FCT categories'),
    companies:exportSelection('fctCompany','All FCT companies'),
    weekdays:exportSelection('fctWeekday','All weekdays'),
    positions:exportSelection('fctAdPosition','All ad positions'),
    breakSizes:exportSelection('fctBreakSize','All break sizes'),
    coverage:exportSelection('fctCoverage','All coverage states'),
    sourceFiles:exportSelection('fctSourceFile','All source workbooks'),
    sourceSheets:exportSelection('fctSourceSheet','All source sheets'),
  };
}
function fctAdvancedExportHeaders(){
  return [
    'Selected FCT Weekdays','Selected FCT Ad Positions',
    'Selected FCT Break Sizes','Selected FCT Coverage States',
    'Selected FCT Source Workbooks','Selected FCT Source Sheets',
    'Selected On-air Time From','Selected On-air Time To',
    'Selected Program Start Time From','Selected Program Start Time To',
    'Selected Ad Duration Minimum Seconds','Selected Ad Duration Maximum Seconds',
    'Selected Program Duration Minimum Seconds',
    'Selected Program Duration Maximum Seconds',
  ];
}
function fctAdvancedExportValues(filters,selections){
  return [
    selections.weekdays,selections.positions,selections.breakSizes,
    selections.coverage,selections.sourceFiles,selections.sourceSheets,
    filters.timeFrom||'All',filters.timeTo||'All',
    filters.programTimeFrom||'All',filters.programTimeTo||'All',
    filters.durationMin||'No minimum',filters.durationMax||'No maximum',
    filters.programDurationMin||'No minimum',
    filters.programDurationMax||'No maximum',
  ];
}
function exportFctCsv(){
  const rows=selectedFctRows(),filters=fctFilterContext();
  const selections=fctExportSelections();
  const header=[
    'Selected Date From','Selected Date To','FCT Classification',
    'Selected FCT Feeds','Selected FCT Languages','Selected FCT Brands',
    'Selected FCT Captions','Selected FCT Programs',
    'Selected FCT Categories','Selected FCT Companies',
    ...fctAdvancedExportHeaders(),
    'On-air IST','Feed','Brand','Caption','Program','Program Start IST',
    'Program Duration Seconds','Ad Duration Seconds','Language','Category',
    'Company','Ad Position','Total Ads','Filename Spillover',
    'Declared File Start','Declared File End','Source File','Source Sheet',
    'Source Row',
  ];
  const csvRows=rows.slice()
    .sort((a,b)=>String(a.event_ist).localeCompare(String(b.event_ist)))
    .map(row=>[
      filters.dateFrom,filters.dateTo,fctClassMode,selections.feeds,
      selections.languages,selections.brands,selections.captions,
      selections.programs,selections.categories,selections.companies,
      ...fctAdvancedExportValues(filters,selections),
      formatIstSeconds(row.event_ist),row.feed_name,row.brand_name,row.caption,
      row.program_name,
      row.program_start_ist?formatIstSeconds(row.program_start_ist):'',
      row.program_duration_seconds,row.duration_seconds,row.language,row.category,
      row.company,row.ad_position,row.total_ads,
      row.is_filename_spillover?'Yes':'No',row.declared_start,row.declared_end,
      row.source_file,row.source_sheet,row.source_row,
    ]);
  downloadCsv(
    'fct_monitored_ad_occurrences_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',
    header,
    csvRows,
  );
}
function exportFctAudienceCsv(){
  const events=selectedFctRows(),filters=fctFilterContext();
  const selections=fctExportSelections();
  const fastPlatforms=exportSelection('fastPlatform','All FAST platforms');
  const fastChannels=exportSelection('fastChannel','All FAST channels');
  const streamChannels=exportSelection('streamChannel','All STREAM channels');
  const amagiPlatforms=exportSelection('amagiPlatform','All AMAGI platforms');
  const amagiChannels=exportSelection('amagiChannel','All AMAGI channels');
  const youtubeChannels=indiaTvYoutubeScopeLabel();
  const header=[
    'Selected Date From','Selected Date To','FCT Classification',
    'Selected FCT Feeds','Selected FCT Languages','Selected FCT Brands',
    'Selected FCT Captions','Selected FCT Programs',
    'Selected FCT Categories','Selected FCT Companies',
    ...fctAdvancedExportHeaders(),
    'FCT On-air IST','Feed','Brand','Caption','Program','Ad Duration Seconds',
    'Language','Category','Company','5-Minute Window IST','FAST Platforms',
    'FAST Channels','STREAM Channels','AMAGI Platforms','AMAGI Channels',
    'India TV YouTube Channel',
    'FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency',
    'AMAGI 5-Minute Actual Concurrency','India TV YouTube Scope',
    'India TV YouTube Minute Concurrency','India TV YouTube Active Live Videos',
    'India TV YouTube Active Video IDs','India TV YouTube Active Video Titles',
    'Combined Concurrency','Coverage Status','Source File','Source Sheet',
    'Source Row',
  ];
  const rows=fctAudienceRows(
    events,fctAudienceMinuteMap('fast'),fctAudienceMinuteMap('stream')
  ).map(row=>{
    const event=row.event;
    return [
      filters.dateFrom,filters.dateTo,fctClassMode,selections.feeds,
      selections.languages,selections.brands,selections.captions,
      selections.programs,selections.categories,selections.companies,
      ...fctAdvancedExportValues(filters,selections),
      formatIstSeconds(event.event_ist),event.feed_name,event.brand_name,
      event.caption,event.program_name,event.duration_seconds,event.language,
      event.category,event.company,row.fast.window,fastPlatforms,fastChannels,
      streamChannels,amagiPlatforms,amagiChannels,youtubeChannels,
      row.fast.total??'',row.stream.total??'',row.amagi.total??'',
      row.youtube.scope,row.youtube.total,
      row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,
      row.total??'',row.partial?'Partial source coverage':'All sources covered',
      event.source_file,event.source_sheet,event.source_row,
    ];
  });
  downloadCsv(
    'fct_audience_context_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',
    header,
    rows,
  );
}
function audienceLines(events,state){const preview=events.slice().sort((a,b)=>String(a.on_air_start_ist).localeCompare(String(b.on_air_start_ist))).slice(-50).reverse();if(!preview.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return preview.map(event=>{const metric=audienceValue(event,state);return '<div class="event-line"><span>'+formatIst(event.on_air_start_ist)+'</span><span><strong>'+esc(event.event_id)+'</strong><small>'+esc(event.ad_type)+'</small></span><span>'+esc(event.creative_title)+'</span><span class="duration">'+fmt(event.actual_duration_seconds)+' sec</span><span class="audience-value">'+esc(metric.value)+'</span></div>';}).join('');}
function amagiLines(events,state){if(!AMAGI.available)return '<div class="audience-empty">'+esc(AMAGI.reason||'Amagi concurrency data is unavailable.')+'</div>';return audienceLines(events,state);}
function combinedRows(events,fast,stream){const amagi=amagiMinuteMap();return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const fastMetric=audienceValue(e,fast),streamMetric=audienceValue(e,stream),amagiMetric=audienceValue(e,amagi),youtubeMetric=youtubeFiveMinuteValue(e),all=[fastMetric.total,streamMetric.total,amagiMetric.total,youtubeMetric.total];return {event:e,fast:fastMetric,stream:streamMetric,amagi:amagiMetric,youtube:youtubeMetric,total:all.some(v=>v===null)?null:all.reduce((sum,v)=>sum+v,0)};});}
function combinedLines(events,fast,stream){const rows=combinedRows(events,fast,stream),preview=rows.slice(-50).reverse();if(!preview.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return preview.map(row=>{const e=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="combined-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="combined-value fast-col">'+esc(row.fast.value)+'</span><span class="combined-value stream-col">'+esc(row.stream.value)+'</span><span class="combined-value amagi-col">'+esc(row.amagi.value)+'</span><span class="combined-value youtube-col">'+esc(row.youtube.value)+'</span><span class="combined-value total-col">'+esc(total)+'</span></div>';}).join('');}
function renderAudience(events){if(!dashboardSourceLoaded('viewer')||!dashboardSourceLoaded('amagi')){const failed=dashboardSourceError('viewer')||dashboardSourceError('amagi'),message=failed||'Loading FAST, STREAM, and AMAGI audience data...';$('allRows').innerHTML='<div class="audience-empty">'+esc(message)+'</div>';$('allNote').textContent='';return}refreshAmagiFilters();const fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),visible=Math.min(events.length,50),note='Showing latest '+fmt(visible)+' of '+fmt(events.length)+' delivered events. CSV exports the complete filtered result.';$('allRows').innerHTML=combinedLines(events,fast,stream);$('allNote').textContent=note;}
function exportSelection(id,allLabel,keepExactValues=false){const menu=$(id+'Menu');if(!menu)return 'Not available';const inputs=[...menu.querySelectorAll('input[data-value]')],selected=inputs.filter(input=>input.checked).map(input=>input.dataset.value);if(!selected.length)return 'None';return selected.length===inputs.length&&!keepExactValues?allLabel:selected.join(' | ');}
function exportDeliverySelection(kind){const types=selectedDeliveryAdTypes();if(!types.size)return 'None';return DELIVERY_AD_TYPES.filter(type=>types.has(type)).map(type=>{const prefix=type==='Spot'?'spot':'lband',suffix=kind==='adIds'?'AdId':'Creative',label=kind==='adIds'?'ad IDs':'creative titles';return type+': '+exportSelection(prefix+suffix,'All '+type+' '+label)}).join(' || ');}
function exportFilterContext(){return {dateFrom:$('from').value,dateTo:$('to').value,adTypes:deliveryAdTypeLabel(),adIds:exportDeliverySelection('adIds'),creatives:exportDeliverySelection('creatives')};}
function exportAllEventsCsv(){const events=filtered(),fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),amagi=amagiMinuteMap(),filters=exportFilterContext(),fastPlatforms=exportSelection('fastPlatform','All FAST platforms',true),fastChannels=exportSelection('fastChannel','All FAST channels',true),streamChannels=exportSelection('streamChannel','All STREAM channels',true),amagiPlatforms=exportSelection('amagiPlatform','All AMAGI platforms',true),amagiChannels=exportSelection('amagiChannel','All AMAGI channels',true),youtubeChannels=indiaTvYoutubeScopeLabel(),header=['Selected Date From','Selected Date To','Selected Ad Types','Selected Ad IDs','Selected Creative Titles','On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','AMAGI Platforms','AMAGI Channels','India TV YouTube Channel','FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency','AMAGI 5-Minute Actual Concurrency','India TV YouTube Scope','India TV YouTube Minute Concurrency','India TV YouTube Active Live Videos','India TV YouTube Active Video IDs','India TV YouTube Active Video Titles','Combined Concurrency'],rows=combinedRows(events,fast,stream).map(row=>[filters.dateFrom,filters.dateTo,filters.adTypes,filters.adIds,filters.creatives,formatIst(row.event.on_air_start_ist),row.event.ad_type,row.event.event_id,row.event.creative_title,row.event.actual_duration_seconds,row.fast.window,fastPlatforms,fastChannels,streamChannels,amagiPlatforms,amagiChannels,youtubeChannels,row.fast.total,row.stream.total,row.amagi.total,row.youtube.scope,row.youtube.total,row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,row.total??'']);downloadCsv('asrun_all_delivered_events_'+deliveryAdTypeFileToken()+'_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,rows);}
function amagiBreakdownScopes(){const rows=selectedAmagiRows(),seen=new Set(),scopes=[];for(const row of rows){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA'),key=platform+'\u0000'+channel;if(!seen.has(key)){seen.add(key);scopes.push({source:'AMAGI',platform,channel})}}return scopes.sort((a,b)=>a.platform.localeCompare(b.platform)||a.channel.localeCompare(b.channel));}
function amagiScopeMap(scope){const map=new Map();for(const row of selectedAmagiRows()){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA');if(platform!==scope.platform||channel!==scope.channel)continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return map;}
function exportAudienceBreakdownCsv(){const events=filtered(),filters=exportFilterContext(),scopes=[...audienceBreakdownScopes('fast'),...audienceBreakdownScopes('stream'),...amagiBreakdownScopes()],header=['Selected Date From','Selected Date To','Selected Ad Types','Selected Ad IDs','Selected Creative Titles','On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','Source','Platform','Channel','5-Minute Window IST','Individual 5-Minute Concurrency','Metric Basis'],rows=[];for(const scope of scopes){const map=scope.source==='AMAGI'?amagiScopeMap(scope):audienceScopeMap(scope),basis=scope.source==='AMAGI'?'Actual platform-reported concurrent viewers':'Unique IP minute sum';for(const event of events){const metric=audienceScopeValue(event,map);rows.push([filters.dateFrom,filters.dateTo,filters.adTypes,filters.adIds,filters.creatives,formatIst(event.on_air_start_ist),event.ad_type,event.event_id,event.creative_title,event.actual_duration_seconds,scope.source,scope.platform,scope.channel,metric.window,metric.total,basis])}}downloadCsv('asrun_audience_platform_channel_breakdown_'+deliveryAdTypeFileToken()+'_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,rows)}
function replaceDownloadAction(id,handler){const button=$(id);if(!button)return;const replacement=button.cloneNode(true);button.replaceWith(replacement);replacement.addEventListener('click',handler);}
function ensureScopePanel(){if($('dataScopeRows'))return;$('youtubePanel').insertAdjacentHTML('afterend','<section class="panel scope-panel" id="dataScopePanel"><div class="panel-head"><div><h2>Data Scope And Validation</h2><small>True range is all data embedded in this dashboard run. Used range updates with the active filters. Date continuity checks source coverage inside the date window, independently of channel/platform choices; a gap can mean no activity or missing source data.</small></div></div><div class="scope-table-wrap"><table class="scope-table"><thead><tr><th>Dataset</th><th>True range (IST)</th><th>Used range (IST)</th><th>Used rows / points</th><th>Date continuity</th><th>Applied scope</th></tr></thead><tbody id="dataScopeRows"></tbody></table></div></section>');}
function sourceBounds(rows,startKey,endKey){if(!rows.length)return null;const starts=rows.map(row=>String(row[startKey]||'')).filter(Boolean).sort(),ends=rows.map(row=>String(row[endKey||startKey]||'')).filter(Boolean).sort();return starts.length&&ends.length?{start:starts[0],end:ends[ends.length-1]}:null;}
function scopeRangeText(bounds){return bounds?formatIst(bounds.start)+' to '+formatIst(bounds.end):'No matching data';}
function isoDatePart(value){const match=String(value||'').match(/^(\d{4}-\d{2}-\d{2})/);return match?match[1]:'';}
function inclusiveIsoDates(start,end){const first=isoDatePart(start),last=isoDatePart(end);if(!first||!last||first>last)return [];const dates=[],cursor=new Date(first+'T00:00:00Z'),stop=new Date(last+'T00:00:00Z');for(;cursor<=stop;cursor.setUTCDate(cursor.getUTCDate()+1))dates.push(cursor.toISOString().slice(0,10));return dates;}
function coverageBounds(dateValues){const values=[...new Set((dateValues||[]).map(isoDatePart).filter(Boolean))].sort();return values.length?{start:values[0]+'T00:00:00',end:values[values.length-1]+'T23:59:59'}:null;}
function dateContinuity(dateValues,start,end){const expected=inclusiveIsoDates(start,end);if(!expected.length)return {valid:false,total:0,present:0,missing:[]};const represented=new Set((dateValues||[]).map(isoDatePart).filter(Boolean)),missing=expected.filter(date=>!represented.has(date));return {valid:true,total:expected.length,present:expected.length-missing.length,missing};}
function usedDateContinuity(dateValues,start,end,trueBounds){const selected=inclusiveIsoDates(start,end),sourceFirst=isoDatePart(trueBounds?.start),sourceLast=isoDatePart(trueBounds?.end);if(!selected.length)return {valid:false,total:0,present:0,missing:[],outside:0};if(!sourceFirst||!sourceLast)return {...dateContinuity(dateValues,start,end),outside:0};const overlapStart=selected[0]>sourceFirst?selected[0]:sourceFirst,overlapEnd=selected[selected.length-1]<sourceLast?selected[selected.length-1]:sourceLast;if(overlapStart>overlapEnd)return {valid:true,total:0,present:0,missing:[],outside:selected.length,noOverlap:true};const value=dateContinuity(dateValues,overlapStart,overlapEnd);value.outside=selected.length-value.total;return value;}
function continuityLine(label,coverage){if(!coverage.valid)return '<span class="scope-continuity-line"><strong>'+esc(label)+':</strong> No range</span>';if(coverage.noOverlap)return '<span class="scope-continuity-line"><strong>'+esc(label)+': Outside source range</strong> · '+fmt(coverage.outside)+' selected dates</span>';const outside=coverage.outside?' · '+fmt(coverage.outside)+' outside source range':'';if(!coverage.missing.length)return '<span class="scope-continuity-line complete"><strong>'+esc(label)+': Complete</strong> · '+fmt(coverage.present)+'/'+fmt(coverage.total)+' dates'+outside+'</span>';const preview=coverage.missing.slice(0,4).map(shortDate).join(', '),more=coverage.missing.length>4?' +'+fmt(coverage.missing.length-4)+' more':'';return '<span class="scope-continuity-line gap"><strong>'+esc(label)+': '+fmt(coverage.missing.length)+' gap'+(coverage.missing.length===1?'':'s')+'</strong> · '+fmt(coverage.present)+'/'+fmt(coverage.total)+' dates<span title="'+esc(coverage.missing.map(shortDate).join(', '))+'"> · '+esc(preview+more)+'</span>'+outside+'</span>';}
function scopeContinuityHtml(dateValues,trueBounds,usedStart,usedEnd){const effectiveTrue=trueBounds||coverageBounds(dateValues);return '<span class="scope-continuity">'+continuityLine('True',dateContinuity(dateValues,effectiveTrue?.start,effectiveTrue?.end))+continuityLine('Used',usedDateContinuity(dateValues,usedStart,usedEnd,effectiveTrue))+'</span>';}
function selectedViewerRows(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;return viewerScope(source).filter(row=>(!platforms||platforms.has(String(row.platform_name)))&&channels.has(String(row.channel_name)));}
function selectedAmagiRows(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),from=$('from').value,to=$('to').value;return (AMAGI.minute||[]).filter(row=>String(row.log_date)>=from&&String(row.log_date)<=to&&platforms.has(String(row.platform_name))&&channels.has(String(row.channel_name)));}
let youtubeDateMode='follow';
let youtubeDateOverlap=true;
function ensureYoutubeDateModeControls(){
  if($('youtubeDateMode'))return;
  const bar=document.querySelector('.youtube-filter-bar');
  $('youtubeFrom').closest('.filter-label').classList.add('youtube-independent-date-control');
  $('youtubeTo').closest('.filter-label').classList.add('youtube-independent-date-control');
  document.querySelector('.youtube-filter-actions')?.classList.add(
    'youtube-independent-date-control'
  );
  bar.insertAdjacentHTML(
    'afterbegin',
    '<div class="youtube-date-mode" id="youtubeDateMode">'
    +'<span>Date scope</span><div class="youtube-date-mode-buttons" role="group" '
    +'aria-label="YouTube date relationship">'
    +'<button type="button" data-youtube-date-mode="independent">Independent</button>'
    +'<button type="button" data-youtube-date-mode="follow">Follow Main</button>'
    +'</div></div>'
  );
  bar.insertAdjacentHTML(
    'beforeend',
    '<div class="youtube-date-help" id="youtubeDateHelp" aria-live="polite"></div>'
  );
  document.querySelectorAll('[data-youtube-date-mode]').forEach(button=>
    button.addEventListener('click',()=>setYoutubeDateMode(button.dataset.youtubeDateMode))
  );
  for(const id of ['youtubeFrom','youtubeTo']){
    $(id).addEventListener('change',()=>{
      if(youtubeDateMode!=='independent')return;
      youtubeDateOverlap=true;
      updateYoutubeDateHelp();
    },true);
  }
}
function youtubeMainOverlapRange(){
  const bounds=youtubeTrueBounds();
  const start=$('from').value>bounds.start?$('from').value:bounds.start;
  const end=$('to').value<bounds.end?$('to').value:bounds.end;
  return {start,end,valid:Boolean(start&&end&&start<=end),bounds};
}
function updateYoutubeDateHelp(){
  const help=$('youtubeDateHelp');
  if(!help)return;
  help.classList.toggle('error',youtubeDateMode==='follow'&&!youtubeDateOverlap);
  if(youtubeDateMode==='independent'){
    help.textContent='Independent YouTube range; main dashboard dates do not change this section.';
  }else if(youtubeDateOverlap){
    help.textContent='Following main dashboard dates, clipped to available YouTube data.';
  }else{
    help.textContent='No YouTube data overlaps the selected main dashboard dates.';
  }
}
function applyYoutubeMainDate(renderNow=true){
  const overlap=youtubeMainOverlapRange();
  youtubeDateOverlap=overlap.valid;
  if(overlap.valid){
    $('youtubeFrom').value=overlap.start;
    $('youtubeTo').value=overlap.end;
  }else{
    const anchor=$('to').value<overlap.bounds.start
      ?overlap.bounds.start
      :overlap.bounds.end;
    $('youtubeFrom').value=anchor;
    $('youtubeTo').value=anchor;
  }
  refreshYoutubeDateLimits();
  updateYoutubeRangeButtons('');
  updateYoutubeDateHelp();
  if(renderNow)renderYoutube();
}
function syncDateControlVisibility(){
  const filters=document.querySelector('.filters');
  if(!filters)return;
  const hideMaster=(activeDashboardPage==='content'&&nctDateMode==='independent')
    ||(activeDashboardPage==='audience'&&youtubeDateMode==='independent');
  filters.classList.toggle('master-date-hidden',hideMaster);
}
function setYoutubeDateMode(mode,renderNow=true){
  youtubeDateMode=mode==='follow'?'follow':'independent';
  document.querySelectorAll('[data-youtube-date-mode]').forEach(button=>
    button.classList.toggle('active',button.dataset.youtubeDateMode===youtubeDateMode)
  );
  const follow=youtubeDateMode==='follow';
  document.querySelector('.youtube-filter-bar')?.classList.toggle('follow-main',follow);
  $('youtubeFrom').disabled=follow;
  $('youtubeTo').disabled=follow;
  syncDateControlVisibility();
  if(follow){
    applyYoutubeMainDate(renderNow);
    updateResetState();
    return;
  }
  youtubeDateOverlap=true;
  updateYoutubeDateHelp();
  if(renderNow)renderYoutube();
  updateResetState();
}
function initializeYoutubeDates(){
  const overlap=youtubeMainOverlapRange(),bounds=overlap.bounds;
  if(overlap.valid){
    $('youtubeFrom').value=overlap.start;
    $('youtubeTo').value=overlap.end;
  }else{
    $('youtubeFrom').value=bounds.end;
    $('youtubeTo').value=bounds.end;
  }
  refreshYoutubeDateLimits();
}
function ensureYoutubeChartIntervalControls(){
  if($('youtubeChartInterval'))return;
  $('youtubeSelectionNote').insertAdjacentHTML(
    'beforebegin',
    '<div class="youtube-chart-interval-controls">'
    +'<label class="filter-label">Chart interval'
    +'<select id="youtubeChartInterval">'
    +'<option value="1">1 minute</option>'
    +'<option value="5" selected>5 minutes</option>'
    +'<option value="15">15 minutes</option>'
    +'<option value="30">30 minutes</option>'
    +'<option value="60">1 hour</option>'
    +'<option value="custom">Custom minutes</option>'
    +'</select></label>'
    +'<label class="filter-label" id="youtubeCustomIntervalLabel" hidden>'
    +'Custom minutes<input id="youtubeCustomInterval" type="number" '
    +'min="1" max="1440" step="1" value="120"></label></div>'
  );
  $('youtubeChartInterval').addEventListener('change',()=>{
    const custom=$('youtubeChartInterval').value==='custom';
    $('youtubeCustomIntervalLabel').hidden=!custom;
    showLoading('Updating YouTube chart interval...');
    renderYoutube();
  });
  $('youtubeCustomInterval').addEventListener('change',()=>{
    const value=Math.min(1440,Math.max(1,Number($('youtubeCustomInterval').value)||1));
    $('youtubeCustomInterval').value=String(Math.round(value));
    showLoading('Updating YouTube chart interval...');
    renderYoutube();
  });
}
let youtubeChartRestoreState=[];
let youtubeChartPreviousFocus=null;
function resizeYoutubeTrendChart(){
  requestAnimationFrame(()=>{
    if(youtubeTrendChart)youtubeTrendChart.resize();
  });
}
function openYoutubeChart(){
  const modal=$('youtubeChartModal'),body=$('youtubeChartModalBody');
  if(!modal||!modal.hidden)return;
  closeMultiMenus('');
  youtubeChartPreviousFocus=document.activeElement;
  const nodes=[
    document.querySelector('#youtubePanel .youtube-filter-bar'),
    document.querySelector('#youtubePanel .youtube-controls'),
    document.querySelector('#youtubePanel .youtube-chart-shell'),
  ].filter(Boolean);
  youtubeChartRestoreState=nodes.map(node=>({
    node,
    parent:node.parentNode,
    nextSibling:node.nextSibling,
  }));
  for(const entry of youtubeChartRestoreState)body.appendChild(entry.node);
  modal.hidden=false;
  document.body.classList.add('youtube-chart-expanded');
  $('expandYoutubeChart').setAttribute('aria-expanded','true');
  $('closeYoutubeChart').focus();
  resizeYoutubeTrendChart();
}
function closeYoutubeChart(){
  const modal=$('youtubeChartModal');
  if(!modal||modal.hidden)return;
  closeMultiMenus('');
  for(const entry of youtubeChartRestoreState.slice().reverse()){
    entry.parent.insertBefore(entry.node,entry.nextSibling);
  }
  youtubeChartRestoreState=[];
  modal.hidden=true;
  document.body.classList.remove('youtube-chart-expanded');
  $('expandYoutubeChart').setAttribute('aria-expanded','false');
  if(youtubeChartPreviousFocus&&document.contains(youtubeChartPreviousFocus)){
    youtubeChartPreviousFocus.focus();
  }
  youtubeChartPreviousFocus=null;
  resizeYoutubeTrendChart();
}
function ensureYoutubeChartExpand(){
  if($('expandYoutubeChart'))return;
  const panel=$('youtubePanel'),tag=panel.querySelector('.youtube-tag');
  const actions=document.createElement('div');
  actions.className='panel-actions';
  actions.innerHTML='<button id="expandYoutubeChart" type="button" '
    +'aria-expanded="false" aria-controls="youtubeChartModal">Expand chart</button>';
  tag.before(actions);
  actions.appendChild(tag);
  document.body.insertAdjacentHTML(
    'beforeend',
    '<div id="youtubeChartModal" class="youtube-chart-modal" hidden '
    +'role="dialog" aria-modal="true" aria-labelledby="youtubeChartModalTitle">'
    +'<div class="youtube-chart-dialog">'
    +'<div class="youtube-chart-modal-head">'
    +'<h2 id="youtubeChartModalTitle">YouTube Channel Concurrency</h2>'
    +'<button id="closeYoutubeChart" type="button">Close</button>'
    +'</div><div id="youtubeChartModalBody" class="youtube-chart-modal-body"></div>'
    +'</div></div>'
  );
  $('expandYoutubeChart').addEventListener('click',openYoutubeChart);
  $('closeYoutubeChart').addEventListener('click',closeYoutubeChart);
  $('youtubeChartModal').addEventListener('click',event=>{
    if(event.target===$('youtubeChartModal'))closeYoutubeChart();
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!$('youtubeChartModal').hidden)closeYoutubeChart();
  });
}
function youtubeChartIntervalMinutes(){
  const selected=$('youtubeChartInterval')?.value||'5';
  if(selected!=='custom')return Number(selected);
  return Math.min(1440,Math.max(1,Math.round(Number($('youtubeCustomInterval').value)||1)));
}
function youtubeIntervalLabel(minutes){
  if(minutes===1)return '1-minute';
  if(minutes===60)return '1-hour';
  if(minutes%60===0)return (minutes/60)+'-hour';
  return minutes+'-minute';
}
setYoutubeRange=function(kind){
  setYoutubeDateMode('independent',false);
  const bounds=youtubeTrueBounds(),end=new Date(bounds.end+'T00:00:00Z');
  if(kind==='all'){
    $('youtubeFrom').value=bounds.start;
    $('youtubeTo').value=bounds.end;
  }else{
    const days=kind==='latest'?1:Number(kind);
    end.setUTCDate(end.getUTCDate()-(days-1));
    $('youtubeFrom').value=[end.toISOString().slice(0,10),bounds.start].sort().at(-1);
    $('youtubeTo').value=bounds.end;
  }
  syncYoutubeDates('from');
  updateYoutubeRangeButtons(kind);
  updateYoutubeDateHelp();
  renderYoutube();
};
syncYoutubeDates=function(changed){
  const fromInput=$('youtubeFrom'),toInput=$('youtubeTo');
  let adjusted=false;
  if(fromInput.value>toInput.value){
    if(changed==='from')toInput.value=fromInput.value;
    else fromInput.value=toInput.value;
    adjusted=true;
  }
  refreshYoutubeDateLimits();
  if(adjusted&&$('youtubeDateHelp')){
    $('youtubeDateHelp').textContent=changed==='from'
      ?'End date moved to match the later start date.'
      :'Start date moved to match the earlier end date.';
  }
};
function ensureYoutubeChannelFilter(){
  if($('youtubeChannelToggle'))return;
  const videoLabel=$('youtubeVideoToggle').closest('.filter-label');
  videoLabel.insertAdjacentHTML(
    'beforebegin',
    '<label class="filter-label">YouTube channels'
    +'<span class="multi-select"><button id="youtubeChannelToggle" '
    +'class="multi-toggle" type="button">All channels</button>'
    +'<span id="youtubeChannelMenu" class="multi-menu"></span></span></label>'
  );
}
function youtubeChannels(){
  const youtube=DATA.youtube||{},declared=(youtube.channels||[]).map(String);
  const derived=(youtube.video_daily||[]).map(row=>String(row.youtube_channel||'Unknown / NA'));
  return [...new Set([...declared,...derived].filter(Boolean))].sort((a,b)=>a.localeCompare(b));
}
function isIndiaTvYoutubeChannel(value){
  return String(value||'').replace(/[^a-z0-9]+/gi,'').toLowerCase()==='indiatv';
}
function indiaTvYoutubeChannels(){
  return youtubeChannels().filter(isIndiaTvYoutubeChannel);
}
function youtubeDefaultChannels(channels){
  return channels.filter(isIndiaTvYoutubeChannel);
}
function indiaTvYoutubeScopeLabel(){
  const channels=indiaTvYoutubeChannels();
  return channels.length?channels.join(' | '):'No India TV YouTube collector';
}
function youtubeSelectedChannels(){return selectedMulti('youtubeChannel');}
function youtubeRowInChannels(row,channels){
  return channels.has(String(row.youtube_channel||'Unknown / NA'));
}
function youtubeTrueBounds(){
  const youtube=DATA.youtube||{};
  return {
    start:String(youtube.true_start||youtube.full_start||'').slice(0,10),
    end:String(youtube.true_end||youtube.full_end||'').slice(0,10),
  };
}
youtubeBounds=function(){return youtubeTrueBounds();};
function refreshYoutubeDateLimits(){
  const bounds=youtubeTrueBounds();
  for(const id of ['youtubeFrom','youtubeTo']){
    $(id).min=bounds.start;
    $(id).max=bounds.end;
  }
}
let youtubeVideoSelectAll=true;
function youtubeVideoMetaMap(rows){
  const meta=new Map();
  for(const row of rows.slice().sort((a,b)=>String(a.log_date).localeCompare(String(b.log_date)))){
    meta.set(String(row.video_id),{
      title:String(row.title||'Untitled live video'),
      channel:String(row.youtube_channel||'Unknown / NA'),
    });
  }
  return meta;
}
function youtubeVideoMultiSummary(videoIds,selected){
  const button=$('youtubeVideoToggle');
  if(!selected.size){button.textContent='No live videos selected';return;}
  button.textContent=youtubeSelectionIsAll(videoIds,selected)
    ?'All videos in selected channels'
    :selected.size===1?'1 live video selected':selected.size+' live videos selected';
}
function buildYoutubeVideoMultiChannel(videoIds,meta){
  const menu=$('youtubeVideoMenu'),old=youtubeSelectedVideoIds(),allowed=new Set(videoIds);
  const selected=youtubeVideoSelectAll
    ?new Set(videoIds)
    :new Set([...old].filter(id=>allowed.has(id)));
  const allChecked=youtubeSelectionIsAll(videoIds,selected);
  const items=videoIds.map(id=>({id,...(meta.get(id)||{
    title:'Untitled live video',
    channel:'Unknown / NA',
  })}));
  menu.innerHTML='<span class="multi-search-shell"><input id="youtubeVideoSearch" '
    +'class="multi-search" type="search" '
    +'placeholder="Search channel, video ID, or title..." autocomplete="off"></span>'
    +'<label class="multi-option multi-all"><input type="checkbox" data-all '
    +(allChecked?'checked':'')+'>All videos in selected channels</label>'
    +items.map(item=>'<label class="multi-option" data-video-option data-search="'
      +esc((item.channel+' '+item.id+' '+item.title).toLowerCase())+'">'
      +'<input type="checkbox" data-video="'+esc(item.id)+'" '
      +(selected.has(item.id)?'checked':'')+'>'
      +'<span><strong class="youtube-channel-label">'+esc(item.channel)+'</strong>'
      +'<small>'+esc(item.id)+' · '+esc(item.title)+'</small></span></label>').join('');
  youtubeVideoMultiSummary(videoIds,selected);
  $('youtubeVideoToggle').onclick=event=>{
    event.stopPropagation();
    const open=!menu.classList.contains('open');
    closeMultiMenus('youtubeVideo');
    menu.classList.toggle('open',open);
    if(open)requestAnimationFrame(()=>{
      alignMultiMenu(menu);
      $('youtubeVideoSearch').focus();
    });
    else clearMultiMenuSearch(menu);
  };
  $('youtubeVideoSearch').oninput=event=>{
    const term=event.target.value.trim().toLowerCase();
    for(const option of menu.querySelectorAll('[data-video-option]')){
      option.style.display=!term||option.dataset.search.includes(term)?'flex':'none';
    }
  };
  $('youtubeVideoSearch').onkeydown=event=>{
    if(event.key==='Escape'){
      closeMultiMenu(menu);
      $('youtubeVideoToggle').focus();
    }
  };
  menu.onchange=event=>{
    const all=menu.querySelector('input[data-all]');
    if(event.target.hasAttribute('data-all')){
      for(const input of menu.querySelectorAll('input[data-video]')){
        input.checked=event.target.checked;
      }
    }else{
      all.checked=[...menu.querySelectorAll('input[data-video]')].every(input=>input.checked);
    }
    youtubeVideoSelectAll=all.checked;
    youtubeVideoMultiSummary(videoIds,youtubeSelectedVideoIds());
    renderYoutube();
  };
}
function youtubeMinuteStats(rows){
  const stats=new Map();
  for(const row of rows){
    const key=youtubeMinuteKey(row.timestamp_ist);
    const current=stats.get(key)||{total:0,peak:0,videos:new Set(),channels:new Set()};
    const value=Number(row.concurrent_viewers||0);
    current.total+=value;
    current.peak=Math.max(current.peak,value);
    current.videos.add(String(row.video_id));
    current.channels.add(String(row.youtube_channel||'Unknown / NA'));
    stats.set(key,current);
  }
  return stats;
}
const youtubeChannelColors={
  'Aaj Tak':'#e11d48',
  'ABP News':'#f59e0b',
  'CNN-News18':'#2563eb',
  'India TV':'#7c3aed',
  'NDTV India':'#0891b2',
  'Republic Bharat':'#dc2626',
  'TV9 Bharatvarsh':'#16a34a',
  'Zee News':'#db2777',
  'Unknown / NA':'#64748b',
};
const youtubeFallbackColors=[
  '#0f766e','#9333ea','#ea580c','#0369a1','#4d7c0f','#be123c','#4338ca','#a16207',
];
function youtubeChannelChartData(rows,selectedChannels,intervalMinutes){
  const byChannelMinute=new Map();
  for(const row of rows){
    const channel=String(row.youtube_channel||'Unknown / NA');
    if(!byChannelMinute.has(channel))byChannelMinute.set(channel,new Map());
    const minute=youtubeMinuteKey(row.timestamp_ist),series=byChannelMinute.get(channel);
    series.set(minute,(series.get(minute)||0)+Number(row.concurrent_viewers||0));
  }
  const intervalMs=intervalMinutes*60000,byChannel=new Map(),allBuckets=new Set();
  for(const [channel,minutes] of byChannelMinute){
    const buckets=new Map();
    for(const [minute,value] of minutes){
      const bucketMillis=Math.floor(naiveMillis(minute)/intervalMs)*intervalMs;
      const bucket=new Date(bucketMillis).toISOString().slice(0,16)+':00';
      const current=buckets.get(bucket)||{sum:0,count:0,peak:0};
      current.sum+=value;
      current.count++;
      current.peak=Math.max(current.peak,value);
      buckets.set(bucket,current);
      allBuckets.add(bucket);
    }
    byChannel.set(channel,buckets);
  }
  const rawBuckets=[...allBuckets].sort(),maxChartPoints=6000;
  const displayStep=Math.max(1,Math.ceil(rawBuckets.length/maxChartPoints));
  const visualBuckets=[];
  for(let index=0;index<rawBuckets.length;index+=displayStep){
    visualBuckets.push(rawBuckets.slice(index,index+displayStep));
  }
  const displayMinutes=intervalMinutes*displayStep;
  const labels=visualBuckets.map(group=>{
    const start=group[0];
    if(displayMinutes===1)return formatIst(start);
    const endMillis=naiveMillis(group.at(-1))+(intervalMinutes-1)*60000;
    const end=new Date(endMillis).toISOString().slice(0,16)+':00';
    return formatIst(start)+' to '+formatIst(end);
  });
  const ordered=[...selectedChannels].filter(channel=>byChannel.has(channel))
    .sort((a,b)=>a.localeCompare(b));
  const datasets=ordered.map((channel,index)=>{
    const series=byChannel.get(channel);
    return {
      label:channel,
      data:visualBuckets.map(group=>{
        let sum=0,count=0;
        for(const bucket of group){
          const value=series.get(bucket);
          if(!value)continue;
          sum+=value.sum;
          count+=value.count;
        }
        return count?sum/count:null;
      }),
      borderColor:youtubeChannelColors[channel]
        ||youtubeFallbackColors[index%youtubeFallbackColors.length],
      backgroundColor:'transparent',
      fill:false,
      spanGaps:false,
      tension:.16,
      pointRadius:0,
      pointHoverRadius:5,
      pointHitRadius:10,
      borderWidth:1.8,
    };
  });
  return {
    labels,
    datasets,
    intervalMinutes,
    displayMinutes,
    condensed:displayStep>1,
  };
}
function renderYoutubeChannelTrend(rows,selectedChannels){
  const canvas=$('youtubeTrend'),empty=$('youtubeChartEmpty');
  const chartData=youtubeChannelChartData(
    rows,
    selectedChannels,
    youtubeChartIntervalMinutes(),
  );
  if(!chartData.labels.length||!chartData.datasets.length){
    canvas.style.display='none';
    empty.style.display='flex';
    empty.textContent='No YouTube live-concurrency data for the selected channels and videos.';
    if(youtubeTrendChart){
      youtubeTrendChart.data={labels:[],datasets:[]};
      youtubeTrendChart.update('none');
    }
    return chartData;
  }
  canvas.style.display='block';
  empty.style.display='none';
  const data={labels:chartData.labels,datasets:chartData.datasets};
  const yTitle=chartData.intervalMinutes===1
    ?'Live concurrent viewers by channel'
    :'Average concurrent viewers by channel';
  if(youtubeTrendChart){
    youtubeTrendChart.data=data;
    youtubeTrendChart.options.scales.y.title.text=yTitle;
    youtubeTrendChart.update('none');
    return chartData;
  }
  youtubeTrendChart=new Chart(canvas,{
    type:'line',
    data,
    options:{
      responsive:true,
      maintainAspectRatio:false,
      normalized:true,
      animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{
          display:true,
          position:'bottom',
          labels:{usePointStyle:true,pointStyle:'line',boxWidth:18,font:{size:10}},
        },
        tooltip:{
          backgroundColor:'#1f2937',
          borderColor:'#475569',
          borderWidth:1,
          titleColor:'#f8fafc',
          bodyColor:'#f8fafc',
          padding:10,
          displayColors:true,
          filter:context=>Number.isFinite(Number(context.parsed.y)),
          itemSort:(left,right)=>Number(right.parsed.y)-Number(left.parsed.y),
          callbacks:{label:context=>context.dataset.label+': '+fmt(context.parsed.y)},
        },
      },
      scales:{
        x:{
          title:{display:true,text:'IST time',font:{size:11,weight:'700'}},
          ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:18,font:{size:10},color:'#5b6b7a'},
          grid:{color:'#edf2f7'},
        },
        y:{
          title:{
            display:true,
            text:yTitle,
            font:{size:11,weight:'700'},
          },
          beginAtZero:true,
          ticks:{color:'#5b6b7a',callback:value=>fmt(value)},
          grid:{color:'#edf2f7'},
        },
      },
    },
  });
  return chartData;
}
function renderYoutubeChannelTable(chartData){
  const table=$('youtubeTrendTable').closest('table');
  const valueLabel=chartData.intervalMinutes===1
    ?'Live concurrency'
    :youtubeIntervalLabel(chartData.displayMinutes)+' average concurrency';
  table.querySelector('thead').innerHTML='<tr><th>IST time</th>'
    +'<th>YouTube channel</th><th>'+esc(valueLabel)+'</th></tr>';
  const possible=chartData.labels.length*Math.max(1,chartData.datasets.length);
  const step=Math.max(1,Math.ceil(possible/600)),rows=[];
  for(let index=0;index<chartData.labels.length;index+=step){
    for(const dataset of chartData.datasets){
      const value=dataset.data[index];
      if(value===null||value===undefined)continue;
      rows.push('<tr><td>'+esc(chartData.labels[index])+'</td><td>'
        +esc(dataset.label)+'</td><td>'+fmt(value)+'</td></tr>');
    }
  }
  $('youtubeTrendTable').innerHTML=rows.length
    ?rows.join('')
    :'<tr><td colspan="3">No values for this selection.</td></tr>';
}
function youtubeSelectedVideoMinuteRows(youtube,from,to){
  if(youtubeDateMode==='follow'&&!youtubeDateOverlap)return [];
  const channels=youtubeSelectedChannels(),videos=youtubeSelectedVideoIds();
  return youtubeRowsForDate(youtube.video_minute,from,to).filter(row=>
    youtubeRowInChannels(row,channels)&&videos.has(String(row.video_id))
  );
}
function renderYoutubeChannelAware(){
  const youtube=DATA.youtube||{};
  if(!youtube.available){
    $('youtubeMeta').textContent=youtube.reason||'YouTube source data is not available.';
    $('youtubeMetrics').innerHTML='';
    $('youtubeVideoRanking').innerHTML='<div class="audience-empty">'
      +'YouTube live-audience data is unavailable.</div>';
    $('youtubeEventContext').innerHTML='';
    $('youtubeSelectionNote').textContent='';
    renderYoutubeChannelTable(renderYoutubeChannelTrend([],new Set()));
    return;
  }
  if(!dashboardSourceLoaded('youtube')){
    const message=dashboardSourceError('youtube')
      ||'Loading YouTube live-audience data...';
    $('youtubeMeta').textContent=message;
    $('youtubeMetrics').innerHTML='';
    $('youtubeVideoRanking').innerHTML='<div class="audience-empty">'
      +esc(message)+'</div>';
    $('youtubeEventContext').innerHTML='';
    $('youtubeSelectionNote').textContent='';
    renderYoutubeChannelTable(renderYoutubeChannelTrend([],new Set()));
    for(const id of ['youtubeChannelToggle','youtubeVideoToggle','youtubeFrom','youtubeTo']){
      if($(id))$(id).disabled=true;
    }
    return;
  }
  for(const id of ['youtubeChannelToggle','youtubeVideoToggle','youtubeFrom','youtubeTo']){
    if($(id))$(id).disabled=false;
  }
  ensureYoutubeChannelFilter();
  refreshYoutubeDateLimits();
  const from=$('youtubeFrom').value,to=$('youtubeTo').value;
  const channels=youtubeChannels();
  buildMulti('youtubeChannel',channels,'channels',youtubeDefaultChannels(channels),()=>{
    youtubeDeliveryMinuteIndex=null;
    resetSemanticAllSelection('nctYoutubeVideo');
    resetNctAudienceCaches();
    if(nctPayload)refreshNctStorySourceFilters();
    render();
    renderYoutube();
  });
  const selectedChannels=youtubeSelectedChannels();
  const dateSelectionAvailable=youtubeDateMode!=='follow'||youtubeDateOverlap;
  const allDaily=dateSelectionAvailable
    ?youtubeRowsForDate(youtube.video_daily,from,to)
    :[];
  const daily=allDaily.filter(row=>youtubeRowInChannels(row,selectedChannels));
  const videoIds=[...new Set(daily.map(row=>String(row.video_id)))].sort();
  const videoMeta=youtubeVideoMetaMap(daily);
  buildYoutubeVideoMultiChannel(videoIds,videoMeta);
  const selectedVideos=youtubeSelectedVideoIds();
  const videoMinute=dateSelectionAvailable
    ?youtubeRowsForDate(youtube.video_minute,from,to).filter(row=>
      youtubeRowInChannels(row,selectedChannels)&&selectedVideos.has(String(row.video_id))
    )
    :[];
  const stats=youtubeMinuteStats(videoMinute);
  const points=[...stats.entries()].sort((a,b)=>a[0].localeCompare(b[0]))
    .map(([label,value])=>({label,value:value.total}));
  const values=points.map(point=>point.value);
  const peak=values.length?Math.max(...values):0;
  const average=values.length?values.reduce((sum,value)=>sum+value,0)/values.length:0;
  const viewerMinutes=values.reduce((sum,value)=>sum+value,0);
  const peakLiveVideos=stats.size?Math.max(...[...stats.values()].map(row=>row.videos.size)):0;
  const representedChannels=new Set(videoMinute.map(row=>
    String(row.youtube_channel||'Unknown / NA')));
  const selectedScope=selectedChannels.size===channels.length
    ?'All '+channels.length+' YouTube channels'
    :selectedChannels.size+' selected YouTube channel'+(selectedChannels.size===1?'':'s');
  const scopeLabel=selectedScope+' · '+representedChannels.size+' with data in range';
  $('youtubeMeta').textContent='Available data: '+String(youtube.true_start).slice(0,16)
    +' to '+String(youtube.true_end).slice(0,16)+' IST | '+channels.length
    +' collected channels | '+fmt(youtube.completed_files||0)+' completed and '
    +fmt(youtube.partial_files||0)+' active partial files';
  $('youtubeMetrics').innerHTML=[
    ['Peak live concurrency',fmt(peak),scopeLabel],
    ['Average live concurrency',fmt(average),scopeLabel],
    ['Estimated viewer-minutes',fmt(viewerMinutes),'Live concurrency summed by minute'],
    ['Peak simultaneous live videos',fmt(peakLiveVideos),scopeLabel],
  ].map(metric=>'<div class="youtube-metric"><div class="youtube-metric-label">'
    +metric[0]+'</div><div class="youtube-metric-value">'+metric[1]
    +'</div><div class="youtube-metric-note">'+metric[2]+'</div></div>').join('');
  const chartData=renderYoutubeChannelTrend(videoMinute,selectedChannels);
  renderYoutubeChannelTable(chartData);
  const intervalNote=chartData.intervalMinutes===1
    ?'Chart: minute-by-minute concurrency'
    :'Chart: '+youtubeIntervalLabel(chartData.intervalMinutes)+' average concurrency';
  const displayNote=chartData.condensed
    ?' · display condensed to '+youtubeIntervalLabel(chartData.displayMinutes)
      +' averages for browser performance'
    :'';
  $('youtubeSelectionNote').textContent=dateSelectionAvailable
    ?scopeLabel+' | '+selectedVideos.size+' selected live video'
      +(selectedVideos.size===1?'':'s')+' | '+from+' to '+to
      +' | '+intervalNote+displayNote
    :'No YouTube data overlaps the selected main dashboard dates.';
  const grouped=new Map();
  for(const row of daily){
    if(!selectedVideos.has(String(row.video_id)))continue;
    const channel=String(row.youtube_channel||'Unknown / NA');
    const key=channel+'\u0000'+String(row.video_id);
    const current=grouped.get(key)||{
      id:String(row.video_id),channel,title:String(row.title||''),
      viewerMinutes:0,peak:0,liveMinutes:0,lastDate:'',
    };
    current.viewerMinutes+=Number(row.viewer_minutes||0);
    current.peak=Math.max(current.peak,Number(row.peak_concurrent_viewers||0));
    current.liveMinutes+=Number(row.live_minutes||0);
    if(String(row.log_date)>=current.lastDate){
      current.lastDate=String(row.log_date);
      current.title=String(row.title||current.title);
    }
    grouped.set(key,current);
  }
  const ranking=[...grouped.values()].sort((a,b)=>b.viewerMinutes-a.viewerMinutes).slice(0,20);
  const maxRank=Math.max(1,...ranking.map(row=>row.viewerMinutes));
  $('youtubeVideoRanking').innerHTML=ranking.length
    ?ranking.map(row=>'<div class="youtube-video-row"><span class="youtube-video-label">'
      +'<strong class="youtube-channel-label">'+esc(row.channel)+'</strong>'
      +'<small>'+esc(row.id)+' · '+esc(row.title)+'</small></span>'
      +'<div class="youtube-mini-bar"><i style="width:'
      +((row.viewerMinutes/maxRank)*100)+'%"></i></div>'
      +'<span class="youtube-video-value">'+fmt(row.viewerMinutes)
      +'<small>viewer-minutes<br>Peak '+fmt(row.peak)+'</small></span></div>').join('')
    :'<div class="audience-empty">No live YouTube videos for this selection.</div>';
  const events=youtubeRangeEvents(from,to);
  const eventPreview=events.slice().sort((a,b)=>
    a.on_air_start_ist.localeCompare(b.on_air_start_ist)).slice(-50).reverse();
  $('youtubeEventContext').innerHTML=eventPreview.length
    ?eventPreview.map(event=>{
      const row=stats.get(youtubeMinuteKey(event.on_air_start_ist));
      return '<div class="youtube-context-row"><span>'+formatIst(event.on_air_start_ist)
        +'</span><span><strong>'+esc(event.event_id)+'</strong><small>'
        +esc(event.ad_type)+'</small></span><span>'+esc(event.creative_title)
        +'</span><span class="youtube-context-value">'
        +(row?fmt(row.total):'0')+'</span><span class="youtube-context-value">'
        +(row?fmt(row.videos.size):'0')+'</span></div>';
    }).join('')
    :'<div class="audience-empty">No delivered ad events in this selection.</div>';
}
function youtubeMinuteChannelExportRows(youtube,from,to){
  const stats=new Map();
  for(const row of youtubeSelectedVideoMinuteRows(youtube,from,to)){
    const channel=String(row.youtube_channel||'Unknown / NA');
    const key=youtubeMinuteKey(row.timestamp_ist)+'\u0000'+channel;
    const current=stats.get(key)||{
      timestamp:youtubeMinuteKey(row.timestamp_ist),date:String(row.log_date),
      channel,total:0,peak:0,videos:new Set(),
    };
    const value=Number(row.concurrent_viewers||0);
    current.total+=value;
    current.peak=Math.max(current.peak,value);
    current.videos.add(String(row.video_id));
    stats.set(key,current);
  }
  return [...stats.values()].sort((a,b)=>
    a.timestamp.localeCompare(b.timestamp)||a.channel.localeCompare(b.channel));
}
function exportYoutubeCsvChannelAware(){
  const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value;
  const interval=$('youtubeExportInterval').value;
  const selectedChannels=[...youtubeSelectedChannels()].sort().join(' | ');
  let header,rows;
  if(interval==='1'){
    header=[
      'IST Time','Date IST','Selected YouTube Channels','YouTube Channel',
      'Live Concurrency','Peak Video Concurrency','Live Video Count','Metric Basis',
    ];
    rows=youtubeMinuteChannelExportRows(youtube,from,to).map(row=>[
      formatIst(row.timestamp),row.date,selectedChannels,row.channel,row.total,
      row.peak,row.videos.size,'Minute total for selected videos in this channel',
    ]);
  }else{
    const channels=youtubeSelectedChannels(),videos=youtubeSelectedVideoIds();
    header=[
      'IST Time (5-minute bucket)','Date IST','Selected YouTube Channels',
      'YouTube Channel','Video ID','Video Title','Average Live Concurrency',
      'Peak Live Concurrency','Metric Basis',
    ];
    rows=(youtubeDateMode==='follow'&&!youtubeDateOverlap
      ?[]
      :youtubeRowsForDate(youtube.video_5min,from,to))
      .filter(row=>youtubeRowInChannels(row,channels)&&videos.has(String(row.video_id)))
      .sort((a,b)=>String(a.bucket_ist).localeCompare(String(b.bucket_ist))
        ||String(a.youtube_channel).localeCompare(String(b.youtube_channel))
        ||String(a.video_id).localeCompare(String(b.video_id)))
      .map(row=>[
        formatIst(row.bucket_ist),row.log_date,selectedChannels,row.youtube_channel,
        row.video_id,row.title,Number(row.avg_concurrent_viewers||0),
        Number(row.peak_concurrent_viewers||0),'5-minute per-video average and peak',
      ]);
  }
  downloadCsv(
    'youtube_live_audience_'+interval+'min_'+from+'_to_'+to+'_selected_channels.csv',
    header,
    rows,
  );
}
function exportYoutubeReferenceCsvChannelAware(){
  const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value;
  const channels=youtubeSelectedChannels(),videos=youtubeSelectedVideoIds(),grouped=new Map();
  const sourceRows=youtubeDateMode==='follow'&&!youtubeDateOverlap
    ?[]
    :youtubeRowsForDate(youtube.video_5min,from,to);
  for(const row of sourceRows){
    if(!youtubeRowInChannels(row,channels)||!videos.has(String(row.video_id)))continue;
    const channel=String(row.youtube_channel||'Unknown / NA');
    const id=String(row.video_id),key=channel+'\u0000'+id;
    const current=grouped.get(key)||{
      channel,id,title:String(row.title||''),first:String(row.bucket_ist),
      last:String(row.bucket_ist),buckets:0,viewerMinutes:0,peak:0,
    };
    current.title=String(row.title||current.title);
    current.first=String(row.bucket_ist)<current.first?String(row.bucket_ist):current.first;
    current.last=String(row.bucket_ist)>current.last?String(row.bucket_ist):current.last;
    current.buckets++;
    current.viewerMinutes+=Number(row.avg_concurrent_viewers||0)*5;
    current.peak=Math.max(current.peak,Number(row.peak_concurrent_viewers||0));
    grouped.set(key,current);
  }
  const rows=[...grouped.values()].sort((a,b)=>b.viewerMinutes-a.viewerMinutes).map(row=>[
    from+' to '+to,row.channel,row.id,row.title,formatIst(row.first),
    formatIst(row.last),row.buckets,row.viewerMinutes,row.peak,
  ]);
  downloadCsv(
    'youtube_channel_video_reference_'+from+'_to_'+to+'.csv',
    [
      'Selected YouTube Range','YouTube Channel','Video ID','Video Title',
      'First Observed IST','Last Observed IST','5-Minute Live Buckets',
      'Estimated Viewer-Minutes','Peak Live Concurrency',
    ],
    rows,
  );
}
function ensureGlobalAudienceFilters(){
  if($('globalAudienceFilters'))return;
  const filters=document.querySelector('.filters');
  filters.insertAdjacentHTML(
    'beforeend',
    '<details class="global-audience-details" id="globalAudienceDetails" open>'
    +'<summary>Audience Scope '
    +'<small>ASRUN / FAST / STREAM / AMAGI / YOUTUBE</small></summary>'
    +'<section class="global-audience-filters" id="globalAudienceFilters" '
    +'aria-label="Global audience source filters">'
    +'<div class="global-audience-heading"><strong>Audience Scope</strong>'
    +'<small>Applies across all dashboard pages</small></div>'
    +'<div class="global-source-group" id="globalFastFilters">'
    +'<span class="source-tag fast-tag">FAST</span></div>'
    +'<div class="global-source-group" id="globalStreamFilters">'
    +'<span class="source-tag stream-tag">STREAM</span></div>'
    +'<div class="global-source-group" id="globalAmagiFilters">'
    +'<span class="source-tag amagi-tag">AMAGI</span></div>'
    +'<div class="global-source-group" id="globalYoutubeFilters">'
    +'<span class="source-tag youtube-tag">YOUTUBE</span></div>'
    +'<div class="global-source-group global-asrun-group" id="globalAsrunFilters">'
    +'<span class="source-tag combined-tag">ASRUN</span></div>'
    +'<div class="nct-story-source-note">Audience/concurrency metrics follow this '
    +'scope. Source-native ASRUN, FCT, and NCT record counts remain unchanged.</div>'
    +'</section></details>',
  );
  const move=(target,...ids)=>{
    for(const id of ids){
      const label=$(id+'Toggle')?.closest('.filter-label');
      if(label)$(target).append(label);
    }
  };
  move('globalFastFilters','fastPlatform','fastChannel');
  move('globalStreamFilters','streamChannel');
  move('globalAmagiFilters','amagiPlatform','amagiChannel');
  move('globalYoutubeFilters','youtubeChannel');
  move(
    'globalAsrunFilters',
    'spotAdId','spotCreative','lbandAdId','lbandCreative',
  );
  for(const controls of document.querySelectorAll('.rank-controls')){
    if(!controls.children.length)controls.remove();
  }
  if(window.matchMedia('(max-width: 680px)').matches){
    $('globalAudienceDetails').open=false;
  }
}
youtubeDeliveryDetails=function(event){
  const youtube=DATA.youtube||{},key=youtubeMinuteKey(event.on_air_start_ist);
  if(!dashboardSourceLoaded('youtube'))return {
    value:dashboardSourceError('youtube')||'Loading',
    total:null,
    live_videos:0,
    video_ids:'',
    video_titles:'',
    scope:'India TV YouTube is loading',
  };
  const channels=new Set(indiaTvYoutubeChannels());
  if(!channels.size)return {
    value:'0',total:0,live_videos:0,video_ids:'',video_titles:'',
    scope:'No India TV YouTube collector',
  };
  const selectionKey=[...channels].sort().join('\u0000');
  if(!(youtubeDeliveryMinuteIndex instanceof Map)){
    youtubeDeliveryMinuteIndex=new Map();
  }
  if(!youtubeDeliveryMinuteIndex.has(selectionKey)){
    const totals=new Map(),videos=new Map();
    for(const row of youtube.video_minute||[]){
      if(!channels.has(String(row.youtube_channel||'Unknown / NA')))continue;
      const minuteKey=youtubeMinuteKey(row.timestamp_ist);
      totals.set(
        minuteKey,
        (totals.get(minuteKey)||0)+Number(row.concurrent_viewers||0),
      );
      const list=videos.get(minuteKey)||[];
      list.push(row);
      videos.set(minuteKey,list);
    }
    youtubeDeliveryMinuteIndex.set(selectionKey,{totals,videos});
  }
  const index=youtubeDeliveryMinuteIndex.get(selectionKey);
  const hasMinute=index.totals.has(key);
  const videoRows=index.videos.get(key)||[];
  let scope=indiaTvYoutubeScopeLabel();
  if(!hasMinute)return {
    value:'0',total:0,live_videos:0,video_ids:'',video_titles:'',
    scope:(()=>{
      const eventDate=isoDatePart(event.on_air_start_ist),bounds=youtubeTrueBounds();
      if(eventDate&&bounds.start&&bounds.end
        &&(eventDate<bounds.start||eventDate>bounds.end)){
        return 'Outside India TV YouTube source range';
      }
      return 'No India TV YouTube minute record';
    })(),
  };
  const videoIds=[...new Set(videoRows.map(row=>String(row.video_id||'')).filter(Boolean))];
  const titles=[...new Set(videoRows.map(row=>
    youtubeVideoTitle(youtube,row.video_id,row.log_date)).filter(Boolean))];
  const total=Number(index.totals.get(key)||0);
  return {
    value:fmt(total),
    total,
    live_videos:videoIds.length,
    video_ids:videoIds.join(' | '),
    video_titles:titles.join(' | '),
    scope,
  };
};
youtubeFiveMinuteValue=function(event){
  return youtubeDeliveryDetails(event);
};
function applyYoutubeAggregateLabels(){
  const combined=document.querySelector('.combined-panel');
  if(combined){
    const subtitle=combined.querySelector('.panel-head small');
    const column=combined.querySelector('.youtube-col');
    if(subtitle)subtitle.textContent='FAST + STREAM selected 5-minute concurrency | Amagi actual 5-minute concurrency | India TV YouTube minute concurrency';
    if(column){
      column.textContent='INDIA TV YOUTUBE';
      column.title='India TV YouTube minute concurrency';
    }
  }
  const fct=document.querySelector('.fct-audience-panel');
  if(fct){
    const subtitle=fct.querySelector('.panel-head small');
    const column=fct.querySelector('.youtube-col');
    if(subtitle)subtitle.textContent='FCT-selected occurrences | FAST + STREAM + AMAGI 5-minute concurrency | India TV YouTube minute concurrency';
    if(column){
      column.textContent='INDIA TV YOUTUBE';
      column.title='India TV YouTube minute concurrency';
    }
  }
}
queueMicrotask(applyYoutubeAggregateLabels);
function selectedYoutubeRows(){
  const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value;
  if(youtubeDateMode==='follow'&&!youtubeDateOverlap)return [];
  return youtubeSelectedVideoMinuteRows(youtube,from,to);
}
function renderScopeValidation(){
  ensureScopePanel();
  const coverage=DATA.date_coverage||{};
  const asrunRows=filtered(),asrunTrue=sourceBounds(DATA.events||[],'on_air_start_ist','on_air_end_ist'),asrunUsed=sourceBounds(asrunRows,'on_air_start_ist','on_air_end_ist');
  const fastTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='fast'),'minute_ist')||coverageBounds(coverage.fast),fastUsedRows=selectedViewerRows('fast'),fastUsed=sourceBounds(fastUsedRows,'minute_ist');
  const streamTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='stream'),'minute_ist')||coverageBounds(coverage.stream),streamUsedRows=selectedViewerRows('stream'),streamUsed=sourceBounds(streamUsedRows,'minute_ist');
  const amagiTrue=sourceBounds(AMAGI.minute||[],'minute_ist')||coverageBounds(coverage.amagi),amagiUsedRows=selectedAmagiRows(),amagiUsed=sourceBounds(amagiUsedRows,'minute_ist');
  const fctTrue=(FCT.true_start&&FCT.true_end?{start:FCT.true_start,end:FCT.true_end}:null)||coverageBounds(coverage.fct),fctUsedRows=selectedFctRows();
  const fctStart=$('fctFrom').value||isoDatePart(fctTrue?.start),fctEnd=$('fctTo').value||isoDatePart(fctTrue?.end),fctLoaded=dashboardSourceLoaded('fct');
  const fctUsed=sourceBounds(fctUsedRows,'event_ist')||(!fctLoaded&&fctStart&&fctEnd?{start:fctStart+'T00:00:00',end:fctEnd+'T23:59:59'}:null),fctUsedCount=fctLoaded?fctUsedRows.length:'Load on demand';
  const youtube=DATA.youtube||{},youtubeTrue=youtube.true_start&&youtube.true_end?{start:youtube.true_start,end:youtube.true_end}:null,youtubeUsedRows=selectedYoutubeRows(),youtubeUsed=sourceBounds(youtubeUsedRows,'timestamp_ist');
  const masterStart=$('from').value,masterEnd=$('to').value;
  const rows=[
    ['ASRUN delivered ad events',asrunTrue,asrunUsed,asrunRows.length,coverage.asrun,masterStart,masterEnd,'Date, ad type, ad ID, creative title'],
    ['FAST fixed 5-minute audience buckets',fastTrue,fastUsed,fastUsedRows.length,coverage.fast,masterStart,masterEnd,'ASRUN date + FAST platform/channel'],
    ['STREAM fixed 5-minute audience buckets',streamTrue,streamUsed,streamUsedRows.length,coverage.stream,masterStart,masterEnd,'ASRUN date + STREAM channel'],
    ['AMAGI actual 5-minute audience buckets',amagiTrue,amagiUsed,amagiUsedRows.length,coverage.amagi,masterStart,masterEnd,'ASRUN date + AMAGI platform/channel'],
    ['FCT monitored ad occurrences',fctTrue,fctUsed,fctUsedCount,coverage.fct,fctStart,fctEnd,'Independent FCT date + all selected FCT dimensions'],
    ['YouTube live audience',youtubeTrue,youtubeUsed,youtubeUsedRows.length,coverage.youtube,$('youtubeFrom').value,$('youtubeTo').value,'Effective YouTube date + video filter'],
  ];
  $('dataScopeRows').innerHTML=rows.map(row=>'<tr><td><strong>'+esc(row[0])+'</strong></td><td>'+esc(scopeRangeText(row[1]))+'</td><td>'+esc(scopeRangeText(row[2]))+'</td><td>'+(typeof row[3]==='number'?fmt(row[3]):esc(row[3]))+'</td><td>'+scopeContinuityHtml(row[4],row[1],row[5],row[6])+'</td><td class="scope-muted">'+esc(row[7])+'</td></tr>').join('');
}
const NCT=DATA.nct||{};
let nctPayload=null;
let nctLoadPromise=null;
let nctManifest=null;
let nctManifestPromise=null;
let nctInitialized=false;
const nctLoadedDates=new Set();
const nctPartitionPromises=new Map();
let nctDateMode='follow';
let nctAppliedRange=null;
let nctLoadingRange=null;
let nctChart=null;
let nctRenderTimer=null;
let nctFilterCache={key:null,value:null};
let nctChannelIndexes=new Map();
let nctSelectedStory='';
let nctStoryCatalog=[];
const NCT_STORY_OPTION_LIMIT=100;
const NCT_RANK_LIMIT=15;
const NCT_RANK_CONFIG={
  program:{target:'nctProgramRanks',button:'nctProgramExpand',key:'program_name'},
  genre:{target:'nctGenreRanks',button:'nctGenreExpand',key:'primary_genre'},
  geography:{target:'nctGeoRanks',button:'nctGeoExpand',key:'geography'},
};
const nctRankExpanded={program:false,genre:false,geography:false};
let nctStoryAudienceExpanded=false;
let nctAudienceStateCache={key:null,value:null};
let nctStoryAudienceCache={key:null,value:null};
const NCT_SEGMENT_LIMIT=15;
const NCT_SEGMENT_BATCH=200;
let nctSegmentsExpanded=false;
let nctSegmentRenderCount=NCT_SEGMENT_LIMIT;
let nctSegmentRowsCache=[];
const NCT_CONTEXT_LIMIT=15;
let nctContextExpanded=false;
let nctContextRowsCache=[];
const NCT_STORY_SOURCE_FILTER_IDS=['nctYoutubeVideo'];
function resetNctAudienceCaches(){
  nctAudienceStateCache={key:null,value:null};
  nctStoryAudienceCache={key:null,value:null};
}
function preserveNctAllSelections(){
  for(const id of [
    'nctChannel','nctProgram','nctGenre','nctGeo',...NCT_STORY_SOURCE_FILTER_IDS,
  ]){
    const menu=$(id+'Menu');
    if(!menu)continue;
    const inputs=[...menu.querySelectorAll('input[data-value]')];
    if(inputs.length&&inputs.every(input=>input.checked)){
      // "All" is a semantic choice. Reinitializing only all-selected menus
      // includes values that enter when the NCT date universe expands.
      menu.innerHTML='';
      multiInitialized.delete(id);
    }
  }
}
function nctBounds(){
  return {
    start:String(NCT.true_start||NCT.declared_start||'').slice(0,10),
    end:String(NCT.true_end||NCT.declared_end||'').slice(0,10),
  };
}
function updateNctStorySummary(){
  const button=$('nctStoryToggle');
  if(!button)return;
  button.textContent=nctSelectedStory||'All stories';
  button.title=nctSelectedStory||'All stories';
}
function renderNctStoryOptions(){
  const options=$('nctStoryOptions'),count=$('nctStoryCount');
  if(!options||!count)return;
  const query=normalizeMultiSearch($('nctStoryLookup')?.value||'');
  const terms=query.split(/\s+/).filter(Boolean),matches=[];
  for(const item of nctStoryCatalog){
    const text=normalizeMultiSearch(item.value);
    const words=text.split(/\s+/).filter(Boolean);
    const matched=terms.every(term=>words.some(word=>
      word.startsWith(term)||(term.length>=4&&word.includes(term))
    ));
    if(matched)matches.push(item);
    if(matches.length>=NCT_STORY_OPTION_LIMIT)break;
  }
  if(nctSelectedStory&&!matches.some(item=>item.value===nctSelectedStory)){
    const selected=nctStoryCatalog.find(item=>item.value===nctSelectedStory);
    if(selected)matches.unshift(selected);
  }
  options.innerHTML=matches.length?matches.map(item=>
    '<button type="button" class="nct-story-option '
    +(item.value===nctSelectedStory?'active':'')+'" data-nct-story="'+esc(item.value)+'">'
    +'<span>'+esc(item.value)+'</span><small>'+fmt(item.count)+' rows</small></button>'
  ).join(''):'<span class="audience-empty">No matching stories.</span>';
  const suffix=nctStoryCatalog.length>NCT_STORY_OPTION_LIMIT?' · refine with search':'';
  count.textContent=fmt(matches.length)+' shown of '+fmt(nctStoryCatalog.length)+suffix;
}
function refreshNctStoryCatalog(rows){
  const counts=new Map();
  for(const row of rows){
    const value=nctText(row,'story');
    counts.set(value,(counts.get(value)||0)+1);
  }
  nctStoryCatalog=[...counts.entries()]
    .map(([value,count])=>({value,count}))
    .sort((a,b)=>b.count-a.count||a.value.localeCompare(b.value));
  if(nctSelectedStory&&!counts.has(nctSelectedStory))nctSelectedStory='';
  updateNctStorySummary();
  renderNctStoryOptions();
}
function selectNctStory(value){
  nctSelectedStory=String(value||'');
  updateNctStorySummary();
  closeMultiMenu($('nctStoryMenu'));
  nctFilterCache={key:null,value:null};
  scheduleNctRender();
  updateResetState();
}
function initializeNctStoryDropdown(){
  $('nctStoryToggle').addEventListener('click',event=>{
    event.stopPropagation();
    const menu=$('nctStoryMenu'),opening=!menu.classList.contains('open');
    closeMultiMenus('nctStory');
    menu.classList.toggle('open',opening);
    if(opening){
      renderNctStoryOptions();
      requestAnimationFrame(()=>{
        alignMultiMenu(menu);
        $('nctStoryLookup').focus();
      });
    }else clearMultiMenuSearch(menu);
  });
  $('nctStoryLookup').addEventListener('input',renderNctStoryOptions);
  $('nctStoryLookup').addEventListener('change',event=>event.stopPropagation());
  $('nctStoryLookup').addEventListener('keydown',event=>{
    if(event.key==='Escape'){
      closeMultiMenu($('nctStoryMenu'));
      $('nctStoryToggle').focus();
    }
  });
  $('nctStoryAll').addEventListener('click',event=>{
    event.preventDefault();
    event.stopPropagation();
    $('nctStoryLookup').value='';
    selectNctStory('');
  });
  $('nctStoryOptions').addEventListener('click',event=>{
    const option=event.target.closest('[data-nct-story]');
    if(!option)return;
    event.preventDefault();
    event.stopPropagation();
    selectNctStory(option.dataset.nctStory);
  });
}
function ensureNctPanel(){
  if($('nctPanel'))return;
  $('youtubePanel').insertAdjacentHTML(
    'beforebegin',
    '<section class="panel nct-panel" id="nctPanel">'
    +'<div class="panel-head"><div><h2>NCT Content Intelligence</h2>'
    +'<small>Source-reported story monitoring and delivered-ad editorial context</small></div>'
    +'<div class="panel-actions"><button id="exportNctCsv" type="button">Export segments CSV</button>'
    +'<span class="source-tag nct-tag">NCT</span></div></div>'
    +'<div class="nct-controls"><div class="nct-scope-row">'
    +'<label class="filter-label nct-mode-label">Date scope'
    +'<span class="nct-mode"><button type="button" data-nct-date-mode="follow">Follow Dashboard</button>'
    +'<button type="button" data-nct-date-mode="independent">Independent NCT</button></span></label>'
    +'<span class="nct-date-fields" id="nctDateFields" hidden>'
    +'<label class="filter-label">From<input id="nctFrom" type="date"></label>'
    +'<label class="filter-label">To<input id="nctTo" type="date"></label>'
    +'<button class="nct-apply-date" id="nctApplyDate" type="button">Apply dates</button></span>'
    +'<div class="nct-status"><span class="nct-help" id="nctHelp"></span>'
    +'<span class="nct-qa-note" id="nctQaNote" hidden></span></div></div>'
    +'<div class="nct-filter-grid">'
    +'<label class="filter-label">Channels<span class="multi-select"><button id="nctChannelToggle" class="multi-toggle" type="button">All channels</button><span id="nctChannelMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Programs<span class="multi-select"><button id="nctProgramToggle" class="multi-toggle" type="button">All programs</button><span id="nctProgramMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Primary genre<span class="multi-select"><button id="nctGenreToggle" class="multi-toggle" type="button">All genres</button><span id="nctGenreMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label">Geography<span class="multi-select"><button id="nctGeoToggle" class="multi-toggle" type="button">All geographies</button><span id="nctGeoMenu" class="multi-menu"></span></span></label>'
    +'<label class="filter-label nct-story-filter">Story'
    +'<span class="multi-select"><button id="nctStoryToggle" class="multi-toggle" type="button" title="All stories">All stories</button>'
    +'<span id="nctStoryMenu" class="multi-menu nct-story-menu">'
    +'<span class="multi-search-shell"><input id="nctStoryLookup" class="multi-search" type="search" '
    +'placeholder="Search available stories..." autocomplete="off">'
    +'<span class="multi-search-actions"><span id="nctStoryCount" class="multi-search-count"></span>'
    +'<button id="nctStoryAll" type="button">All stories</button></span></span>'
    +'<span id="nctStoryOptions" class="nct-story-options"></span></span></span></label>'
    +'</div></div>'
    +'<div id="nctLoading" class="nct-loading">NCT story data loads when this section is opened.</div>'
    +'<div id="nctContent" hidden>'
    +'<div class="nct-kpis" id="nctKpis"></div>'
    +'<div class="nct-analytics"><div class="nct-chart-card" id="nctChartCard">'
    +'<div class="nct-chart-head"><div class="nct-chart-title"><h3>Monitored Content Trend</h3>'
    +'<small id="nctChartNote">All available channels selected · zero-only series hidden</small></div>'
    +'<div class="nct-chart-actions"><button id="expandNctChart" type="button">Expand chart</button></div></div>'
    +'<div class="nct-chart-wrap"><canvas id="nctTrend"></canvas><div id="nctChartEmpty" class="nct-chart-empty" hidden>No matching NCT segments.</div></div></div>'
    +'<div class="nct-ranks">'
    +'<div class="nct-rank-card"><div class="nct-rank-head"><h3>Top Programs</h3><button class="nct-rank-toggle" id="nctProgramExpand" type="button">Expand All</button></div><div class="nct-rank-list" id="nctProgramRanks"></div></div>'
    +'<div class="nct-rank-card"><div class="nct-rank-head"><h3>Primary Genres</h3><button class="nct-rank-toggle" id="nctGenreExpand" type="button">Expand All</button></div><div class="nct-rank-list" id="nctGenreRanks"></div></div>'
    +'<div class="nct-rank-card"><div class="nct-rank-head"><h3>Story Geographies</h3><button class="nct-rank-toggle" id="nctGeoExpand" type="button">Expand All</button></div><div class="nct-rank-list" id="nctGeoRanks"></div></div>'
    +'</div></div>'
    +'<div class="nct-story-audience nct-rank-card">'
    +'<div class="nct-rank-head"><div><h3>Story Performance</h3>'
    +'<small>Interval-weighted viewer delivery and airtime efficiency for the current filters</small></div>'
    +'<div class="panel-actions nct-story-performance-controls">'
    +'<label class="filter-label">Audience basis<select id="nctStoryAudienceBasis">'
    +'<option value="combined" selected>Combined sources</option><option value="fast">FAST</option>'
    +'<option value="stream">STREAM</option><option value="amagi">AMAGI</option>'
    +'<option value="youtube">YouTube</option></select></label>'
    +'<label class="filter-label">Rank by<select id="nctStoryRankBy">'
    +'<option value="viewerHours" selected>Viewer Hours</option>'
    +'<option value="ama">Average Minute Audience</option>'
    +'<option value="performanceIndex">Performance Index</option>'
    +'<option value="viewingShare">Viewing Share</option><option value="seconds">Monitored Time</option>'
    +'</select></label><button id="exportNctStoryAudienceCsv" type="button">Export CSV</button>'
    +'<button class="nct-rank-toggle" id="nctStoryExpand" type="button">Expand All</button></div></div>'
    +'<div class="nct-story-source-filters" id="nctStorySourceFilters">'
    +'<div class="nct-story-source-group" data-nct-story-source="youtube">'
    +'<label class="filter-label">YouTube video drilldown<span class="multi-select">'
    +'<button id="nctYoutubeVideoToggle" class="multi-toggle" type="button">All videos</button>'
    +'<span id="nctYoutubeVideoMenu" class="multi-menu"></span></span></label></div>'
    +'<div class="nct-story-source-note" id="nctStorySourceNote"></div></div>'
    +'<div class="nct-story-audience-table" id="nctStoryTable">'
    +'<div class="nct-story-audience-columns"><span>Story</span><span>Monitored</span>'
    +'<span>Clips</span><span>Viewer Hours</span><span>AMA</span>'
    +'<span>Viewing Share</span><span>Airtime Share</span>'
    +'<span>Performance Index</span><span>Coverage</span></div>'
    +'<div class="nct-story-audience-list" id="nctStoryRanks"></div></div>'
    +'<div class="nct-preview-note nct-story-audience-note" '
    +'id="nctStoryAudienceNote"></div></div>'
    +'<div class="nct-segment-section nct-rank-card">'
    +'<div class="nct-rank-head"><div><h3>Story Clip Records</h3>'
    +'<small>Latest matching NCT clips for the current filters</small></div>'
    +'<button class="nct-rank-toggle" id="nctSegmentExpand" type="button">Expand All</button></div>'
    +'<div class="nct-segment-table" id="nctSegmentTable">'
    +'<div class="nct-segment-columns"><span>Clip start IST</span><span>Channel</span>'
    +'<span>Program</span><span>Story / Sub-story</span><span>Genre / Geography</span>'
    +'<span>Duration</span></div>'
    +'<div class="nct-segment-list" id="nctSegmentRows"></div></div>'
    +'<div class="nct-preview-note nct-story-audience-note" id="nctSegmentNote"></div></div>'
    +'<div class="nct-context"><div class="nct-context-head"><div><h3>Delivered Ad Content Context</h3>'
    +'<small>Explicit NCT channel assignment; concurrency totals are unchanged</small></div>'
    +'<div class="panel-actions"><label class="filter-label nct-context-control">NCT context channel<select id="nctContextChannel"></select></label>'
    +'<button id="exportNctContextCsv" type="button">Export context CSV</button>'
    +'<button class="nct-rank-toggle" id="nctContextExpand" type="button">Expand All</button></div></div>'
    +'<div class="nct-context-table" id="nctContextTable">'
    +'<div class="nct-context-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Match</span><span>Program</span><span>Story context</span><span>Distance</span></div>'
    +'<div id="nctContextRows"></div></div>'
    +'<div class="nct-preview-note nct-story-audience-note" id="nctContextNote"></div></div>'
    +'</div></section>'
  );
  const bounds=nctBounds();
  for(const id of ['nctFrom','nctTo']){
    $(id).min=bounds.start;
    $(id).max=bounds.end;
    $(id).value=id==='nctFrom'?bounds.start:bounds.end;
    $(id).addEventListener('change',()=>{
      updateNctDateConstraints();
      updateNctApplyState();
      updateNctHelp();
    });
  }
  $('nctApplyDate').addEventListener('click',applyNctDateRange);
  for(const button of document.querySelectorAll('[data-nct-date-mode]')){
    button.addEventListener('click',()=>setNctDateMode(button.dataset.nctDateMode));
  }
  initializeNctStoryDropdown();
  $('exportNctCsv').addEventListener('click',()=>loadNctData().then(exportNctCsv));
  $('exportNctStoryAudienceCsv').addEventListener('click',()=>runWithDashboardSources(
    [loadAudienceDashboardData,loadYoutubeDashboardData,loadNctData],
    exportNctStoryAudienceCsv,
  ));
  $('exportNctContextCsv').addEventListener('click',()=>loadNctData().then(exportNctContextCsv));
  $('nctContextChannel').addEventListener('change',()=>{
    renderNctContext();
    updateResetState();
  });
  $('nctContextExpand').addEventListener('click',toggleNctContext);
  for(const kind of Object.keys(NCT_RANK_CONFIG)){
    $(NCT_RANK_CONFIG[kind].button).addEventListener('click',()=>toggleNctRank(kind));
  }
  $('nctStoryExpand').addEventListener('click',()=>{
    nctStoryAudienceExpanded=!nctStoryAudienceExpanded;
    renderNctStoryAudience(nctFilteredRows());
  });
  for(const id of ['nctStoryAudienceBasis','nctStoryRankBy']){
    $(id).addEventListener('change',()=>{
      if(id==='nctStoryAudienceBasis')updateNctStorySourceControls();
      renderNctStoryAudience(nctFilteredRows());
      updateResetState();
    });
  }
  $('nctSegmentExpand').addEventListener('click',toggleNctSegments);
  $('nctSegmentTable').addEventListener('scroll',event=>{
    const list=event.currentTarget;
    if(
      !nctSegmentsExpanded
      ||nctSegmentRenderCount>=nctSegmentRowsCache.length
      ||list.scrollTop+list.clientHeight<list.scrollHeight-120
    )return;
    nctSegmentRenderCount=Math.min(
      nctSegmentRowsCache.length,nctSegmentRenderCount+NCT_SEGMENT_BATCH
    );
    renderNctSegmentList(false);
  });
  $('expandNctChart').addEventListener('click',toggleNctChart);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&$('nctChartCard')?.classList.contains('expanded'))toggleNctChart();
  });
  setNctDateMode('follow',false);
}
function nctFollowRange(){
  const bounds=nctBounds();
  const start=$('from').value>bounds.start?$('from').value:bounds.start;
  const end=$('to').value<bounds.end?$('to').value:bounds.end;
  return {start,end,valid:Boolean(start&&end&&start<=end)};
}
function nctInputRange(){
  const start=$('nctFrom').value,end=$('nctTo').value,bounds=nctBounds();
  return {
    start,end,
    valid:Boolean(
      start&&end&&start<=end&&start>=bounds.start&&end<=bounds.end
    ),
  };
}
function nctEffectiveRange(){
  if(nctDateMode==='independent')return nctAppliedRange||nctInputRange();
  return nctFollowRange();
}
function updateNctDateConstraints(){
  const bounds=nctBounds(),from=$('nctFrom'),to=$('nctTo');
  from.min=bounds.start;
  from.max=to.value&&to.value<bounds.end?to.value:bounds.end;
  to.min=from.value&&from.value>bounds.start?from.value:bounds.start;
  to.max=bounds.end;
}
function nctDateRangePending(){
  if(nctDateMode!=='independent'||!nctAppliedRange)return false;
  const input=nctInputRange();
  return input.start!==nctAppliedRange.start||input.end!==nctAppliedRange.end;
}
function updateNctApplyState(){
  const button=$('nctApplyDate');
  if(!button)return;
  const pending=nctDateRangePending();
  button.disabled=!nctInputRange().valid||!pending||Boolean(nctLoadingRange);
  button.classList.toggle('pending',pending&&nctInputRange().valid);
  button.textContent=nctLoadingRange?'Loading...':pending?'Apply dates':'Applied';
}
function updateNctHelp(){
  const range=nctEffectiveRange(),missing=NCT.missing_selected_channels||[];
  const bounds=nctBounds();
  const available=bounds.start&&bounds.end
    ?shortDate(bounds.start)+' to '+shortDate(bounds.end)
    :'Not available';
  const used=range.valid?shortDate(range.start)+' to '+shortDate(range.end):'No overlap';
  let detail='Data loads when this page is opened';
  if(nctLoadingRange){
    detail='Loading selected dates';
  }else if(nctPayload?.available&&nctManifest&&range.valid
    &&nctMissingPartitions(range).length===0){
    const rows=nctDateRows();
    const channels=new Set(rows.map(row=>nctText(row,'channel_name')));
    detail=fmt(rows.length)+' rows | '+fmt(channels.size)+' channels in scope';
  }
  $('nctHelp').innerHTML='<strong>Available:</strong> '+esc(available)
    +' &nbsp; <strong>Used:</strong> '+esc(used)+' &nbsp; '+esc(detail)
    +(nctDateRangePending()?' &nbsp; <strong>Pending date changes</strong>':'');
  const qa=$('nctQaNote');
  if(qa){
    qa.hidden=!missing.length;
    qa.textContent=missing.length?fmt(missing.length)+' configured channel absent':'';
    qa.title=missing.length?'No source rows found for: '+missing.join(', '):'';
  }
  updateNctApplyState();
}
function applyNctDateRange(){
  const range=nctInputRange();
  if(!range.valid)return;
  preserveNctAllSelections();
  nctAppliedRange={start:range.start,end:range.end,valid:true};
  nctFilterCache={key:null,value:null};
  resetNctAudienceCaches();
  updateNctApplyState();
  updateNctHelp();
  loadNctData().catch(error=>{
    console.error('NCT date partition load failed:',error);
    showFatalDashboardError('NCT date load',error);
  });
}
function setNctDateMode(mode,renderNow=true){
  preserveNctAllSelections();
  nctDateMode=mode==='independent'?'independent':'follow';
  for(const button of document.querySelectorAll('[data-nct-date-mode]')){
    const active=button.dataset.nctDateMode===nctDateMode;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  }
  const follow=nctDateMode==='follow';
  if(!follow&&!nctAppliedRange){
    const initial=nctFollowRange(),bounds=nctBounds();
    const range=initial.valid?initial:{start:bounds.end,end:bounds.end,valid:true};
    nctAppliedRange={start:range.start,end:range.end,valid:true};
    $('nctFrom').value=range.start;
    $('nctTo').value=range.end;
  }
  $('nctDateFields').hidden=follow;
  $('nctFrom').disabled=follow;
  $('nctTo').disabled=follow;
  updateNctDateConstraints();
  nctFilterCache={key:null,value:null};
  resetNctAudienceCaches();
  syncDateControlVisibility();
  updateNctHelp();
  if(renderNow)loadNctData().catch(error=>{
    console.error('NCT date mode load failed:',error);
    showFatalDashboardError('NCT date mode load',error);
  });
  updateResetState();
}
function loadNctManifest(){
  if(nctManifest)return Promise.resolve(nctManifest);
  if(nctManifestPromise)return nctManifestPromise;
  nctManifestPromise=new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.src=NCT.sidecar||'nct_story_data.js';
    script.onload=()=>{
      nctManifest=window.__NCT_STORY_DATA__||{available:false,segments:[]};
      nctPayload=nctManifest.partitioned
        ?{available:Boolean(nctManifest.available),reason:nctManifest.reason||'',segments:[]}
        :nctManifest;
      resolve(nctManifest);
    };
    script.onerror=()=>reject(new Error('NCT story manifest could not be loaded.'));
    document.head.appendChild(script);
  });
  return nctManifestPromise;
}
function nctMissingPartitions(range){
  if(!nctManifest?.partitioned||!range.valid)return [];
  return Object.entries(nctManifest.dates||{}).filter(([dateValue])=>
    dateValue>=range.start&&dateValue<=range.end&&!nctLoadedDates.has(dateValue)
  );
}
function loadNctPartition(dateValue,file){
  if(nctLoadedDates.has(dateValue))return Promise.resolve();
  if(nctPartitionPromises.has(dateValue))return nctPartitionPromises.get(dateValue);
  const promise=new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.src=file;
    script.onload=()=>{
      const rows=window.__NCT_STORY_PARTITIONS__?.[dateValue];
      if(!Array.isArray(rows)){
        reject(new Error(file+' did not publish NCT rows for '+dateValue));
        return;
      }
      for(const row of rows)nctPayload.segments.push(row);
      delete window.__NCT_STORY_PARTITIONS__[dateValue];
      nctLoadedDates.add(dateValue);
      resolve();
    };
    script.onerror=()=>reject(new Error('NCT daily partition could not be loaded: '+file));
    document.head.appendChild(script);
  }).finally(()=>nctPartitionPromises.delete(dateValue));
  nctPartitionPromises.set(dateValue,promise);
  return promise;
}
async function loadNctPartitions(missing){
  const batchSize=12;
  for(let index=0;index<missing.length;index+=batchSize){
    const batch=missing.slice(index,index+batchSize);
    $('nctLoading').textContent='Loading NCT dates '+fmt(index+1)+'-'
      +fmt(index+batch.length)+' of '+fmt(missing.length)+'...';
    await Promise.all(batch.map(([dateValue,file])=>
      loadNctPartition(dateValue,file)
    ));
  }
}
async function loadNctData(){
  ensureNctPanel();
  if(!NCT.available){
    $('nctLoading').textContent=NCT.reason||'NCT story data is unavailable.';
    $('nctLoading').classList.add('nct-load-error');
    return null;
  }
  if(nctLoadPromise){
    await nctLoadPromise;
    if(nctMissingPartitions(nctEffectiveRange()).length)return loadNctData();
    return nctPayload;
  }
  $('nctLoading').textContent='Loading validated NCT story segments...';
  $('nctLoading').hidden=false;
  nctLoadingRange={...nctEffectiveRange()};
  updateNctHelp();
  const operation=(async()=>{
    await loadNctManifest();
    const range=nctEffectiveRange();
    const missing=nctMissingPartitions(range);
    await loadNctPartitions(missing);
    if(missing.length){
      nctPayload.segments.sort((a,b)=>
        String(a.clip_start_ist).localeCompare(String(b.clip_start_ist))
      );
    }
    nctChannelIndexes=new Map();
    nctFilterCache={key:null,value:null};
    if(!nctInitialized){
      initializeNctData();
      nctInitialized=true;
    }else{
      refreshNctFilters();
      renderNct(false);
    }
    $('nctLoading').hidden=true;
    return nctPayload;
  })();
  nctLoadPromise=operation;
  try{
    return await operation;
  }catch(error){
      $('nctLoading').textContent=error.message;
      $('nctLoading').classList.add('nct-load-error');
    throw error;
  }finally{
    nctLoadPromise=null;
    nctLoadingRange=null;
    updateNctHelp();
  }
}
function initializeNctData(){
  const channels=NCT.channels||[];
  $('nctContextChannel').innerHTML=channels.map(channel=>
    '<option value="'+esc(channel)+'">'+esc(channel)+'</option>'
  ).join('');
  if(channels.includes('INDIA TV'))$('nctContextChannel').value='INDIA TV';
  $('nctLoading').hidden=true;
  $('nctContent').hidden=false;
  for(const id of ['nctChannel','nctProgram','nctGenre','nctGeo']){
    multiInitialized.delete(id);
  }
  refreshNctFilters();
  renderNct(false);
}
function nctDateRows(){
  if(!nctPayload?.available)return [];
  const range=nctEffectiveRange();
  if(!range.valid)return [];
  return (nctPayload.segments||[]).filter(row=>
    String(row.log_date)>=range.start&&String(row.log_date)<=range.end
  );
}
function nctText(row,key){
  const value=String(row[key]??'').trim();
  return value||'Unknown / NA';
}
const NCT_FILTER_SPECS=[
  ['nctChannel','channel_name','channels'],
  ['nctProgram','program_name','programs'],
  ['nctGenre','primary_genre','genres'],
  ['nctGeo','geography','geographies'],
];
function wrapNctOptionLabels(id){
  const menu=$(id+'Menu');
  if(!menu)return;
  for(const label of menu.querySelectorAll('.multi-option')){
    if(label.querySelector('.nct-option-label'))continue;
    const textNodes=[...label.childNodes].filter(node=>
      node.nodeType===Node.TEXT_NODE&&node.textContent.trim()
    );
    if(!textNodes.length)continue;
    const text=textNodes.map(node=>node.textContent.trim()).join(' ');
    for(const node of textNodes)node.remove();
    const span=document.createElement('span');
    span.className='nct-option-label';
    span.textContent=text;
    label.appendChild(span);
  }
}
function resetSemanticAllSelection(id){
  const menu=$(id+'Menu');
  if(!menu)return;
  const inputs=[...menu.querySelectorAll('input[data-value]')];
  if(inputs.length&&inputs.every(input=>input.checked)){
    menu.innerHTML='';
    multiInitialized.delete(id);
  }
}
function nctStorySourceDateRows(rows){
  const range=nctEffectiveRange();
  if(!range.valid)return [];
  return rows.filter(row=>
    String(row.log_date)>=range.start&&String(row.log_date)<=range.end
  );
}
function updateNctStorySourceControls(){
  const basis=nctStoryAudienceBasis();
  for(const group of document.querySelectorAll('[data-nct-story-source]')){
    group.hidden=!['combined','youtube'].includes(basis);
  }
  const note=$('nctStorySourceNote');
  if(note){
    note.textContent='Audience platform/channel scope comes from the fixed header. '
      +(basis==='combined'
        ?'Combined source totals are not cross-source deduplicated.'
        :nctStoryBasisLabel(basis)+' uses its matching header filters.')
      +(groupVisibleForNctYoutube(basis)
        ?' The YouTube video control is an optional local drilldown.':'');
  }
}
function groupVisibleForNctYoutube(basis){
  return basis==='combined'||basis==='youtube';
}
function nctStorySourceSelectionChanged(dependentId=''){
  if(dependentId)resetSemanticAllSelection(dependentId);
  resetNctAudienceCaches();
  refreshNctStorySourceFilters();
  if(nctPayload)renderNctStoryAudience(nctFilteredRows());
  updateResetState();
}
function labelNctYoutubeVideoOptions(titleById){
  wrapNctOptionLabels('nctYoutubeVideo');
  const menu=$('nctYoutubeVideoMenu');
  if(!menu)return;
  for(const input of menu.querySelectorAll('input[data-value]')){
    const label=input.closest('.multi-option'),text=label?.querySelector('.nct-option-label');
    if(text){
      const title=titleById.get(String(input.dataset.value))||String(input.dataset.value);
      text.textContent=title+' · '+String(input.dataset.value);
    }
  }
  const selected=[...selectedMulti('nctYoutubeVideo')];
  const total=menu.querySelectorAll('input[data-value]').length;
  if(selected.length===total&&total)$('nctYoutubeVideoToggle').textContent='All videos';
  else if(selected.length===1){
    $('nctYoutubeVideoToggle').textContent=titleById.get(selected[0])||selected[0];
  }else $('nctYoutubeVideoToggle').textContent=selected.length+' videos selected';
  applyMultiSearch('nctYoutubeVideo');
}
function refreshNctStorySourceFilters(){
  if(!$('nctStorySourceFilters'))return;
  const youtube=nctStorySourceDateRows((DATA.youtube||{}).video_minute||[]);
  const selectedYoutubeChannels=selectedMulti('youtubeChannel');
  const selectedYoutubeRows=youtube.filter(row=>selectedYoutubeChannels.has(
    String(row.youtube_channel||'Unknown / NA')
  ));
  const videoIds=[...new Set(selectedYoutubeRows
    .map(row=>String(row.video_id||'')).filter(Boolean))]
    .sort();
  const titleById=new Map();
  for(const row of ((DATA.youtube||{}).video_daily||[])){
    const channel=String(row.youtube_channel||'Unknown / NA');
    if(!selectedYoutubeChannels.has(channel))continue;
    const id=String(row.video_id||'');
    if(id&&String(row.title||'').trim()){
      titleById.set(id,channel+' Â· '+String(row.title).trim());
    }
  }
  buildMulti(
    'nctYoutubeVideo',videoIds,'videos',videoIds,
    ()=>nctStorySourceSelectionChanged(),
  );
  for(const id of NCT_STORY_SOURCE_FILTER_IDS)wrapNctOptionLabels(id);
  labelNctYoutubeVideoOptions(titleById);
  updateNctStorySourceControls();
}
function refreshNctFilters(){
  if(!nctPayload?.available)return;
  const base=nctDateRows();
  refreshNctStoryCatalog(base);
  // Keep each NCT selector independent for the same reason as FCT: a user
  // clearing Program must not silently erase Channel, Genre, or Geography.
  for(const [id,key,kind] of NCT_FILTER_SPECS){
    const values=[...new Set(base.map(row=>nctText(row,key)))].sort();
    buildMulti(id,values,kind,values,()=>{
      nctFilterCache={key:null,value:null};
      scheduleNctRender();
    });
    wrapNctOptionLabels(id);
  }
  refreshNctStorySourceFilters();
  updateNctHelp();
}
function nctFilteredRows(){
  if(!nctPayload?.available)return [];
  const range=nctEffectiveRange();
  const key=[
    range.start,range.end,
    [...selectedMulti('nctChannel')].sort().join('|'),
    [...selectedMulti('nctProgram')].sort().join('|'),
    [...selectedMulti('nctGenre')].sort().join('|'),
    [...selectedMulti('nctGeo')].sort().join('|'),
    nctSelectedStory,
  ].join('\u0000');
  if(nctFilterCache.key===key&&nctFilterCache.value)return nctFilterCache.value;
  const channels=selectedMulti('nctChannel'),programs=selectedMulti('nctProgram');
  const genres=selectedMulti('nctGenre'),geographies=selectedMulti('nctGeo');
  const result=nctDateRows().filter(row=>
    channels.has(nctText(row,'channel_name'))
    &&programs.has(nctText(row,'program_name'))
    &&genres.has(nctText(row,'primary_genre'))
    &&geographies.has(nctText(row,'geography'))
    &&(!nctSelectedStory||nctText(row,'story')===nctSelectedStory)
  );
  nctFilterCache={key,value:result};
  return result;
}
function scheduleNctRender(){
  clearTimeout(nctRenderTimer);
  nctRenderTimer=setTimeout(()=>renderNct(false),120);
}
function nctHours(seconds){
  const value=Number(seconds||0),hours=Math.round(value/3600);
  return hours?fmt(hours)+' h':fmt(Math.round(value/60))+' min';
}
function nctAudienceSelectionKey(range){
  return [
    range.start,range.end,
    [...selectedMulti('fastPlatform')].sort().join('|'),
    [...selectedMulti('fastChannel')].sort().join('|'),
    [...selectedMulti('streamChannel')].sort().join('|'),
    [...selectedMulti('amagiPlatform')].sort().join('|'),
    [...selectedMulti('amagiChannel')].sort().join('|'),
    [...selectedMulti('youtubeChannel')].sort().join('|'),
    [...selectedMulti('nctYoutubeVideo')].sort().join('|'),
  ].join('\u0000');
}
function nctLowerBound(values,target){
  let low=0,high=values.length;
  while(low<high){
    const middle=(low+high)>>1;
    if(values[middle]<target)low=middle+1;
    else high=middle;
  }
  return low;
}
function nctPrepareAudienceState(state){
  const entries=[...state.map.entries()].map(([key,value])=>[
    naiveMillis(String(key).replace(' ','T')),
    Number(value||0),
  ]).filter(entry=>Number.isFinite(entry[0])).sort((a,b)=>a[0]-b[0]);
  const times=[],values=[],prefixValues=[0],prefixCoverage=[0],valueByMillis=new Map();
  for(const [time,value] of entries){
    times.push(time);
    values.push(value);
    valueByMillis.set(time,value);
    prefixValues.push(prefixValues.at(-1)+value);
    prefixCoverage.push(prefixCoverage.at(-1)+1);
  }
  return {...state,times,values,prefixValues,prefixCoverage,valueByMillis};
}
function nctAudienceRangeSum(state,startMinute,endMinute){
  if(!state.times.length||startMinute>=endMinute)return {value:0,covered:0};
  const startIndex=nctLowerBound(state.times,startMinute);
  const endIndex=nctLowerBound(state.times,endMinute);
  return {
    value:state.prefixValues[endIndex]-state.prefixValues[startIndex],
    covered:state.prefixCoverage[endIndex]-state.prefixCoverage[startIndex],
  };
}
function nctAudienceInterval(state,startMillis,endMillis){
  if(!state?.times?.length||!Number.isFinite(startMillis)||!Number.isFinite(endMillis)
    ||endMillis<=startMillis){
    return {viewerMinutes:0,coveredMinutes:0};
  }
  const minute=60000,startMinute=Math.floor(startMillis/minute)*minute;
  const endMinute=Math.floor(endMillis/minute)*minute;
  if(startMinute===endMinute){
    const fraction=(endMillis-startMillis)/minute;
    return state.valueByMillis.has(startMinute)
      ?{
        viewerMinutes:Number(state.valueByMillis.get(startMinute)||0)*fraction,
        coveredMinutes:fraction,
      }
      :{viewerMinutes:0,coveredMinutes:0};
  }
  let viewerMinutes=0,coveredMinutes=0;
  const firstFraction=(startMinute+minute-startMillis)/minute;
  if(state.valueByMillis.has(startMinute)){
    viewerMinutes+=Number(state.valueByMillis.get(startMinute)||0)*firstFraction;
    coveredMinutes+=firstFraction;
  }
  const middle=nctAudienceRangeSum(state,startMinute+minute,endMinute);
  viewerMinutes+=middle.value;
  coveredMinutes+=middle.covered;
  const finalFraction=(endMillis-endMinute)/minute;
  if(finalFraction>0&&state.valueByMillis.has(endMinute)){
    viewerMinutes+=Number(state.valueByMillis.get(endMinute)||0)*finalFraction;
    coveredMinutes+=finalFraction;
  }
  return {viewerMinutes,coveredMinutes};
}
function nctViewerAudienceMinuteMap(source,range){
  const channelId=source==='fast'?'fastChannel':'streamChannel';
  const channels=selectedMulti(channelId),allChannels=multiSelectionIsAll(channelId);
  const platforms=source==='fast'?selectedMulti('fastPlatform'):null;
  const allPlatforms=source!=='fast'||multiSelectionIsAll('fastPlatform');
  const map=new Map();
  let boundStart='',boundEnd='';
  for(const row of (DATA.viewer_minute||[])){
    if(row.source!==source)continue;
    const key=minuteKey(row.minute_ist);
    if(!boundStart||key<boundStart)boundStart=key;
    if(!boundEnd||key>boundEnd)boundEnd=key;
    if(String(row.log_date)<range.start||String(row.log_date)>range.end)continue;
    if(source==='fast'&&!allPlatforms&&!platforms.has(String(row.platform_name)))continue;
    if(!allChannels&&!channels.has(String(row.channel_name)))continue;
    map.set(key,(map.get(key)||0)+Number(row.distinct_cliips||0));
  }
  return {map,bounds:boundStart&&boundEnd?{start:boundStart,end:boundEnd}:null};
}
function nctAmagiAudienceMinuteMap(range){
  const platforms=selectedMulti('amagiPlatform');
  const channels=selectedMulti('amagiChannel');
  const allPlatforms=multiSelectionIsAll('amagiPlatform');
  const allChannels=multiSelectionIsAll('amagiChannel');
  const map=new Map();
  let boundStart='',boundEnd='';
  for(const row of (AMAGI.minute||[])){
    const key=minuteKey(row.minute_ist);
    if(!boundStart||key<boundStart)boundStart=key;
    if(!boundEnd||key>boundEnd)boundEnd=key;
    if(String(row.log_date)<range.start||String(row.log_date)>range.end)continue;
    if(!allPlatforms&&!platforms.has(String(row.platform_name)))continue;
    if(!allChannels&&!channels.has(String(row.channel_name)))continue;
    map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));
  }
  return {map,bounds:boundStart&&boundEnd?{start:boundStart,end:boundEnd}:null};
}
function nctYoutubeAudienceMinuteMap(range){
  const map=new Map(),channels=selectedMulti('youtubeChannel');
  const allChannels=multiSelectionIsAll('youtubeChannel');
  const videos=selectedMulti('nctYoutubeVideo');
  const allVideos=multiSelectionIsAll('nctYoutubeVideo');
  for(const row of ((DATA.youtube||{}).video_minute||[])){
    if(!allChannels&&!channels.has(String(row.youtube_channel||'Unknown / NA')))continue;
    if(String(row.log_date)<range.start||String(row.log_date)>range.end)continue;
    if(!allVideos&&!videos.has(String(row.video_id||'')))continue;
    const key=minuteKey(row.timestamp_ist);
    map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));
  }
  return {map,bounds:map.size?{start:[...map.keys()][0],end:[...map.keys()].at(-1)}:null};
}
function nctCombinedAudienceState(states){
  const map=new Map();
  for(const source of ['fast','stream','amagi','youtube']){
    for(const [key,value] of states[source].map){
      map.set(key,(map.get(key)||0)+Number(value||0));
    }
  }
  return nctPrepareAudienceState({map,bounds:null});
}
function nctAudienceStates(){
  const range=nctEffectiveRange(),key=nctAudienceSelectionKey(range);
  if(nctAudienceStateCache.key===key&&nctAudienceStateCache.value){
    return nctAudienceStateCache.value;
  }
  const value={key};
  value.fast=nctPrepareAudienceState(nctViewerAudienceMinuteMap('fast',range));
  value.stream=nctPrepareAudienceState(nctViewerAudienceMinuteMap('stream',range));
  value.amagi=nctPrepareAudienceState(nctAmagiAudienceMinuteMap(range));
  value.youtube=nctPrepareAudienceState(nctYoutubeAudienceMinuteMap(range));
  value.combined=nctCombinedAudienceState(value);
  nctAudienceStateCache={key,value};
  return value;
}
function nctStoryAudienceRows(rows){
  const states=nctAudienceStates();
  const cacheKey=[nctFilterCache.key||'',states.key].join('\u0000');
  if(nctStoryAudienceCache.key===cacheKey&&nctStoryAudienceCache.value){
    return nctStoryAudienceCache.value;
  }
  const sources=['fast','stream','amagi','youtube','combined'];
  const stories=new Map();
  for(const row of rows){
    const story=nctText(row,'story');
    if(!stories.has(story)){
      stories.set(story,{
        story,
        seconds:0,
        clips:0,
        metrics:Object.fromEntries(sources.map(source=>[
          source,{viewerMinutes:0,coveredMinutes:0},
        ])),
      });
    }
    const entry=stories.get(story);
    const start=naiveMillis(String(row.clip_start_ist||'').replace(' ','T'));
    let end=naiveMillis(String(row.clip_end_ist||'').replace(' ','T'));
    const fallbackSeconds=Math.max(0,Number(row.duration_seconds||0));
    if(!Number.isFinite(end)||end<=start)end=start+(fallbackSeconds*1000);
    const durationSeconds=Number.isFinite(start)&&Number.isFinite(end)&&end>start
      ?(end-start)/1000
      :fallbackSeconds;
    if(!Number.isFinite(start)||!Number.isFinite(end)||durationSeconds<=0)continue;
    entry.seconds+=durationSeconds;
    entry.clips+=1;
    for(const source of sources){
      const interval=nctAudienceInterval(states[source],start,end);
      entry.metrics[source].viewerMinutes+=interval.viewerMinutes;
      entry.metrics[source].coveredMinutes+=interval.coveredMinutes;
    }
  }
  const result=[...stories.values()];
  const totalSeconds=result.reduce((sum,entry)=>sum+entry.seconds,0);
  const totalViewerMinutes=Object.fromEntries(sources.map(source=>[
    source,
    result.reduce((sum,entry)=>sum+entry.metrics[source].viewerMinutes,0),
  ]));
  for(const entry of result){
    entry.airtimeShare=totalSeconds?entry.seconds/totalSeconds*100:0;
    for(const source of sources){
      const metric=entry.metrics[source];
      metric.viewerHours=metric.viewerMinutes/60;
      metric.ama=metric.coveredMinutes
        ?metric.viewerMinutes/metric.coveredMinutes
        :null;
      metric.viewingShare=totalViewerMinutes[source]
        ?metric.viewerMinutes/totalViewerMinutes[source]*100
        :null;
      metric.coverage=entry.seconds
        ?Math.min(100,metric.coveredMinutes/(entry.seconds/60)*100)
        :0;
      metric.performanceIndex=metric.viewingShare!==null&&entry.airtimeShare
        ?metric.viewingShare/entry.airtimeShare*100
        :null;
    }
  }
  nctStoryAudienceCache={key:cacheKey,value:result};
  return result;
}
function nctStoryAudienceBasis(){
  const value=$('nctStoryAudienceBasis')?.value||'combined';
  return ['fast','stream','amagi','youtube','combined'].includes(value)
    ?value:'combined';
}
function nctStoryBasisLabel(source){
  return {
    fast:'FAST',stream:'STREAM',amagi:'AMAGI',
    youtube:'YouTube',combined:'Combined sources',
  }[source]||'Combined sources';
}
function nctStoryRankMetric(){
  const value=$('nctStoryRankBy')?.value||'viewerHours';
  return ['performanceIndex','viewerHours','ama','viewingShare','seconds'].includes(value)
    ?value:'viewerHours';
}
function nctStoryRankValue(entry,basis,metric){
  const value=metric==='seconds'?entry.seconds:entry.metrics[basis][metric];
  return value===null||!Number.isFinite(Number(value))?Number.NEGATIVE_INFINITY:Number(value);
}
function nctSortedStoryAudienceRows(rows){
  const basis=nctStoryAudienceBasis(),metric=nctStoryRankMetric();
  return [...rows].sort((a,b)=>
    nctStoryRankValue(b,basis,metric)-nctStoryRankValue(a,basis,metric)
    ||b.metrics[basis].viewerMinutes-a.metrics[basis].viewerMinutes
    ||b.seconds-a.seconds
    ||a.story.localeCompare(b.story)
  );
}
function nctPerformanceCell(label,value,suffix='',digits=2,title=''){
  const available=value!==null&&Number.isFinite(Number(value));
  const display=available
    ?new Intl.NumberFormat('en-IN',{maximumFractionDigits:digits}).format(Number(value))+suffix
    :'Not available';
  return '<span class="audience-number'+(available?'':' audience-unavailable')
    +'" data-label="'+esc(label)+'" title="'+esc(title)+'">'+esc(display)+'</span>';
}
function renderNctStoryAudience(rows){
  const basis=nctStoryAudienceBasis(),basisLabel=nctStoryBasisLabel(basis);
  const ranked=nctSortedStoryAudienceRows(nctStoryAudienceRows(rows));
  const visible=nctStoryAudienceExpanded?ranked:ranked.slice(0,NCT_RANK_LIMIT);
  const list=$('nctStoryRanks'),table=$('nctStoryTable');
  list.innerHTML=visible.length?visible.map((entry,index)=>{
    const metric=entry.metrics[basis];
    const metricTitle='Based on '+basisLabel+' minute-level audience overlapping '
      +fmt(entry.clips)+' story clip interval'+(entry.clips===1?'':'s');
    const lowBase=entry.seconds<300?' · low time base (<5 min)':'';
    return '<div class="nct-story-audience-row">'
      +'<span class="story-label" data-label="Story"><strong>#'+(index+1)+' '
      +esc(entry.story)+'</strong><small>'+esc(basisLabel)
      +' · full clip-interval audience measurement'+esc(lowBase)+'</small></span>'
      +'<span data-label="Monitored">'+esc(nctHours(entry.seconds))+'</span>'
      +'<span data-label="Clips">'+fmt(entry.clips)+'</span>'
      +nctPerformanceCell('Viewer Hours',metric.viewerHours,' h',2,metricTitle)
      +nctPerformanceCell('AMA',metric.ama,'',2,'Average Minute Audience · '+metricTitle)
      +nctPerformanceCell('Viewing Share',metric.viewingShare,'%',2,metricTitle)
      +nctPerformanceCell('Airtime Share',entry.airtimeShare,'%',2,'Share of selected monitored duration')
      +nctPerformanceCell(
        'Performance Index',metric.performanceIndex,'',1,
        'Viewing Share ÷ Airtime Share × 100; above 100 overperforms airtime',
      )
      +nctPerformanceCell(
        'Coverage',metric.coverage,'%',1,
        'Percent of monitored story duration covered by '+basisLabel+' audience data',
      )
      +'</div>';
  }).join(''):'<div class="audience-empty">No matching stories.</div>';
  table.classList.toggle('expandable',ranked.length>NCT_RANK_LIMIT);
  table.classList.toggle('expanded',nctStoryAudienceExpanded);
  if(!nctStoryAudienceExpanded)table.scrollTop=0;
  const button=$('nctStoryExpand');
  button.hidden=ranked.length<=NCT_RANK_LIMIT;
  button.textContent=nctStoryAudienceExpanded
    ?'Show Top 15':'Expand All ('+fmt(ranked.length)+')';
  button.setAttribute('aria-expanded',String(nctStoryAudienceExpanded));
  $('nctStoryAudienceNote').textContent=ranked.length
    ?'Audience basis: '+basisLabel+'. Viewer Hours and AMA use every overlapping '
      +'minute, weighted for partial minutes. Performance Index = Viewing Share ÷ '
      +'Airtime Share × 100; above 100 overperforms its airtime. Combined sources '
      +'are summed and are not cross-source deduplicated. Treat Performance Index '
      +'as directional when monitored time is below 5 minutes.'
    :'No story audience observations match the current filters.';
}
function nctSegmentLine(row){
  return '<div class="nct-segment-row"><span>'
    +formatIstSeconds(row.clip_start_ist)+'</span>'
    +'<span>'+esc(nctText(row,'channel_name'))+'</span>'
    +'<span><strong>'+esc(nctText(row,'program_name'))+'</strong><small>'
    +esc(nctText(row,'anchor'))+'</small></span>'
    +'<span><strong>'+esc(nctText(row,'story'))+'</strong><small>'
    +esc(nctText(row,'sub_story'))+'</small></span>'
    +'<span>'+esc(nctText(row,'primary_genre'))+'<small>'
    +esc(nctText(row,'geography'))+'</small></span>'
    +'<span>'+fmt(row.duration_seconds||0)+' sec</span></div>';
}
function renderNctSegmentList(preserveScroll=true){
  const list=$('nctSegmentRows'),table=$('nctSegmentTable');
  const scrollTop=preserveScroll?table.scrollTop:0;
  const visible=nctSegmentRowsCache.slice(0,nctSegmentRenderCount);
  list.innerHTML=visible.length
    ?visible.map(nctSegmentLine).join('')
    :'<div class="audience-empty">No NCT segments match the selected filters.</div>';
  table.classList.toggle(
    'expandable',nctSegmentRowsCache.length>NCT_SEGMENT_LIMIT
  );
  table.classList.toggle('expanded',nctSegmentsExpanded);
  if(preserveScroll)table.scrollTop=scrollTop;
  else table.scrollTop=0;
  const button=$('nctSegmentExpand');
  button.hidden=nctSegmentRowsCache.length<=NCT_SEGMENT_LIMIT;
  button.textContent=nctSegmentsExpanded
    ?'Show Top 15':'Expand All ('+fmt(nctSegmentRowsCache.length)+')';
  button.setAttribute('aria-expanded',String(nctSegmentsExpanded));
  $('nctSegmentNote').textContent=nctSegmentsExpanded
    ?'Showing latest '+fmt(visible.length)+' of '+fmt(nctSegmentRowsCache.length)
      +' matching clips. Scroll to load more; CSV exports the complete filtered result.'
    :'Showing latest '+fmt(visible.length)+' of '+fmt(nctSegmentRowsCache.length)
      +' matching clips. Expand All keeps the complete list inside this scroll area.';
}
function renderNctSegments(rows){
  nctSegmentRowsCache=rows.slice().sort(
    (a,b)=>String(b.clip_start_ist).localeCompare(String(a.clip_start_ist))
  );
  nctSegmentRenderCount=nctSegmentsExpanded
    ?Math.min(NCT_SEGMENT_BATCH,nctSegmentRowsCache.length)
    :Math.min(NCT_SEGMENT_LIMIT,nctSegmentRowsCache.length);
  renderNctSegmentList(false);
}
function toggleNctSegments(){
  nctSegmentsExpanded=!nctSegmentsExpanded;
  nctSegmentRenderCount=nctSegmentsExpanded
    ?Math.min(NCT_SEGMENT_BATCH,nctSegmentRowsCache.length)
    :Math.min(NCT_SEGMENT_LIMIT,nctSegmentRowsCache.length);
  renderNctSegmentList(false);
}
function nctRankEntries(rows,key){
  const totals=new Map();
  for(const row of rows){
    const label=nctText(row,key);
    totals.set(label,(totals.get(label)||0)+Number(row.duration_seconds||0));
  }
  return [...totals.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
}
function renderNctRank(kind,rows){
  const config=NCT_RANK_CONFIG[kind],ranked=nctRankEntries(rows,config.key);
  const expanded=nctRankExpanded[kind],visible=expanded?ranked:ranked.slice(0,NCT_RANK_LIMIT);
  const max=Math.max(1,...ranked.map(item=>item[1]));
  const list=$(config.target),button=$(config.button);
  list.innerHTML=visible.length?visible.map(([label,value],index)=>
    '<div class="nct-rank-row"><span>#'+(index+1)+' '+esc(label)+'</span>'
    +'<strong>'+esc(nctHours(value))+'</strong><span class="nct-mini-bar"><i style="width:'
    +((value/max)*100).toFixed(2)+'%"></i></span></div>'
  ).join(''):'<div class="audience-empty">No matching values.</div>';
  list.classList.toggle('expandable',ranked.length>NCT_RANK_LIMIT);
  list.classList.toggle('expanded',expanded);
  if(!expanded)list.scrollTop=0;
  button.hidden=ranked.length<=NCT_RANK_LIMIT;
  button.textContent=expanded?'Show Top 15':'Expand All ('+fmt(ranked.length)+')';
  button.setAttribute('aria-expanded',String(expanded));
}
function toggleNctRank(kind){
  nctRankExpanded[kind]=!nctRankExpanded[kind];
  renderNctRank(kind,nctFilteredRows());
}
function renderNctChart(rows){
  const canvas=$('nctTrend'),empty=$('nctChartEmpty');
  const daily=new Map(),channelTotals=new Map();
  for(const row of rows){
    const channel=nctText(row,'channel_name'),key=String(row.log_date)+'\u0000'+channel;
    const minutes=Number(row.duration_seconds||0)/60;
    daily.set(key,(daily.get(key)||0)+minutes);
    channelTotals.set(channel,(channelTotals.get(channel)||0)+minutes);
  }
  const dates=[...new Set(rows.map(row=>String(row.log_date)))].sort();
  if(!dates.length){
    canvas.hidden=true;
    empty.hidden=false;
    if(nctChart){nctChart.destroy();nctChart=null}
    return;
  }
  canvas.hidden=false;
  empty.hidden=true;
  const colors=['#0f766e','#2563eb','#dc2626','#ca8a04','#7c3aed','#db2777','#16a34a','#475569','#ea580c'];
  const rankedChannels=[...channelTotals.entries()]
    .filter(([_channel,total])=>total>0)
    .sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
  if(!rankedChannels.length){
    canvas.hidden=true;
    empty.hidden=false;
    empty.textContent='No positive monitored minutes for this selection.';
    if(nctChart){nctChart.destroy();nctChart=null}
    return;
  }
  const datasets=rankedChannels.map(([channel],index)=>({
    label:channel,
    data:dates.map(date=>Number((daily.get(date+'\u0000'+channel)||0).toFixed(1))),
    borderColor:colors[index%colors.length],
    backgroundColor:'transparent',
    borderWidth:1.8,
    pointRadius:0,
    pointHoverRadius:5,
    tension:.18,
    fill:false,
  }));
  $('nctChartNote').textContent=fmt(rankedChannels.length)
    +' selected channels · zero-only series hidden';
  const values=datasets.flatMap(dataset=>dataset.data).filter(Number.isFinite);
  const minValue=Math.min(...values),maxValue=Math.max(...values);
  const spread=Math.max(1,maxValue-minValue),axisPadding=Math.max(5,spread*.08);
  const axisMin=Math.max(0,minValue-axisPadding),axisMax=maxValue+axisPadding;
  const data={labels:dates.map(shortDate),datasets};
  if(nctChart){
    nctChart.data=data;
    nctChart.options.scales.y.suggestedMin=axisMin;
    nctChart.options.scales.y.suggestedMax=axisMax;
    nctChart.options.plugins.legend.display=datasets.length>1;
    nctChart.update('none');
  }else{
    nctChart=new Chart(canvas,{
      type:'line',
      data,
      options:{
        responsive:true,
        maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{display:datasets.length>1,position:'bottom',labels:{usePointStyle:true,pointStyle:'line',boxWidth:14,font:{size:10}}},
          tooltip:{itemSort:(a,b)=>Number(b.raw||0)-Number(a.raw||0),callbacks:{label:item=>item.dataset.label+': '+fmt(Number(item.raw||0))+' min'}},
        },
        scales:{
          x:{ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:20,font:{size:9}},grid:{display:false}},
          y:{
            beginAtZero:false,
            suggestedMin:axisMin,
            suggestedMax:axisMax,
            title:{display:true,text:'Monitored content minutes'},
            ticks:{font:{size:9},maxTicksLimit:12,callback:value=>fmt(value)+' min'},
          },
        },
      },
    });
  }
}
function renderNct(refresh=true){
  ensureNctPanel();
  updateNctHelp();
  if(!nctPayload){
    if(NCT.available)$('nctLoading').hidden=false;
    return;
  }
  if(refresh)refreshNctFilters();
  const rows=nctFilteredRows(),seconds=rows.reduce(
    (sum,row)=>sum+Number(row.duration_seconds||0),0
  );
  $('nctKpis').innerHTML=[
    [nctHours(seconds),'Monitored content'],
    [fmt(rows.length),'Story clips'],
    [fmt(new Set(rows.map(row=>nctText(row,'story'))).size),'Distinct stories'],
    [fmt(new Set(rows.map(row=>nctText(row,'program_name'))).size),'Distinct programs'],
  ].map(item=>'<div class="nct-kpi"><strong>'+item[0]+'</strong><small>'+item[1]+'</small></div>').join('');
  renderNctChart(rows);
  renderNctStoryAudience(rows);
  for(const kind of Object.keys(NCT_RANK_CONFIG))renderNctRank(kind,rows);
  renderNctSegments(rows);
  renderNctContext();
  updateResetState();
}
function toggleNctChart(){
  const card=$('nctChartCard'),expanded=!card.classList.contains('expanded');
  card.classList.toggle('expanded',expanded);
  document.body.classList.toggle('nct-chart-expanded',expanded);
  $('expandNctChart').textContent=expanded?'Close chart':'Expand chart';
  $('expandNctChart').setAttribute('aria-expanded',String(expanded));
  requestAnimationFrame(()=>nctChart?.resize());
}
function exportNctCsv(){
  const range=nctEffectiveRange(),rows=nctFilteredRows();
  const header=['NCT Date From','NCT Date To','Clip Start IST','Clip End IST','Channel','Program','Story','Sub-story','Primary Genre','Secondary Genre','Geography','Duration Seconds','Anchor','Reporter','Personality','Guest','Logistics','Telecast Format','Assist Used','Split','Story Format','Source File','Source Row'];
  const values=rows.map(row=>[
    range.start,range.end,formatIstSeconds(row.clip_start_ist),formatIstSeconds(row.clip_end_ist),
    nctText(row,'channel_name'),nctText(row,'program_name'),nctText(row,'story'),
    nctText(row,'sub_story'),nctText(row,'primary_genre'),nctText(row,'secondary_genre'),
    nctText(row,'geography'),row.duration_seconds,nctText(row,'anchor'),
    nctText(row,'reporter'),nctText(row,'personality'),nctText(row,'guest'),
    nctText(row,'logistics'),nctText(row,'telecast_format'),nctText(row,'assist_used'),
    nctText(row,'split'),nctText(row,'story_format'),nctText(row,'source_file'),row.source_row,
  ]);
  downloadCsv('nct_story_segments_'+range.start+'_to_'+range.end+'.csv',header,values);
}
function exportNctStoryAudienceCsv(){
  const range=nctEffectiveRange(),basis=nctStoryAudienceBasis();
  const rankMetric=nctStoryRankMetric();
  const rows=nctSortedStoryAudienceRows(nctStoryAudienceRows(nctFilteredRows()));
  const selections=[
    'fastPlatform','fastChannel','streamChannel','amagiPlatform','amagiChannel',
    'youtubeChannel','nctYoutubeVideo',
  ].map(id=>
    [...selectedMulti(id)].sort().join(' | ')
  );
  const header=[
    'NCT Date From','NCT Date To','Audience Basis','Rank Metric','Rank','Story',
    'Selected FAST Platforms','Selected FAST Channels','Selected STREAM Channels',
    'Selected AMAGI Platforms','Selected AMAGI Channels',
    'Selected YouTube Channels','Selected YouTube Video IDs',
    'Monitored Duration Seconds','Monitored Hours','Story Clip Count',
    'Selected Viewer Minutes','Selected Viewer Hours','Selected Average Minute Audience',
    'Selected Viewing Share Percent','Airtime Share Percent',
    'Selected Performance Index','Selected Audience Coverage Percent',
    'FAST Viewer Hours','FAST AMA','FAST Coverage Percent',
    'STREAM Viewer Hours','STREAM AMA','STREAM Coverage Percent',
    'AMAGI Viewer Hours','AMAGI AMA','AMAGI Coverage Percent',
    'YouTube Viewer Hours','YouTube AMA',
    'YouTube Coverage Percent','Combined Viewer Hours','Combined AMA',
    'Combined Coverage Percent',
  ];
  const values=rows.map((row,index)=>{
    const selected=row.metrics[basis];
    const sourceValues=source=>{
      const metric=row.metrics[source];
      const zeroMissing=source==='youtube';
      return [
        Number(metric.viewerHours.toFixed(4)),
        metric.ama===null?(zeroMissing?0:''):Number(metric.ama.toFixed(4)),
        Number(metric.coverage.toFixed(4)),
      ];
    };
    const zeroSelected=basis==='youtube';
    return [
      range.start,range.end,nctStoryBasisLabel(basis),rankMetric,index+1,row.story,
      ...selections,
      Number(row.seconds.toFixed(3)),Number((row.seconds/3600).toFixed(4)),row.clips,
      Number(selected.viewerMinutes.toFixed(4)),
      Number(selected.viewerHours.toFixed(4)),
      selected.ama===null?(zeroSelected?0:''):Number(selected.ama.toFixed(4)),
      selected.viewingShare===null?(zeroSelected?0:''):Number(selected.viewingShare.toFixed(4)),
      Number(row.airtimeShare.toFixed(4)),
      selected.performanceIndex===null?(zeroSelected?0:''):Number(selected.performanceIndex.toFixed(4)),
      Number(selected.coverage.toFixed(4)),
      ...sourceValues('fast'),...sourceValues('stream'),...sourceValues('amagi'),
      ...sourceValues('youtube'),...sourceValues('combined'),
    ];
  });
  downloadCsv(
    'nct_story_performance_'+basis+'_'+range.start+'_to_'+range.end+'.csv',
    header,
    values,
  );
}
function nctIndex(channel){
  if(nctChannelIndexes.has(channel))return nctChannelIndexes.get(channel);
  const rows=(nctPayload?.segments||[]).filter(
    row=>nctText(row,'channel_name')===channel
  ).sort((a,b)=>String(a.clip_start_ist).localeCompare(String(b.clip_start_ist)));
  const index=rows.map(row=>({
    row,
    start:naiveMillis(String(row.clip_start_ist).replace(' ','T')),
    end:naiveMillis(String(row.clip_end_ist).replace(' ','T')),
  }));
  nctChannelIndexes.set(channel,index);
  return index;
}
function nctNeighbors(event,channel){
  const index=nctIndex(channel),time=naiveMillis(event.on_air_start_ist);
  let low=0,high=index.length;
  while(low<high){
    const middle=(low+high)>>1;
    if(index[middle].start<=time)low=middle+1;
    else high=middle;
  }
  let active=null;
  for(let position=low-1;position>=0;position--){
    if(index[position].end<time)break;
    if(index[position].start<=time&&index[position].end>=time){
      active=index[position];
      break;
    }
  }
  let previous=null;
  for(let position=low-1;position>=0;position--){
    if(index[position].end<=time){previous=index[position];break}
  }
  const following=low<index.length?index[low]:null;
  return {time,active,previous,following};
}
function nctContextForEvent(event,channel){
  const bounds=nctBounds(),eventDate=String(event.on_air_start_ist).slice(0,10);
  if(eventDate<bounds.start||eventDate>bounds.end)return null;
  const match=nctNeighbors(event,channel);
  if(event.ad_type==='L-band'){
    let selected=match.active,matchType='Active story';
    if(!selected){
      const previousDistance=match.previous?Math.abs(match.time-match.previous.end):Infinity;
      const followingDistance=match.following?Math.abs(match.following.start-match.time):Infinity;
      selected=previousDistance<=followingDistance?match.previous:match.following;
      matchType=selected===match.previous?'Nearest previous':'Nearest following';
    }
    return {
      event,channel,matchType,
      active:selected?.row||null,
      previous:match.previous?.row||null,
      following:match.following?.row||null,
      distanceSeconds:selected?Math.round(
        match.active?0:Math.min(
          Math.abs(match.time-selected.start),
          Math.abs(match.time-selected.end)
        )/1000
      ):null,
    };
  }
  const previousDistance=match.previous?Math.abs(match.time-match.previous.end):Infinity;
  const followingDistance=match.following?Math.abs(match.following.start-match.time):Infinity;
  return {
    event,channel,
    matchType:match.active?'Active story':'Before / after stories',
    active:match.active?.row||null,
    previous:match.previous?.row||null,
    following:match.following?.row||null,
    distanceSeconds:match.active?0:Math.round(Math.min(
      previousDistance,
      followingDistance
    )/1000),
  };
}
function nctContextStory(context){
  if(context.active)return nctText(context.active,'story');
  const before=context.previous?nctText(context.previous,'story'):'None';
  const after=context.following?nctText(context.following,'story'):'None';
  return 'Before: '+before+' | After: '+after;
}
function nctContextProgram(context){
  if(context.active)return nctText(context.active,'program_name');
  const before=context.previous?nctText(context.previous,'program_name'):'None';
  const after=context.following?nctText(context.following,'program_name'):'None';
  return 'Before: '+before+' | After: '+after;
}
function nctContextRows(){
  if(!nctPayload?.available)return [];
  const channel=$('nctContextChannel').value;
  return filtered().map(event=>nctContextForEvent(event,channel)).filter(context=>
    context&&(context.active||context.previous||context.following)
  );
}
function nctContextLine(context){
  const event=context.event,detail=context.active||context.previous||context.following;
  return '<div class="nct-context-row"><span>'
    +formatIstSeconds(event.on_air_start_ist)+'</span>'
    +'<span><strong>'+esc(event.event_id)+'</strong><small>'
    +esc(event.ad_type)+'</small></span>'
    +'<span>'+esc(context.matchType)+'</span>'
    +'<span>'+esc(nctContextProgram(context))+'</span>'
    +'<span><strong>'+esc(nctContextStory(context))+'</strong><small>'
    +esc(
      detail
        ?nctText(detail,'primary_genre')+' | '+nctText(detail,'geography')
        :'No NCT context'
    )+'</small></span>'
    +'<span>'+(Number.isFinite(context.distanceSeconds)
      ?fmt(context.distanceSeconds)+' sec':'NA')+'</span></div>';
}
function renderNctContext(){
  if(!nctPayload?.available||!$('nctContextRows'))return;
  nctContextRowsCache=nctContextRows().slice().sort(
    (a,b)=>String(b.event.on_air_start_ist).localeCompare(String(a.event.on_air_start_ist))
  );
  const visible=nctContextExpanded
    ?nctContextRowsCache
    :nctContextRowsCache.slice(0,NCT_CONTEXT_LIMIT);
  $('nctContextRows').innerHTML=visible.length
    ?visible.map(nctContextLine).join('')
    :'<div class="audience-empty">No delivered events have NCT context in the selected scope.</div>';
  const table=$('nctContextTable'),button=$('nctContextExpand');
  table.classList.toggle(
    'expandable',nctContextRowsCache.length>NCT_CONTEXT_LIMIT
  );
  table.classList.toggle('expanded',nctContextExpanded);
  if(!nctContextExpanded)table.scrollTop=0;
  button.hidden=nctContextRowsCache.length<=NCT_CONTEXT_LIMIT;
  button.textContent=nctContextExpanded
    ?'Show Top 15':'Expand All ('+fmt(nctContextRowsCache.length)+')';
  button.setAttribute('aria-expanded',String(nctContextExpanded));
  $('nctContextNote').textContent='Showing latest '+fmt(visible.length)+' of '
    +fmt(nctContextRowsCache.length)+' context matches for '
    +$('nctContextChannel').value+'. CSV exports the complete filtered result.';
}
function toggleNctContext(){
  nctContextExpanded=!nctContextExpanded;
  renderNctContext();
}
function exportNctContextCsv(){
  const rows=nctContextRows(),channel=$('nctContextChannel').value;
  const fields=(row,prefix)=>[
    row?nctText(row,'program_name'):'',
    row?nctText(row,'story'):'',
    row?nctText(row,'sub_story'):'',
    row?nctText(row,'primary_genre'):'',
    row?nctText(row,'geography'):'',
    row?nctText(row,'anchor'):'',
  ];
  const header=['NCT Context Channel','On-air IST','Ad Type','Ad ID','Creative Title','Match Type','Distance Seconds','Active Program','Active Story','Active Sub-story','Active Genre','Active Geography','Active Anchor','Previous Program','Previous Story','Previous Sub-story','Previous Genre','Previous Geography','Previous Anchor','Following Program','Following Story','Following Sub-story','Following Genre','Following Geography','Following Anchor'];
  const values=rows.map(context=>[
    channel,formatIstSeconds(context.event.on_air_start_ist),context.event.ad_type,
    context.event.event_id,context.event.creative_title,context.matchType,
    Number.isFinite(context.distanceSeconds)?context.distanceSeconds:'',
    ...fields(context.active,'active'),
    ...fields(context.previous,'previous'),
    ...fields(context.following,'following'),
  ]);
  const range=nctEffectiveRange();
  downloadCsv('asrun_nct_story_context_'+channel.replace(/[^A-Za-z0-9]+/g,'_')+'_'+range.start+'_to_'+range.end+'.csv',header,values);
}
const baseScopeValidationWithNct=renderScopeValidation;
renderScopeValidation=function(){
  baseScopeValidationWithNct();
  const tbody=$('dataScopeRows');
  if(!tbody)return;
  const trueBounds=NCT.true_start&&NCT.true_end?{start:NCT.true_start,end:NCT.true_end}:null;
  const range=nctEffectiveRange();
  const usedBounds=range.valid?{start:range.start+'T00:00:00',end:range.end+'T23:59:59'}:null;
  const usedRows=nctPayload?.available?nctFilteredRows().length:'Load on demand';
  const continuity=scopeContinuityHtml((DATA.date_coverage||{}).nct,trueBounds,range.start,range.end);
  tbody.insertAdjacentHTML(
    'beforeend',
    '<tr><td><strong>NCT story segments</strong></td><td>'+esc(scopeRangeText(trueBounds))
    +'</td><td>'+esc(scopeRangeText(usedBounds))+'</td><td>'
    +(typeof usedRows==='number'?fmt(usedRows):esc(usedRows))+'</td>'
    +'<td>'+continuity+'</td>'
    +'<td class="scope-muted">NCT date, channel, program, genre, geography, story</td></tr>'
  );
};
const baseResetWithNct=resetDashboardFilters;
resetDashboardFilters=function(){
  baseResetWithNct();
  youtubeVideoSelectAll=true;
  for(const id of ['youtubeChannel','youtubeVideo']){
    const menu=$(id+'Menu');
    if(menu)menu.innerHTML='';
    multiInitialized.delete(id);
  }
  initializeYoutubeDates();
  setYoutubeDateMode('follow',false);
  if($('youtubeChartInterval'))$('youtubeChartInterval').value='5';
  if($('youtubeCustomInterval'))$('youtubeCustomInterval').value='120';
  if($('youtubeCustomIntervalLabel'))$('youtubeCustomIntervalLabel').hidden=true;
  if($('youtubeExportInterval'))$('youtubeExportInterval').value='5';
  updateYoutubeRangeButtons('');
  if($('nctPanel')){
    nctStoryAudienceExpanded=false;
    nctSegmentsExpanded=false;
    nctContextExpanded=false;
    $('nctStoryAudienceBasis').value='combined';
    $('nctStoryRankBy').value='viewerHours';
    for(const kind of Object.keys(nctRankExpanded))nctRankExpanded[kind]=false;
    const bounds=nctBounds();
    nctAppliedRange=null;
    $('nctFrom').value=bounds.start;
    $('nctTo').value=bounds.end;
    setNctDateMode('follow',false);
    nctSelectedStory='';
    $('nctStoryLookup').value='';
    updateNctStorySummary();
    for(const id of [
      'nctChannel','nctProgram','nctGenre','nctGeo',...NCT_STORY_SOURCE_FILTER_IDS,
    ]){
      const menu=$(id+'Menu');
      if(menu)menu.innerHTML='';
      multiInitialized.delete(id);
    }
    resetNctAudienceCaches();
    const defaultContext=(NCT.channels||[]).includes('INDIA TV')
      ?'INDIA TV'
      :String((NCT.channels||[])[0]||'');
    if(defaultContext&&$('nctContextChannel').querySelector(
      'option[value="'+CSS.escape(defaultContext)+'"]'
    )){
      $('nctContextChannel').value=defaultContext;
    }
    nctFilterCache={key:null,value:null};
    if(nctPayload){refreshNctFilters();updateNctStorySourceControls();renderNct(false)}
  }
  renderYoutube();
  updateResetState();
};
function initializeNctLazyLoad(){
  ensureNctPanel();
  if(!NCT.available){
    updateNctHelp();
    $('nctLoading').textContent=NCT.reason||'NCT story data is unavailable.';
    return;
  }
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting)){
        observer.disconnect();
        loadNctData().catch(()=>{});
      }
    },{rootMargin:'500px 0px'});
    observer.observe($('nctPanel'));
  }else{
    loadNctData().catch(()=>{});
  }
}
function resetSourceMenus(ids){
  for(const id of ids){
    const menu=$(id+'Menu');
    if(menu)menu.innerHTML='';
    multiInitialized.delete(id);
  }
}
function reportDashboardSourceFailure(name,error){
  dashboardSourceState.set(name,'failed');
  console.error('ASRUN dashboard '+name+' sidecar failed:',error);
  if(name==='fct')renderFctAndScope(false);
  else if(name==='youtube')renderYoutube();
  else render();
  hideLoading();
}
async function loadAudienceDashboardData(){
  const alreadyLoaded=dashboardSourceLoaded('viewer')&&dashboardSourceLoaded('amagi');
  await loadDashboardSources(['viewer','amagi']);
  if(alreadyLoaded)return;
  resetNctAudienceCaches();
  resetSourceMenus([
    'fastPlatform','fastChannel','streamChannel','amagiPlatform','amagiChannel',
  ]);
  refreshAudienceFilters();
  refreshAmagiFilters();
  refreshNctStorySourceFilters();
  render();
}
async function loadFctDashboardData(){
  const alreadyLoaded=dashboardSourceLoaded('fct');
  await loadDashboardSource('fct');
  if(alreadyLoaded)return;
  initializeFctDates();
  resetSourceMenus([
    ...FCT_FILTER_SPECS.map(([id])=>id),
  ]);
  renderFctAndScope(true);
}
async function loadYoutubeDashboardData(){
  const alreadyLoaded=dashboardSourceLoaded('youtube');
  await loadDashboardSource('youtube');
  if(alreadyLoaded)return;
  resetNctAudienceCaches();
  resetSourceMenus([
    'youtubeChannel','nctYoutubeVideo',
  ]);
  $('youtubeVideoMenu').innerHTML='';
  youtubeVideoMultiInitialized=false;
  youtubeVideoSelectAll=true;
  youtubeDeliveryMinuteIndex=null;
  refreshNctStorySourceFilters();
  refreshYoutubeDateLimits();
  initializeYoutubeDates();
  render();
  renderYoutube();
}
let activeDashboardPage='audience';
const DASHBOARD_PAGE_IDS={
  audience:'dashboardPageAudience',
  delivery:'dashboardPageDelivery',
  content:'dashboardPageContent',
};
function ensureDashboardPages(){
  if($('dashboardPageNav'))return;
  ensureFctAudiencePanel();
  const main=document.querySelector('main.wrap');
  if(!main)throw new Error('ASRUN dashboard main container is missing.');
  main.insertAdjacentHTML(
    'afterbegin',
    '<nav class="dashboard-page-nav" id="dashboardPageNav" '
    +'aria-label="Dashboard pages">'
    +'<button type="button" data-dashboard-page-target="audience" '
    +'aria-controls="dashboardPageAudience">Audience Sources</button>'
    +'<button type="button" data-dashboard-page-target="delivery" '
    +'aria-controls="dashboardPageDelivery">Ad Delivery</button>'
    +'<button type="button" data-dashboard-page-target="content" '
    +'aria-controls="dashboardPageContent">Content Intelligence</button>'
    +'</nav>'
    +'<section class="dashboard-page" id="dashboardPageAudience" '
    +'data-dashboard-page="audience"></section>'
    +'<section class="dashboard-page" id="dashboardPageDelivery" '
    +'data-dashboard-page="delivery" hidden></section>'
    +'<section class="dashboard-page" id="dashboardPageContent" '
    +'data-dashboard-page="content" hidden></section>',
  );
  const filters=document.querySelector('.filters');
  if(!filters)throw new Error('Dashboard filter toolbar is missing.');
  filters.insertBefore($('dashboardPageNav'),filters.firstChild);
  const nodes={
    kpis:$('kpis'),
    rankings:document.querySelector('.rank-grid'),
    audience:document.querySelector('.audience-grid'),
    combined:document.querySelector('.combined-panel'),
    fct:document.querySelector('.fct-panel'),
    fctAudience:document.querySelector('.fct-audience-panel'),
    nct:$('nctPanel'),
    youtube:$('youtubePanel'),
    scope:$('dataScopePanel'),
  };
  const missing=Object.entries(nodes)
    .filter(([_name,node])=>!node)
    .map(([name])=>name);
  if(missing.length){
    throw new Error('Dashboard page sections are missing: '+missing.join(', '));
  }
  // Source controls already live in the global header. Remove the three
  // duplicate source event panels and keep only their consolidated result.
  nodes.audience.remove();
  $('dashboardPageAudience').append(nodes.combined,nodes.youtube);
  $('dashboardPageDelivery').append(
    nodes.kpis,
    nodes.rankings,
    nodes.fct,
    nodes.fctAudience,
  );
  $('dashboardPageContent').append(nodes.nct,nodes.scope);
  for(const button of document.querySelectorAll('[data-dashboard-page-target]')){
    button.addEventListener('click',()=>setDashboardPage(
      button.dataset.dashboardPageTarget,
    ));
  }
  setDashboardPage('audience',false,false);
}
function dashboardPageNeedsLoading(page){
  if(page==='audience'){
    return !dashboardSourceLoaded('viewer')||!dashboardSourceLoaded('amagi')
      ||!dashboardSourceLoaded('youtube');
  }
  if(page==='delivery'){
    return !dashboardSourceLoaded('viewer')||!dashboardSourceLoaded('amagi')
      ||!dashboardSourceLoaded('fct')||!dashboardSourceLoaded('youtube');
  }
  return !nctPayload||!dashboardSourceLoaded('viewer')
    ||!dashboardSourceLoaded('amagi')||!dashboardSourceLoaded('youtube');
}
async function activateDashboardPageData(page){
  if(page==='audience'){
    await Promise.all([loadAudienceDashboardData(),loadYoutubeDashboardData()]);
    renderYoutube();
    if(youtubeTrendChart)requestAnimationFrame(()=>youtubeTrendChart.resize());
    return;
  }
  if(page==='delivery'){
    await Promise.all([
      loadAudienceDashboardData(),
      loadFctDashboardData(),
      loadYoutubeDashboardData(),
    ]);
    renderFctAndScope(false);
    return;
  }
  await Promise.all([
    loadAudienceDashboardData(),
    loadYoutubeDashboardData(),
    loadNctData(),
  ]);
  if(nctPayload)renderNct(false);
  if(nctChart)requestAnimationFrame(()=>nctChart.resize());
}
function setDashboardPage(page,loadData=true,scroll=true){
  const target=Object.hasOwn(DASHBOARD_PAGE_IDS,page)?page:'audience';
  activeDashboardPage=target;
  syncDateControlVisibility();
  closeMultiMenus('');
  for(const [name,id] of Object.entries(DASHBOARD_PAGE_IDS)){
    const section=$(id);
    const active=name===target;
    section.hidden=!active;
    section.setAttribute('aria-hidden',active?'false':'true');
  }
  for(const button of document.querySelectorAll('[data-dashboard-page-target]')){
    const active=button.dataset.dashboardPageTarget===target;
    button.classList.toggle('active',active);
    button.setAttribute('aria-selected',active?'true':'false');
  }
  if(scroll)$('dashboardPageNav').scrollIntoView({block:'start',behavior:'smooth'});
  if(!loadData)return;
  if(dashboardPageNeedsLoading(target)){
    showLoading('Loading '+(
      target==='audience'
        ?'audience source'
        :target==='delivery'?'ad delivery':'content intelligence'
    )+' data...');
  }
  activateDashboardPageData(target)
    .catch(error=>{
      console.error('Dashboard page activation failed:',error);
      showFatalDashboardError('dashboard page activation',error);
    })
    .finally(hideLoading);
}
function observeDashboardSource(name,target,loader){
  if(dashboardSourceLoaded(name)||!target)return;
  const start=()=>{
    loader().catch(error=>reportDashboardSourceFailure(name,error));
  };
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting)){
        observer.disconnect();
        start();
      }
    },{rootMargin:'600px 0px'});
    observer.observe(target);
  }else{
    start();
  }
}
function initializeDashboardSourceLoading(){
  if(FCT.available){
    observeDashboardSource('fct',document.querySelector('.fct-panel'),loadFctDashboardData);
  }
  if((DATA.youtube||{}).available){
    observeDashboardSource('youtube',$('youtubePanel'),loadYoutubeDashboardData);
  }
}
function runWithDashboardSources(loaders,action){
  showLoading('Loading data required for export...');
  return Promise.all(loaders.map(loader=>loader()))
    .then(()=>action())
    .catch(error=>{
      console.error('Dashboard export data load failed:',error);
      showFatalDashboardError('export data load',error);
    })
    .finally(hideLoading);
}
const asrunBaseRender=render;
render=function(){
  if(youtubeDateMode==='follow')applyYoutubeMainDate(false);
  asrunBaseRender();
  renderFct();
  if(nctPayload){
    if(nctDateMode==='follow'){
      nctFilterCache={key:null,value:null};
      if(nctMissingPartitions(nctEffectiveRange()).length){
        loadNctData().catch(error=>{
          console.error('NCT follow-range load failed:',error);
          showFatalDashboardError('NCT follow-range load',error);
        });
      }else{
        refreshNctFilters();
        renderNct(false);
      }
    }else{
      renderNct(false);
    }
  }
  if(youtubeDateMode==='follow')renderYoutube();
  else renderScopeValidation();
  updateResetState();
  hideLoading();
};
renderYoutube=renderYoutubeChannelAware;
const asrunBaseRenderYoutube=renderYoutube;
renderYoutube=function(){asrunBaseRenderYoutube();renderScopeValidation();updateResetState();hideLoading();};
ensurePeriodControls();ensureCreativeFilters();ensureYoutubeDateModeControls();ensureYoutubeChannelFilter();ensureYoutubeChartIntervalControls();ensureYoutubeChartExpand();refreshYoutubeDateLimits();initializeYoutubeDates();setYoutubeDateMode('follow',false);refreshDependentOptions();ensureAmagiPanel();ensureFctPanel();ensureNctPanel();ensureScopePanel();ensureGlobalAudienceFilters();ensureDashboardPages();initializeNctLazyLoad();initializeDashboardSourceLoading();$('reset').onclick=resetDashboardFilters;
replaceDownloadAction('exportAllEvents',()=>runWithDashboardSources(
  [loadAudienceDashboardData,loadYoutubeDashboardData],exportAllEventsCsv
));
replaceDownloadAction('exportAudienceBreakdown',()=>runWithDashboardSources(
  [loadAudienceDashboardData,loadYoutubeDashboardData],exportAudienceBreakdownCsv
));
replaceDownloadAction('exportYoutubeCsv',()=>runWithDashboardSources(
  [loadYoutubeDashboardData],exportYoutubeCsvChannelAware
));
replaceDownloadAction('exportYoutubeReferenceCsv',()=>runWithDashboardSources(
  [loadYoutubeDashboardData],exportYoutubeReferenceCsvChannelAware
));
replaceDownloadAction('exportFctCsv',()=>runWithDashboardSources(
  [loadFctDashboardData],exportFctCsv
));
replaceDownloadAction('exportFctAudienceCsv',()=>runWithDashboardSources(
  [loadAudienceDashboardData,loadFctDashboardData,loadYoutubeDashboardData],
  exportFctAudienceCsv
));
async function bootstrapDashboard(){
  try{
    render();
    renderYoutube();
    showLoading('Loading FAST, STREAM, and AMAGI audience data...');
    await loadAudienceDashboardData();
    await activateDashboardPageData(activeDashboardPage);
    captureDefaultFilterSignature();
    renderYoutube();
  }catch(startupError){
    showFatalDashboardError('initial render',startupError);
    throw startupError;
  }
}
bootstrapDashboard();
</script>'''
    return (
        template.replace("__TITLE__", title)
        .replace("__CHARTJS__", chartjs)
        # The extension reuses elements created by the base script, so it must
        # run after the base document and its initial render have completed.
        .replace("</body>", amagi_extension + "</body>")
    )


def main() -> None:
    """Build source marts, write lazy payload sidecars, and publish the dashboard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", help="One or more ASRUN .txt files. Defaults to data/raw/*.txt.")
    parser.add_argument("--channel", required=True, help="Canonical Veto channel for these ASRUN files.")
    parser.add_argument(
        "--identity-minute",
        type=Path,
        default=DEFAULT_IDENTITY_MINUTE,
        help="Audience Operations identity_minute.parquet used for FAST/STREAM Unique IP Minute Sum.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-stage cache decisions and elapsed times.",
    )
    args = parser.parse_args()
    configure_logging(args.verbose)
    pipeline_started = perf_counter()
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
    events = timed_step(
        "ASRUN parsing and brand mapping",
        lambda: apply_brand_map(
            pd.concat(
                [parse_asrun(path, args.channel) for path in input_paths],
                ignore_index=True,
            )
        ),
    )
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed_path = PARSED_DIR / "asrun_events.parquet"
    atomic_write_parquet(parsed_path, events)
    # FCT can extend beyond the ASRUN text-file dates. Build its range first so
    # valid historical FAST/STREAM audience minutes are not clipped away.
    fct = timed_step("FCT occurrence mart", build_fct_ad_mart)
    fct_ranges = (
        [(str(fct["true_start"])[:10], str(fct["true_end"])[:10])]
        if fct["available"]
        else []
    )
    viewer_minute = timed_step(
        "Audience Operations viewer-minute snapshot",
        load_viewer_minute_snapshot,
        events,
        args.identity_minute,
        fct_ranges,
    )
    youtube = timed_step("YouTube concurrency marts", build_youtube_marts)
    amagi = timed_step("Amagi concurrency mart", build_amagi_minute_mart, events)
    nct = timed_step("NCT story mart", build_nct_story_mart)
    viewer_snapshot_path = PARSED_DIR / "audience_ops_identity_minute_asrun_dates.parquet"
    atomic_write_parquet(viewer_snapshot_path, viewer_minute)
    payload = timed_step(
        "Dashboard payload preparation",
        build_payload,
        events,
        viewer_minute,
        youtube,
        amagi,
        fct,
        nct,
    )
    core_payload, source_chunks = split_dashboard_payload(payload)
    (OUTPUT_DIR / "asrun_ad_events.csv").write_text(
        events.loc[events["is_ad"]].to_csv(index=False), encoding="utf-8-sig"
    )
    payload_path = OUTPUT_DIR / CORE_PAYLOAD_FILENAME
    write_payload_script(payload_path, core_payload)
    sidecar_paths = write_dashboard_sidecars(source_chunks)
    nct_payload_path = OUTPUT_DIR / "nct_story_data.js"
    write_nct_payload_script(nct_payload_path, nct)
    html_path = OUTPUT_DIR / "asrun_delivery_demo.html"
    html_path.write_text(render_dashboard(core_payload), encoding="utf-8")
    print(f"Parsed events : {len(events):,}")
    print(f"Ad events     : {payload['kpis']['ad_plays']:,}")
    print(f"Viewer rows   : {len(viewer_minute):,} (Audience Operations identity-minute snapshot)")
    print(f"YouTube files : {youtube['completed_files']:,} completed, {youtube['partial_files']:,} partial")
    print(f"Amagi rows    : {len(amagi['minute']):,} actual viewer minutes from {amagi['files']:,} file(s)")
    print(
        f"FCT events    : {len(fct['events']):,} monitored occurrences "
        f"from {fct['files']:,} workbook(s)"
    )
    print(
        f"NCT segments  : {len(nct['segments']):,} story segments "
        f"across {len(nct['channels']):,} channel(s)"
    )
    print(f"Parquet       : {parsed_path}")
    print(f"Viewer mart   : {viewer_snapshot_path}")
    print(f"Dashboard data: {payload_path}")
    for source_name, sidecar_path in sidecar_paths.items():
        print(f"{source_name.title():<14}: {sidecar_path}")
    print(f"NCT data      : {nct_payload_path}")
    print(f"Dashboard     : {html_path}")
    print(f"Elapsed       : {perf_counter() - pipeline_started:.2f} seconds")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
