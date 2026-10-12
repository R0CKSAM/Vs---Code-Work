"""
Media Reporting System - ET BrandEquity Configuration
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


ET_BRAND_EQUITY = WebsiteConfig(
    name="ET BrandEquity",
    key="et_brand_equity",
    url="https://brandequity.economictimes.indiatimes.com/",
    sections=(
        SectionConfig(
            "Latest News",
            "https://brandequity.economictimes.indiatimes.com/latest-news",
            key="latest-news",
        ),
        SectionConfig(
            "Marketing",
            "https://brandequity.economictimes.indiatimes.com/news/marketing",
            key="marketing",
        ),
        SectionConfig(
            "Advertising",
            "https://brandequity.economictimes.indiatimes.com/news/advertising",
            key="advertising",
        ),
        SectionConfig(
            "Digital",
            "https://brandequity.economictimes.indiatimes.com/news/digital",
            key="digital",
        ),
        SectionConfig(
            "Media",
            "https://brandequity.economictimes.indiatimes.com/news/media",
            key="media",
        ),
        SectionConfig(
            "Business of Brands",
            "https://brandequity.economictimes.indiatimes.com/news/business-of-brands",
            key="business-of-brands",
        ),
        SectionConfig(
            "The People Report",
            "https://brandequity.economictimes.indiatimes.com/news/the-people-report",
            key="the-people-report",
        ),
        SectionConfig(
            "The Pitch Report",
            "https://brandequity.economictimes.indiatimes.com/news/the-pitch-report",
            key="the-pitch-report",
        ),
        SectionConfig(
            "Research",
            "https://brandequity.economictimes.indiatimes.com/news/research",
            key="research",
        ),
        SectionConfig(
            "News",
            "https://brandequity.economictimes.indiatimes.com/news",
            key="news",
        ),
        SectionConfig(
            "Exclusives",
            "https://brandequity.economictimes.indiatimes.com/exclusives",
            key="exclusives",
        ),
    ),
)

# Mapping of URL slugs to clean section names
SECTION_SLUG_MAP: dict[str, str] = {
    "latest-news": "Latest News",
    "exclusives": "Exclusives",
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
