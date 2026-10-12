"""
parser.py – Defensive parser for FanCode Live Now payloads and DOM representations.

Extracts live match records from heterogeneous JSON structures, embedded Next.js data,
and fallback structures. Tolerates missing fields and malformed payloads without crashing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.scraper.discovery.url_normalizer import (
    extract_match_id_from_url,
    normalize as normalize_url,
)
from app.scraper.live_now.models import LiveMatchRecord, RawLiveItem
from app.scraper.live_now.normalizer import (
    GENERIC_UI_TITLES,
    extract_title_from_slug_or_url,
    is_valid_match_title,
    is_vs_title,
)
from app.scraper.schedule.normalizer import (
    derive_slug,
    normalize_datetime,
    normalize_status,
)

logger = logging.getLogger(__name__)


def safe_get(data: Any, *keys: Any, default: Any = None) -> Any:
    """Safely traverse nested dicts/lists without raising KeyError or TypeError."""
    curr = data
    for k in keys:
        if curr is None:
            return default
        if isinstance(curr, dict):
            curr = curr.get(k)
        elif isinstance(curr, (list, tuple)) and isinstance(k, int):
            if 0 <= k < len(curr):
                curr = curr[k]
            else:
                return default
        else:
            return default
    return curr if curr is not None else default


class LiveNowParser:
    """Defensive extractor and parser for Live Now match items."""

    @staticmethod
    def find_match_id(d: Dict[str, Any]) -> Optional[str]:
        for k in (
            "matchId", "match_id", "eventId", "event_id", "id",
            "externalId", "external_id", "contentId",
        ):
            v = d.get(k)
            if v is not None and str(v).strip():
                val = str(v).strip()
                if val and val.lower() not in ("live", "live-now", "match"):
                    return val

        # Check nested match.id or match.externalId
        match_obj = d.get("match")
        if isinstance(match_obj, dict):
            for k in ("id", "matchId", "match_id", "externalId", "external_id"):
                v = match_obj.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()

        # Check URL fields for embedded match ID
        for url_key in ("url", "source_url", "matchUrl", "match_url", "webUrl", "shareUrl", "link", "href"):
            raw_url = d.get(url_key)
            if raw_url and isinstance(raw_url, str):
                extracted = extract_match_id_from_url(raw_url)
                if extracted:
                    return extracted

        return None

    @staticmethod
    def find_source_url(d: Dict[str, Any], default_url: Optional[str] = None) -> str:
        for k in ("url", "source_url", "matchUrl", "match_url", "webUrl", "shareUrl", "link", "href"):
            v = d.get(k)
            if v and isinstance(v, str) and v.strip():
                raw = v.strip()
                if raw.startswith("http"):
                    norm = normalize_url(raw)
                    return norm or raw
                if raw.startswith("/"):
                    norm = normalize_url(f"https://www.fancode.com{raw}")
                    return norm or f"https://www.fancode.com{raw}"

        # Try constructing from match slug or ID
        slug = safe_get(d, "features", "slug") or d.get("slug")
        m_id = LiveNowParser.find_match_id(d)
        if slug and m_id:
            return f"https://www.fancode.com/match/{slug}/{m_id}"
        elif slug:
            return f"https://www.fancode.com/match/{slug}"
        elif m_id:
            return f"https://www.fancode.com/matches/{m_id}"

        return default_url or ""

    @staticmethod
    def find_title(d: Dict[str, Any]) -> str:
        # 1. First check if explicit title has "vs" pattern
        for k in ("title", "name", "eventName", "event_name", "matchName", "match_name"):
            v = d.get(k)
            if v and isinstance(v, str) and is_vs_title(v) and is_valid_match_title(v):
                return v.strip()

        # 2. Check team objects if available
        team_a = safe_get(d, "teamA", "name") or safe_get(d, "homeTeam", "name")
        team_b = safe_get(d, "teamB", "name") or safe_get(d, "awayTeam", "name")
        if team_a and team_b:
            candidate = f"{team_a} vs {team_b}"
            if is_valid_match_title(candidate):
                return candidate

        # 3. Check teams array or match.teams array
        teams_list = safe_get(d, "match", "teams") or d.get("teams") or d.get("participants")
        if isinstance(teams_list, list) and len(teams_list) >= 2:
            t1 = teams_list[0].get("name") if isinstance(teams_list[0], dict) else str(teams_list[0])
            t2 = teams_list[1].get("name") if isinstance(teams_list[1], dict) else str(teams_list[1])
            if t1 and t2:
                candidate = f"{t1} vs {t2}"
                if is_valid_match_title(candidate):
                    return candidate

        # 4. Check URL or slug for vs-match title
        for url_key in ("url", "source_url", "matchUrl", "match_url", "webUrl", "link", "href"):
            raw_url = d.get(url_key)
            if raw_url and isinstance(raw_url, str):
                recovered = extract_title_from_slug_or_url(raw_url)
                if recovered and is_vs_title(recovered):
                    return recovered

        slug = safe_get(d, "features", "slug") or d.get("slug")
        if slug and isinstance(slug, str):
            recovered = extract_title_from_slug_or_url(slug)
            if recovered and is_vs_title(recovered):
                return recovered

        # 5. Check match.name / match.title
        match_obj = d.get("match")
        if isinstance(match_obj, dict):
            for k in ("name", "title", "eventName", "matchName"):
                v = match_obj.get(k)
                if v and isinstance(v, str) and is_valid_match_title(v):
                    return v.strip()

        # 6. Fallback to any valid non-generic title provided
        for k in ("title", "name", "eventName", "event_name", "matchName", "match_name"):
            v = d.get(k)
            if v and isinstance(v, str) and is_valid_match_title(v):
                return v.strip()

        # 7. Fallback to slug title if valid
        if slug and isinstance(slug, str):
            recovered = extract_title_from_slug_or_url(slug)
            if recovered:
                return recovered
            words = slug.replace("-vs-", " vs ").replace("-v-", " vs ").replace("-", " ").title()
            if is_valid_match_title(words):
                return words

        for url_key in ("url", "source_url", "matchUrl", "match_url", "webUrl", "link", "href"):
            raw_url = d.get(url_key)
            if raw_url and isinstance(raw_url, str):
                recovered = extract_title_from_slug_or_url(raw_url)
                if recovered:
                    return recovered

        return ""

    @staticmethod
    def find_status(d: Dict[str, Any]) -> str:
        # Check dict status e.g. {"status": "LIVE", "streamingStatus": "STARTED"}
        raw_status = d.get("status")
        if isinstance(raw_status, dict):
            status_str = raw_status.get("status") or raw_status.get("streamingStatus") or raw_status.get("state")
            if status_str and isinstance(status_str, str):
                normalized = normalize_status(status_str)
                if normalized != "UNKNOWN":
                    return normalized

        for k in (
            "status", "matchStatus", "match_status", "eventStatus",
            "state", "liveStatus", "streamStatus", "streamingStatus",
        ):
            v = d.get(k)
            if v and isinstance(v, str) and v.strip():
                normalized = normalize_status(v)
                if normalized != "UNKNOWN":
                    return normalized

        # If boolean indicator indicates live
        if d.get("isLive") is True or d.get("is_live") is True or d.get("streaming") is True:
            return "LIVE"

        streaming_status = safe_get(d, "status", "streamingStatus")
        if streaming_status == "STARTED":
            return "LIVE"

        return "LIVE"  # Default for items captured specifically from live-now endpoint

    @staticmethod
    def find_start_time(d: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[str]]:
        for k in (
            "startTime", "start_time", "matchDate", "match_date", "date",
            "startDate", "start_date", "dateTime", "timestamp",
        ):
            v = d.get(k)
            if v:
                dt, time_str = normalize_datetime(v)
                if dt:
                    return dt, time_str
        return None, None

    @staticmethod
    def find_live_started_at(d: Dict[str, Any]) -> Optional[datetime]:
        for k in (
            "liveStartedAt", "live_started_at", "actualStartTime",
            "streamStartedAt", "streamStartTime",
        ):
            v = d.get(k)
            if v:
                dt, _ = normalize_datetime(v)
                if dt:
                    return dt
        return None

    @staticmethod
    def find_teams(d: Dict[str, Any]) -> Tuple[
        Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]
    ]:
        """Returns (team_a_name, team_b_name, team_a_id, team_b_id, team_a_logo, team_b_logo)."""
        team_a_name, team_b_name = None, None
        team_a_id, team_b_id = None, None
        team_a_logo, team_b_logo = None, None

        # Check explicit teamA / teamB
        t_a = d.get("teamA") or d.get("homeTeam") or d.get("team_a")
        if isinstance(t_a, dict):
            team_a_name = t_a.get("name") or t_a.get("title")
            team_a_id = str(t_a.get("id")) if t_a.get("id") is not None else None
            team_a_logo = t_a.get("logoUrl") or t_a.get("logo_url") or t_a.get("image") or t_a.get("logo")
        elif isinstance(t_a, str):
            team_a_name = t_a

        t_b = d.get("teamB") or d.get("awayTeam") or d.get("team_b")
        if isinstance(t_b, dict):
            team_b_name = t_b.get("name") or t_b.get("title")
            team_b_id = str(t_b.get("id")) if t_b.get("id") is not None else None
            team_b_logo = t_b.get("logoUrl") or t_b.get("logo_url") or t_b.get("image") or t_b.get("logo")
        elif isinstance(t_b, str):
            team_b_name = t_b

        # Check teams array (including under match.teams)
        teams_list = safe_get(d, "match", "teams") or d.get("teams") or d.get("participants")
        if isinstance(teams_list, list) and len(teams_list) >= 2:
            el_a, el_b = teams_list[0], teams_list[1]
            if not team_a_name:
                team_a_name = el_a.get("name") if isinstance(el_a, dict) else str(el_a)
                if isinstance(el_a, dict):
                    team_a_id = str(el_a.get("id")) if el_a.get("id") is not None else None
                    team_a_logo = el_a.get("logoUrl") or el_a.get("logo_url") or el_a.get("image") or el_a.get("logo")
            if not team_b_name:
                team_b_name = el_b.get("name") if isinstance(el_b, dict) else str(el_b)
                if isinstance(el_b, dict):
                    team_b_id = str(el_b.get("id")) if el_b.get("id") is not None else None
                    team_b_logo = el_b.get("logoUrl") or el_b.get("logo_url") or el_b.get("image") or el_b.get("logo")

        return team_a_name, team_b_name, team_a_id, team_b_id, team_a_logo, team_b_logo

    @staticmethod
    def find_score(d: Dict[str, Any]) -> Optional[str]:
        for k in (
            "scoreSummary", "score_summary", "score", "liveScore",
            "currentScore", "scores", "result",
        ):
            v = d.get(k)
            if v:
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, dict):
                    # Format composite score objects
                    summary = v.get("summary") or v.get("text") or v.get("display")
                    if summary:
                        return str(summary).strip()
                    parts = []
                    for sk, sv in v.items():
                        if isinstance(sv, (str, int, float)) and sv:
                            parts.append(f"{sk}: {sv}")
                    if parts:
                        return ", ".join(parts)
        return None

    @staticmethod
    def find_sport(d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Returns (sport_id, sport_name)."""
        sport = d.get("sport")
        if isinstance(sport, dict):
            s_id = str(sport.get("id")) if sport.get("id") is not None else None
            s_name = sport.get("name") or sport.get("title")
            return s_id, s_name
        s_name = d.get("sportName") or d.get("sport_name")
        s_id = str(d.get("sportId") or d.get("sport_id") or "") or None
        return s_id, s_name

    @staticmethod
    def find_tour(d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Returns (tour_id, tour_name)."""
        tour = d.get("tour") or d.get("tournament") or d.get("series") or d.get("competition") or safe_get(d, "match", "tour")
        if isinstance(tour, dict):
            t_id = str(tour.get("id") or tour.get("collectionId") or tour.get("tourId") or "") or None
            t_name = tour.get("name") or tour.get("title")
            return t_id, t_name
        t_name = d.get("tourName") or d.get("tour_name") or d.get("tournamentName") or d.get("seriesName")
        t_id = str(d.get("tourId") or d.get("tour_id") or "") or None
        return t_id, t_name

    @staticmethod
    def find_stream(d: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str]]:
        """Returns (stream_available, stream_language)."""
        available = None
        lang = None

        streaming_status = safe_get(d, "status", "streamingStatus")
        if streaming_status == "STARTED":
            available = True

        for k in ("isStreaming", "is_streaming", "streaming", "streamAvailable", "liveStream"):
            if k in d:
                v = d.get(k)
                if isinstance(v, bool):
                    available = v
                    break
                if isinstance(v, dict):
                    available = bool(v)
                    lang = v.get("language") or v.get("lang")
                    break

        if not lang:
            for lk in ("language", "streamLanguage", "audioLanguage"):
                if lk in d and isinstance(d[lk], str):
                    lang = d[lk].strip()
                    break

        return available, lang

    @staticmethod
    def find_image(d: Dict[str, Any]) -> Optional[str]:
        for k in ("imageUrl", "image_url", "thumbnail", "thumbnailUrl", "bannerUrl", "image"):
            v = d.get(k)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        for k in ("bgImageUrl", "matchSportyBgImage", "imageUrl", "thumbnail"):
            v = safe_get(d, "features", k)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return None

    @staticmethod
    def find_description(d: Dict[str, Any]) -> Optional[str]:
        for k in ("description", "subtitle", "summary", "shortDescription"):
            v = d.get(k)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return None

    @staticmethod
    def parse_live_item(
        raw_item: RawLiveItem,
        default_url: Optional[str] = None,
    ) -> Optional[LiveMatchRecord]:
        """Parse raw extracted dictionary into normalized LiveMatchRecord."""
        data = raw_item.raw_data
        if not isinstance(data, dict):
            return None

        try:
            match_ext_id = LiveNowParser.find_match_id(data)
            source_url = LiveNowParser.find_source_url(data, default_url)
            if not match_ext_id and source_url:
                match_ext_id = extract_match_id_from_url(source_url)
            title = LiveNowParser.find_title(data)

            # Must have at least a title or a match_id to be a valid match item
            if not title and not match_ext_id:
                return None

            status = LiveNowParser.find_status(data)
            match_date, start_time = LiveNowParser.find_start_time(data)
            live_started_at = LiveNowParser.find_live_started_at(data)

            team_a_name, team_b_name, team_a_id, team_b_id, team_a_logo, team_b_logo = (
                LiveNowParser.find_teams(data)
            )

            # If title is missing or generic UI label, attempt recovery from teams or URL
            if not is_valid_match_title(title):
                if team_a_name and team_b_name and is_valid_match_title(f"{team_a_name} vs {team_b_name}"):
                    title = f"{team_a_name} vs {team_b_name}"
                elif source_url:
                    recovered = extract_title_from_slug_or_url(source_url)
                    if recovered:
                        title = recovered

            # Reject candidate if title is still invalid or generic UI label
            if not is_valid_match_title(title):
                return None

            # Reject candidate if source_url is a landing page without match evidence
            norm_url = normalize_url(source_url) if source_url else ""
            if norm_url in (
                "https://www.fancode.com",
                "https://www.fancode.com/live",
                "https://www.fancode.com/live-now",
                "https://www.fancode.com/live-now/all-sports",
                "https://www.fancode.com/schedule",
                "https://www.fancode.com/video",
            ) and not match_ext_id and not (team_a_name and team_b_name):
                return None

            venue = data.get("venue")
            if isinstance(venue, dict):
                venue = venue.get("name") or venue.get("title")

            score = LiveNowParser.find_score(data)
            sport_id, sport_name = LiveNowParser.find_sport(data)
            tour_id, tour_name = LiveNowParser.find_tour(data)
            stream_available, stream_lang = LiveNowParser.find_stream(data)
            thumbnail = LiveNowParser.find_image(data)
            description = LiveNowParser.find_description(data)

            # Extract any remaining extra fields into metadata
            meta: Dict[str, Any] = {}
            for k in ("innings", "overs", "period", "quarter", "matchType", "format"):
                if k in data:
                    meta[k] = data[k]

            return LiveMatchRecord(
                match_external_id=match_ext_id,
                source_url=source_url,
                title=title,
                status=status,
                sport_id=sport_id,
                sport_name=sport_name,
                tour_id=tour_id,
                tour_name=tour_name,
                start_time=start_time,
                match_date=match_date,
                live_started_at=live_started_at,
                venue=str(venue).strip() if venue else None,
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                team_a_id=team_a_id,
                team_b_id=team_b_id,
                team_a_logo=team_a_logo,
                team_b_logo=team_b_logo,
                score_summary=score,
                stream_available=stream_available,
                stream_language=stream_lang,
                thumbnail_url=thumbnail,
                description=description,
                metadata=meta,
            )
        except Exception as exc:
            logger.debug("Failed parsing live item: %s", exc)
            return None

    @staticmethod
    def extract_embedded_json(html: str) -> Optional[Dict[str, Any]]:
        """Extract Next.js SSR state or window.__INITIAL_STATE__ from HTML."""
        match = re.search(
            r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception as exc:
                logger.debug("Failed to decode __NEXT_DATA__: %s", exc)

        # Look for window.__INITIAL_STATE__ = { ... };
        state_match = re.search(
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>',
            html,
            re.DOTALL,
        )
        if state_match:
            try:
                return json.loads(state_match.group(1).strip())
            except Exception as exc:
                logger.debug("Failed to decode __INITIAL_STATE__: %s", exc)

        # Also search for any script containing live matches / topMatches
        for m in re.finditer(r'<script[^>]*>(\{.*?"(?:liveNowMatches|topMatches|live-now-view)".*?\})</script>', html, re.DOTALL):
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                continue

        return None

    @classmethod
    def extract_live_items_from_payload(cls, payload: Any) -> List[RawLiveItem]:
        """
        Defensively traverses arbitrary JSON payload looking for live match records.
        Supports { "matches": [...] }, { "data": { "matches": [...] } },
        { "events": [...] }, and nested arrays.
        """
        results: List[RawLiveItem] = []

        if not payload:
            return results

        seen_ids = set()

        def is_match_candidate(obj: Dict[str, Any]) -> bool:
            if not isinstance(obj, dict):
                return False
            # Check for strong match identity indicators
            has_id = any(k in obj for k in ("matchId", "eventId", "contentId", "id")) or isinstance(obj.get("match"), dict)
            has_teams = any(k in obj for k in ("teamA", "teamB", "teams", "participants")) or safe_get(obj, "match", "teams") is not None
            has_sport_or_tour = any(k in obj for k in ("sport", "tour", "tournament", "series")) or safe_get(obj, "match", "tour") is not None
            has_score_or_status = any(k in obj for k in ("score", "scoreSummary", "matchStatus", "isLive", "streamingStatus")) or isinstance(obj.get("status"), dict)
            title_cand = obj.get("title") or obj.get("name") or obj.get("eventName") or safe_get(obj, "features", "slug")
            has_title = is_valid_match_title(title_cand) if isinstance(title_cand, str) else bool(safe_get(obj, "features", "slug"))

            # Require at least two contextual signals to avoid spurious dicts
            signals = sum([bool(has_id), bool(has_teams), bool(has_sport_or_tour), bool(has_score_or_status), bool(has_title)])
            return signals >= 2

        def traverse(node: Any) -> None:
            if isinstance(node, dict):
                if is_match_candidate(node):
                    obj_id = id(node)
                    if obj_id not in seen_ids:
                        seen_ids.add(obj_id)
                        results.append(RawLiveItem(raw_data=node, source_type="json"))
                else:
                    for v in node.values():
                        traverse(v)
            elif isinstance(node, list):
                for elem in node:
                    traverse(elem)

        traverse(payload)
        return results

