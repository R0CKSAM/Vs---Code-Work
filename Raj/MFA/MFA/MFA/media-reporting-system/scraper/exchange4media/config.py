"""
Media Reporting System - Exchange4media Configuration
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


EXCHANGE4MEDIA = WebsiteConfig(
    name="Exchange4media",
    key="exchange4media",
    url="https://www.exchange4media.com/",
    sections=(
        SectionConfig(
            "Advertising",
            "https://www.exchange4media.com/advertising-news",
        ),
        SectionConfig(
            "Marketing",
            "https://www.exchange4media.com/marketing-news",
        ),
        SectionConfig(
            "Digital",
            "https://www.exchange4media.com/digital-news",
        ),
        SectionConfig(
            "Media",
            "https://www.exchange4media.com/media-others-news",
        ),
        SectionConfig(
            "Television",
            "https://www.exchange4media.com/television-news",
        ),
        SectionConfig(
            "Print",
            "https://www.exchange4media.com/print-news",
        ),
        SectionConfig(
            "Out Of Home",
            "https://www.exchange4media.com/ooh-news",
        ),
        SectionConfig(
            "People Movement",
            "https://www.exchange4media.com/people-movement-news",
        ),
        SectionConfig(
            "Industry Briefing",
            "https://www.exchange4media.com/industry-briefing-news",
        ),
    ),
)

# Mapping of URL slugs to clean, normalized section names
E4M_SECTION_SLUG_MAP: dict[str, str] = {
    "advertising-news": "Advertising",
    "marketing-news": "Marketing",
    "digital-news": "Digital",
    "media-others-news": "Media",
    "television-news": "Television",
    "print-news": "Print",
    "ooh-news": "Out Of Home",
    "people-movement-news": "People Movement",
    "industry-briefing-news": "Industry Briefing",
    "broadcasting-news": "Television",
    "announcements-news": "Announcements",
    "advertising": "Advertising",
    "marketing": "Marketing",
    "digital": "Digital",
    "media": "Media",
    "television": "Television",
    "print": "Print",
    "ooh": "Out Of Home",
    "people-movement": "People Movement",
    "pr-news": "Public Relations",
    "brands": "Brands",
    "agency": "Advertising",
}
