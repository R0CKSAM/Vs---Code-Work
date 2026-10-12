"""
parser.py – Defensive parser for extracting match items from FanCode payloads and DOM.

Handles heterogeneous JSON shapes gracefully:
- Nested dict structures
- Lists of matches / events
- FanCode specific GraphQL / REST schemas
- Fallback HTML / DOM element attributes
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.scraper.discovery.url_normalizer import (
    extract_match_id_from_url,
    normalize as normalize_url,
)
from app.scraper.schedule.models import RawScheduleItem, ScheduleMatch
from app.scraper.schedule.normalizer import (
    derive_slug,
    normalize_datetime,
    normalize_status,
)

logger = logging.getLogger(__name__)


def safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    """Traverse nested dictionary keys safely without throwing KeyError."""
    curr = d
    for k in keys:
        if not isinstance(curr, dict):
            return default
        curr = curr.get(k)
        if curr is None:
            return default
    return curr


class ScheduleParser:
    """Defensive extractor for FanCode schedule entries."""

    @classmethod
    def parse_item(cls, item: RawScheduleItem) -> Optional[ScheduleMatch]:
        """Convert a RawScheduleItem into a normalized ScheduleMatch."""
        data = item.raw_data
        if not isinstance(data, dict):
            return None

        # 1. Title / Event Name
        title = (
            safe_get(data, "title")
            or safe_get(data, "name")
            or safe_get(data, "eventName")
            or safe_get(data, "matchName")
            or safe_get(data, "header")
        )

        # 2. External Match ID
        ext_id = (
            safe_get(data, "id")
            or safe_get(data, "matchId")
            or safe_get(data, "eventId")
            or safe_get(data, "externalId")
        )
        if ext_id is not None:
            ext_id = str(ext_id)

        # 3. Source URL
        raw_url = (
            safe_get(data, "source_url")
            or safe_get(data, "url")
            or safe_get(data, "matchUrl")
            or safe_get(data, "webUrl")
            or safe_get(data, "shareUrl")
            or safe_get(data, "href")
        )
        if raw_url:
            source_url = normalize_url(raw_url) or raw_url
            if not ext_id:
                ext_id = extract_match_id_from_url(raw_url)
        elif ext_id:
            source_url = f"https://www.fancode.com/matches/{ext_id}"
        else:
            source_url = "https://www.fancode.com/schedule"

        # 4. Teams
        team_a_name, team_a_id, team_a_logo = cls._extract_team(data, 0, "teamA", "team_a", "homeTeam")
        team_b_name, team_b_id, team_b_logo = cls._extract_team(data, 1, "teamB", "team_b", "awayTeam")

        # If title missing, synthesize from teams
        if not title:
            if team_a_name and team_b_name:
                title = f"{team_a_name} vs {team_b_name}"
            elif team_a_name:
                title = team_a_name
            elif ext_id:
                title = f"Match {ext_id}"
            else:
                return None  # Unidentifiable item

        # 5. Status
        raw_status = (
            safe_get(data, "status")
            or safe_get(data, "matchStatus")
            or safe_get(data, "state")
        )
        status = normalize_status(raw_status)

        # 6. Dates and Times
        raw_date = (
            safe_get(data, "matchDate")
            or safe_get(data, "startTime")
            or safe_get(data, "date")
            or safe_get(data, "start_time")
            or safe_get(data, "startDate")
        )
        match_date, start_time = normalize_datetime(raw_date)

        # 7. Sport details
        sport_name = (
            safe_get(data, "sport", "name")
            or safe_get(data, "sportName")
            or safe_get(data, "sport")
        )
        if isinstance(sport_name, dict):
            sport_name = safe_get(sport_name, "name")
        sport_id = safe_get(data, "sport", "id") or safe_get(data, "sportId")

        # 8. Tournament / Tour details
        tour_name = (
            safe_get(data, "tour", "name")
            or safe_get(data, "tourName")
            or safe_get(data, "tournament", "name")
            or safe_get(data, "seriesName")
            or safe_get(data, "series", "name")
        )
        tour_id = (
            safe_get(data, "tour", "id")
            or safe_get(data, "tourId")
            or safe_get(data, "seriesId")
        )

        venue = safe_get(data, "venue") or safe_get(data, "venueName")
        score_summary = safe_get(data, "scoreSummary") or safe_get(data, "score")

        slug = derive_slug(title, ext_id)

        return ScheduleMatch(
            external_id=ext_id,
            title=title,
            slug=slug,
            source_url=source_url,
            status=status,
            sport_name=sport_name,
            sport_external_id=str(sport_id) if sport_id else None,
            sport_slug=derive_slug(sport_name) if sport_name else None,
            tour_name=tour_name,
            tour_external_id=str(tour_id) if tour_id else None,
            tour_slug=derive_slug(tour_name) if tour_name else None,
            match_date=match_date,
            start_time=start_time,
            venue=venue,
            team_a_name=team_a_name,
            team_a_external_id=team_a_id,
            team_a_logo_url=team_a_logo,
            team_b_name=team_b_name,
            team_b_external_id=team_b_id,
            team_b_logo_url=team_b_logo,
            image_url=safe_get(data, "imageUrl") or safe_get(data, "thumbnail"),
            score_summary=str(score_summary) if score_summary else None,
            raw_metadata=data,
        )

    @classmethod
    def _extract_team(cls, data: Dict[str, Any], index: int, *preferred_keys: str):
        # 1. Try preferred keys
        for k in preferred_keys:
            val = data.get(k)
            if isinstance(val, dict):
                return (
                    val.get("name") or val.get("shortName"),
                    str(val.get("id")) if val.get("id") else None,
                    val.get("logoUrl") or val.get("logo") or val.get("image"),
                )
            elif isinstance(val, str):
                return val, None, None

        # 2. Try teams list
        teams_list = data.get("teams") or data.get("competitors")
        if isinstance(teams_list, list) and len(teams_list) > index:
            t = teams_list[index]
            if isinstance(t, dict):
                return (
                    t.get("name") or t.get("shortName"),
                    str(t.get("id")) if t.get("id") else None,
                    t.get("logoUrl") or t.get("logo") or t.get("image"),
                )
            elif isinstance(t, str):
                return t, None, None

        return None, None, None

    @classmethod
    def extract_raw_items_from_json(cls, payload: Any) -> List[RawScheduleItem]:
        """Recursively locate match or schedule objects within arbitrary JSON trees."""
        items: List[RawScheduleItem] = []

        def _walk(obj: Any):
            if isinstance(obj, list):
                for elem in obj:
                    _walk(elem)
            elif isinstance(obj, dict):
                # Detect if this dict looks like a match/event item
                is_match = any(k in obj for k in ("matchId", "eventId", "teamA", "teams", "matchName", "matchStatus"))
                if is_match and ("title" in obj or "name" in obj or "teamA" in obj or "teams" in obj or "id" in obj):
                    items.append(RawScheduleItem(raw_data=obj, source_type="json"))
                else:
                    for v in obj.values():
                        _walk(v)

        _walk(payload)
        return items
