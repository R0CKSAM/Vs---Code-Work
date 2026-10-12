"""
Media Reporting System - Indian Television Configuration
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


INDIAN_TELEVISION = WebsiteConfig(
    name="Indian Television",
    key="indiantelevision",
    url="https://indiantelevision.com/",
    sections=(
        SectionConfig(
            "Television",
            "https://indiantelevision.com/television/",
        ),
        SectionConfig(
            "MAM",
            "https://indiantelevision.com/mam/",
        ),
        SectionConfig(
            "Marketing",
            "https://indiantelevision.com/category/mam/marketing/",
        ),
        SectionConfig(
            "Media & Advertising",
            "https://indiantelevision.com/category/mam/media-and-advertising/",
        ),
        SectionConfig(
            "iWorld",
            "https://indiantelevision.com/iworld/",
        ),
        SectionConfig(
            "Cable TV",
            "https://indiantelevision.com/cable-tv/",
        ),
        SectionConfig(
            "DTH",
            "https://indiantelevision.com/dth/",
        ),
        SectionConfig(
            "Movies",
            "https://indiantelevision.com/movies/",
        ),
        SectionConfig(
            "Regulators",
            "https://indiantelevision.com/regulators/",
        ),
    ),
)

INDIAN_TELEVISION_SECTION_SLUG_MAP: dict[str, str] = {
    "television": "Television",
    "mam": "MAM",
    "iworld": "iWorld",
    "cable-tv": "Cable TV",
    "dth": "DTH",
    "movies": "Movies",
    "regulators": "Regulators",
    "resources": "Resources",
    "digital": "Digital",
    "marketing": "Marketing",
    "advertising": "Advertising",
    "media-and-advertising": "Media & Advertising",
    "brands": "Brands",
    "gaming": "Gaming",
    "broadband": "Broadband",
    "ott": "OTT",
}
