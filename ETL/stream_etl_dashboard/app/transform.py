from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote


IST = timezone(timedelta(hours=5, minutes=30))


def path_matches(request_path: str, stream: str) -> bool:
    clean = unquote(request_path or "").split("?", 1)[0].strip("/")
    return stream in clean.split("/")


def parse_file(
    path: Path,
    streams: tuple[str, ...],
    target_date: str,
    stream_aliases: dict[str, str] | None = None,
):
    aggregates: Counter[tuple[str, str, str, str]] = Counter()
    errors_4xx: Counter[tuple[str, str, str, str]] = Counter()
    errors_5xx: Counter[tuple[str, str, str, str]] = Counter()
    records = skipped = 0
    latest_event = None

    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
                epoch = float(event["reqTimeSec"])
                timestamp = datetime.fromtimestamp(epoch, tz=IST)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
                skipped += 1
                continue
            if timestamp.date().isoformat() != target_date:
                continue

            request_path = event.get("reqPath") or event.get("reqUrl") or ""
            ip = str(event.get("cliIP") or "").strip()
            if not ip or ip == "-":
                continue
            aliases = stream_aliases or {}
            matched = [
                stream for stream in streams
                if path_matches(request_path, aliases.get(stream, stream))
            ]
            if not matched:
                continue

            state = unquote(str(event.get("state") or "Unknown")).strip() or "Unknown"
            minute = timestamp.replace(second=0, microsecond=0).isoformat()
            try:
                status = int(event.get("statusCode") or 0)
            except (TypeError, ValueError):
                status = 0

            for stream in matched:
                key = (minute, stream, ip, state)
                aggregates[key] += 1
                if 400 <= status < 500:
                    errors_4xx[key] += 1
                elif status >= 500:
                    errors_5xx[key] += 1
            records += 1
            if latest_event is None or timestamp > latest_event:
                latest_event = timestamp

    return aggregates, errors_4xx, errors_5xx, records, skipped, latest_event
