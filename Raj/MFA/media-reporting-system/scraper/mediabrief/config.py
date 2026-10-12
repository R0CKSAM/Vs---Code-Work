"""
Media Reporting System - MediaBrief Configuration
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectionConfig:
    name: str
    url: str
    key: str = ""


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
            "https://mediabrief.com/category/marketing/advertising/",
        ),
        SectionConfig(
            "Marketing",
            "https://mediabrief.com/category/marketing/",
        ),
        SectionConfig(
            "Media",
            "https://mediabrief.com/category/media/",
        ),
        SectionConfig(
            "Digital",
            "https://mediabrief.com/category/digital/",
        ),
        SectionConfig(
            "Television",
            "https://mediabrief.com/category/television/",
        ),
        SectionConfig(
            "OTT",
            "https://mediabrief.com/category/ott/",
        ),
        SectionConfig(
            "Exclusives",
            "https://mediabrief.com/category/exclusives/",
        ),
        SectionConfig(
            "Appointments",
            "https://mediabrief.com/category/appointments/",
        ),
        SectionConfig(
            "News",
            "https://mediabrief.com/category/news/",
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
    "appointments": "Appointments",
    "news": "News",
}
