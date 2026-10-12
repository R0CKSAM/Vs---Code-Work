"""
Media Reporting System - Social Samosa Configuration
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


SOCIAL_SAMOSA = WebsiteConfig(
    name="Social Samosa",
    key="social_samosa",
    url="https://www.socialsamosa.com/",
    sections=(
        SectionConfig(
            "Industry Updates",
            "https://www.socialsamosa.com/industry-updates",
        ),
        SectionConfig(
            "Campaign Spot",
            "https://www.socialsamosa.com/campaign-spot",
        ),
        SectionConfig(
            "Campaign Features",
            "https://www.socialsamosa.com/campaign-feature",
        ),
        SectionConfig(
            "Campaign Reviews",
            "https://www.socialsamosa.com/campaign-reviews",
        ),
        SectionConfig(
            "Campaign Face Off",
            "https://www.socialsamosa.com/campaign-face-off",
        ),
        SectionConfig(
            "Topical Spot",
            "https://www.socialsamosa.com/topical-spot",
        ),
        SectionConfig(
            "Ad Spot",
            "https://www.socialsamosa.com/ad-spot",
        ),
        SectionConfig(
            "Interviews",
            "https://www.socialsamosa.com/interviews",
        ),
        SectionConfig(
            "Case Studies",
            "https://www.socialsamosa.com/indian-social-media-case-studies",
        ),
        SectionConfig(
            "Social Media Strategy",
            "https://www.socialsamosa.com/social-media-strategy",
        ),
        SectionConfig(
            "Experts Speak",
            "https://www.socialsamosa.com/experts-speak",
        ),
        SectionConfig(
            "Brand Saga",
            "https://www.socialsamosa.com/brand-saga",
        ),
        SectionConfig(
            "Deep Dive",
            "https://www.socialsamosa.com/deep-dive",
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
    "industry-updates": "Industry Updates",
    "campaign-spot": "Campaign Spot",
    "campaign-feature": "Campaign Features",
    "campaign-reviews": "Campaign Reviews",
    "campaign-face-off": "Campaign Face Off",
    "topical-spot": "Topical Spot",
    "ad-spot": "Ad Spot",
    "experts-speak": "Experts Speak",
    "brand-saga": "Brand Saga",
    "deep-dive": "Deep Dive",
    "indian-social-media-case-studies": "Case Studies",
    "social-media-strategy": "Social Media Strategy",
}
