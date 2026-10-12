"""
page_classifier.py – Classifies FanCode pages by type.

Classification is based on OBSERVED URL patterns from the live FanCode
website.  Each pattern is documented with the source of evidence.

Classification order matters: more specific patterns are checked first.
The classifier is deterministic and stateless — same input always gives
same output.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from app.scraper.discovery.models import PageType


# ──────────────────────────────────────────────────────────────────────────────
# Pattern registry
#
# Each entry: (PageType, compiled regex applied to the URL PATH)
# Patterns are tried in order; first match wins.
# All patterns are derived from OBSERVED FanCode URL structure.
# ──────────────────────────────────────────────────────────────────────────────

_PATH_PATTERNS: list[tuple[PageType, re.Pattern]] = [
    # HOME – root path only
    (PageType.HOME,     re.compile(r"^/?$")),

    # LIVE – /live or /live-now
    (PageType.LIVE,     re.compile(r"^/live", re.IGNORECASE)),

    # SCHEDULE – /schedule
    (PageType.SCHEDULE, re.compile(r"^/schedule", re.IGNORECASE)),

    # VIDEO / HIGHLIGHTS
    (PageType.VIDEO,    re.compile(r"^/videos?|^/highlights?|^/watch", re.IGNORECASE)),

    # MATCH – /matches/ or /match/ or /match/...
    (PageType.MATCH,    re.compile(r"^/(matches|match)(/|$)", re.IGNORECASE)),

    # SERIES / TOUR – /series/ or /tour/
    (PageType.SERIES,   re.compile(r"^/series/", re.IGNORECASE)),
    (PageType.TOUR,     re.compile(r"^/tours?/", re.IGNORECASE)),

    # TEAM – /teams/
    (PageType.TEAM,     re.compile(r"^/teams?/", re.IGNORECASE)),

    # PLAYER – /players/
    (PageType.PLAYER,   re.compile(r"^/players?/", re.IGNORECASE)),

    # SPORT – /sports/ or /cricket, /football etc.
    (PageType.SPORT,    re.compile(
        r"^/sports?(/|$)|"
        r"^/(cricket|football|kabaddi|basketball|badminton|hockey|tennis|racing)(/|$)",
        re.IGNORECASE
    )),
]


def classify_url(url: str) -> PageType:
    """
    Classify a FanCode URL into a PageType.

    Parameters
    ----------
    url : str
        A normalized FanCode URL.

    Returns
    -------
    PageType
        The best matching classification, or UNKNOWN if no pattern matches.
    """
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return PageType.UNKNOWN

    for page_type, pattern in _PATH_PATTERNS:
        if pattern.match(path):
            return page_type

    return PageType.UNKNOWN


def classify_page(url: str, title: str = "") -> PageType:
    """
    Classify using both URL and page title for better accuracy.

    Title-based classification only overrides UNKNOWN results from
    URL classification — URL patterns are the primary signal.
    """
    by_url = classify_url(url)
    if by_url != PageType.UNKNOWN:
        return by_url

    # Fallback: title-based classification
    title_lower = title.lower()
    if "schedule" in title_lower:
        return PageType.SCHEDULE
    if "live" in title_lower:
        return PageType.LIVE
    if any(w in title_lower for w in ("match", "vs", " v ")):
        return PageType.MATCH
    if any(w in title_lower for w in ("series", "tour", "tournament", "cup", "championship")):
        return PageType.SERIES
    if any(w in title_lower for w in ("cricket", "football", "kabaddi", "sport")):
        return PageType.SPORT
    if any(w in title_lower for w in ("video", "highlight", "watch")):
        return PageType.VIDEO

    return PageType.UNKNOWN
