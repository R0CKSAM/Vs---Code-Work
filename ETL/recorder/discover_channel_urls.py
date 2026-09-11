#!/usr/bin/env python3
"""Discover and validate live HLS playlists from recent CDN lake partitions."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import ssl
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import duckdb


ETL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAKE = ETL_ROOT / "data" / "lake"
DEFAULT_CHANNELS = Path(__file__).resolve().parent / "channels.json"
SKIP_SEGMENTS = {"", "v1", "live", "stream", "hls", "nntv", "out"}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"


@dataclass(frozen=True)
class Candidate:
    channel_name: str
    req_host: str
    req_path: str
    requests: int
    latest_timestamp: float

    @property
    def url(self) -> str:
        host = self.req_host.strip().removesuffix(":443")
        path = quote(self.req_path.strip().lstrip("/"), safe="/%._~-:@!$&'()*+,;=")
        return f"https://{host}/{path}"

    @property
    def rank(self) -> tuple[int, int, float]:
        name = self.req_path.casefold().split("?", 1)[0].rsplit("/", 1)[-1]
        if name == "master.m3u8" or "master" in name:
            kind = 5
        elif name == "playlist.m3u8" or "playlist" in name:
            kind = 4
        elif re.fullmatch(r"main(?:_\d+)?\.m3u8", name):
            kind = 3
        elif name in {"index.m3u8", "live.m3u8"}:
            kind = 2
        else:
            kind = 1
        return kind, self.requests, self.latest_timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--channels", type=Path, default=DEFAULT_CHANNELS)
    parser.add_argument("--recent-partitions", type=int, default=4)
    parser.add_argument("--candidates-per-channel", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parent / "channel_discovery_report.json")
    return parser.parse_args()


def recent_parquet_files(lake: Path, count: int) -> list[Path]:
    files = list(lake.glob("source=*/year=*/month=*/day=*/*.parquet"))
    if not files:
        raise FileNotFoundError(f"No lake Parquet files found under {lake}")

    def partition_key(path: Path) -> tuple[int, int, int]:
        values: dict[str, int] = {}
        for part in path.parts:
            if "=" in part:
                key, value = part.split("=", 1)
                if key in {"year", "month", "day"} and value.isdigit():
                    values[key] = int(value)
        return values.get("year", 0), values.get("month", 0), values.get("day", 0)

    dates = sorted({partition_key(path) for path in files}, reverse=True)[: max(1, count)]
    selected_dates = set(dates)
    return sorted(path for path in files if partition_key(path) in selected_dates)


def channel_candidate(req_path: str) -> str:
    path = str(req_path or "").strip().lstrip("/")
    match = re.search(r"(?i)(vglive-sk-\d+)", path)
    if match:
        return match.group(1).casefold()
    segments = [segment.casefold() for segment in path.split("/") if segment]
    for segment in segments:
        if segment not in SKIP_SEGMENTS:
            return segment
    return ""


def load_resolver():
    import sys

    workspace = ETL_ROOT.parent
    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
    from ETL.src.profile.vglive_core import resolve_channel

    return resolve_channel


def query_candidates(files: list[Path]) -> list[Candidate]:
    connection = duckdb.connect()
    paths = [str(path) for path in files]
    columns = {
        row[0]
        for row in connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true)", [paths]
        ).fetchall()
    }
    required = {"reqHost", "reqPath", "statusCode"}
    missing = required - columns
    if missing:
        raise ValueError(f"Lake files are missing columns: {', '.join(sorted(missing))}")
    timestamp_expr = (
        "MAX(TRY_CAST(reqTimeSec AS DOUBLE))" if "reqTimeSec" in columns else "0::DOUBLE"
    )
    rows = connection.execute(
        f"""
        SELECT
            CAST(reqHost AS VARCHAR) AS req_host,
            CAST(reqPath AS VARCHAR) AS req_path,
            COUNT(*)::BIGINT AS requests,
            {timestamp_expr} AS latest_timestamp
        FROM read_parquet(?, union_by_name=true)
        WHERE TRY_CAST(statusCode AS INTEGER) BETWEEN 200 AND 299
          AND regexp_matches(lower(COALESCE(CAST(reqPath AS VARCHAR), '')), '\\.m3u8(?:$|\\?)')
          AND COALESCE(CAST(reqHost AS VARCHAR), '') <> ''
        GROUP BY 1, 2
        """,
        [paths],
    ).fetchall()
    resolve_channel = load_resolver()
    result = []
    for host, path, requests, latest in rows:
        channel_name = resolve_channel(host, channel_candidate(path))
        if channel_name not in {"Other", "Unknown", ""}:
            result.append(
                Candidate(channel_name, host, path, int(requests), float(latest or 0))
            )
    return result


def validate(candidate: Candidate, timeout: float) -> dict[str, Any]:
    request = Request(
        candidate.url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.apple.mpegurl,*/*"},
    )
    try:
        context = ssl.create_default_context()
        with urlopen(request, timeout=timeout, context=context) as response:
            body = response.read(32_768)
            status = int(getattr(response, "status", 200))
        text = body.decode("utf-8", errors="replace").lstrip("\ufeff\r\n ")
        valid = status < 400 and text.startswith("#EXTM3U")
        return {
            "channel_name": candidate.channel_name,
            "candidate_url": candidate.url,
            # Keep the stable CDN request URL. Redirect targets may contain
            # short-lived credentials and must never enter the registry.
            "url": candidate.url,
            "valid": valid,
            "http_status": status,
            "requests": candidate.requests,
            "playlist_type": "master" if "#EXT-X-STREAM-INF" in text else "media",
            "error": "" if valid else "Response is not an HLS manifest",
        }
    except HTTPError as exc:
        return {"channel_name": candidate.channel_name, "candidate_url": candidate.url, "url": candidate.url, "valid": False, "http_status": exc.code, "requests": candidate.requests, "playlist_type": "", "error": str(exc)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"channel_name": candidate.channel_name, "candidate_url": candidate.url, "url": candidate.url, "valid": False, "http_status": 0, "requests": candidate.requests, "playlist_type": "", "error": str(exc)}


def discover(args: argparse.Namespace) -> dict[str, Any]:
    files = recent_parquet_files(args.lake, args.recent_partitions)
    candidates = query_candidates(files)
    grouped: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.channel_name].append(candidate)
    shortlisted = []
    for values in grouped.values():
        shortlisted.extend(
            sorted(values, key=lambda item: item.rank, reverse=True)[: args.candidates_per_channel]
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        validations = list(pool.map(lambda item: validate(item, args.timeout), shortlisted))
    verified: dict[str, dict[str, Any]] = {}
    for item in validations:
        if not item["valid"]:
            continue
        previous = verified.get(item["channel_name"])
        if previous is None or (item["playlist_type"] == "master", item["requests"]) > (
            previous["playlist_type"] == "master", previous["requests"]
        ):
            verified[item["channel_name"]] = item
    return {
        "lake_files": [str(path) for path in files],
        "mapped_channels_seen": len(grouped),
        "candidate_urls_tested": len(shortlisted),
        "verified_channels": list(sorted(verified.values(), key=lambda row: row["channel_name"])),
        "failed_candidates": [item for item in validations if not item["valid"]],
    }


def update_registry(path: Path, report: dict[str, Any], overwrite: bool) -> int:
    registry = json.loads(path.read_text(encoding="utf-8"))
    verified = {item["channel_name"].casefold(): item for item in report["verified_channels"]}
    updates = 0
    for channel in registry:
        match = verified.get(str(channel.get("name", "")).casefold())
        if not match or (channel.get("hls_url") and not overwrite):
            continue
        channel["hls_url"] = match["url"]
        channel["enabled"] = True
        channel["discovered_from_lake"] = True
        updates += 1
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return updates


def main() -> None:
    args = parse_args()
    report = discover(args)
    report["registry_updates"] = update_registry(args.channels, report, args.overwrite) if args.write else 0
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "mapped_channels_seen": report["mapped_channels_seen"],
        "candidate_urls_tested": report["candidate_urls_tested"],
        "verified_channels": len(report["verified_channels"]),
        "registry_updates": report["registry_updates"],
        "report": str(args.report),
    }, indent=2))


if __name__ == "__main__":
    main()
