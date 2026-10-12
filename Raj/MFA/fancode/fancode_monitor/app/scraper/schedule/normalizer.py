"""
normalizer.py – Normalizes dates, times, statuses, teams, and URLs for FanCode matches.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

from app.scraper.discovery.url_normalizer import normalize as normalize_url

logger = logging.getLogger(__name__)

# Known FanCode / generic status mapping
STATUS_MAP = {
    "live": "LIVE",
    "ongoing": "LIVE",
    "in_progress": "LIVE",
    "upcoming": "UPCOMING",
    "scheduled": "SCHEDULED",
    "fixture": "SCHEDULED",
    "completed": "COMPLETED",
    "finished": "COMPLETED",
    "result": "COMPLETED",
    "ended": "COMPLETED",
    "match_ended": "COMPLETED",
    "concluded": "COMPLETED",
    "final": "COMPLETED",
    "ft": "COMPLETED",
    "full_time": "COMPLETED",
    "stumps": "COMPLETED",
    "cancelled": "CANCELLED",
    "canceled": "CANCELLED",
    "postponed": "POSTPONED",
    "delayed": "POSTPONED",
    "abandoned": "CANCELLED",
}


def normalize_status(raw_status: Optional[str]) -> str:
    """Normalize match status to consistent uppercase enum. Returns 'UNKNOWN' if unrecognizable."""
    if not raw_status or not isinstance(raw_status, str):
        return "UNKNOWN"
    cleaned = raw_status.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in STATUS_MAP:
        return STATUS_MAP[cleaned]
    # Check for substring indicators of completed matches (e.g. "Thailand won by 8 wkts")
    lower_raw = raw_status.strip().lower()
    if any(term in lower_raw for term in ("won by", "beat", "result", "ended", "completed", "match drawn", "tied")):
        return "COMPLETED"
    if any(term in lower_raw for term in ("live now", "in progress", "streaming live")):
        return "LIVE"
    return "UNKNOWN"


def normalize_datetime(raw_val: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Attempt to parse a date/time representation into (datetime in UTC, start_time_str).
    Accepts ISO strings, unix epoch timestamps (seconds or milliseconds), or date strings.
    """
    if raw_val is None:
        return None, None

    # Timestamp integer/float
    if isinstance(raw_val, (int, float)):
        try:
            # Handle milliseconds
            ts = raw_val / 1000.0 if raw_val > 1e11 else float(raw_val)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt, dt.strftime("%H:%M")
        except Exception:
            return None, None

    if isinstance(raw_val, str):
        raw_val = raw_val.strip()
        if not raw_val:
            return None, None

        # ISO 8601 strings and common date formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y %H.%M",
            "%d-%b-%Y",
            "%d %b %Y %H:%M",
            "%d %b %Y %H.%M",
            "%d %b %Y",
            "%Y-%m-%d %H.%M",
        ):
            try:
                dt = datetime.strptime(raw_val.replace("Z", "+0000"), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt, dt.strftime("%H:%M")
            except Exception:
                continue

        # Try fromisoformat (Python 3.11+)
        try:
            dt = datetime.fromisoformat(raw_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt, dt.strftime("%H:%M")
        except Exception:
            pass

    return None, None


def derive_slug(title: str, fallback_id: Optional[str] = None) -> str:
    """Generate a clean URL slug from title and/or fallback_id."""
    clean = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", clean).strip("-")
    if not slug and fallback_id:
        slug = f"match-{fallback_id}"
    return slug or "unnamed-match"


def derive_stable_identity(
    external_id: Optional[str],
    source_url: Optional[str],
    title: str,
    date_str: Optional[str] = None,
) -> str:
    """
    Establish deterministic match identity. Priority:
    1. external_id
    2. normalized source_url
    3. slug + date_str
    """
    if external_id and str(external_id).strip():
        return str(external_id).strip()

    if source_url:
        norm = normalize_url(source_url)
        if norm:
            return norm

    slug = derive_slug(title)
    if date_str:
        return f"{slug}-{date_str}"
    return slug
