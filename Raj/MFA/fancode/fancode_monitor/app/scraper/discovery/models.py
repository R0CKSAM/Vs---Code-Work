"""
models.py – Data models for the FanCode Discovery Engine.

All models use plain dataclasses (no database dependency) so they can
be used by all phases without pulling in SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Page Classification
# ──────────────────────────────────────────────────────────────────────────────

class PageType(str, Enum):
    """
    Classification of a discovered FanCode page.

    Values are derived from OBSERVED URL patterns and page content.
    Do not add values here based on assumptions.
    """
    HOME     = "HOME"
    SCHEDULE = "SCHEDULE"
    LIVE     = "LIVE"
    SPORT    = "SPORT"
    TOUR     = "TOUR"
    MATCH    = "MATCH"
    VIDEO    = "VIDEO"
    SERIES   = "SERIES"
    TEAM     = "TEAM"
    PLAYER   = "PLAYER"
    UNKNOWN  = "UNKNOWN"

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]


# ──────────────────────────────────────────────────────────────────────────────
# Network Event
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class NetworkEvent:
    """
    A single network request observed during Playwright page navigation.

    Only safe, non-sensitive fields are recorded.
    No cookies, tokens, or auth headers.
    """
    url: str
    method: str
    resource_type: str           # "fetch", "xhr", "document", "image", etc.
    status: Optional[int]        # HTTP response status
    content_type: Optional[str]  # response content-type header
    is_json: bool = False        # True if content-type indicates JSON
    observed_on: str = ""        # URL of the page that triggered this request

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "method": self.method,
            "resource_type": self.resource_type,
            "status": self.status,
            "content_type": self.content_type,
            "is_json": self.is_json,
            "observed_on": self.observed_on,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Discovered Page
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DiscoveredPage:
    """
    Metadata collected for a single FanCode page during discovery.
    """
    url: str
    canonical_url: Optional[str]
    title: str
    page_type: PageType
    depth: int                              # crawl depth from homepage (0 = homepage)
    http_status: Optional[int]
    internal_links: List[str] = field(default_factory=list)
    image_urls: List[str] = field(default_factory=list)
    network_events: List[NetworkEvent] = field(default_factory=list)
    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    error: Optional[str] = None             # set if navigation/extraction failed

    @property
    def json_endpoints(self) -> List[NetworkEvent]:
        """Return only the network events that appear to be JSON API calls."""
        return [e for e in self.network_events if e.is_json]

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "page_type": self.page_type.value,
            "depth": self.depth,
            "http_status": self.http_status,
            "internal_links": self.internal_links,
            "image_urls": self.image_urls,
            "json_endpoints": [e.to_dict() for e in self.json_endpoints],
            "all_network_events": len(self.network_events),
            "discovered_at": self.discovered_at.isoformat(),
            "error": self.error,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Discovery Result
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    """
    Aggregated result of a full discovery run.
    """
    base_url: str
    pages: List[DiscoveredPage] = field(default_factory=list)
    all_network_events: List[NetworkEvent] = field(default_factory=list)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    finished_at: Optional[datetime] = None
    terminated_early: bool = False     # True if hit a limit before finishing
    termination_reason: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def unique_urls(self) -> List[str]:
        return list({p.url for p in self.pages})

    @property
    def json_endpoints(self) -> List[NetworkEvent]:
        return [e for e in self.all_network_events if e.is_json]

    @property
    def pages_by_type(self) -> Dict[str, List[DiscoveredPage]]:
        result: Dict[str, List[DiscoveredPage]] = {}
        for page in self.pages:
            key = page.page_type.value
            result.setdefault(key, []).append(page)
        return result

    def to_dict(self) -> Dict:
        return {
            "base_url": self.base_url,
            "page_count": self.page_count,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "terminated_early": self.terminated_early,
            "termination_reason": self.termination_reason,
            "pages": [p.to_dict() for p in self.pages],
            "json_endpoint_count": len(self.json_endpoints),
            "json_endpoints": [e.to_dict() for e in self.json_endpoints],
        }
