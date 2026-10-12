"""
models.py – Normalized SportRecord model for Sports Scraper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SportRecord:
    """Normalized sport item ready for database persistence."""
    name: str
    slug: str
    source_url: str
    external_id: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "source_url": self.source_url,
            "external_id": self.external_id,
            "description": self.description,
            "image_url": self.image_url,
            "is_active": self.is_active,
            "raw_metadata": self.raw_metadata,
        }
