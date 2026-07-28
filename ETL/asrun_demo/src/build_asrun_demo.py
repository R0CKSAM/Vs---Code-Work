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
FCT_ROOT = Path(
    os.getenv("VG_ASRUN_FCT_ROOT", r"Z:\Veto Logs Backup\DO NOT DELETE\source=FCT")
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
FCT_MART_VERSION = 2

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


def fct_file_fingerprint(path: Path) -> dict[str, int]:
    """Use stable local metadata to identify unchanged source workbooks."""
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def parse_fct_workbook(path: Path, source_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize one FCT workbook without changing its source-reported IST wall clock."""
    declared_start, declared_end = fct_filename_range(path)
    sheets = pd.read_excel(path, sheet_name=None, dtype=object)
    normalized: list[pd.DataFrame] = []
    source_rows = 0
    excluded_rows = 0

    for sheet_name, raw in sheets.items():
        missing = sorted(FCT_REQUIRED_COLUMNS.difference(raw.columns))
        if missing:
            raise ValueError(
                f"{path.name}/{sheet_name} is missing FCT column(s): {', '.join(missing)}"
            )
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
        str(path.relative_to(FCT_ROOT)): fct_file_fingerprint(path) for path in paths
    }
    old_manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # A damaged cache manifest is recoverable because the source workbooks
            # remain authoritative; force a clean rebuild below.
            old_manifest = {}

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

    temp_mart = mart_path.with_name(f".{mart_path.name}.tmp")
    temp_manifest = manifest_path.with_name(f".{manifest_path.name}.tmp")
    try:
        events.to_parquet(temp_mart, index=False)
        temp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(temp_mart, mart_path)
        os.replace(temp_manifest, manifest_path)
    finally:
        temp_mart.unlink(missing_ok=True)
        temp_manifest.unlink(missing_ok=True)

    return fct_result(
        events,
        files=len(paths),
        source_rows=sum(int(meta.get("source_rows", 0)) for meta in file_metadata.values()),
        excluded_rows=sum(int(meta.get("excluded_rows", 0)) for meta in file_metadata.values()),
        skipped=[],
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
    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    for parquet_path in completed_files:
        try:
            frame = pd.read_parquet(parquet_path, columns=YOUTUBE_COLUMNS)
        except (OSError, ValueError, KeyError) as exc:
            skipped.append(f"{parquet_path.name}: {exc}")
            continue
        collector_key, youtube_channel = youtube_channel_from_path(parquet_path)
        frame["youtube_collector_key"] = collector_key
        frame["youtube_channel"] = youtube_channel
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
            "channels": [],
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
        "channels": sorted(live["youtube_channel"].dropna().unique().tolist()),
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
) -> dict[str, Any]:
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
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(
            f"window.__ASRUN_DATA__={encoded};",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


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
.filter-shell { position: sticky; top: 0; z-index: 10; min-height: 52px; background: #eef3f8; border-bottom: 1px solid #cbd5e1; box-shadow: 0 3px 8px rgba(22, 36, 49, .08); }
.filters { min-height: 52px; display: grid; grid-template-columns: minmax(260px, 1.3fr) repeat(2, minmax(150px, 220px)) auto; gap: 8px; align-items: center; justify-content: start; }
.date-mode-group { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px; min-width: 0; }
.date-mode-group button { min-width: 0; overflow: hidden; padding: 0 8px; border: 1px solid #9dbde7; background: #ffffff; color: var(--blue); text-overflow: ellipsis; }
.date-mode-group button.active { border-color: var(--blue); background: var(--blue); color: #ffffff; }
.period-field[hidden] { display: none; }
.filter-label { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--muted); font-size: 11px; line-height: 1; white-space: nowrap; }
.filter-label input, .filter-label select { flex: 1 1 auto; min-width: 0; }
input, select { width: 100%; height: 30px; border: 1px solid #aebdca; border-radius: 4px; padding: 4px 7px; background: #ffffff; color: var(--ink); font-family: inherit; font-size: 12px; letter-spacing: 0; }
button { height: 30px; border: 0; border-radius: 4px; padding: 0 11px; background: var(--blue); color: #ffffff; cursor: pointer; font-family: var(--display-font); font-size: 12px; letter-spacing: 0; white-space: nowrap; }
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

.youtube-panel { margin-top: 16px; border-top: 3px solid #e62117; }
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
  .filters { grid-template-columns: minmax(240px, 1.3fr) repeat(2, minmax(140px, 1fr)) auto; padding: 6px 0; }
  .filter-shell { min-height: 52px; }
  .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 960px) {
  .topbar-inner { min-height: 60px; align-items: flex-start; flex-wrap: wrap; padding: 7px 0; gap: 3px 12px; }
  .meta { width: 100%; justify-content: flex-start; }
  .rank-grid, .audience-grid, .youtube-grid { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .wrap { padding: 0; }
  .filters { grid-template-columns: repeat(2, minmax(0, 1fr)) 58px; }
  .date-mode-group { grid-column: 1 / -1; }
  .filters > button { grid-column: auto; }
  .filter-shell { min-height: 76px; }
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
  .filters { grid-template-columns: repeat(2, minmax(0, 1fr)) 58px; }
  .filter-shell { min-height: 76px; }
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
.scope-table { width: 100%; min-width: 780px; border-collapse: collapse; font-size: 11px; }
.scope-table th, .scope-table td { padding: 9px 8px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
.scope-table th { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .03em; }
.scope-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
.scope-muted { color: var(--muted); }
@media (max-width: 1220px) {
  .youtube-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .youtube-filter-actions { grid-column: 1 / -1; }
}
@media (max-width: 680px) {
  .youtube-filter-bar { grid-template-columns: 1fr; }
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
}
</style><script>
const AMAGI=DATA.amagi||{};
const FCT=DATA.fct||{};
let fctClassMode='Commercial';
function showLoading(message='Updating dashboard...'){const toast=$('loadingToast');if(!toast)return;toast.classList.remove('hidden','error');$('loadingText').textContent=message;}
function hideLoading(){const toast=$('loadingToast');if(toast)toast.classList.add('hidden');}
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
function ensurePeriodControls(){if($('dateModeGroup'))return;const filters=document.querySelector('.filters'),fromLabel=$('from').closest('.filter-label'),toLabel=$('to').closest('.filter-label');fromLabel.id='dateFromLabel';toLabel.id='dateToLabel';fromLabel.classList.add('period-field');toLabel.classList.add('period-field');filters.insertAdjacentHTML('afterbegin','<div class="date-mode-group" id="dateModeGroup" role="group" aria-label="Date period"><button type="button" data-date-mode="range" title="Custom date range">Range</button><button type="button" data-date-mode="cy" title="Calendar Year, January to December">CY</button><button type="button" data-date-mode="fy" title="Indian Financial Year, April to March">FY</button><button type="button" data-date-mode="barc" title="BARC Year and Week, Saturday to Friday">BY/BW</button></div><label class="filter-label period-field" id="calendarYearLabel" hidden>Calendar Year<select id="calendarYear"></select></label><label class="filter-label period-field" id="financialYearLabel" hidden>Financial Year<select id="financialYear"></select></label><label class="filter-label period-field" id="barcYearLabel" hidden>BARC Year<select id="barcYear"></select></label><label class="filter-label period-field" id="barcWeekLabel" hidden>BARC Week<select id="barcWeek"></select></label>');const minYear=utcDay(minDate).getUTCFullYear(),maxYear=utcDay(maxDate).getUTCFullYear(),calendarYears=[];for(let year=minYear;year<=maxYear;year++)calendarYears.push({value:String(year),label:'CY '+year});fillSelect($('calendarYear'),calendarYears,String(maxYear));const minFy=fiscalStartYear(minDate),maxFy=fiscalStartYear(maxDate),financialYears=[];for(let year=minFy;year<=maxFy;year++)financialYears.push({value:String(year),label:'FY '+year+'-'+String(year+1).slice(-2)});fillSelect($('financialYear'),financialYears,String(maxFy));const minBarc=barcYearWeek(minDate).year,maxBarc=barcYearWeek(maxDate).year,barcYears=[];for(let year=minBarc;year<=maxBarc;year++)barcYears.push({value:String(year),label:'BY '+year});fillSelect($('barcYear'),barcYears,String(maxBarc));populateBarcWeeks();document.querySelectorAll('[data-date-mode]').forEach(button=>button.addEventListener('click',()=>setDateMode(button.dataset.dateMode)));$('calendarYear').addEventListener('change',applyCalendarYear);$('financialYear').addEventListener('change',applyFinancialYear);$('barcYear').addEventListener('change',()=>{populateBarcWeeks();applyBarcPeriod()});$('barcWeek').addEventListener('change',applyBarcPeriod);for(const id of ['from','to'])$(id).addEventListener('change',()=>{setDateMode('range',false);updatePeriodMeta()});setDateMode('range',false);}
function ensureCreativeFilters(){if($('spotAdIdToggle'))return;for(const id of ['typeToggle','adIdToggle','creativeToggle']){const control=$(id);if(control)control.closest('.filter-label').remove()}const panels=document.querySelectorAll('.rank-panel'),controls=(prefix,type)=>'<div class="rank-controls" aria-label="'+type+' creative filters"><label class="filter-label">Ad ID<span class="multi-select"><button id="'+prefix+'AdIdToggle" class="multi-toggle" type="button">All ad IDs</button><span id="'+prefix+'AdIdMenu" class="multi-menu"></span></span></label><label class="filter-label">Creative title<span class="multi-select"><button id="'+prefix+'CreativeToggle" class="multi-toggle" type="button">All creative titles</button><span id="'+prefix+'CreativeMenu" class="multi-menu"></span></span></label></div>';panels[0].querySelector('.panel-head').insertAdjacentHTML('afterend',controls('spot','Spot'));panels[1].querySelector('.panel-head').insertAdjacentHTML('afterend',controls('lband','L-band'));}
function sectionDateRows(type){return dateScope().filter(event=>event.ad_type===type);}
function sectionFilteredRows(type,prefix){const ids=selectedMulti(prefix+'AdId'),creatives=selectedMulti(prefix+'Creative');return sectionDateRows(type).filter(event=>(!ids.size||ids.has(event.event_id))&&(!creatives.size||creatives.has(event.creative_title)));}
function refreshSectionOptions(type,prefix){const rows=sectionDateRows(type),ids=countedOptions(rows,'event_id');buildHeaderMulti(prefix+'AdId',ids,'ad IDs',ids.map(item=>item.value),'All '+type+' ad IDs ('+fmt(rows.length)+')',()=>{refreshSectionOptions(type,prefix);refreshAudienceFilters();scheduleRender()});const selectedIds=selectedMulti(prefix+'AdId'),titleRows=rows.filter(event=>!selectedIds.size||selectedIds.has(event.event_id)),titles=countedOptions(titleRows,'creative_title');buildHeaderMulti(prefix+'Creative',titles,'creative titles',titles.map(item=>item.value),'All '+type+' creative titles ('+fmt(titleRows.length)+')',scheduleRender);}
function refreshDependentOptions(){ensureCreativeFilters();refreshSectionOptions('Spot','spot');refreshSectionOptions('L-band','lband');}
function scope(){return [...sectionDateRows('Spot'),...sectionDateRows('L-band')];}
function filterKey(){return [$('from').value,$('to').value,[...selectedMulti('spotAdId')].sort().join('|'),[...selectedMulti('spotCreative')].sort().join('|'),[...selectedMulti('lbandAdId')].sort().join('|'),[...selectedMulti('lbandCreative')].sort().join('|')].join('\u0000');}
function filtered(){const key=filterKey();if(filterCache.key===key&&filterCache.value)return filterCache.value;const result=[...sectionFilteredRows('Spot','spot'),...sectionFilteredRows('L-band','lband')].sort((a,b)=>String(a.on_air_start_ist).localeCompare(String(b.on_air_start_ist)));filterCache={key,value:result};return result;}
function resetDashboardFilters(){showLoading('Resetting dashboard...');$('from').value=minDate;$('to').value=maxDate;setDateMode('range',false);fctClassMode='Commercial';for(const id of ['spotAdId','spotCreative','lbandAdId','lbandCreative','fastPlatform','fastChannel','streamChannel','amagiPlatform','amagiChannel','fctFeed','fctLanguage','fctBrand','fctCategory','fctCompany']){const menu=$(id+'Menu');if(menu)menu.innerHTML='';}multiInitialized.clear();clearFilterCache();refreshDependentOptions();refreshAudienceFilters();updatePeriodMeta();scheduleRender();}
document.addEventListener('change',event=>{if(event.target.closest('.filters,.rank-controls,.audience-controls,.fct-class-filter,.youtube-filter-bar,.youtube-controls'))showLoading('Updating dashboard...')},true);
document.addEventListener('click',event=>{if(event.target.closest('[data-date-mode],[data-youtube-date-mode],[data-fct-class],[data-youtube-range],#reset'))showLoading('Updating dashboard...')},true);
function refreshAmagiFilters(){const rows=(AMAGI.minute||[]).filter(r=>String(r.log_date)>=String($('from').value)&&String(r.log_date)<=String($('to').value)),platforms=[...new Set(rows.map(r=>String(r.platform_name)))].sort();buildMulti('amagiPlatform',platforms,'platforms',platforms,()=>{refreshAmagiFilters();render()});const selectedPlatforms=selectedMulti('amagiPlatform'),channels=[...new Set(rows.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('amagiChannel',channels,'channels',channels,render);}
function amagiMinuteMap(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),map=new Map();for(const row of (AMAGI.minute||[])){if(!platforms.has(String(row.platform_name))||!channels.has(String(row.channel_name)))continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return {map};}
function ensureAmagiPanel(){if($('amagiRows'))return;const grid=document.querySelector('.audience-grid');grid.insertAdjacentHTML('beforeend','<div class="panel audience-panel amagi-panel"><div class="panel-head"><div><h2>AMAGI Delivered Ad Events</h2><small>Actual platform-reported concurrent viewers</small></div><span class="source-tag amagi-tag">AMAGI</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="amagiPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="amagiPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="amagiChannelToggle" class="multi-toggle" type="button">All channels</button><span id="amagiChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">Concurrency</span></div><div class="audience-list" id="amagiRows"></div><div class="audience-note" id="amagiNote"></div></div>');const header=document.querySelector('.combined-columns');header.querySelector('.youtube-col').insertAdjacentHTML('beforebegin','<span class="amagi-col">AMAGI</span>');document.querySelector('.combined-panel .panel-head small').textContent='FAST + STREAM selected 5-minute concurrency | Amagi actual 5-minute concurrency | YouTube minute concurrency';document.querySelector('.combined-panel .combined-tag').textContent='FAST + STREAM + AMAGI';}
function ensureFctPanel(){if($('fctRows'))return;ensureAmagiPanel();document.querySelector('.amagi-panel').insertAdjacentHTML('afterend','<div class="panel audience-panel fct-panel"><div class="panel-head"><div><h2>FCT Monitored Ad Occurrences</h2><small>External feed-monitoring evidence</small></div><div class="panel-actions"><button id="exportFctCsv" type="button">Export CSV</button><span class="source-tag fct-tag">FCT</span></div></div><div class="fct-class-filter" role="group" aria-label="FCT occurrence classification"><button type="button" data-fct-class="Commercial" class="active">Commercial</button><button type="button" data-fct-class="In-House">In-House</button><button type="button" data-fct-class="All">All</button><button type="button" data-fct-class="Internal / Promo">Internal &amp; Promo</button></div><div class="audience-controls fct-controls"><label class="filter-label">Feed<span class="multi-select"><button id="fctFeedToggle" class="multi-toggle" type="button">All feeds</button><span id="fctFeedMenu" class="multi-menu"></span></span></label><label class="filter-label">Language<span class="multi-select"><button id="fctLanguageToggle" class="multi-toggle" type="button">All languages</button><span id="fctLanguageMenu" class="multi-menu"></span></span></label><label class="filter-label">Brand<span class="multi-select"><button id="fctBrandToggle" class="multi-toggle" type="button">All brands</button><span id="fctBrandMenu" class="multi-menu"></span></span></label><label class="filter-label">Category<span class="multi-select"><button id="fctCategoryToggle" class="multi-toggle" type="button">All categories</button><span id="fctCategoryMenu" class="multi-menu"></span></span></label><label class="filter-label">Company<span class="multi-select"><button id="fctCompanyToggle" class="multi-toggle" type="button">All companies</button><span id="fctCompanyMenu" class="multi-menu"></span></span></label></div><div class="fct-kpis" id="fctKpis"></div><div class="fct-columns"><span>On-air IST</span><span>Feed</span><span>Brand / Caption</span><span>Program</span><span>Duration</span><span>Classification</span></div><div class="audience-list" id="fctRows"></div><div class="fct-preview-note" id="fctNote"></div></div>');for(const button of document.querySelectorAll('[data-fct-class]'))button.addEventListener('click',()=>{fctClassMode=button.dataset.fctClass;for(const id of ['fctFeed','fctLanguage','fctBrand','fctCategory','fctCompany']){$(id+'Menu').innerHTML='';multiInitialized.delete(id)}renderFctAndScope()});$('exportFctCsv').addEventListener('click',exportFctCsv);}
function ensureFctAudiencePanel(){if($('fctAllRows'))return;document.querySelector('.combined-panel').insertAdjacentHTML('afterend','<section class="panel fct-audience-panel"><div class="panel-head"><div><h2>All FCT Monitored Ad Occurrences</h2><small>FCT-selected occurrences | FAST + STREAM + AMAGI 5-minute concurrency | YouTube minute concurrency</small></div><div class="panel-actions"><button id="exportFctAudienceCsv" type="button">Export CSV</button><span class="source-tag fct-tag">FCT ANCHORED</span></div></div><div class="fct-audience-columns"><span>On-air IST</span><span>Feed</span><span>Brand / Caption</span><span class="duration">Duration</span><span class="fast-col">FAST</span><span class="stream-col">STREAM</span><span class="amagi-col">AMAGI</span><span class="youtube-col">YOUTUBE</span><span class="total-col">Combined</span></div><div class="combined-list" id="fctAllRows"></div><div class="fct-preview-note" id="fctAllNote"></div></section>');$('exportFctAudienceCsv').addEventListener('click',exportFctAudienceCsv);}
function fctValue(row,key){const value=String(row[key]??'').trim();return value||'Unknown / NA';}
function formatIstSeconds(value){const normalized=String(value).replace(' ','T'),[datePart,timePart='00:00:00']=normalized.split('T'),[year,month,day]=datePart.split('-'),[rawHour='0',minute='00',second='00']=timePart.split(':'),hour=Number(rawHour),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return day+'-'+month+'-'+year.slice(-2)+' '+String(twelve).padStart(2,'0')+':'+minute+':'+second.slice(0,2)+' '+suffix;}
function fctDateRows(){const from=$('from').value,to=$('to').value;return (FCT.events||[]).filter(row=>String(row.log_date)>=from&&String(row.log_date)<=to);}
function fctClassRows(){return fctDateRows().filter(row=>fctClassMode==='All'||String(row.event_class)===fctClassMode);}
function refreshFctFilters(){if(!FCT.available)return;const base=fctClassRows(),feeds=[...new Set(base.map(row=>fctValue(row,'feed_name')))].sort();buildMulti('fctFeed',feeds,'feeds',feeds,()=>{refreshFctFilters();renderFctAndScope(false)});const selectedFeeds=selectedMulti('fctFeed'),feedRows=base.filter(row=>selectedFeeds.has(fctValue(row,'feed_name'))),languages=[...new Set(feedRows.map(row=>fctValue(row,'language')))].sort();buildMulti('fctLanguage',languages,'languages',languages,()=>{refreshFctFilters();renderFctAndScope(false)});const selectedLanguages=selectedMulti('fctLanguage'),languageRows=feedRows.filter(row=>selectedLanguages.has(fctValue(row,'language'))),brands=[...new Set(languageRows.map(row=>fctValue(row,'brand_name')))].sort();buildMulti('fctBrand',brands,'brands',brands,()=>{refreshFctFilters();renderFctAndScope(false)});const selectedBrands=selectedMulti('fctBrand'),brandRows=languageRows.filter(row=>selectedBrands.has(fctValue(row,'brand_name'))),categories=[...new Set(brandRows.map(row=>fctValue(row,'category')))].sort();buildMulti('fctCategory',categories,'categories',categories,()=>{refreshFctFilters();renderFctAndScope(false)});const selectedCategories=selectedMulti('fctCategory'),categoryRows=brandRows.filter(row=>selectedCategories.has(fctValue(row,'category'))),companies=[...new Set(categoryRows.map(row=>fctValue(row,'company')))].sort();buildMulti('fctCompany',companies,'companies',companies,()=>renderFctAndScope(false));}
function selectedFctRows(){if(!FCT.available)return [];const feeds=selectedMulti('fctFeed'),languages=selectedMulti('fctLanguage'),brands=selectedMulti('fctBrand'),categories=selectedMulti('fctCategory'),companies=selectedMulti('fctCompany');if(!feeds.size||!languages.size||!brands.size||!categories.size||!companies.size)return [];return fctClassRows().filter(row=>feeds.has(fctValue(row,'feed_name'))&&languages.has(fctValue(row,'language'))&&brands.has(fctValue(row,'brand_name'))&&categories.has(fctValue(row,'category'))&&companies.has(fctValue(row,'company')));}
function fctAudienceRows(events,fast,stream){const amagi=amagiMinuteMap();return events.slice().sort((a,b)=>String(a.event_ist).localeCompare(String(b.event_ist))).map(event=>{const anchor={on_air_start_ist:event.event_ist},fastMetric=audienceValue(anchor,fast),streamMetric=audienceValue(anchor,stream),amagiMetric=audienceValue(anchor,amagi),youtubeMetric=youtubeFiveMinuteValue(anchor),values=[fastMetric.total,streamMetric.total,amagiMetric.total,youtubeMetric.total],total=values.some(value=>value===null)?null:values.reduce((sum,value)=>sum+value,0);return {event,fast:fastMetric,stream:streamMetric,amagi:amagiMetric,youtube:youtubeMetric,total};});}
function fctAudienceLines(events){const rows=fctAudienceRows(events,audienceMinuteMap('fast'),audienceMinuteMap('stream')),preview=rows.slice(-50).reverse();if(!preview.length)return '<div class="audience-empty">No FCT occurrences match the selected date and FCT filters.</div>';return preview.map(row=>{const event=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="fct-audience-line"><span>'+formatIstSeconds(event.event_ist)+'</span><span><strong>'+esc(fctValue(event,'feed_name'))+'</strong><small>'+esc(event.event_class)+'</small></span><span><strong>'+esc(fctValue(event,'brand_name'))+'</strong><small>'+esc(fctValue(event,'caption'))+'</small></span><span class="duration">'+fmt(event.duration_seconds||0)+' sec</span><span class="fct-audience-value fast-col">'+esc(row.fast.value)+'</span><span class="fct-audience-value stream-col">'+esc(row.stream.value)+'</span><span class="fct-audience-value amagi-col">'+esc(row.amagi.value)+'</span><span class="fct-audience-value youtube-col">'+esc(row.youtube.value)+'</span><span class="fct-audience-value total-col">'+esc(total)+'</span></div>';}).join('');}
function renderFctAudience(rows){ensureFctAudiencePanel();$('fctAllRows').innerHTML=fctAudienceLines(rows);$('fctAllNote').textContent='Showing latest '+fmt(Math.min(rows.length,50))+' of '+fmt(rows.length)+' matching FCT occurrences. CSV exports the complete filtered result.';}
function renderFct(refresh=true){ensureFctPanel();ensureFctAudiencePanel();for(const button of document.querySelectorAll('[data-fct-class]'))button.classList.toggle('active',button.dataset.fctClass===fctClassMode);if(!FCT.available){$('fctKpis').innerHTML='';$('fctRows').innerHTML='<div class="audience-empty">'+esc(FCT.reason||'FCT monitoring data is unavailable.')+'</div>';$('fctNote').textContent='';$('fctAllRows').innerHTML='<div class="audience-empty">'+esc(FCT.reason||'FCT monitoring data is unavailable.')+'</div>';$('fctAllNote').textContent='';return}if(refresh)refreshFctFilters();const rows=selectedFctRows(),duration=rows.reduce((sum,row)=>sum+Number(row.duration_seconds||0),0),brands=new Set(rows.map(row=>fctValue(row,'brand_name')).filter(value=>value!=='Unknown / NA')),feeds=new Set(rows.map(row=>fctValue(row,'feed_name'))),spillovers=rows.filter(row=>row.is_filename_spillover===true).length;$('fctKpis').innerHTML=[[fmt(rows.length),'Detected events'],[mins(duration),'Detected duration'],[fmt(brands.size),'Brands'],[fmt(feeds.size),'Feeds']].map(item=>'<div class="fct-kpi"><strong>'+item[0]+'</strong><small>'+item[1]+'</small></div>').join('');const preview=rows.slice().sort((a,b)=>String(b.event_ist).localeCompare(String(a.event_ist))).slice(0,50);$('fctRows').innerHTML=preview.length?preview.map(row=>'<div class="fct-line"><span>'+formatIstSeconds(row.event_ist)+'</span><span><strong>'+esc(fctValue(row,'feed_name'))+'</strong><small>Ad '+fmt(row.ad_position||0)+' of '+fmt(row.total_ads||0)+'</small></span><span><strong>'+esc(fctValue(row,'brand_name'))+'</strong><small>'+esc(fctValue(row,'caption'))+'</small></span><span>'+esc(fctValue(row,'program_name'))+'<small>'+esc(fctValue(row,'category'))+'</small></span><span class="fct-duration">'+fmt(row.duration_seconds||0)+' sec</span><span class="fct-class">'+esc(row.event_class)+(row.is_filename_spillover===true?'<small>Filename spillover</small>':'')+'</span></div>').join(''):'<div class="audience-empty">No FCT occurrences match the selected date and FCT filters.</div>';$('fctNote').textContent='Showing '+fmt(preview.length)+' of '+fmt(rows.length)+' matching occurrences'+(spillovers?' | '+fmt(spillovers)+' source-file spillover row(s)':'')+'. CSV exports the complete filtered result.';renderFctAudience(rows);}
function renderFctAndScope(refresh=true){renderFct(refresh);if(typeof renderScopeValidation==='function')renderScopeValidation();hideLoading();}
function exportFctCsv(){const rows=selectedFctRows(),filters=exportFilterContext(),fctFeeds=exportSelection('fctFeed','All FCT feeds'),fctLanguages=exportSelection('fctLanguage','All FCT languages'),fctBrands=exportSelection('fctBrand','All FCT brands'),fctCategories=exportSelection('fctCategory','All FCT categories'),fctCompanies=exportSelection('fctCompany','All FCT companies'),header=['Selected Date From','Selected Date To','FCT Classification','Selected FCT Feeds','Selected FCT Languages','Selected FCT Brands','Selected FCT Categories','Selected FCT Companies','On-air IST','Feed','Brand','Caption','Program','Program Start IST','Program Duration Seconds','Ad Duration Seconds','Language','Category','Company','Ad Position','Total Ads','Filename Spillover','Declared File Start','Declared File End','Source File','Source Sheet','Source Row'],csvRows=rows.slice().sort((a,b)=>String(a.event_ist).localeCompare(String(b.event_ist))).map(row=>[filters.dateFrom,filters.dateTo,fctClassMode,fctFeeds,fctLanguages,fctBrands,fctCategories,fctCompanies,formatIstSeconds(row.event_ist),row.feed_name,row.brand_name,row.caption,row.program_name,row.program_start_ist?formatIstSeconds(row.program_start_ist):'',row.program_duration_seconds,row.duration_seconds,row.language,row.category,row.company,row.ad_position,row.total_ads,row.is_filename_spillover?'Yes':'No',row.declared_start,row.declared_end,row.source_file,row.source_sheet,row.source_row]);downloadCsv('fct_monitored_ad_occurrences_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,csvRows);}
function exportFctAudienceCsv(){const events=selectedFctRows(),filters=exportFilterContext(),fctFeeds=exportSelection('fctFeed','All FCT feeds'),fctLanguages=exportSelection('fctLanguage','All FCT languages'),fctBrands=exportSelection('fctBrand','All FCT brands'),fctCategories=exportSelection('fctCategory','All FCT categories'),fctCompanies=exportSelection('fctCompany','All FCT companies'),fastPlatforms=exportSelection('fastPlatform','All FAST platforms'),fastChannels=exportSelection('fastChannel','All FAST channels'),streamChannels=exportSelection('streamChannel','All STREAM channels'),amagiPlatforms=exportSelection('amagiPlatform','All AMAGI platforms'),amagiChannels=exportSelection('amagiChannel','All AMAGI channels'),header=['Selected Date From','Selected Date To','FCT Classification','Selected FCT Feeds','Selected FCT Languages','Selected FCT Brands','Selected FCT Categories','Selected FCT Companies','FCT On-air IST','Feed','Brand','Caption','Program','Ad Duration Seconds','Language','Category','Company','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','AMAGI Platforms','AMAGI Channels','FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency','AMAGI 5-Minute Actual Concurrency','YouTube Scope','YouTube Minute Concurrency','YouTube Active Live Videos','YouTube Active Video IDs','YouTube Active Video Titles','Combined Concurrency','Source File','Source Sheet','Source Row'],rows=fctAudienceRows(events,audienceMinuteMap('fast'),audienceMinuteMap('stream')).map(row=>{const event=row.event;return [filters.dateFrom,filters.dateTo,fctClassMode,fctFeeds,fctLanguages,fctBrands,fctCategories,fctCompanies,formatIstSeconds(event.event_ist),event.feed_name,event.brand_name,event.caption,event.program_name,event.duration_seconds,event.language,event.category,event.company,row.fast.window,fastPlatforms,fastChannels,streamChannels,amagiPlatforms,amagiChannels,row.fast.value,row.stream.value,row.amagi.value,row.youtube.scope,row.youtube.value,row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,row.total===null?'No combined data':fmt(row.total),event.source_file,event.source_sheet,event.source_row]});downloadCsv('fct_audience_context_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,rows);}
function audienceLines(events,state){const preview=events.slice().sort((a,b)=>String(a.on_air_start_ist).localeCompare(String(b.on_air_start_ist))).slice(-50).reverse();if(!preview.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return preview.map(event=>{const metric=audienceValue(event,state);return '<div class="event-line"><span>'+formatIst(event.on_air_start_ist)+'</span><span><strong>'+esc(event.event_id)+'</strong><small>'+esc(event.ad_type)+'</small></span><span>'+esc(event.creative_title)+'</span><span class="duration">'+fmt(event.actual_duration_seconds)+' sec</span><span class="audience-value">'+esc(metric.value)+'</span></div>';}).join('');}
function amagiLines(events,state){if(!AMAGI.available)return '<div class="audience-empty">'+esc(AMAGI.reason||'Amagi concurrency data is unavailable.')+'</div>';return audienceLines(events,state);}
function combinedRows(events,fast,stream){const amagi=amagiMinuteMap();return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const fastMetric=audienceValue(e,fast),streamMetric=audienceValue(e,stream),amagiMetric=audienceValue(e,amagi),youtubeMetric=youtubeFiveMinuteValue(e),all=[fastMetric.total,streamMetric.total,amagiMetric.total,youtubeMetric.total];return {event:e,fast:fastMetric,stream:streamMetric,amagi:amagiMetric,youtube:youtubeMetric,total:all.some(v=>v===null)?null:all.reduce((sum,v)=>sum+v,0)};});}
function combinedLines(events,fast,stream){const rows=combinedRows(events,fast,stream),preview=rows.slice(-50).reverse();if(!preview.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return preview.map(row=>{const e=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="combined-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="combined-value fast-col">'+esc(row.fast.value)+'</span><span class="combined-value stream-col">'+esc(row.stream.value)+'</span><span class="combined-value amagi-col">'+esc(row.amagi.value)+'</span><span class="combined-value youtube-col">'+esc(row.youtube.value)+'</span><span class="combined-value total-col">'+esc(total)+'</span></div>';}).join('');}
function renderAudience(events){ensureAmagiPanel();refreshAmagiFilters();const fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),amagi=amagiMinuteMap(),visible=Math.min(events.length,50),note='Showing latest '+fmt(visible)+' of '+fmt(events.length)+' delivered events. CSV exports the complete filtered result.';$('fastRows').innerHTML=audienceLines(events,fast);$('streamRows').innerHTML=audienceLines(events,stream);$('amagiRows').innerHTML=amagiLines(events,amagi);$('allRows').innerHTML=combinedLines(events,fast,stream);$('fastNote').textContent=note;$('streamNote').textContent=note;$('amagiNote').textContent=note;$('allNote').textContent=note;}
function exportSelection(id,allLabel,keepExactValues=false){const menu=$(id+'Menu');if(!menu)return 'Not available';const inputs=[...menu.querySelectorAll('input[data-value]')],selected=inputs.filter(input=>input.checked).map(input=>input.dataset.value);if(!selected.length)return 'None';return selected.length===inputs.length&&!keepExactValues?allLabel:selected.join(' | ');}
function exportFilterContext(){return {dateFrom:$('from').value,dateTo:$('to').value,adTypes:'Spot | L-band',adIds:'Spot: '+exportSelection('spotAdId','All Spot ad IDs')+' || L-band: '+exportSelection('lbandAdId','All L-band ad IDs'),creatives:'Spot: '+exportSelection('spotCreative','All Spot creative titles')+' || L-band: '+exportSelection('lbandCreative','All L-band creative titles')};}
function exportAllEventsCsv(){const events=filtered(),fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),amagi=amagiMinuteMap(),filters=exportFilterContext(),fastPlatforms=exportSelection('fastPlatform','All FAST platforms',true),fastChannels=exportSelection('fastChannel','All FAST channels',true),streamChannels=exportSelection('streamChannel','All STREAM channels',true),amagiPlatforms=exportSelection('amagiPlatform','All AMAGI platforms',true),amagiChannels=exportSelection('amagiChannel','All AMAGI channels',true),header=['Selected Date From','Selected Date To','Selected Ad Types','Selected Ad IDs','Selected Creative Titles','On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','AMAGI Platforms','AMAGI Channels','FAST 5-Minute Concurrency','STREAM 5-Minute Concurrency','AMAGI 5-Minute Actual Concurrency','YouTube Scope','YouTube Minute Concurrency','YouTube Active Live Videos','YouTube Active Video IDs','YouTube Active Video Titles','Combined Concurrency'],rows=combinedRows(events,fast,stream).map(row=>[filters.dateFrom,filters.dateTo,filters.adTypes,filters.adIds,filters.creatives,formatIst(row.event.on_air_start_ist),row.event.ad_type,row.event.event_id,row.event.creative_title,row.event.actual_duration_seconds,row.fast.window,fastPlatforms,fastChannels,streamChannels,amagiPlatforms,amagiChannels,row.fast.value,row.stream.value,row.amagi.value,row.youtube.scope,row.youtube.value,row.youtube.live_videos,row.youtube.video_ids,row.youtube.video_titles,row.total===null?'No combined data':fmt(row.total)]);downloadCsv('asrun_all_delivered_events_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,rows);}
function amagiBreakdownScopes(){const rows=selectedAmagiRows(),seen=new Set(),scopes=[];for(const row of rows){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA'),key=platform+'\u0000'+channel;if(!seen.has(key)){seen.add(key);scopes.push({source:'AMAGI',platform,channel})}}return scopes.sort((a,b)=>a.platform.localeCompare(b.platform)||a.channel.localeCompare(b.channel));}
function amagiScopeMap(scope){const map=new Map();for(const row of selectedAmagiRows()){const platform=String(row.platform_name||'Unknown / NA'),channel=String(row.channel_name||'Unknown / NA');if(platform!==scope.platform||channel!==scope.channel)continue;const key=minuteKey(row.minute_ist);map.set(key,(map.get(key)||0)+Number(row.concurrent_viewers||0));}return map;}
function exportAudienceBreakdownCsv(){const events=filtered(),filters=exportFilterContext(),scopes=[...audienceBreakdownScopes('fast'),...audienceBreakdownScopes('stream'),...amagiBreakdownScopes()],header=['Selected Date From','Selected Date To','Selected Ad Types','Selected Ad IDs','Selected Creative Titles','On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','Source','Platform','Channel','5-Minute Window IST','Individual 5-Minute Concurrency','Metric Basis'],rows=[];for(const scope of scopes){const map=scope.source==='AMAGI'?amagiScopeMap(scope):audienceScopeMap(scope),basis=scope.source==='AMAGI'?'Actual platform-reported concurrent viewers':'Unique IP minute sum';for(const event of events){const metric=audienceScopeValue(event,map);rows.push([filters.dateFrom,filters.dateTo,filters.adTypes,filters.adIds,filters.creatives,formatIst(event.on_air_start_ist),event.ad_type,event.event_id,event.creative_title,event.actual_duration_seconds,scope.source,scope.platform,scope.channel,metric.window,metric.total,basis])}}downloadCsv('asrun_audience_platform_channel_breakdown_'+filters.dateFrom+'_to_'+filters.dateTo+'.csv',header,rows)}
function replaceDownloadAction(id,handler){const button=$(id);if(!button)return;const replacement=button.cloneNode(true);button.replaceWith(replacement);replacement.addEventListener('click',handler);}
function ensureScopePanel(){if($('dataScopeRows'))return;$('youtubePanel').insertAdjacentHTML('afterend','<section class="panel scope-panel" id="dataScopePanel"><div class="panel-head"><div><h2>Data Scope And Validation</h2><small>True range is all data embedded in this dashboard run. Used range updates with the active filters.</small></div></div><div class="scope-table-wrap"><table class="scope-table"><thead><tr><th>Dataset</th><th>True range (IST)</th><th>Used range (IST)</th><th>Used rows / points</th><th>Applied scope</th></tr></thead><tbody id="dataScopeRows"></tbody></table></div></section>');}
function sourceBounds(rows,startKey,endKey){if(!rows.length)return null;const starts=rows.map(row=>String(row[startKey]||'')).filter(Boolean).sort(),ends=rows.map(row=>String(row[endKey||startKey]||'')).filter(Boolean).sort();return starts.length&&ends.length?{start:starts[0],end:ends[ends.length-1]}:null;}
function scopeRangeText(bounds){return bounds?formatIst(bounds.start)+' to '+formatIst(bounds.end):'No matching data';}
function selectedViewerRows(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;return viewerScope(source).filter(row=>(!platforms||platforms.has(String(row.platform_name)))&&channels.has(String(row.channel_name)));}
function selectedAmagiRows(){const platforms=selectedMulti('amagiPlatform'),channels=selectedMulti('amagiChannel'),from=$('from').value,to=$('to').value;return (AMAGI.minute||[]).filter(row=>String(row.log_date)>=from&&String(row.log_date)<=to&&platforms.has(String(row.platform_name))&&channels.has(String(row.channel_name)));}
let youtubeDateMode='independent';
let youtubeDateOverlap=true;
function ensureYoutubeDateModeControls(){
  if($('youtubeDateMode'))return;
  const bar=document.querySelector('.youtube-filter-bar');
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
function setYoutubeDateMode(mode,renderNow=true){
  youtubeDateMode=mode==='follow'?'follow':'independent';
  document.querySelectorAll('[data-youtube-date-mode]').forEach(button=>
    button.classList.toggle('active',button.dataset.youtubeDateMode===youtubeDateMode)
  );
  const follow=youtubeDateMode==='follow';
  $('youtubeFrom').disabled=follow;
  $('youtubeTo').disabled=follow;
  if(follow){
    applyYoutubeMainDate(renderNow);
    return;
  }
  youtubeDateOverlap=true;
  updateYoutubeDateHelp();
  if(renderNow)renderYoutube();
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
  menu.innerHTML='<input id="youtubeVideoSearch" class="multi-search" type="search" '
    +'placeholder="Search channel, video ID, or title...">'
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
    if(open)$('youtubeVideoSearch').focus();
  };
  $('youtubeVideoSearch').oninput=event=>{
    const term=event.target.value.trim().toLowerCase();
    for(const option of menu.querySelectorAll('[data-video-option]')){
      option.style.display=!term||option.dataset.search.includes(term)?'flex':'none';
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
  ensureYoutubeChannelFilter();
  refreshYoutubeDateLimits();
  const from=$('youtubeFrom').value,to=$('youtubeTo').value;
  const channels=youtubeChannels();
  buildMulti('youtubeChannel',channels,'channels',channels,()=>{
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
        +(row?fmt(row.total):'No data')+'</span><span class="youtube-context-value">'
        +(row?fmt(row.videos.size):'-')+'</span></div>';
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
youtubeDeliveryDetails=function(event){
  const youtube=DATA.youtube||{},key=youtubeMinuteKey(event.on_air_start_ist);
  if(!youtubeDeliveryMinuteIndex){
    const totals=new Map((youtube.minute||[]).map(row=>[youtubeMinuteKey(row.timestamp_ist),row]));
    const videos=new Map();
    for(const row of youtube.video_minute||[]){
      const minuteKey=youtubeMinuteKey(row.timestamp_ist),list=videos.get(minuteKey)||[];
      list.push(row);
      videos.set(minuteKey,list);
    }
    youtubeDeliveryMinuteIndex={totals,videos};
  }
  const totalRow=youtubeDeliveryMinuteIndex.totals.get(key);
  const videoRows=youtubeDeliveryMinuteIndex.videos.get(key)||[];
  if(!totalRow)return {
    value:'No YouTube data',total:null,live_videos:0,video_ids:'',
    video_titles:'',scope:'All collected YouTube channels at the on-air minute',
  };
  const videoIds=[...new Set(videoRows.map(row=>String(row.video_id||'')).filter(Boolean))];
  const titles=[...new Set(videoRows.map(row=>
    youtubeVideoTitle(youtube,row.video_id,row.log_date)).filter(Boolean))];
  const channels=[...new Set(videoRows.map(row=>
    String(row.youtube_channel||'Unknown / NA')))].sort();
  return {
    value:fmt(Number(totalRow.total_concurrent_viewers||0)),
    total:Number(totalRow.total_concurrent_viewers||0),
    live_videos:Number(totalRow.live_videos||videoIds.length),
    video_ids:videoIds.join(' | '),
    video_titles:titles.join(' | '),
    scope:'All collected YouTube channels at the on-air minute: '+channels.join(' | '),
  };
};
function selectedYoutubeRows(){
  const youtube=DATA.youtube||{},from=$('youtubeFrom').value,to=$('youtubeTo').value;
  if(youtubeDateMode==='follow'&&!youtubeDateOverlap)return [];
  return youtubeSelectedVideoMinuteRows(youtube,from,to);
}
function renderScopeValidation(){ensureScopePanel();const asrunTrue=sourceBounds(DATA.events||[],'on_air_start_ist','on_air_end_ist'),asrunUsed=sourceBounds(filtered(),'on_air_start_ist','on_air_end_ist'),fastTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='fast'),'minute_ist'),fastUsed=selectedViewerRows('fast'),streamTrue=sourceBounds((DATA.viewer_minute||[]).filter(row=>row.source==='stream'),'minute_ist'),streamUsed=selectedViewerRows('stream'),amagiTrue=sourceBounds(AMAGI.minute||[],'minute_ist'),amagiUsed=selectedAmagiRows(),fctTrue=FCT.true_start&&FCT.true_end?{start:FCT.true_start,end:FCT.true_end}:null,fctUsed=selectedFctRows(),youtube=DATA.youtube||{},youtubeTrue={start:youtube.true_start||'',end:youtube.true_end||''},youtubeUsed=selectedYoutubeRows(),rows=[['ASRUN delivered ad events',asrunTrue,asrunUsed,filtered().length,'Date, ad type, ad ID, creative title'],['FAST fixed 5-minute audience buckets',fastTrue,sourceBounds(fastUsed,'minute_ist'),fastUsed.length,'ASRUN date + FAST platform/channel'],['STREAM fixed 5-minute audience buckets',streamTrue,sourceBounds(streamUsed,'minute_ist'),streamUsed.length,'ASRUN date + STREAM channel'],['AMAGI actual 5-minute audience buckets',amagiTrue,sourceBounds(amagiUsed,'minute_ist'),amagiUsed.length,'ASRUN date + AMAGI platform/channel'],['FCT monitored ad occurrences',fctTrue,sourceBounds(fctUsed,'event_ist'),fctUsed.length,'ASRUN date + FCT class/feed/language/brand/category/company'],['YouTube live audience',youtubeTrue.start&&youtubeTrue.end?youtubeTrue:null,sourceBounds(youtubeUsed,'timestamp_ist'),youtubeUsed.length,'Independent YouTube date + video filter']];$('dataScopeRows').innerHTML=rows.map(row=>'<tr><td><strong>'+esc(row[0])+'</strong></td><td>'+esc(scopeRangeText(row[1]))+'</td><td>'+esc(scopeRangeText(row[2]))+'</td><td>'+fmt(row[3])+'</td><td class="scope-muted">'+esc(row[4])+'</td></tr>').join('');}
const asrunBaseRender=render;render=function(){if(youtubeDateMode==='follow')applyYoutubeMainDate(false);asrunBaseRender();renderFct();if(youtubeDateMode==='follow')renderYoutube();else renderScopeValidation();hideLoading();};
renderYoutube=renderYoutubeChannelAware;
const asrunBaseRenderYoutube=renderYoutube;
renderYoutube=function(){asrunBaseRenderYoutube();renderScopeValidation();hideLoading();};
ensurePeriodControls();ensureCreativeFilters();ensureYoutubeDateModeControls();ensureYoutubeChannelFilter();ensureYoutubeChartIntervalControls();ensureYoutubeChartExpand();refreshYoutubeDateLimits();initializeYoutubeDates();setYoutubeDateMode('independent',false);refreshDependentOptions();ensureAmagiPanel();ensureFctPanel();ensureScopePanel();$('reset').onclick=resetDashboardFilters;replaceDownloadAction('exportAllEvents',exportAllEventsCsv);replaceDownloadAction('exportAudienceBreakdown',exportAudienceBreakdownCsv);replaceDownloadAction('exportYoutubeCsv',exportYoutubeCsvChannelAware);replaceDownloadAction('exportYoutubeReferenceCsv',exportYoutubeReferenceCsvChannelAware);render();renderYoutube();
</script>'''
    return (
        template.replace("__TITLE__", title)
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
    fct = build_fct_ad_mart()
    viewer_snapshot_path = PARSED_DIR / "audience_ops_identity_minute_asrun_dates.parquet"
    viewer_minute.to_parquet(viewer_snapshot_path, index=False)
    payload = build_payload(events, viewer_minute, youtube, amagi, fct)
    (OUTPUT_DIR / "asrun_ad_events.csv").write_text(
        events.loc[events["is_ad"]].to_csv(index=False), encoding="utf-8-sig"
    )
    payload_path = OUTPUT_DIR / "asrun_delivery_data.js"
    write_payload_script(payload_path, payload)
    html_path = OUTPUT_DIR / "asrun_delivery_demo.html"
    html_path.write_text(render_dashboard(payload), encoding="utf-8")
    print(f"Parsed events : {len(events):,}")
    print(f"Ad events     : {payload['kpis']['ad_plays']:,}")
    print(f"Viewer rows   : {len(viewer_minute):,} (Audience Operations identity-minute snapshot)")
    print(f"YouTube files : {youtube['completed_files']:,} completed, {youtube['partial_files']:,} partial")
    print(f"Amagi rows    : {len(amagi['minute']):,} actual viewer minutes from {amagi['files']:,} file(s)")
    print(
        f"FCT events    : {len(fct['events']):,} monitored occurrences "
        f"from {fct['files']:,} workbook(s)"
    )
    print(f"Parquet       : {parsed_path}")
    print(f"Viewer mart   : {viewer_snapshot_path}")
    print(f"Dashboard data: {payload_path}")
    print(f"Dashboard     : {html_path}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
