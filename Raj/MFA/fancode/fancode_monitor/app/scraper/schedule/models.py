"""
models.py – Typed data models for FanCode Schedule Scraping.

Entities:
- RawScheduleItem: Raw dictionary wrapper with safe query accessors
- ScheduleMatch: Normalized, validated match/event representation ready for DB persistence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RawScheduleItem:
    """
    Wrapper for a single unnormalized schedule item (from JSON or DOM).
    Provides safe dictionary traversal without raising KeyErrors.
    """
    raw_data: Dict[str, Any]
    source_type: str = "json"  # "json" or "dom"

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw_data.get(key, default)


@dataclass
class ScheduleMatch:
    """
    Normalized match entity ready to be persisted via Phase 2 repositories.
    """
    title: str
    source_url: str
    external_id: Optional[str] = None
    slug: Optional[str] = None
    status: str = "UNKNOWN"
    sport_name: Optional[str] = None
    sport_external_id: Optional[str] = None
    sport_slug: Optional[str] = None
    tour_name: Optional[str] = None
    tour_external_id: Optional[str] = None
    tour_slug: Optional[str] = None

    match_date: Optional[datetime] = None
    start_time: Optional[str] = None
    venue: Optional[str] = None

    team_a_name: Optional[str] = None
    team_a_external_id: Optional[str] = None
    team_a_logo_url: Optional[str] = None

    team_b_name: Optional[str] = None
    team_b_external_id: Optional[str] = None
    team_b_logo_url: Optional[str] = None

    image_url: Optional[str] = None
    score_summary: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "slug": self.slug,
            "source_url": self.source_url,
            "status": self.status,
            "sport_name": self.sport_name,
            "sport_external_id": self.sport_external_id,
            "sport_slug": self.sport_slug,
            "tour_name": self.tour_name,
            "tour_external_id": self.tour_external_id,
            "tour_slug": self.tour_slug,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "start_time": self.start_time,
            "venue": self.venue,
            "team_a_name": self.team_a_name,
            "team_a_external_id": self.team_a_external_id,
            "team_a_logo_url": self.team_a_logo_url,
            "team_b_name": self.team_b_name,
            "team_b_external_id": self.team_b_external_id,
            "team_b_logo_url": self.team_b_logo_url,
            "image_url": self.image_url,
            "score_summary": self.score_summary,
            "raw_metadata": self.raw_metadata,
        }
