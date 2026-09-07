from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote
from zoneinfo import ZoneInfo

from ..profile.vglive_core import SKIP_PATH_SEGMENTS, resolve_channel


IST = ZoneInfo("Asia/Kolkata")
GLOBAL_TARGET = "__all__"
CHANNEL_MAPPING_VERSION = 4


@dataclass
class FileBatch:
    rows: int = 0
    rejected_rows: int = 0
    latest_timestamp: float | None = None
    metrics: dict[tuple[str, str, str], list[int]] = field(
        default_factory=lambda: defaultdict(lambda: [0, 0, 0, 0, 0])
    )
    minute_viewers: set[tuple[str, str, str, str]] = field(default_factory=set)
    minute_devices: set[tuple[str, str, str, str]] = field(default_factory=set)
    minute_sessions: set[tuple[str, str, str, str]] = field(default_factory=set)
    daily_viewers: set[tuple[str, str, str, str]] = field(default_factory=set)
    dimensions: dict[tuple[str, str, str, str, str], list[int]] = field(
        default_factory=lambda: defaultdict(lambda: [0, 0])
    )


def request_timestamp(value: object) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1000.0
    try:
        dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return timestamp


def integer_value(value: object) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def query_metadata(value: object) -> dict[str, str]:
    """Decode a CDN query string once and return non-empty, normalized keys."""
    raw = str(value or "").strip()
    if not raw or raw in {"-", "null"}:
        return {}
    if "=" not in raw and "%3d" in raw.casefold():
        raw = unquote(raw)
    return {
        key.casefold(): values[0].strip()
        for key, values in parse_qs(raw.lstrip("?"), keep_blank_values=False).items()
        if values and values[0].strip()
    }


def query_identifiers(value: object) -> tuple[str, str]:
    """Return device/session IDs exactly as supplied in a CDN query string."""
    parsed = query_metadata(value)

    def valid(name: str) -> str:
        result = parsed.get(name, "")
        return "" if result.casefold() in {"-", "null", "none", "unknown"} else result

    return valid("device_id") or valid("deviceid"), valid("session_id") or valid("sessionid")


def identifier_key(value: str, namespace: str) -> str:
    if not value:
        return ""
    return hashlib.blake2b(
        f"{namespace}:{value}".encode("utf-8"), digest_size=16
    ).hexdigest()


def dimension_value(value: object, fallback: str = "Unknown") -> str:
    text = unquote(str(value or "")).strip()
    return fallback if not text or text.casefold() in {"-", "null", "none", "unknown"} else text[:120]


def inferred_client(user_agent: object) -> tuple[str, str]:
    """Return conservative platform/device groups without an external API."""
    ua = unquote(str(user_agent or "")).casefold()
    if not ua or ua == "-":
        return "Unknown", "Unknown"
    rules = (
        (("tizen", "smart-tv", "smarttv"), "Smart TV", "Samsung/Tizen TV"),
        (("webos",), "Smart TV", "LG/webOS TV"),
        (("aft", "fire tv"), "Connected TV", "Amazon Fire TV"),
        (("android tv", "googletv"), "Connected TV", "Android TV"),
        (("roku",), "Connected TV", "Roku"),
        (("ipad",), "iOS", "iPad"),
        (("iphone",), "iOS", "iPhone"),
        (("android",), "Android", "Android device"),
        (("windows",), "Windows", "Windows computer"),
        (("macintosh", "mac os"), "macOS", "Mac"),
        (("linux",), "Linux", "Linux computer"),
    )
    for needles, platform, device in rules:
        if any(needle in ua for needle in needles):
            return platform, device
    return "Other / inferred", "Other / inferred"


def request_dimensions(row: dict, request_path: str, query: dict[str, str]) -> dict[str, str]:
    status = integer_value(row.get("statusCode"))
    status_class = f"{status // 100}xx" if 100 <= status < 600 else "Unknown"
    cache_raw = dimension_value(row.get("cacheStatus"))
    cache = {"1": "Hit", "0": "Miss"}.get(cache_raw, cache_raw)
    inferred_platform, inferred_device = inferred_client(row.get("UA"))
    platform = dimension_value(query.get("platform"), inferred_platform)
    device = dimension_value(query.get("device"), inferred_device)
    resolution_match = re.search(r"(?<!\d)(2160|1440|1080|720|576|540|480|360|240)p?(?!\d)", request_path.casefold())
    resolution = f"{resolution_match.group(1)}p" if resolution_match else "Unknown"
    return {
        "status": status_class,
        "cache": cache,
        "country": dimension_value(row.get("country")),
        "state": dimension_value(row.get("state")),
        "city": dimension_value(row.get("city")),
        "asn": dimension_value(row.get("asn")),
        "platform_inferred": platform,
        "device_inferred": device,
        "resolution_inferred": resolution,
        "delivery_format": dimension_value(row.get("deliveryFormat")),
        "host": dimension_value(row.get("reqHost")),
    }


def channel_candidate(path: str) -> str:
    """Mirror the ETL channel candidate extraction for one request path."""
    value = path.casefold().split("?", 1)[0]
    vglive = re.search(r"vglive-sk-[0-9]+", value)
    if vglive:
        return vglive.group(0)
    if "/" in value:
        parts = value.lstrip("/").split("/")
        first = parts[0] if parts else ""
        return parts[1] if first in SKIP_PATH_SEGMENTS and len(parts) > 1 else first
    candidate = re.sub(r"\.ts$", "", value.rsplit("/", 1)[-1])
    return re.sub(r"[_-]?(1080p?|720p?|480p?|360p?|[0-9]+)$", "", candidate)


def matching_targets(host: str, path: str) -> tuple[str, str]:
    return GLOBAL_TARGET, resolve_channel(host, channel_candidate(path))


def parse_gzip_file(path: Path, watched_paths: tuple[str, ...]) -> FileBatch:
    """Parse one immutable GZIP NDJSON object into transaction-ready aggregates."""
    batch = FileBatch()
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                batch.rejected_rows += 1
                continue
            timestamp = request_timestamp(row.get("reqTimeSec"))
            if timestamp is None:
                batch.rejected_rows += 1
                continue
            event_time = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(IST)
            minute = event_time.strftime("%Y-%m-%dT%H:%M:00%z")
            day = event_time.strftime("%Y-%m-%d")
            host = str(row.get("reqHost") or "Unknown / NA").strip() or "Unknown / NA"
            request_path = unquote(str(row.get("reqPath") or row.get("reqUrl") or ""))
            cli_ip = str(row.get("cliIP") or "").strip()
            viewer_key = (
                hashlib.blake2b(cli_ip.encode("utf-8"), digest_size=16).hexdigest()
                if cli_ip and cli_ip != "-"
                else ""
            )
            query = query_metadata(row.get("queryStr"))
            device_id = query.get("device_id") or query.get("deviceid") or ""
            session_id = query.get("session_id") or query.get("sessionid") or ""
            if device_id.casefold() in {"-", "null", "none", "unknown"}:
                device_id = ""
            if session_id.casefold() in {"-", "null", "none", "unknown"}:
                session_id = ""
            device_key = identifier_key(device_id, "device")
            session_key = identifier_key(session_id, "session")
            status = integer_value(row.get("statusCode"))
            byte_count = integer_value(
                row.get("bytes", row.get("bytesSent", row.get("respBytes", 0)))
            )
            lower_path = request_path.casefold().split("?", 1)[0]
            is_segment = int(lower_path.endswith((".ts", ".m4s", ".mp4")))
            dimensions = request_dimensions(row, request_path, query)
            for target in matching_targets(host, request_path):
                values = batch.metrics[(minute, host, target)]
                values[0] += 1
                values[1] += byte_count
                values[2] += int(400 <= status < 500)
                values[3] += int(500 <= status < 600)
                values[4] += is_segment
                if viewer_key:
                    batch.minute_viewers.add((minute, host, target, viewer_key))
                    batch.daily_viewers.add((day, host, target, viewer_key))
                if device_key:
                    batch.minute_devices.add((minute, host, target, device_key))
                if session_key:
                    batch.minute_sessions.add((minute, host, target, session_key))
                for dimension, value in dimensions.items():
                    dimension_totals = batch.dimensions[
                        (minute, host, target, dimension, value)
                    ]
                    dimension_totals[0] += 1
                    dimension_totals[1] += byte_count
            batch.rows += 1
            batch.latest_timestamp = max(batch.latest_timestamp or timestamp, timestamp)
    return batch
