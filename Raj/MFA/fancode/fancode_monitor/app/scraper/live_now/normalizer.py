"""
normalizer.py – Normalization, validation, and deduplication rules for Live Now match records.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.scraper.discovery.url_normalizer import (
    extract_match_id_from_url,
    normalize as normalize_url,
)
from app.scraper.live_now.models import LiveMatchRecord
from app.scraper.schedule.normalizer import (
    STATUS_MAP,
    derive_slug,
    normalize_status,
)

logger = logging.getLogger(__name__)

# Extra status mappings specific to live stream contexts
LIVE_STATUS_MAP = dict(STATUS_MAP)
LIVE_STATUS_MAP.update({
    "live_now": "LIVE",
    "streaming": "LIVE",
    "in_play": "LIVE",
    "started": "LIVE",
    "active": "LIVE",
    "breaks": "LIVE",
    "innings_break": "LIVE",
    "half_time": "LIVE",
})

# Generic UI and status labels that must never be treated as valid match titles
GENERIC_UI_TITLES = {
    "live",
    "watch live",
    "live now",
    "watch",
    "match",
    "matches",
    "score",
    "scores",
    "live score",
    "live scores",
    "sport",
    "sports",
    "all sports",
    "live match",
    "live matches",
    "live stream",
    "live streaming",
    "stream",
    "streams",
    "upcoming",
    "featured",
    "highlights",
    "videos",
}


def clean_match_external_id(raw_id: Any) -> Optional[str]:
    """
    Clean and validate a FanCode match external ID.
    Must be a non-empty, printable identifier token. FanCode currently uses numeric
    IDs in public URLs, but API/test feeds may use opaque IDs. Treating every opaque
    ID as invalid broke cross-scraper identity resolution and created duplicates.
    """
    if raw_id is None:
        return None
    s = str(raw_id).strip()
    if not s or len(s) < 4 or len(s) > 100:
        return None
    # Numeric FanCode IDs need at least three digits. Opaque or slug IDs
    # are accepted if alphanumeric (including hyphens and underscores).
    if not (re.fullmatch(r"\d{3,}", s) or re.fullmatch(r"[A-Za-z0-9_-]+", s)):
        return None
    return s


def is_valid_match_external_id(raw_id: Any) -> bool:
    """Return True if raw_id is a valid, clean FanCode match external ID."""
    return clean_match_external_id(raw_id) is not None


def is_valid_match_title(title: Optional[str]) -> bool:
    """Check if a string is a legitimate match title and not a generic UI label."""
    if not title or not isinstance(title, str):
        return False
    cleaned = title.strip().lower()
    if not cleaned:
        return False
    if cleaned in GENERIC_UI_TITLES:
        return False
    if len(cleaned) < 3:
        return False
    return True


RACING_EVENT_KEYWORDS = re.compile(
    r"\b(?:grand prix|gp|practice|qualifying|fp[1-4]|sprint|motogp|formula 1|f1|race|round \d+|shootout|warm up|stage \d+|golf)\b",
    re.IGNORECASE,
)


def is_racing_or_event_title(title: Optional[str]) -> bool:
    """Check if candidate string represents a racing session, tournament round, or standalone event."""
    if not title or not isinstance(title, str):
        return False
    return bool(RACING_EVENT_KEYWORDS.search(title.strip()))


def is_vs_title(title: Optional[str]) -> bool:
    """Check if a candidate string has strong match vs-pattern ('Team A vs Team B')."""
    if not title or not isinstance(title, str):
        return False
    cleaned = title.strip().lower()
    return bool(re.search(r"\b(?:vs|v)\b", cleaned))


def extract_title_from_slug_or_url(url_or_slug: Optional[str]) -> Optional[str]:
    """Recover match title from a URL path or slug like 'new-south-wales-vs-tasmania'."""
    if not url_or_slug or not isinstance(url_or_slug, str):
        return None
    cleaned = url_or_slug.strip().lower()

    # Pattern A: Match slug containing "-vs-" or "-v-"
    m = re.search(r"([a-z0-9-]+-(?:vs|v)-[a-z0-9-]+)", cleaned)
    if m:
        slug_part = m.group(1)
        # Strip trailing ID if attached (e.g. "new-south-wales-vs-tasmania-4249663" -> "new-south-wales-vs-tasmania")
        slug_part = re.sub(r"-\d+$", "", slug_part)
        words = slug_part.replace("-vs-", " vs ").replace("-v-", " vs ").replace("-", " ")
        parts = [w.capitalize() for w in words.split() if w]
        candidate = " ".join(parts).replace(" Vs ", " vs ")
        if is_valid_match_title(candidate):
            return candidate

    # Pattern B: /matches/<match-slug>-<id>/ (e.g. /matches/day-1-world-feed-4249774/live-match-info)
    m = re.search(r"/matches/([a-z0-9-]+)-(\d+)(?:/|$|\?)", cleaned)
    if m:
        slug_part = m.group(1)
        words = slug_part.replace("-vs-", " vs ").replace("-v-", " vs ").replace("-", " ")
        parts = [w.capitalize() for w in words.split() if w]
        candidate = " ".join(parts).replace(" Vs ", " vs ")
        if is_valid_match_title(candidate):
            return candidate

    # Pattern C: /match/<match-slug>/<id> (e.g. /match/mumbai-indians-vs-chennai-super-kings/104921)
    m = re.search(r"/match/([a-z0-9-]+)/(\d+)(?:/|$|\?)", cleaned)
    if m:
        slug_part = m.group(1)
        words = slug_part.replace("-vs-", " vs ").replace("-v-", " vs ").replace("-", " ")
        parts = [w.capitalize() for w in words.split() if w]
        candidate = " ".join(parts).replace(" Vs ", " vs ")
        if is_valid_match_title(candidate):
            return candidate

    return None


def has_sufficient_match_identity(
    external_id: Optional[str],
    source_url: Optional[str],
    title: Optional[str],
) -> bool:
    """
    Validate that an unmatched record possesses sufficient identity information
    to safely create a new Match entity without risking duplicate/polluted records.
    Requires:
    1. Valid numeric external_id
    2. Valid non-generic source_url
    3. Valid non-generic match title
    """
    clean_id = clean_match_external_id(external_id)
    if not clean_id:
        return False
    if not title or not is_valid_match_title(title):
        return False
    if not source_url or not isinstance(source_url, str):
        return False
    clean_url = source_url.strip().lower()
    if clean_url in (
        "https://www.fancode.com",
        "https://www.fancode.com/",
        "https://www.fancode.com/live",
        "https://www.fancode.com/live-now",
        "https://www.fancode.com/live-now/all-sports",
        "https://www.fancode.com/schedule",
        "https://www.fancode.com/video",
        "/live",
        "/live-now",
        "/schedule",
    ):
        return False
    return True


def score_live_record_richness(rec: LiveMatchRecord) -> int:
    """Score a LiveMatchRecord based on how populated its fields are."""
    score = 0
    if rec.score_summary and str(rec.score_summary).strip():
        score += 10
    if rec.venue and str(rec.venue).strip():
        score += 5
    if rec.match_date:
        score += 3
    if rec.start_time:
        score += 3
    if rec.tour_name:
        score += 2
    if rec.sport_name:
        score += 2
    if rec.team_a_name and rec.team_b_name:
        score += 5
    if rec.thumbnail_url:
        score += 1
    if rec.stream_available is not None:
        score += 1
    return score


def choose_richest_live_record(records: List[LiveMatchRecord]) -> LiveMatchRecord:
    """Choose and return the richest record from a list of records for the same match."""
    if not records:
        raise ValueError("Cannot choose from empty record list")
    if len(records) == 1:
        return records[0]

    # Sort descending by richness score
    sorted_records = sorted(records, key=score_live_record_richness, reverse=True)
    canonical = sorted_records[0]

    # Non-destructively enrich canonical from other records
    for other in sorted_records[1:]:
        if not canonical.score_summary and other.score_summary:
            canonical.score_summary = other.score_summary
        if not canonical.venue and other.venue:
            canonical.venue = other.venue
        if not canonical.match_date and other.match_date:
            canonical.match_date = other.match_date
        if not canonical.start_time and other.start_time:
            canonical.start_time = other.start_time
        if not canonical.tour_name and other.tour_name:
            canonical.tour_name = other.tour_name
        if not canonical.sport_name and other.sport_name:
            canonical.sport_name = other.sport_name
        if not canonical.team_a_name and other.team_a_name:
            canonical.team_a_name = other.team_a_name
        if not canonical.team_b_name and other.team_b_name:
            canonical.team_b_name = other.team_b_name
        if not canonical.team_a_logo and other.team_a_logo:
            canonical.team_a_logo = other.team_a_logo
        if not canonical.team_b_logo and other.team_b_logo:
            canonical.team_b_logo = other.team_b_logo
        if not canonical.thumbnail_url and other.thumbnail_url:
            canonical.thumbnail_url = other.thumbnail_url
        if canonical.stream_available is None and other.stream_available is not None:
            canonical.stream_available = other.stream_available

    return canonical


class LiveNowNormalizer:
    """Normalizes live attributes and deduplicates live match records."""

    @staticmethod
    def normalize_live_status(raw_status: Optional[str]) -> str:
        """Standardize status string to canonical status enum."""
        if not raw_status or not isinstance(raw_status, str):
            return "LIVE"  # Default assumption if on Live Now section without status

        cleaned = raw_status.strip().lower().replace("-", "_").replace(" ", "_")
        return LIVE_STATUS_MAP.get(cleaned, normalize_status(raw_status))

    @staticmethod
    def derive_match_identity(
        external_id: Optional[str],
        source_url: str,
        title: Optional[str] = None,
    ) -> str:
        """
        Determines deterministic, unique identity key for a live match.
        Priority:
        1. Stable FanCode external match/event ID (cleaned digits)
        2. Normalized source URL
        3. Deterministic slug derived from title
        """
        clean_ext = clean_match_external_id(external_id)
        if clean_ext:
            return f"ext:{clean_ext}"

        norm = normalize_url(source_url)
        if norm:
            return f"url:{norm}"

        if title and str(title).strip():
            slug = derive_slug(title)
            return f"slug:{slug}"

        return f"url:{source_url}"

    @classmethod
    def filter_valid_records(cls, records: List[LiveMatchRecord]) -> List[LiveMatchRecord]:
        """
        Filter out invalid records that represent generic UI labels or landing pages.
        A valid live match must have a genuine match title and evidence of being a match.
        """
        valid: List[LiveMatchRecord] = []
        for rec in records:
            if not rec or not isinstance(rec, LiveMatchRecord):
                continue

            # Must have a valid, non-generic title
            if not is_valid_match_title(rec.title):
                logger.debug(
                    "Filtered out live record with invalid/generic title: %r (url=%r)",
                    rec.title,
                    rec.source_url,
                )
                continue

            # If URL is purely a landing page without an external match ID, reject it
            norm_url = normalize_url(rec.source_url) if rec.source_url else ""
            clean_ext = clean_match_external_id(rec.match_external_id)
            if norm_url in (
                "https://www.fancode.com",
                "https://www.fancode.com/live",
                "https://www.fancode.com/live-now",
                "https://www.fancode.com/live-now/all-sports",
                "https://www.fancode.com/schedule",
                "https://www.fancode.com/video",
            ) and not clean_ext and not (rec.team_a_name and rec.team_b_name):
                logger.debug("Filtered out live record pointing to landing page: %r", rec.source_url)
                continue

            valid.append(rec)
        return valid

    @classmethod
    def deduplicate_records(cls, records: List[LiveMatchRecord]) -> List[LiveMatchRecord]:
        """
        Deduplicates records keeping the record with richer information
        (e.g. score present, more fields populated).
        """
        valid_records = cls.filter_valid_records(records)
        grouped: Dict[str, List[LiveMatchRecord]] = {}

        for rec in valid_records:
            key = cls.derive_match_identity(
                rec.match_external_id,
                rec.source_url,
                rec.title,
            )
            grouped.setdefault(key, []).append(rec)

        deduped = [choose_richest_live_record(group_recs) for group_recs in grouped.values()]
        return deduped
