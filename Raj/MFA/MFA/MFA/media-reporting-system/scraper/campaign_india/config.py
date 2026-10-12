"""
Media Reporting System - Campaign India Configuration
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


CAMPAIGN_INDIA = WebsiteConfig(
    name="Campaign India",
    key="campaign_india",
    url="https://www.campaignindia.in/news",
    sections=(
        SectionConfig(
            "Advertising",
            "https://www.campaignindia.in/section/advertising/1",
        ),
        SectionConfig(
            "Marketing",
            "https://www.campaignindia.in/section/marketing/2",
        ),
        SectionConfig(
            "Media",
            "https://www.campaignindia.in/section/media/3",
        ),
        SectionConfig(
            "Digital",
            "https://www.campaignindia.in/section/digital/4",
        ),
        SectionConfig(
            "People",
            "https://www.campaignindia.in/section/people/5",
        ),
    ),
)

CAMPAIGN_INDIA_SECTION_SLUG_MAP: dict[str, str] = {
    "advertising": "Advertising",
    "marketing": "Marketing",
    "media": "Media",
    "digital": "Digital",
    "people": "People",
    "features": "Features",
    "news": "News",
    "agency": "Advertising",
    "brands": "Marketing",
    "creative": "Advertising",
    "tech": "Digital",
}
