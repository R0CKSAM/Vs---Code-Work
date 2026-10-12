"""
models.py – Data models for FanCode Live Now scraper.

Represents raw extracted payloads and normalized current live match records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class RawLiveItem:
    """Raw payload captured from network JSON, embedded Next.js state, or rendered DOM."""
    raw_data: Any
    source_type: str = "json"  # "json", "embedded", "dom"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LiveMatchRecord:
    """Normalized live match entity reflecting active live-state."""
    match_external_id: Optional[str] = None
    source_url: str = ""
    title: str = ""
    status: str = "LIVE"
    sport_id: Optional[str] = None
    sport_name: Optional[str] = None
    tour_id: Optional[str] = None
    tour_name: Optional[str] = None
    match_id: Optional[int] = None
    match_title: Optional[str] = None
    start_time: Optional[str] = None
    match_date: Optional[datetime] = None
    live_started_at: Optional[datetime] = None
    venue: Optional[str] = None
    team_a_name: Optional[str] = None
    team_b_name: Optional[str] = None
    team_a_id: Optional[str] = None
    team_b_id: Optional[str] = None
    team_a_logo: Optional[str] = None
    team_b_logo: Optional[str] = None
    score_summary: Optional[str] = None
    stream_available: Optional[bool] = None
    stream_language: Optional[str] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
