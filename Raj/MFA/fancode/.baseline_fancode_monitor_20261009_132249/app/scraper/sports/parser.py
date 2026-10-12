"""
parser.py – Defensive parser for extracting Sports records from payloads or DOM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.parser import safe_get
from app.scraper.sports.models import SportRecord
from app.scraper.sports.normalizer import derive_sport_slug

logger = logging.getLogger(__name__)


class SportsParser:
    """Defensive extractor for FanCode sports."""

    @classmethod
    def parse_sport_dict(cls, data: Dict[str, Any]) -> Optional[SportRecord]:
        if not isinstance(data, dict):
            return None

        name = (
            safe_get(data, "name")
            or safe_get(data, "sportName")
            or safe_get(data, "title")
            or safe_get(data, "label")
        )
        if not name or not str(name).strip():
            return None

        name = str(name).strip()

        ext_id = safe_get(data, "id") or safe_get(data, "sportId") or safe_get(data, "externalId")
        if ext_id is not None:
            ext_id = str(ext_id)

        slug = safe_get(data, "slug") or derive_sport_slug(name, ext_id)

        raw_url = safe_get(data, "source_url") or safe_get(data, "url") or safe_get(data, "href")
        if raw_url:
            source_url = normalize_url(raw_url) or raw_url
        else:
            source_url = f"https://www.fancode.com/{slug}"

        description = safe_get(data, "description")
        image_url = safe_get(data, "imageUrl") or safe_get(data, "icon") or safe_get(data, "logo")
        is_active = safe_get(data, "isActive", default=True)

        return SportRecord(
            name=name,
            slug=slug,
            source_url=source_url,
            external_id=ext_id,
            description=description,
            image_url=image_url,
            is_active=bool(is_active),
            raw_metadata=data,
        )

    @classmethod
    def extract_sports_from_json(cls, payload: Any) -> List[SportRecord]:
        results: List[SportRecord] = []

        def _walk(obj: Any):
            if isinstance(obj, list):
                for elem in obj:
                    _walk(elem)
            elif isinstance(obj, dict):
                # Check if this node looks like a sport object
                has_sport_id = "sportId" in obj or ("id" in obj and ("sport" in str(obj.get("slug", "")).lower() or "sport" in str(obj.get("name", "")).lower()))
                has_sport_name = "sportName" in obj or ("name" in obj and "slug" in obj)
                if has_sport_id or has_sport_name:
                    record = cls.parse_sport_dict(obj)
                    if record:
                        results.append(record)
                for v in obj.values():
                    _walk(v)

        _walk(payload)
        return results
