"""
normalizer.py – Normalization rules for Tour / Series / Tournament records.
"""

from __future__ import annotations

import re
from typing import Optional

from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.normalizer import normalize_datetime, normalize_status


def derive_tour_slug(name: str, fallback_id: Optional[str] = None) -> str:
    """Generate clean URL slug for a tour/series."""
    clean = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[-\s]+", "-", clean).strip("-")
    if not slug and fallback_id:
        slug = f"tour-{fallback_id}"
    return slug or "unknown-tour"


def derive_tour_identity(
    external_id: Optional[str],
    source_url: Optional[str],
    name: str,
) -> str:
    """
    Establish deterministic tour identity.
    Priority:
    1. external_id
    2. normalized source_url
    3. slug from name
    """
    if external_id and str(external_id).strip():
        return str(external_id).strip()

    if source_url:
        norm = normalize_url(source_url)
        if norm:
            return norm

    return derive_tour_slug(name)
