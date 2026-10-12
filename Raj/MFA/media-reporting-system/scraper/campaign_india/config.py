"""
Media Reporting System - Campaign India Configuration
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


CAMPAIGN_INDIA = WebsiteConfig(
    name="Campaign India",
    key="campaign_india",
    url="https://www.campaignindia.in/news",
    sections=(
        SectionConfig(
            "Agencies",
            "https://www.campaignindia.in/news/agencies",
        ),
        SectionConfig(
            "Brands",
            "https://www.campaignindia.in/news/brands",
        ),
        SectionConfig(
            "Creators",
            "https://www.campaignindia.in/news/creators",
        ),
        SectionConfig(
            "Media",
            "https://www.campaignindia.in/news/media",
        ),
        SectionConfig(
            "Digital",
            "https://www.campaignindia.in/news/digital",
        ),
        SectionConfig(
            "PR",
            "https://www.campaignindia.in/news/pr",
        ),
        SectionConfig(
            "Regional",
            "https://www.campaignindia.in/news/regional",
        ),
        SectionConfig(
            "Sports",
            "https://www.campaignindia.in/news/sports",
        ),
        SectionConfig(
            "Technology",
            "https://www.campaignindia.in/news/technology",
        ),
        SectionConfig(
            "People Moves",
            "https://www.campaignindia.in/latest/people-moves",
        ),
        SectionConfig(
            "New Campaigns",
            "https://www.campaignindia.in/latest/new-campaigns",
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
    "agencies": "Agencies",
    "creators": "Creators",
    "pr": "PR",
    "regional": "Regional",
    "sports": "Sports",
    "technology": "Technology",
    "people-moves": "People Moves",
    "new-campaigns": "New Campaigns",
}
