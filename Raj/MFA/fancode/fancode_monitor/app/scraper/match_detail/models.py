"""
models.py – MatchDetail data models for Phase 5 Match Detail Scraper.

Entities:
- RawMatchDetail: Wrapper for raw JSON/DOM details with safe lookups
- MatchDetail: Normalized representation of detailed match attributes for enrichment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RawMatchDetail:
    """Wrapper for raw match detail data with safe dictionary accessors."""
    raw_data: Dict[str, Any]
    source_type: str = "json"  # "json", "embedded", or "dom"
    source_url: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw_data.get(key, default)


@dataclass
class MatchDetail:
    """
    Normalized match detail record.
    Used to enrich existing Match records without overwriting good data with None.
    """
    source_url: str
    match_external_id: Optional[str] = None
    title: Optional[str] = None
    slug: Optional[str] = None

    sport_name: Optional[str] = None
    sport_external_id: Optional[str] = None

    tour_name: Optional[str] = None
    tour_external_id: Optional[str] = None

    match_date: Optional[datetime] = None
    start_time: Optional[str] = None
    status: Optional[str] = None

    venue: Optional[str] = None
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    venue_country: Optional[str] = None

    team_a_name: Optional[str] = None
    team_a_external_id: Optional[str] = None
    team_a_logo_url: Optional[str] = None

    team_b_name: Optional[str] = None
    team_b_external_id: Optional[str] = None
    team_b_logo_url: Optional[str] = None

    image_url: Optional[str] = None
    description: Optional[str] = None
    score_summary: Optional[str] = None
    streaming_available: Optional[bool] = None
    language: Optional[str] = None

    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "match_external_id": self.match_external_id,
            "title": self.title,
            "slug": self.slug,
            "sport_name": self.sport_name,
            "sport_external_id": self.sport_external_id,
            "tour_name": self.tour_name,
            "tour_external_id": self.tour_external_id,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "start_time": self.start_time,
            "status": self.status,
            "venue": self.venue,
            "venue_name": self.venue_name,
            "venue_city": self.venue_city,
            "venue_country": self.venue_country,
            "team_a_name": self.team_a_name,
            "team_a_external_id": self.team_a_external_id,
            "team_a_logo_url": self.team_a_logo_url,
            "team_b_name": self.team_b_name,
            "team_b_external_id": self.team_b_external_id,
            "team_b_logo_url": self.team_b_logo_url,
            "image_url": self.image_url,
            "description": self.description,
            "score_summary": self.score_summary,
            "streaming_available": self.streaming_available,
            "language": self.language,
            "raw_metadata": self.raw_metadata,
        }
