"""
Media Reporting System - Adgully Configuration
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


ADGULLY = WebsiteConfig(
    name="Adgully",
    key="adgully",
    url="https://www.adgully.com/",
    sections=(
        SectionConfig(
            "Marketing",
            "https://www.adgully.com/marketing",
        ),
        SectionConfig(
            "Advertising",
            "https://www.adgully.com/advertising",
        ),
        SectionConfig(
            "Media",
            "https://www.adgully.com/media",
        ),
        SectionConfig(
            "Digital",
            "https://www.adgully.com/digital",
        ),
        SectionConfig(
            "Entertainment",
            "https://www.adgully.com/entertainment",
        ),
        SectionConfig(
            "Exclusives",
            "https://www.adgully.com/exclusives",
        ),
        SectionConfig(
            "People Movement",
            "https://www.adgully.com/people-movement",
        ),
        SectionConfig(
            "Account Wins",
            "https://www.adgully.com/account-wins",
        ),
        SectionConfig(
            "Global",
            "https://www.adgully.com/global",
        ),
        SectionConfig(
            "AG Voice",
            "https://www.adgully.com/ag-voice",
        ),
        SectionConfig(
            "Focus East",
            "https://www.adgully.com/focus-east",
        ),
        SectionConfig(
            "Focus South",
            "https://www.adgully.com/focus-south",
        ),
        SectionConfig(
            "Technology",
            "https://www.adgully.com/technology",
        ),
        SectionConfig(
            "The Adtech Edge",
            "https://www.adgully.com/the-adtech-edge",
        ),
    ),
)

ADGULLY_SECTION_SLUG_MAP: dict[str, str] = {
    "marketing": "Marketing",
    "advertising": "Advertising",
    "media": "Media",
    "digital": "Digital",
    "entertainment": "Entertainment",
    "exclusives": "Exclusives",
    "the-pitch-report": "The Pitch Report",
    "people": "People Movement",
    "people-movement": "People Movement",
    "brand": "Brands",
    "agency": "Advertising",
    "broadcast": "Broadcast",
    "technology": "Technology",
    "account-wins": "Account Wins",
    "global": "Global",
    "ag-voice": "AG Voice",
    "focus-east": "Focus East",
    "focus-south": "Focus South",
    "the-adtech-edge": "The Adtech Edge",
}
