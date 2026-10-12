"""
models.py – Normalized TourRecord model for Tours Scraper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class TourRecord:
    """Normalized tour / series / competition item ready for database persistence."""
    name: str
    slug: str
    source_url: str
    external_id: Optional[str] = None
    sport_external_id: Optional[str] = None
    sport_name: Optional[str] = None
    sport_slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "source_url": self.source_url,
            "external_id": self.external_id,
            "sport_external_id": self.sport_external_id,
            "sport_name": self.sport_name,
            "sport_slug": self.sport_slug,
            "description": self.description,
            "image_url": self.image_url,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "raw_metadata": self.raw_metadata,
        }
