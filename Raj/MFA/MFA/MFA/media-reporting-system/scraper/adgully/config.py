"""
Media Reporting System - Adgully Configuration
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectionConfig:
    name: str
    url: str


@dataclass(frozen=True)
class WebsiteConfig:
    name: str
    key: str
    url: str
    sections: tuple[SectionConfig, ...] = field(default_factory=tuple)


ADGULLY = WebsiteConfig(
    name="Adgully",
    key="adgully",
    url="https://www.adgully.com/",
    sections=(
        SectionConfig(
            "Marketing",
            "https://www.adgully.com/category/marketing",
        ),
        SectionConfig(
            "Advertising",
            "https://www.adgully.com/category/advertising",
        ),
        SectionConfig(
            "Media",
            "https://www.adgully.com/category/media",
        ),
        SectionConfig(
            "Digital",
            "https://www.adgully.com/category/digital",
        ),
        SectionConfig(
            "Exclusives",
            "https://www.adgully.com/category/exclusives",
        ),
    ),
)

ADGULLY_SECTION_SLUG_MAP: dict[str, str] = {
    "marketing": "Marketing",
    "advertising": "Advertising",
    "media": "Media",
    "digital": "Digital",
    "exclusives": "Exclusives",
    "the-pitch-report": "The Pitch Report",
    "people": "People",
    "brand": "Brands",
    "agency": "Agencies",
    "broadcast": "Broadcast",
    "technology": "Technology",
}
