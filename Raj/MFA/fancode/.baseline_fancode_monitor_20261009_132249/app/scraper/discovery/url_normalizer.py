"""
url_normalizer.py – URL normalization and validation utilities.

Rules applied (in order):
1.  Parse the raw URL.
2.  Force scheme to https (FanCode is HTTPS-only).
3.  Lowercase the netloc.
4.  Remove known tracking/non-content query parameters.
5.  Strip URL fragment (#section).
6.  Remove trailing slash from path (unless path is root "/").
7.  Re-assemble and return canonical string.

Only parameters confirmed as pure tracking params are removed.
Content-bearing query params (e.g. ?tab=cricket) are preserved.
"""

from __future__ import annotations

import re
from typing import Optional, Set
from urllib.parse import (
    ParseResult,
    parse_qs,
    urlencode,
    urlparse,
    urlunparse,
)

# ──────────────────────────────────────────────────────────────────────────────
# Known tracking / session parameters to strip (OBSERVED, not assumed)
# These appear in FanCode and common analytics tooling.
# DO NOT add parameters unless they are confirmed non-content.
# ──────────────────────────────────────────────────────────────────────────────
TRACKING_PARAMS: Set[str] = {
    # UTM / marketing
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id",
    # Generic analytics / tracking
    "ref", "referrer", "source", "fbclid", "gclid", "msclkid",
    "_ga", "_gl",
}

FANCODE_DOMAIN = "fancode.com"
FANCODE_NETLOCS = {
    "fancode.com",
    "www.fancode.com",
}


def normalize(raw_url: str, base_url: str = "https://www.fancode.com") -> Optional[str]:
    """
    Normalize *raw_url* relative to *base_url*.

    Returns the normalized absolute URL string, or None if the URL
    is invalid, empty, or belongs to a different domain.

    Parameters
    ----------
    raw_url : str
        The href value extracted from the page (may be relative).
    base_url : str
        The page's URL, used to resolve relative hrefs.
    """
    raw_url = (raw_url or "").strip()
    if not raw_url or raw_url.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None

    # Resolve relative URLs against base
    from urllib.parse import urljoin
    absolute = urljoin(base_url, raw_url)

    parsed = urlparse(absolute)

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return None

    # Must belong to FanCode domain
    netloc = parsed.netloc.lower().split(":")[0]  # strip port if any
    if netloc != FANCODE_DOMAIN and not netloc.endswith("." + FANCODE_DOMAIN):
        return None


    # Strip tracking query parameters
    qs = parse_qs(parsed.query, keep_blank_values=False)
    clean_qs = {k: v for k, v in qs.items() if k.lower() not in TRACKING_PARAMS}

    # Rebuild query string (sorted for deterministic output)
    new_query = urlencode(sorted(clean_qs.items()), doseq=True)

    # Normalize path: remove trailing slash unless it's root
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    normalized = urlunparse((
        "https",           # force https
        parsed.netloc.lower(),
        path,
        parsed.params,
        new_query,
        "",                # strip fragment
    ))
    return normalized


def is_internal(url: str) -> bool:
    """Return True if *url* belongs to the FanCode domain."""
    try:
        netloc = urlparse(url).netloc.lower().split(":")[0]
        return netloc == FANCODE_DOMAIN or netloc.endswith("." + FANCODE_DOMAIN)
    except Exception:
        return False



def are_duplicates(url_a: str, url_b: str) -> bool:
    """
    Return True if two *already-normalized* URLs represent the same resource.
    Uses simple string equality after normalization.
    """
    return url_a == url_b


def deduplicate(urls: list[str]) -> list[str]:
    """Remove duplicate URLs while preserving order of first occurrence."""
    seen: Set[str] = set()
    result = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def extract_match_id_from_url(url: Optional[str]) -> Optional[str]:
    """
    Extract numeric FanCode match ID specifically from match URL structures.

    Supported shapes:
    - .../matches/<slug>-<numeric_id>/... (e.g. /matches/tasmania-vs-new-south-wales-4249663/live-match-info)
    - .../matches/<numeric_id> or .../match/<numeric_id>
    - .../matches/<slug>/<numeric_id> or .../match/<slug>/<numeric_id>
    - /cricket/.../matches/<slug>-<numeric_id>/... or /cricket/.../matches/.../<numeric_id>

    Explicitly ignores:
    - Generic listing URLs (/schedule, /live-now, /sports, /video)
    - Tour / series URLs with only tour IDs (/tour/sheffield-shield-19896475 without /matches/)
    - Standalone non-URL strings or ordinal slugs (e.g. match-16)
    """
    if not url or not isinstance(url, str):
        return None

    cleaned = url.strip()
    if not cleaned:
        return None

    # Parse URL path to avoid matching query strings or fragments
    try:
        parsed = urlparse(cleaned)
        path = parsed.path or cleaned
    except Exception:
        path = cleaned

    # Path must contain /match/ or /matches/ to ensure it's a match resource
    # Pattern 1: /matches/<slug>-<numeric_id> or /match/<slug>-<numeric_id> (with minimum 4 digits)
    m = re.search(r"/match(?:es)?/(?:.+/)?(?:[a-z0-9_\-]+-)?(\d{4,})(?:[/?#]|$)", path, re.IGNORECASE)
    if m:
        return m.group(1)

    # Pattern 2: /match/<numeric_id> or /matches/<numeric_id> or /matches/.../<numeric_id>
    m = re.search(r"/match(?:es)?/(?:.+/)?(\d{4,})(?:[/?#]|$)", path, re.IGNORECASE)
    if m:
        return m.group(1)

    return None

