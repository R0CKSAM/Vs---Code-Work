"""
Media Reporting System - Storyboard18 Configuration
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


STORYBOARD18 = WebsiteConfig(
    name="Storyboard18",
    key="storyboard18",
    url="https://www.storyboard18.com/",
    sections=(
        SectionConfig(
            "Latest News",
            "https://www.storyboard18.com/latest-news",
        ),
        SectionConfig(
            "Advertising",
            "https://www.storyboard18.com/advertising",
        ),
        SectionConfig(
            "Agency",
            "https://www.storyboard18.com/agency-news",
        ),
        SectionConfig(
            "Digital",
            "https://www.storyboard18.com/digital",
        ),
        SectionConfig(
            "Brand Marketing",
            "https://www.storyboard18.com/brand-marketing",
        ),
        SectionConfig(
            "Media & Entertainment",
            "https://www.storyboard18.com/media-and-entertainment",
        ),
    ),
)

STORYBOARD18_SECTION_SLUG_MAP: dict[str, str] = {
    "latest-news": "Latest News",
    "advertising": "Advertising",
    "agency-news": "Agency",
    "digital": "Digital",
    "brand-marketing": "Brand Marketing",
    "brand-makers": "Brand Makers",
    "media-and-entertainment": "Media & Entertainment",
    "how-it-works": "How it Works",
    "trending": "Trending",
    "influencer-marketing": "Influencer Marketing",
    "brand-connect-initiative": "Brand Connect Initiative",
    "television": "Television",
    "ott-news": "OTT",
    "social-media": "Social Media",
    "gaming-news": "Gaming News",
    "interviews": "Interviews",
    "youngguns": "Young Guns",
}
