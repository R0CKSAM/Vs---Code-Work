"""
Media Reporting System - Storyboard18 Configuration
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
            "Brand Makers",
            "https://www.storyboard18.com/brand-makers",
        ),
        SectionConfig(
            "Media & Entertainment",
            "https://www.storyboard18.com/media-and-entertainment",
        ),
        SectionConfig(
            "How It Works",
            "https://www.storyboard18.com/how-it-works",
        ),
        SectionConfig(
            "Trending",
            "https://www.storyboard18.com/trending",
        ),
        SectionConfig(
            "Influencer Marketing",
            "https://www.storyboard18.com/influencer-marketing",
        ),
        SectionConfig(
            "Television",
            "https://www.storyboard18.com/television",
        ),
        SectionConfig(
            "OTT",
            "https://www.storyboard18.com/ott-news",
        ),
        SectionConfig(
            "Social Media",
            "https://www.storyboard18.com/social-media",
        ),
        SectionConfig(
            "Interviews",
            "https://www.storyboard18.com/interviews",
        ),
        SectionConfig(
            "Young Guns",
            "https://www.storyboard18.com/youngguns",
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
    "how-it-works": "How It Works",
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
