"""
parser.py – Defensive parser for FanCode match detail pages.

Extracts rich metadata from:
1. Public intercepted JSON payloads
2. Public embedded Next.js / JSON-LD script tags
3. Rendered DOM semantic elements
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.scraper.discovery.url_normalizer import (
    extract_match_id_from_url,
    normalize as normalize_url,
)
from app.scraper.match_detail.models import MatchDetail, RawMatchDetail
from app.scraper.match_detail.normalizer import (
    derive_match_identity,
    normalize_venue_details,
)
from app.scraper.schedule.normalizer import (
    derive_slug,
    normalize_datetime,
    normalize_status,
)
from app.scraper.schedule.parser import ScheduleParser, safe_get

logger = logging.getLogger(__name__)


class MatchDetailParser:
    """Defensive extractor for detailed FanCode match data."""

    @classmethod
    def parse_detail(cls, raw: RawMatchDetail, default_url: str = "") -> Optional[MatchDetail]:
        data = raw.raw_data
        if not isinstance(data, dict):
            return None

        # 1. External ID
        ext_id = (
            safe_get(data, "id")
            or safe_get(data, "matchId")
            or safe_get(data, "eventId")
            or safe_get(data, "externalId")
        )
        if ext_id is not None:
            ext_id = str(ext_id)

        # 2. Source URL
        source_url = (
            safe_get(data, "source_url")
            or safe_get(data, "url")
            or safe_get(data, "matchUrl")
            or safe_get(data, "href")
            or raw.source_url
            or default_url
        )
        if source_url:
            source_url = normalize_url(source_url) or source_url
            if not ext_id:
                ext_id = extract_match_id_from_url(source_url)

        # 3. Title
        title = (
            safe_get(data, "title")
            or safe_get(data, "name")
            or safe_get(data, "matchName")
            or safe_get(data, "eventName")
        )

        # 4. Status
        raw_status = (
            safe_get(data, "status")
            or safe_get(data, "matchStatus")
            or safe_get(data, "state")
        )
        status = normalize_status(raw_status) if raw_status else None

        # 5. Dates & Times
        raw_date = (
            safe_get(data, "matchDate")
            or safe_get(data, "startTime")
            or safe_get(data, "date")
            or safe_get(data, "startDate")
        )
        match_date, start_time = normalize_datetime(raw_date)

        # 6. Venue
        raw_venue = safe_get(data, "venue") or safe_get(data, "venueName")
        city = safe_get(data, "city") or safe_get(data, "venueCity")
        country = safe_get(data, "country") or safe_get(data, "venueCountry")
        full_venue, v_name, v_city, v_country = normalize_venue_details(raw_venue, city, country)

        # 7. Teams
        team_a_name, team_a_id, team_a_logo = ScheduleParser._extract_team(data, 0, "teamA", "team_a", "homeTeam")
        team_b_name, team_b_id, team_b_logo = ScheduleParser._extract_team(data, 1, "teamB", "team_b", "awayTeam")

        # 8. Sport & Tour
        sport_name = safe_get(data, "sport", "name") or safe_get(data, "sportName")
        sport_id = safe_get(data, "sport", "id") or safe_get(data, "sportId")

        tour_name = safe_get(data, "tour", "name") or safe_get(data, "tourName") or safe_get(data, "seriesName")
        tour_id = safe_get(data, "tour", "id") or safe_get(data, "tourId") or safe_get(data, "seriesId")

        # 9. Extra fields
        image_url = safe_get(data, "imageUrl") or safe_get(data, "thumbnail") or safe_get(data, "banner")
        description = safe_get(data, "description") or safe_get(data, "summary")
        score_summary = safe_get(data, "scoreSummary") or safe_get(data, "score")
        streaming_available = safe_get(data, "isStreaming") or safe_get(data, "streamingAvailable")
        language = safe_get(data, "language")

        return MatchDetail(
            source_url=source_url,
            match_external_id=ext_id,
            title=title,
            slug=derive_slug(title, ext_id) if title else None,
            sport_name=sport_name,
            sport_external_id=str(sport_id) if sport_id else None,
            tour_name=tour_name,
            tour_external_id=str(tour_id) if tour_id else None,
            match_date=match_date,
            start_time=start_time,
            status=status,
            venue=full_venue,
            venue_name=v_name,
            venue_city=v_city,
            venue_country=v_country,
            team_a_name=team_a_name,
            team_a_external_id=team_a_id,
            team_a_logo_url=team_a_logo,
            team_b_name=team_b_name,
            team_b_external_id=team_b_id,
            team_b_logo_url=team_b_logo,
            image_url=image_url,
            description=description,
            score_summary=str(score_summary) if score_summary else None,
            streaming_available=bool(streaming_available) if streaming_available is not None else None,
            language=language,
            raw_metadata=data,
        )

    @classmethod
    def extract_embedded_json(cls, html_content: str) -> Optional[Dict[str, Any]]:
        """Extract public Next.js state or JSON-LD script from rendered HTML."""
        import re
        # Look for __NEXT_DATA__
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return None
