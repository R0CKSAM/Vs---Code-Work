"""
Media Reporting System - BestMediaInfo Configuration
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


BESTMEDIAINFO = WebsiteConfig(
    name="BestMediaInfo",
    key="bestmediainfo",
    url="https://bestmediainfo.com/",
    sections=(
        SectionConfig(
            "Advertising",
            "https://bestmediainfo.com/mediainfo/advertising",
        ),
        SectionConfig(
            "Marketing",
            "https://bestmediainfo.com/mediainfo/mediainfo-marketing",
        ),
        SectionConfig(
            "Digital",
            "https://bestmediainfo.com/mediainfo/mediainfo-digital",
        ),
        SectionConfig(
            "Television",
            "https://bestmediainfo.com/mediainfo/television",
        ),
        SectionConfig(
            "Print",
            "https://bestmediainfo.com/mediainfo/print",
        ),
        SectionConfig(
            "Radio",
            "https://bestmediainfo.com/mediainfo/mediainfo-radio",
        ),
        SectionConfig(
            "Ad Craft",
            "https://bestmediainfo.com/ad-craft",
        ),
        SectionConfig(
            "Insights",
            "https://bestmediainfo.com/insights",
        ),
        SectionConfig(
            "Guest Times",
            "https://bestmediainfo.com/guest-times",
        ),
        SectionConfig(
            "Partner Content",
            "https://bestmediainfo.com/partner-content",
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
    "mediainfo-marketing": "Marketing",
    "mediainfo-digital": "Digital",
    "mediainfo-radio": "Radio",
    "ad-craft": "Ad Craft",
    "insights": "Insights",
    "guest-times": "Guest Times",
    "partner-content": "Partner Content",
}
