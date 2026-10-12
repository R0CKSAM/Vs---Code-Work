"""
Media Reporting System - ET BrandEquity Configuration
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


ET_BRAND_EQUITY = WebsiteConfig(
    name="ET BrandEquity",
    key="et_brand_equity",
    url="https://brandequity.economictimes.indiatimes.com/",
    sections=(
        SectionConfig(
            "Marketing",
            "https://brandequity.economictimes.indiatimes.com/news/marketing",
        ),
        SectionConfig(
            "Advertising",
            "https://brandequity.economictimes.indiatimes.com/news/advertising",
        ),
        SectionConfig(
            "Digital",
            "https://brandequity.economictimes.indiatimes.com/news/digital",
        ),
        SectionConfig(
            "Media",
            "https://brandequity.economictimes.indiatimes.com/news/media",
        ),
        SectionConfig(
            "Business of Brands",
            "https://brandequity.economictimes.indiatimes.com/news/business-of-brands",
        ),
        SectionConfig(
            "The People Report",
            "https://brandequity.economictimes.indiatimes.com/news/the-people-report",
        ),
        SectionConfig(
            "Research",
            "https://brandequity.economictimes.indiatimes.com/news/research",
        ),
    ),
)

# Mapping of URL slugs to clean section names
SECTION_SLUG_MAP: dict[str, str] = {
    "marketing": "Marketing",
    "advertising": "Advertising",
    "digital": "Digital",
    "media": "Media",
    "business-of-brands": "Business of Brands",
    "the-people-report": "The People Report",
    "research": "Research",
    "the-pitch-report": "The Pitch Report",
    "agency": "Agency",
    "industry": "Industry",
    "brand-speaks": "Brand Speaks",
    "consumer-insights": "Consumer Insights",
    "trends": "Trends",
    "startups": "Startups",
}
