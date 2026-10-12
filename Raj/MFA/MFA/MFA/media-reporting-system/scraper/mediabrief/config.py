"""
Media Reporting System - MediaBrief Configuration
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


MEDIABRIEF = WebsiteConfig(
    name="MediaBrief",
    key="mediabrief",
    url="https://mediabrief.com/",
    sections=(
        SectionConfig(
            "Advertising",
            "https://mediabrief.com/advertising/",
        ),
        SectionConfig(
            "Marketing",
            "https://mediabrief.com/marketing/",
        ),
        SectionConfig(
            "Media",
            "https://mediabrief.com/media/",
        ),
        SectionConfig(
            "Digital",
            "https://mediabrief.com/digital/",
        ),
        SectionConfig(
            "Exclusive",
            "https://mediabrief.com/exclusive/",
        ),
    ),
)

MEDIABRIEF_SECTION_SLUG_MAP: dict[str, str] = {
    "advertising": "Advertising",
    "marketing": "Marketing",
    "media": "Media",
    "digital": "Digital",
    "exclusive": "Exclusive",
    "exclusives": "Exclusive",
    "broadcast": "Broadcast",
    "people": "People",
    "brand": "Brands",
    "brands": "Brands",
    "ott": "OTT",
    "television": "Television",
}
