"""
parser.py – Defensive parser for extracting Tour / Series / Tournament records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.normalizer import normalize_datetime, normalize_status
from app.scraper.schedule.parser import safe_get
from app.scraper.sports.normalizer import derive_sport_slug
from app.scraper.tours.models import TourRecord
from app.scraper.tours.normalizer import derive_tour_slug

logger = logging.getLogger(__name__)


class ToursParser:
    """Defensive extractor for FanCode tours / series / competitions."""

    @classmethod
    def parse_tour_dict(cls, data: Dict[str, Any]) -> Optional[TourRecord]:
        if not isinstance(data, dict):
            return None

        name = (
            safe_get(data, "name")
            or safe_get(data, "tourName")
            or safe_get(data, "seriesName")
            or safe_get(data, "tournamentName")
            or safe_get(data, "title")
        )
        if not name or not str(name).strip():
            return None

        name = str(name).strip()

        ext_id = safe_get(data, "id") or safe_get(data, "tourId") or safe_get(data, "seriesId")
        if ext_id is not None:
            ext_id = str(ext_id)

        slug = safe_get(data, "slug") or derive_tour_slug(name, ext_id)

        raw_url = safe_get(data, "source_url") or safe_get(data, "url") or safe_get(data, "href")
        if raw_url:
            norm_url = normalize_url(raw_url) or str(raw_url).strip()
            # If the raw URL is a match/video detail route, extract the tour prefix or fallback to tour slug URL
            if "/matches/" in norm_url:
                source_url = norm_url.split("/matches/")[0]
            elif "/match/" in norm_url:
                source_url = norm_url.split("/match/")[0]
            elif "/video/" in norm_url or "/videos/" in norm_url:
                source_url = f"https://www.fancode.com/tours/{slug}"
            else:
                source_url = norm_url
        else:
            source_url = f"https://www.fancode.com/tours/{slug}"

        # Sport association
        sport_name = safe_get(data, "sport", "name") or safe_get(data, "sportName")
        sport_id = safe_get(data, "sport", "id") or safe_get(data, "sportId")

        # Dates & Status
        start_date, _ = normalize_datetime(safe_get(data, "startDate") or safe_get(data, "start_date"))
        end_date, _ = normalize_datetime(safe_get(data, "endDate") or safe_get(data, "end_date"))
        raw_status = safe_get(data, "status") or safe_get(data, "state")
        status = normalize_status(raw_status) if raw_status else None

        return TourRecord(
            name=name,
            slug=slug,
            source_url=source_url,
            external_id=ext_id,
            sport_name=sport_name,
            sport_external_id=str(sport_id) if sport_id else None,
            sport_slug=derive_sport_slug(sport_name) if sport_name else None,
            description=safe_get(data, "description"),
            image_url=safe_get(data, "imageUrl") or safe_get(data, "banner") or safe_get(data, "image"),
            start_date=start_date,
            end_date=end_date,
            status=status,
            raw_metadata=data,
        )

    @classmethod
    def extract_tours_from_json(cls, payload: Any) -> List[TourRecord]:
        results: List[TourRecord] = []

        def _walk(obj: Any):
            if isinstance(obj, list):
                for elem in obj:
                    _walk(elem)
            elif isinstance(obj, dict):
                has_tour_id = "tourId" in obj or "seriesId" in obj or "tournamentId" in obj
                has_tour_name = "tourName" in obj or "seriesName" in obj or "tournamentName" in obj
                has_tour_indicator = (
                    "name" in obj
                    and any(k in str(obj.get("slug", "")).lower() or k in str(obj.get("url", "")).lower() for k in ("tour", "series", "ipl", "league", "cup"))
                )
                if has_tour_id or has_tour_name or has_tour_indicator:
                    record = cls.parse_tour_dict(obj)
                    if record:
                        results.append(record)
                for v in obj.values():
                    _walk(v)


        _walk(payload)
        return results
