"""
normalizer.py – Normalization rules for Match Detail attributes.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.normalizer import (
    derive_slug,
    normalize_datetime,
    normalize_status,
)


def derive_match_identity(
    external_id: Optional[str],
    source_url: str,
) -> str:
    """Stable match identity prioritization."""
    if external_id and str(external_id).strip():
        return str(external_id).strip()
    norm = normalize_url(source_url)
    return norm or source_url


def normalize_venue_details(
    raw_venue: Optional[str],
    city: Optional[str] = None,
    country: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Format venue strings cleanly without guessing unstated cities/countries.
    Returns (full_venue_string, venue_name, city, country).
    """
    if not raw_venue or not str(raw_venue).strip():
        return None, None, city, country

    venue_str = str(raw_venue).strip()
    return venue_str, venue_str, city, country
