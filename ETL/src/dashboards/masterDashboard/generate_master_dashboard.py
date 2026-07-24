"""Build the compact Veto master dashboard from reusable ETL marts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

import pandas as pd


IST_ZONE = ZoneInfo("Asia/Kolkata")
SECONDS_PER_MEDIA_SEGMENT = 6
HOURS_PER_MEDIA_SEGMENT = SECONDS_PER_MEDIA_SEGMENT / 3600
UNKNOWN_LABEL = "Unknown / NA"

DEVICE_LABELS = {
    "smart_tv": "Smart TV",
    "streaming_device": "Streaming Device",
    "desktop": "Desktop",
    "smartphone": "Smartphone",
    "tablet": "Tablet",
    "phablet": "Phablet",
    "peripheral": "Peripheral",
    "smart speaker": "Smart Speaker",
    "car browser": "Car Browser",
    "feature phone": "Feature Phone",
    "bot": "Bot / Automation",
    "unknown device type": UNKNOWN_LABEL,
    "other": UNKNOWN_LABEL,
}

STREAM_DEVICE_LABELS = {
    "android": "Android Device",
    "linux": "Linux / Connected TV",
    "iphone": "iPhone",
    "ipad": "iPad",
    "mac": "Mac",
    "windows": "Windows Device",
    "smart tv": "Smart TV",
    "other": UNKNOWN_LABEL,
}

STREAM_OS_LABELS = {
    "android": "Android",
    "linux": "Linux / TV OS (Unresolved)",
    "iphone": "iOS",
    "ipad": "iPadOS",
    "mac": "macOS",
    "windows": "Windows",
    "smart tv": "Smart TV OS (Unresolved)",
    "other": UNKNOWN_LABEL,
}

OS_LABEL_RULES = [
    (r"android\s*tv", "Android TV"),
    (r"fire\s*os", "Fire OS"),
    (r"gnu/?linux", "GNU/Linux"),
    (r"chrome\s*os", "Chrome OS"),
    (r"firefox\s*os", "Firefox OS"),
    (r"roku\s*os", "Roku OS"),
    (r"coolita\s*os", "Coolita OS"),
    (r"harmony\s*os", "HarmonyOS"),
    (r"apple\s*tv|tvos", "tvOS"),
    (r"ipados", "iPadOS"),
    (r"\bios\b", "iOS"),
    (r"mac\s*os|macos|^mac$", "macOS"),
    (r"windows", "Windows"),
    (r"web\s*os", "webOS"),
    (r"tizen", "Tizen"),
    (r"fuchsia", "Fuchsia"),
    (r"android", "Android"),
    (r"linux", "Linux"),
]

INDIA_STATE_LABELS = {
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chandigarh": "Chandigarh",
    "chattisgarh": "Chhattisgarh",
    "chhattisgarh": "Chhattisgarh",
    "dadra and nagar": "Dadra and Nagar Haveli",
    "dadra and nagar haveli": "Dadra and Nagar Haveli",
    "daman and diu": "Daman and Diu",
    "delhi": "Delhi",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jammu & kashmir": "Jammu and Kashmir",
    "jammu and kashmir": "Jammu and Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "puducherry": "Puducherry",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
}

COUNTRY_LABELS = {
    "AE": "United Arab Emirates",
    "AU": "Australia",
    "BD": "Bangladesh",
    "BH": "Bahrain",
    "CA": "Canada",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "JP": "Japan",
    "NL": "Netherlands",
    "NP": "Nepal",
    "OM": "Oman",
    "PL": "Poland",
    "SG": "Singapore",
    "US": "United States",
}


class MasterDashboardError(RuntimeError):
    """Base exception for master-dashboard generation failures."""


class ParquetReadError(MasterDashboardError):
    """Raised when a required or present optional parquet cannot be read."""


def resolve_src_root() -> Path:
    env = os.getenv("VG_ETL_SRC_ROOT")
    candidates = [Path(env).expanduser().resolve()] if env else []
    candidates.extend(Path(__file__).resolve().parents[:6])
    for candidate in candidates:
        if (candidate / "common" / "chartjs.py").exists() and (candidate / "common" / "render.py").exists():
            return candidate
    raise FileNotFoundError("Cannot find ETL src/common. Set VG_ETL_SRC_ROOT env var.")


SRC_ROOT = resolve_src_root()
ETL_ROOT = SRC_ROOT.parent
DEFAULT_OUTPUT_ROOT = ETL_ROOT / "output"


def load_common_module(module_name: str, file_name: str) -> Any:
    module_path = SRC_ROOT / "common" / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load common module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_chartjs = load_common_module("veto_master_chartjs", "chartjs.py")
_render = load_common_module("veto_master_render", "render.py")
load_chartjs = _chartjs.load_chartjs
chartjs_script = _render.chartjs_script
json_blob = _render.json_blob
render_template = _render.render_template


def warn(message: str) -> None:
    print(f"WARNING: {message}")


def validate_output_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"ETL output root not found: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"ETL output root is not a directory: {resolved}")
    return resolved


def validate_output_target(path: Path, dry_run: bool) -> Path:
    target = path.expanduser().resolve()
    if dry_run:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    # Probe before parquet reads so a permissions problem fails immediately.
    with tempfile.NamedTemporaryFile(prefix=".master-write-test-", suffix=".tmp", dir=target.parent, delete=True):
        pass
    return target


def read_parquet(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required parquet not found: {path}")
    try:
        return pd.read_parquet(path, columns=columns)
    except (OSError, ValueError, TypeError, ImportError) as exc:
        raise ParquetReadError(f"Could not read parquet {path}: {exc}") from exc


def read_optional_parquet(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        warn(f"Optional identity parquet not found: {path}")
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_parquet(path, columns=columns)
    except (OSError, ValueError, TypeError, ImportError) as exc:
        raise ParquetReadError(f"Could not read optional parquet {path}: {exc}") from exc


def date_text(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    return result


def prepare_dates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["log_date"] = date_text(result["log_date"])
    result["source"] = result["source"].fillna("").astype(str).str.lower().str.strip()
    return result[result["log_date"].notna() & result["source"].ne("")].copy()


def source_bounds(frame: pd.DataFrame) -> dict[str, tuple[str, str]]:
    if frame.empty:
        return {}
    return {
        str(source): (str(group["log_date"].min()), str(group["log_date"].max()))
        for source, group in frame.groupby("source", observed=True)
        if not group.empty
    }


def common_source_ranges(
    frames: dict[str, pd.DataFrame],
    identity_available: bool,
) -> list[dict[str, str]]:
    latest_completed = (datetime.now(IST_ZONE).date() - timedelta(days=1)).isoformat()
    bounds = {name: source_bounds(frame) for name, frame in frames.items()}
    sources = sorted(set(bounds["watch_source"]) & set(bounds["watch_channel"]) & set(bounds["views_source"]) & set(bounds["views_channel"]))
    ranges: list[dict[str, str]] = []
    for source in sources:
        required_names = ["watch_source", "watch_channel", "views_source", "views_channel"]
        if source == "stream" and identity_available:
            required_names.extend(["identity_source", "identity_channel"])
        source_bounds_list = [bounds[name].get(source) for name in required_names]
        if any(item is None for item in source_bounds_list):
            continue
        start = max(item[0] for item in source_bounds_list if item is not None)
        end = min([item[1] for item in source_bounds_list if item is not None] + [latest_completed])
        if start <= end:
            ranges.append({"source": source, "min_date": start, "max_date": end})
    return ranges


def filter_to_ranges(frame: pd.DataFrame, ranges: list[dict[str, str]]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    pieces = [
        frame[
            frame["source"].eq(row["source"])
            & frame["log_date"].between(row["min_date"], row["max_date"])
        ]
        for row in ranges
    ]
    return pd.concat(pieces, ignore_index=True) if pieces else frame.iloc[0:0].copy()


def normalize_ua(value: Any) -> str:
    """Return the same stable UA text used by the incremental decode lookup."""
    text = str(value or "").strip()
    for _ in range(5):
        decoded = unquote_plus(text).strip()
        if decoded == text:
            break
        text = decoded
    return re.sub(r"\s+", " ", text).strip()


def ua_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def coalesce_text(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series("", index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        candidate = frame[column].fillna("").astype(str).str.strip()
        mask = result.eq("") & candidate.ne("")
        result.loc[mask] = candidate.loc[mask]
    return result


def canonical_device_labels(series: pd.Series) -> pd.Series:
    clean = series.fillna("").astype(str).str.strip()
    lowered = clean.str.lower()
    labels = lowered.map(DEVICE_LABELS)
    fallback = clean.str.replace("_", " ", regex=False).str.replace(r"\s+", " ", regex=True).str.title()
    labels = labels.fillna(fallback)
    unknown = clean.eq("") | lowered.isin({"unknown", "unknown / na", "not available", "n/a"})
    labels.loc[unknown] = UNKNOWN_LABEL
    return labels


def canonical_os_labels(series: pd.Series) -> pd.Series:
    clean = series.fillna("").astype(str).str.strip()
    lowered = clean.str.lower()
    labels = pd.Series(UNKNOWN_LABEL, index=series.index, dtype="object")
    unmatched = ~lowered.isin(
        {
            "",
            "unknown",
            "unknown / na",
            "os not exposed in ua",
            "os family not exposed in ua",
            "n/a",
        }
    )
    for pattern, label in OS_LABEL_RULES:
        mask = unmatched & lowered.str.contains(pattern, regex=True, na=False)
        labels.loc[mask] = label
        unmatched &= ~mask
    labels.loc[unmatched & lowered.eq("other mobile")] = "Other Mobile OS"
    labels.loc[unmatched & lowered.eq("other smart tv")] = "Other Smart TV OS"
    remaining = unmatched & ~lowered.isin({"other mobile", "other smart tv"})
    labels.loc[remaining] = clean.loc[remaining].str.replace("_", " ", regex=False).str.title()
    return labels


def normalize_channel_names(series: pd.Series) -> pd.Series:
    return series.fillna("Other / Unknown").astype(str).str.strip().replace("", "Other / Unknown")


def dimension_rows(
    frame: pd.DataFrame,
    group_keys: list[str],
    dimension: str,
    labels: pd.Series,
) -> pd.DataFrame:
    work = frame[group_keys + ["raw_ts_rows"]].copy()
    work["dimension"] = dimension
    work["label"] = labels.fillna(UNKNOWN_LABEL).astype(str).str.strip().replace("", UNKNOWN_LABEL)
    work = work[work["raw_ts_rows"].gt(0)]
    grouped = (
        work.groupby(group_keys + ["dimension", "label"], as_index=False, observed=True, dropna=False)["raw_ts_rows"]
        .sum()
    )
    grouped["watch_hours"] = grouped["raw_ts_rows"] * HOURS_PER_MEDIA_SEGMENT
    return grouped


def build_ua_daily(
    output_root: Path,
    ranges: list[dict[str, str]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    watch_dir = output_root / "watch_hours" / "daily_tables"
    concurrency_dir = output_root / "watch_hours" / "concurrency"
    device_dir = output_root / "device_decode"
    input_files = {
        "ua_source": watch_dir / "user_agents_daily.parquet",
        "ua_lookup": device_dir / "ua_decode_lookup_both_all.parquet",
        "ua_channel_coarse": watch_dir / "device_type_by_channel_daily.parquet",
        "ua_channel_fast": concurrency_dir / "fast_platform_channel_ua_device_daily.parquet",
    }

    ua = prepare_dates(
        numeric(
            read_parquet(input_files["ua_source"], ["log_date", "source", "userAgent", "raw_ts_rows"]),
            ["raw_ts_rows"],
        )
    )
    ua = filter_to_ranges(ua, ranges)
    ua["userAgent"] = ua["userAgent"].fillna("").astype(str)

    lookup_columns = [
        "ua_hash",
        "decode_status",
        "device_type",
        "os_name",
        "os_family",
        "api_device_type",
        "api_os_name",
    ]
    lookup = read_parquet(input_files["ua_lookup"], lookup_columns)
    lookup["ua_hash"] = lookup["ua_hash"].fillna("").astype(str)
    lookup = lookup[lookup["ua_hash"].ne("")].drop_duplicates("ua_hash", keep="last")

    # Hash each distinct UA once; the daily mart can contain the same UA thousands of times.
    ua_keys = pd.DataFrame({"userAgent": ua["userAgent"].drop_duplicates()})
    ua_keys["ua_norm"] = ua_keys["userAgent"].map(normalize_ua)
    ua_keys["ua_hash"] = ua_keys["ua_norm"].map(ua_hash)
    ua_keys = ua_keys.merge(lookup, on="ua_hash", how="left", validate="many_to_one")
    status = ua_keys["decode_status"].fillna("not_in_lookup").astype(str).str.lower()
    ua_keys["device_label"] = canonical_device_labels(
        coalesce_text(ua_keys, ["device_type", "api_device_type"])
    )
    ua_keys["os_label"] = canonical_os_labels(coalesce_text(ua_keys, ["os_name", "api_os_name", "os_family"]))
    ua_keys.loc[status.eq("malformed"), ["device_label", "os_label"]] = "Malformed / Noise"
    ua_keys.loc[status.isin({"unknown", "not_in_lookup"}), ["device_label", "os_label"]] = UNKNOWN_LABEL
    ua = ua.merge(
        ua_keys[["userAgent", "device_label", "os_label"]],
        on="userAgent",
        how="left",
        validate="many_to_one",
    )

    source_device = dimension_rows(ua, ["log_date", "source"], "device", ua["device_label"])
    source_os = dimension_rows(ua, ["log_date", "source"], "os", ua["os_label"])
    source_daily = pd.concat([source_device, source_os], ignore_index=True)
    source_daily["scope"] = "source"
    source_daily["channel_name"] = None

    coarse = prepare_dates(
        numeric(
            read_parquet(
                input_files["ua_channel_coarse"],
                ["log_date", "source", "channel_name", "device_type", "raw_ts_rows"],
            ),
            ["raw_ts_rows"],
        )
    )
    coarse = filter_to_ranges(coarse, ranges)
    coarse["channel_name"] = normalize_channel_names(coarse["channel_name"])

    rich_fast = read_optional_parquet(
        input_files["ua_channel_fast"],
        [
            "log_date",
            "source",
            "channel_name",
            "decode_status",
            "device_type_label",
            "os_label",
            "os_family_label",
            "raw_ts_rows",
        ],
    )
    rich_fast = filter_to_ranges(prepare_dates(numeric(rich_fast, ["raw_ts_rows"])), ranges)
    rich_fast = rich_fast[rich_fast["source"].eq("fast")].copy()
    if not rich_fast.empty:
        rich_fast["channel_name"] = normalize_channel_names(rich_fast["channel_name"])
        fast_status = rich_fast["decode_status"].fillna("").astype(str).str.lower()
        fast_device_labels = canonical_device_labels(rich_fast["device_type_label"])
        fast_os_labels = canonical_os_labels(coalesce_text(rich_fast, ["os_label", "os_family_label"]))
        fast_device_labels.loc[fast_status.eq("malformed")] = "Malformed / Noise"
        fast_os_labels.loc[fast_status.eq("malformed")] = "Malformed / Noise"
        fast_device = dimension_rows(
            rich_fast,
            ["log_date", "source", "channel_name"],
            "device",
            fast_device_labels,
        )
        fast_os = dimension_rows(
            rich_fast,
            ["log_date", "source", "channel_name"],
            "os",
            fast_os_labels,
        )
    else:
        fast_coarse = coarse[coarse["source"].eq("fast")].copy()
        fast_device = dimension_rows(
            fast_coarse,
            ["log_date", "source", "channel_name"],
            "device",
            canonical_device_labels(fast_coarse["device_type"]),
        )
        fast_os = dimension_rows(
            fast_coarse,
            ["log_date", "source", "channel_name"],
            "os",
            fast_coarse["device_type"].fillna("").astype(str).str.lower().map(STREAM_OS_LABELS).fillna(UNKNOWN_LABEL),
        )

    stream_coarse = coarse[coarse["source"].eq("stream")].copy()
    stream_key = stream_coarse["device_type"].fillna("").astype(str).str.strip().str.lower()
    stream_device = dimension_rows(
        stream_coarse,
        ["log_date", "source", "channel_name"],
        "device",
        stream_key.map(STREAM_DEVICE_LABELS).fillna(UNKNOWN_LABEL),
    )
    stream_os = dimension_rows(
        stream_coarse,
        ["log_date", "source", "channel_name"],
        "os",
        stream_key.map(STREAM_OS_LABELS).fillna(UNKNOWN_LABEL),
    )

    channel_daily = pd.concat([fast_device, fast_os, stream_device, stream_os], ignore_index=True)
    channel_daily["scope"] = "channel"
    columns = ["log_date", "source", "scope", "channel_name", "dimension", "label", "raw_ts_rows", "watch_hours"]
    daily = pd.concat([source_daily[columns], channel_daily[columns]], ignore_index=True)
    daily = daily.sort_values(["log_date", "source", "scope", "channel_name", "dimension", "label"], na_position="first").reset_index(drop=True)
    if daily.duplicated(["log_date", "source", "scope", "channel_name", "dimension", "label"]).any():
        raise MasterDashboardError("UA daily mart contains duplicate dimension keys")
    return daily, {name: str(path.resolve()) for name, path in input_files.items()}


def country_labels(series: pd.Series) -> pd.Series:
    codes = series.fillna("").astype(str).str.strip().str.upper()
    labels = codes.map(COUNTRY_LABELS)
    fallback = codes.where(codes.ne(""), UNKNOWN_LABEL)
    return labels.fillna(fallback)


def india_state_labels(series: pd.Series) -> pd.Series:
    clean = series.fillna("").astype(str).str.strip()
    return clean.str.lower().map(INDIA_STATE_LABELS).fillna(UNKNOWN_LABEL)


def market_rows(frame: pd.DataFrame, group_keys: list[str]) -> pd.DataFrame:
    country = frame["country"].fillna("").astype(str).str.strip().str.upper()
    india = frame[country.eq("IN")].copy()
    india["market_level"] = "india_state"
    india["label"] = india_state_labels(india["state"])

    international = frame[~country.eq("IN")].copy()
    international["market_level"] = "country"
    international["label"] = country_labels(international["country"])

    work = pd.concat([india, international], ignore_index=True)
    work = work[work["raw_ts_rows"].gt(0)]
    grouped = (
        work.groupby(group_keys + ["market_level", "label"], as_index=False, observed=True, dropna=False)["raw_ts_rows"]
        .sum()
    )
    grouped["watch_hours"] = grouped["raw_ts_rows"] * HOURS_PER_MEDIA_SEGMENT
    return grouped


def build_market_daily(
    output_root: Path,
    ranges: list[dict[str, str]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    watch_dir = output_root / "watch_hours" / "daily_tables"
    input_files = {
        "market_source": watch_dir / "geo_daily.parquet",
        "market_channel": watch_dir / "channel_geo_daily.parquet",
    }
    source = prepare_dates(
        numeric(
            read_parquet(input_files["market_source"], ["log_date", "source", "country", "state", "raw_ts_rows"]),
            ["raw_ts_rows"],
        )
    )
    channel = prepare_dates(
        numeric(
            read_parquet(
                input_files["market_channel"],
                ["log_date", "source", "channel_name", "country", "state", "raw_ts_rows"],
            ),
            ["raw_ts_rows"],
        )
    )
    source = filter_to_ranges(source, ranges)
    channel = filter_to_ranges(channel, ranges)
    channel["channel_name"] = normalize_channel_names(channel["channel_name"])

    source_daily = market_rows(source, ["log_date", "source"])
    source_daily["scope"] = "source"
    source_daily["channel_name"] = None
    channel_daily = market_rows(channel, ["log_date", "source", "channel_name"])
    channel_daily["scope"] = "channel"
    columns = ["log_date", "source", "scope", "channel_name", "market_level", "label", "raw_ts_rows", "watch_hours"]
    daily = pd.concat([source_daily[columns], channel_daily[columns]], ignore_index=True)
    daily = daily.sort_values(["log_date", "source", "scope", "channel_name", "market_level", "label"], na_position="first").reset_index(drop=True)
    if daily.duplicated(["log_date", "source", "scope", "channel_name", "market_level", "label"]).any():
        raise MasterDashboardError("Market daily mart contains duplicate dimension keys")
    return daily, {name: str(path.resolve()) for name, path in input_files.items()}


def build_raw_geo_hierarchy_daily(
    output_root: Path,
    ranges: list[dict[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Load the source-reported country/state/city hierarchy without normalization."""
    watch_dir = output_root / "watch_hours" / "daily_tables"
    input_files = {
        "geo_hierarchy_source": watch_dir / "geo_daily.parquet",
        "geo_hierarchy_channel": watch_dir / "channel_geo_daily.parquet",
    }
    value_columns = ["raw_ts_rows", "approx_unique_ips"]
    geo_columns = ["log_date", "source", "country", "state", "city", *value_columns]
    channel_columns = ["log_date", "source", "channel_name", "country", "state", "city", *value_columns]

    source = filter_to_ranges(
        prepare_dates(numeric(read_parquet(input_files["geo_hierarchy_source"], geo_columns), value_columns)),
        ranges,
    )
    channel = filter_to_ranges(
        prepare_dates(numeric(read_parquet(input_files["geo_hierarchy_channel"], channel_columns), value_columns)),
        ranges,
    )

    # Do not apply country/state/city labels here. This directory is intentionally
    # a direct view of the values supplied by the CDN geography source.
    for frame in (source, channel):
        for column in ("country", "state", "city"):
            frame[column] = frame[column].fillna("").astype(str).str.strip()
    channel["channel_name"] = normalize_channel_names(channel["channel_name"])

    source = source[geo_columns].sort_values(["log_date", "source", "country", "state", "city"]).reset_index(drop=True)
    channel = channel[channel_columns].sort_values(
        ["log_date", "source", "channel_name", "country", "state", "city"]
    ).reset_index(drop=True)
    return source, channel, {name: str(path.resolve()) for name, path in input_files.items()}


def compact_payload(
    frame: pd.DataFrame,
    category_columns: list[str],
    value_columns: list[str],
) -> dict[str, Any]:
    """Dictionary-encode repeated labels so the static HTML stays responsive."""
    columns = category_columns + value_columns
    encoded = pd.DataFrame(index=frame.index)
    dictionaries: dict[str, list[str]] = {}
    for column in category_columns:
        clean = frame[column].where(frame[column].notna(), None)
        values = sorted({str(value) for value in clean.dropna().tolist()}, key=str.casefold)
        dictionaries[column] = values
        mapping = {value: index for index, value in enumerate(values)}
        encoded[column] = clean.map(lambda value: mapping.get(str(value), -1) if value is not None else -1).astype("int32")
    for column in value_columns:
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        encoded[column] = values.round().astype("int64")
    return {
        "columns": columns,
        "dictionaries": dictionaries,
        "rows": encoded[columns].to_numpy().tolist(),
    }


def expand_compact_payload(payload: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(payload["rows"], columns=payload["columns"])
    for column, values in payload["dictionaries"].items():
        lookup = {index: value for index, value in enumerate(values)}
        indices = frame[column].copy()
        decoded = indices.map(lookup).astype(object)
        decoded.loc[indices.lt(0)] = None
        frame[column] = decoded
    return frame

def merge_metrics(
    base: pd.DataFrame,
    addition: pd.DataFrame,
    keys: list[str],
    *,
    how: str = "left",
) -> pd.DataFrame:
    if addition.empty:
        return base.copy()
    if addition.duplicated(keys).any():
        duplicates = int(addition.duplicated(keys, keep=False).sum())
        raise MasterDashboardError(f"Metric mart contains {duplicates} duplicate key rows for {keys}")
    return base.merge(addition, on=keys, how=how, validate="one_to_one")


def build_master_frames(output_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, str]], dict[str, str]]:
    watch_dir = output_root / "watch_hours" / "daily_tables"
    latency_dir = output_root / "latency" / "profile"
    identity_dir = output_root / "identity"

    input_files = {
        "watch_source": watch_dir / "daily_volume.parquet",
        "watch_channel": watch_dir / "channel_audience_daily.parquet",
        "views_source": latency_dir / "daily.parquet",
        "views_channel": latency_dir / "channel_daily.parquet",
        "identity_source": identity_dir / "identity_daily.parquet",
        "identity_channel": identity_dir / "identity_channel_daily.parquet",
    }

    watch_source = prepare_dates(
        numeric(
            read_parquet(input_files["watch_source"], ["log_date", "source", "raw_ts_rows", "approx_unique_ips"]),
            ["raw_ts_rows", "approx_unique_ips"],
        )
    )
    watch_source = watch_source.rename(columns={"raw_ts_rows": "clips_watched", "approx_unique_ips": "ip_users"})
    watch_source["watch_hours"] = watch_source["clips_watched"] * HOURS_PER_MEDIA_SEGMENT
    watch_source = watch_source[["log_date", "source", "watch_hours", "clips_watched", "ip_users"]]

    watch_channel = prepare_dates(
        numeric(
            read_parquet(
                input_files["watch_channel"],
                ["log_date", "source", "channel_name", "raw_ts_chunks", "raw_watch_hours", "approx_unique_ips"],
            ),
            ["raw_ts_chunks", "raw_watch_hours", "approx_unique_ips"],
        )
    )
    watch_channel["channel_name"] = watch_channel["channel_name"].fillna("Other / Unknown").astype(str).str.strip().replace("", "Other / Unknown")
    watch_channel = watch_channel.rename(
        columns={"raw_ts_chunks": "clips_watched", "raw_watch_hours": "watch_hours", "approx_unique_ips": "ip_users"}
    )
    watch_channel = watch_channel[["log_date", "source", "channel_name", "watch_hours", "clips_watched", "ip_users"]]

    views_source = prepare_dates(
        numeric(
            read_parquet(input_files["views_source"], ["log_date", "source", "extension", "rows"]),
            ["rows"],
        )
    )
    views_source = views_source[views_source["extension"].fillna("").astype(str).str.lower().str.lstrip(".").eq("m3u8")]
    views_source = (
        views_source.groupby(["log_date", "source"], as_index=False, observed=True)["rows"].sum().rename(columns={"rows": "total_views"})
    )

    views_channel = prepare_dates(
        numeric(
            read_parquet(input_files["views_channel"], ["log_date", "source", "extension", "channel_name", "rows"]),
            ["rows"],
        )
    )
    views_channel = views_channel[views_channel["extension"].fillna("").astype(str).str.lower().str.lstrip(".").eq("m3u8")]
    views_channel["channel_name"] = views_channel["channel_name"].fillna("Other / Unknown").astype(str).str.strip().replace("", "Other / Unknown")
    views_channel = (
        views_channel.groupby(["log_date", "source", "channel_name"], as_index=False, observed=True)["rows"]
        .sum()
        .rename(columns={"rows": "total_views"})
    )

    identity_source_columns = ["log_date", "source", "total_devices", "total_sessions"]
    identity_channel_columns = identity_source_columns + ["channel_name"]
    identity_source = prepare_dates(numeric(read_optional_parquet(input_files["identity_source"], identity_source_columns), ["total_devices", "total_sessions"]))
    identity_channel = prepare_dates(numeric(read_optional_parquet(input_files["identity_channel"], identity_channel_columns), ["total_devices", "total_sessions"]))
    if not identity_channel.empty:
        identity_channel["channel_name"] = identity_channel["channel_name"].fillna("Other / Unknown").astype(str).str.strip().replace("", "Other / Unknown")

    frames = {
        "watch_source": watch_source,
        "watch_channel": watch_channel,
        "views_source": views_source,
        "views_channel": views_channel,
        "identity_source": identity_source,
        "identity_channel": identity_channel,
    }
    ranges = common_source_ranges(frames, identity_available=not identity_source.empty and not identity_channel.empty)
    if not ranges:
        raise MasterDashboardError("No completed common date range exists across watch and manifest-view marts.")

    source_daily = merge_metrics(watch_source, views_source, ["log_date", "source"])
    source_daily = merge_metrics(
        source_daily,
        identity_source[["log_date", "source", "total_devices", "total_sessions"]] if not identity_source.empty else identity_source,
        ["log_date", "source"],
    )
    # Preserve view-only channels: a playback manifest can be requested even
    # when no media segment is subsequently played on that source/day.
    channel_daily = merge_metrics(
        watch_channel,
        views_channel,
        ["log_date", "source", "channel_name"],
        how="outer",
    )
    channel_daily = merge_metrics(
        channel_daily,
        identity_channel[["log_date", "source", "channel_name", "total_devices", "total_sessions"]]
        if not identity_channel.empty
        else identity_channel,
        ["log_date", "source", "channel_name"],
    )

    source_daily = filter_to_ranges(source_daily, ranges).sort_values(["log_date", "source"]).reset_index(drop=True)
    channel_daily = filter_to_ranges(channel_daily, ranges).sort_values(["log_date", "source", "channel_name"]).reset_index(drop=True)
    for frame in (source_daily, channel_daily):
        frame["total_views"] = pd.to_numeric(frame["total_views"], errors="coerce").fillna(0)
    for column in ("watch_hours", "clips_watched", "ip_users"):
        channel_daily[column] = pd.to_numeric(channel_daily[column], errors="coerce").fillna(0)

    return source_daily, channel_daily, ranges, {name: str(path.resolve()) for name, path in input_files.items()}


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


def build_data(output_root: Path, title: str) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    source_daily, channel_daily, ranges, input_files = build_master_frames(output_root)
    ua_daily, ua_input_files = build_ua_daily(output_root, ranges)
    market_daily, market_input_files = build_market_daily(output_root, ranges)
    geo_source_daily, geo_channel_daily, geo_input_files = build_raw_geo_hierarchy_daily(output_root, ranges)
    input_files.update(ua_input_files)
    input_files.update(market_input_files)
    input_files.update(geo_input_files)

    created = datetime.now(IST_ZONE)
    combined_min = min(row["min_date"] for row in ranges)
    combined_max = max(row["max_date"] for row in ranges)
    channels = sorted(channel_daily["channel_name"].dropna().astype(str).unique().tolist(), key=str.casefold)
    ua_payload = compact_payload(
        ua_daily,
        ["log_date", "source", "channel_name", "dimension", "label"],
        ["raw_ts_rows"],
    )
    market_payload = compact_payload(
        market_daily,
        ["log_date", "source", "channel_name", "market_level", "label"],
        ["raw_ts_rows"],
    )
    geo_source_payload = compact_payload(
        geo_source_daily,
        ["log_date", "source", "country", "state", "city"],
        ["raw_ts_rows", "approx_unique_ips"],
    )
    geo_channel_payload = compact_payload(
        geo_channel_daily,
        ["log_date", "source", "channel_name", "country", "state", "city"],
        ["raw_ts_rows", "approx_unique_ips"],
    )
    data = {
        "meta": {
            "title": title,
            "created_at_ist": created.strftime("%d/%m/%y %I:%M:%S %p IST"),
            "data_min_date": combined_min,
            "data_max_date": combined_max,
            "latest_completed_date": (created.date() - timedelta(days=1)).isoformat(),
            "freshness": "Latest completed ETL data",
            "sources": [row["source"] for row in ranges],
            "source_ranges": ranges,
            "segment_seconds": SECONDS_PER_MEDIA_SEGMENT,
        },
        "source_daily": dataframe_records(source_daily),
        "channel_daily": dataframe_records(channel_daily),
        "ua_daily": ua_payload,
        "market_daily": market_payload,
        "geo_source_daily": geo_source_payload,
        "geo_channel_daily": geo_channel_payload,
        "channels": channels,
        "definitions": {
            "watch_hours": "All-status .ts media-segment requests multiplied by 6 seconds.",
            "ip_users": "Distinct cliIP per day. Multi-day totals are daily distinct sums and may include returning IPs more than once.",
            "device_users": "Distinct STREAM app device_id per day. FAST does not expose this identifier.",
            "session_users": "Distinct STREAM query-string session_id per day. FAST does not expose this identifier.",
            "clips_watched": "All-status .ts media-segment request count; each segment represents the 6-second watch-hour basis.",
            "total_views": "Channel-aware .m3u8 playback-manifest request count.",
            "average_watch": "Selected watch minutes divided by the matching daily distinct cliIP total.",
            "device_os": "UA-attributed .ts watch hours grouped by decoded device type and operating system. STREAM channel OS is a coarse UA-family inference.",
            "markets": "India state/region and international country watch hours from channel-aware CDN geography marts.",
            "raw_geography": "Raw CDN country, state, and city values shown as a country-to-state-to-city directory. No geographic labels or mappings are applied; blank source values display as Unknown / NA.",
        },
        "input_files": input_files,
    }
    return data, source_daily, channel_daily


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        temp_path.write_text(text, encoding=encoding)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        frame.to_parquet(temp_path, index=False, compression="zstd")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Veto unified master dashboard.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--title", default="Veto Master Dashboard")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_root = validate_output_root(args.output_root)
    out = args.out if args.out is not None else output_root / "master" / "veto_master_dashboard.html"
    out = validate_output_target(out, args.dry_run)
    data, source_daily, channel_daily = build_data(output_root, args.title)

    if args.dry_run:
        print(f"[dry-run] Source rows: {len(source_daily):,}")
        print(f"[dry-run] Channel rows: {len(channel_daily):,}")
        print(f"[dry-run] UA rows: {len(data['ua_daily']['rows']):,}")
        print(f"[dry-run] Market rows: {len(data['market_daily']['rows']):,}")
        print(f"[dry-run] Raw geography source rows: {len(data['geo_source_daily']['rows']):,}")
        print(f"[dry-run] Raw geography channel rows: {len(data['geo_channel_daily']['rows']):,}")
        print(f"[dry-run] Coverage: {data['meta']['data_min_date']} to {data['meta']['data_max_date']}")
        print(f"[dry-run] Would write: {out}")
        return

    data_dir = output_root / "master" / "data"
    ua_daily = expand_compact_payload(data["ua_daily"])
    market_daily = expand_compact_payload(data["market_daily"])
    geo_source_daily = expand_compact_payload(data["geo_source_daily"])
    geo_channel_daily = expand_compact_payload(data["geo_channel_daily"])
    for frame in (ua_daily, market_daily):
        frame["scope"] = frame["channel_name"].notna().map({True: "channel", False: "source"})
        frame["watch_hours"] = pd.to_numeric(frame["raw_ts_rows"], errors="coerce").fillna(0) * HOURS_PER_MEDIA_SEGMENT
    atomic_write_parquet(data_dir / "master_source_daily.parquet", source_daily)
    atomic_write_parquet(data_dir / "master_channel_daily.parquet", channel_daily)
    atomic_write_parquet(data_dir / "master_ua_daily.parquet", ua_daily)
    atomic_write_parquet(data_dir / "master_market_daily.parquet", market_daily)
    atomic_write_parquet(data_dir / "master_geo_source_daily.parquet", geo_source_daily)
    atomic_write_parquet(data_dir / "master_geo_channel_daily.parquet", geo_channel_daily)
    manifest = {
        "created_at_ist": data["meta"]["created_at_ist"],
        "source_ranges": data["meta"]["source_ranges"],
        "source_rows": len(source_daily),
        "channel_rows": len(channel_daily),
        "ua_rows": len(ua_daily),
        "market_rows": len(market_daily),
        "geo_source_rows": len(geo_source_daily),
        "geo_channel_rows": len(geo_channel_daily),
        "inputs": data["input_files"],
    }
    atomic_write_text(data_dir / "master_dashboard_manifest.json", json.dumps(manifest, indent=2))

    chartjs_cache = output_root / "cache" / "chartjs" / "chart.umd.min.js"
    chartjs = load_chartjs(chartjs_cache, fallback="window.Chart=null;")
    html = render_template(
        Path(__file__).resolve().parent / "template.html",
        CHARTJS_TAG=chartjs_script(chartjs),
        DATA_BLOB=json_blob(data),
    )
    atomic_write_text(out, html)
    print(f"Master dashboard written: {out}")
    print(f"Size: {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
