"""
Media Reporting System - Social Samosa Configuration
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


SOCIAL_SAMOSA = WebsiteConfig(
    name="Social Samosa",
    key="social_samosa",
    url="https://www.socialsamosa.com/",
    sections=(
        SectionConfig(
            "Social Media",
            "https://www.socialsamosa.com/category/social-media-news/",
        ),
        SectionConfig(
            "Campaigns",
            "https://www.socialsamosa.com/category/campaigns/",
        ),
        SectionConfig(
            "Case Studies",
            "https://www.socialsamosa.com/category/case-studies/",
        ),
        SectionConfig(
            "Interviews",
            "https://www.socialsamosa.com/category/interviews/",
        ),
        SectionConfig(
            "Features",
            "https://www.socialsamosa.com/category/features/",
        ),
    ),
)

SOCIAL_SAMOSA_SECTION_SLUG_MAP: dict[str, str] = {
    "social-media-news": "Social Media",
    "social-media": "Social Media",
    "campaigns": "Campaigns",
    "case-studies": "Case Studies",
    "interviews": "Interviews",
    "features": "Features",
    "agency": "Agencies",
    "brands": "Brands",
    "influencer-marketing": "Influencer Marketing",
    "expert-opinion": "Expert Opinion",
}
