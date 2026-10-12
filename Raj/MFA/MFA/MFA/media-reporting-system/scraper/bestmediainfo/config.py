"""
Media Reporting System - BestMediaInfo Configuration
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


BESTMEDIAINFO = WebsiteConfig(
    name="BestMediaInfo",
    key="bestmediainfo",
    url="https://bestmediainfo.com/",
    sections=(
        SectionConfig(
            "Advertising",
            "https://bestmediainfo.com/category/advertising",
        ),
        SectionConfig(
            "Marketing",
            "https://bestmediainfo.com/category/marketing",
        ),
        SectionConfig(
            "Digital",
            "https://bestmediainfo.com/category/digital",
        ),
        SectionConfig(
            "Television",
            "https://bestmediainfo.com/category/television",
        ),
        SectionConfig(
            "Media",
            "https://bestmediainfo.com/category/media",
        ),
    ),
)

BESTMEDIAINFO_SECTION_SLUG_MAP: dict[str, str] = {
    "advertising": "Advertising",
    "marketing": "Marketing",
    "digital": "Digital",
    "television": "Television",
    "media": "Media",
    "agency": "Advertising",
    "brands": "Marketing",
    "broadcast": "Television",
    "ott": "Digital",
    "print": "Print",
    "people-movement": "People",
    "ooh": "Out Of Home",
}
