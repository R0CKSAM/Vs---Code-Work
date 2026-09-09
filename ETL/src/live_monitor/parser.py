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
from .enrichment import decoded_asn_dimensions, decoded_ua_dimensions


IST = ZoneInfo("Asia/Kolkata")
GLOBAL_TARGET = "__all__"
CHANNEL_MAPPING_VERSION = 4


@dataclass
class FileBatch:
    rows: int = 0
    rejected_rows: int = 0
    latest_timestamp: float | None = None
    metrics: dict[tuple[str, str, str], list[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0] * 16)
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


def nonnegative_number(value: object) -> float | None:
    """Parse an optional non-negative CDN measurement without inventing zeroes."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if 0 <= result < 1_000_000_000 else None


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


def inferred_resolution(request_path: str) -> str:
    """Return a resolution only when the URL exposes a credible frame height."""
    lowered = str(request_path or "").casefold()
    explicit = re.search(r"(?<!\d)(\d{3,4})p(?:\d{2,3})?(?![a-z0-9])", lowered)
    dimensions = re.search(r"(?<!\d)\d{2,4}x(\d{3,4})(?!\d)", lowered)
    legacy = re.search(
        r"(?<!\d)(2160|1440|1080|720|576|540|480|432|360|288|240|216)(?!\d)",
        lowered,
    )
    match = explicit or dimensions or legacy
    if not match:
        return "Unknown"
    height = int(match.group(1))
    return f"{height}p" if 144 <= height <= 4320 else "Unknown"


def request_dimensions(row: dict, request_path: str, query: dict[str, str]) -> dict[str, str]:
    status = integer_value(row.get("statusCode"))
    status_class = f"{status // 100}xx" if 100 <= status < 600 else "Unknown"
    cache_raw = dimension_value(row.get("cacheStatus"))
    cache = {
        "0": "Non-cacheable",
        "1": "Cache hit - child edge",
        "2": "Cache hit - peer/parent edge",
        "3": "Origin",
        "4": "Cached error response",
    }.get(cache_raw, cache_raw)
    delivery_type_raw = dimension_value(row.get("deliveryType"))
    delivery_type = {
        "0": "Default",
        "1": "Adaptive media - live",
        "2": "Adaptive media - VOD",
        "3": "Download delivery",
    }.get(delivery_type_raw, delivery_type_raw)
    delivery_format_raw = dimension_value(row.get("deliveryFormat"))
    delivery_format = {
        "0": "Default",
        "1": "Apple / HLS",
        "2": "ZERI",
        "3": "Silverlight",
        "4": "DASH",
    }.get(delivery_format_raw, delivery_format_raw)
    media_encryption_raw = dimension_value(row.get("mediaEncryption"))
    media_encryption = {
        "0": "Disabled",
        "1": "Enabled",
    }.get(media_encryption_raw, media_encryption_raw)
    inferred_platform, inferred_device = inferred_client(row.get("UA"))
    platform = dimension_value(query.get("platform"), inferred_platform)
    device = dimension_value(query.get("device"), inferred_device)
    resolution = inferred_resolution(request_path)
    dimensions = {
        "status": status_class,
        "cache": cache,
        "country": dimension_value(row.get("country")),
        "state": dimension_value(row.get("state")),
        "city": dimension_value(row.get("city")),
        "asn": dimension_value(row.get("asn")),
        "platform_inferred": platform,
        "device_inferred": device,
        "resolution_inferred": resolution,
        "host": dimension_value(row.get("reqHost")),
        "tls_version": dimension_value(row.get("tlsVersion")),
        "protocol": dimension_value(row.get("proto")),
        "request_method": dimension_value(row.get("reqMethod")),
        "content_type": dimension_value(row.get("rspContentType")),
        "cacheable": {"1": "Cacheable", "0": "Not cacheable"}.get(
            str(row.get("cacheable") or "").strip(), "Unknown"
        ),
        "server_country": dimension_value(row.get("serverCountry")),
        "billing_region": dimension_value(row.get("billingRegion")),
        "delivery_type": delivery_type,
        "delivery_policy_status": dimension_value(row.get("deliveryPolicyReqStatus")),
        "delivery_format": delivery_format,
        "cp_code": dimension_value(row.get("cp")),
        "file_size_bucket": dimension_value(row.get("fileSizeBucket")),
        "media_encryption": media_encryption,
        "akamai_error": dimension_value(row.get("errorCode"), "No Akamai error"),
    }
    dimensions.update(decoded_ua_dimensions(row.get("UA")))
    dimensions.update(decoded_asn_dimensions(row.get("asn")))
    return dimensions


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
            ttfb_ms = nonnegative_number(row.get("timeToFirstByte"))
            turnaround_ms = nonnegative_number(row.get("turnAroundTimeMSec"))
            transfer_ms = nonnegative_number(row.get("transferTimeMSec"))
            throughput = nonnegative_number(row.get("throughput"))
            tls_overhead_ms = nonnegative_number(row.get("tlsOverheadTimeMSec"))
            delivery_policy_status = integer_value(row.get("deliveryPolicyReqStatus"))
            edge_attempts = integer_value(row.get("edgeAttempts"))
            dimensions = request_dimensions(row, request_path, query)
            for target in matching_targets(host, request_path):
                values = batch.metrics[(minute, host, target)]
                values[0] += 1
                values[1] += byte_count
                values[2] += int(400 <= status < 500)
                values[3] += int(500 <= status < 600)
                values[4] += is_segment
                for count_index, total_index, measurement in (
                    (5, 6, ttfb_ms),
                    (7, 8, turnaround_ms),
                    (9, 10, transfer_ms),
                    (11, 12, throughput),
                    (13, 14, tls_overhead_ms),
                ):
                    if measurement is not None:
                        values[count_index] += 1
                        values[total_index] += measurement
                values[15] += int(delivery_policy_status != 0 or edge_attempts > 1)
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
