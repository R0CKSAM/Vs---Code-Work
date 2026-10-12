"""
Media Reporting System - Exchange4media Configuration
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


EXCHANGE4MEDIA = WebsiteConfig(
    name="Exchange4media",
    key="exchange4media",
    url="https://www.exchange4media.com/",
    sections=(
        SectionConfig("Advertising", "https://www.exchange4media.com/advertising-news.html"),
        SectionConfig("Marketing", "https://www.exchange4media.com/marketing-news.html"),
        SectionConfig("PR & Corporate Communication", "https://www.exchange4media.com/pr-and-corporate-communication-news.html"),
        SectionConfig("Television", "https://www.exchange4media.com/media-tv-news.html"),
        SectionConfig("Radio", "https://www.exchange4media.com/media-radio-news.html"),
        SectionConfig("Digital", "https://www.exchange4media.com/digital-news.html"),
        SectionConfig("Out Of Home", "https://www.exchange4media.com/out-of-home-news.html"),
        SectionConfig("Print", "https://www.exchange4media.com/media-print-news.html"),
        SectionConfig("Media Others", "https://www.exchange4media.com/media-others-news.html"),
        SectionConfig("Experiential Marketing", "https://www.exchange4media.com/experiential-marketing-news.html"),
        SectionConfig("People Movement", "https://www.exchange4media.com/people-movement-news.html"),
        SectionConfig("Festive Season", "https://www.exchange4media.com/festive-season-news.html"),
        SectionConfig("Marketing Initiative", "https://www.exchange4media.com/marketing-initiative-news.html"),
        SectionConfig("Industry Briefing", "https://www.exchange4media.com/industry-briefing-news.html"),
        SectionConfig("Cannes Lions", "https://www.exchange4media.com/cannes-lions-news.html"),
        SectionConfig("IPL 2026", "https://www.exchange4media.com/ipl-2026-news.html"),
        SectionConfig("Goafest", "https://www.exchange4media.com/goa-fest-news.html"),
        SectionConfig("Budget", "https://www.exchange4media.com/budget-news.html"),
        SectionConfig("Trends Watch", "https://www.exchange4media.com/trends-watch-news.html"),
        SectionConfig("Influence Zone", "https://www.exchange4media.com/influence-zone-news.html"),
        SectionConfig("Women's Day", "https://www.exchange4media.com/womens-day-news.html"),
        SectionConfig("Tech Talk", "https://www.exchange4media.com/tech-talk-news.html"),
        SectionConfig("E4M Blogs", "https://www.exchange4media.com/e4m-blogs-news.html"),
        SectionConfig("ICC World Cup", "https://www.exchange4media.com/icc-world-cup-news.html"),
        SectionConfig("Announcements", "https://www.exchange4media.com/announcements-news.html"),
        SectionConfig("Budget 2025", "https://www.exchange4media.com/budget-2025-news.html"),
        SectionConfig("IPL 2025", "https://www.exchange4media.com/ipl-2025-news.html"),
        SectionConfig("Latest News", "https://www.exchange4media.com/latest-news.html"),
        SectionConfig("Guest Column", "https://www.exchange4media.com/guest-column-news.html"),
        SectionConfig("Spotlight", "https://www.exchange4media.com/spotlight-news.html"),
        SectionConfig("Brand Speak", "https://www.exchange4media.com/brand-speak-news.html"),
        SectionConfig("Interviews", "https://www.exchange4media.com/interviews-news.html"),
    ),
)

# Mapping of URL slugs to clean, normalized section names
E4M_SECTION_SLUG_MAP: dict[str, str] = {
    "advertising-news": "Advertising",
    "marketing-news": "Marketing",
    "digital-news": "Digital",
    "media-others-news": "Media",
    "television-news": "Television",
    "print-news": "Print",
    "ooh-news": "Out Of Home",
    "people-movement-news": "People Movement",
    "industry-briefing-news": "Industry Briefing",
    "pr-and-corporate-communication-news": "PR & Corporate Communication",
    "media-tv-news": "Television",
    "media-radio-news": "Radio",
    "out-of-home-news": "Out Of Home",
    "media-print-news": "Print",
    "experiential-marketing-news": "Experiential Marketing",
    "festive-season-news": "Festive Season",
    "marketing-initiative-news": "Marketing Initiative",
    "cannes-lions-news": "Cannes Lions",
    "ipl-2026-news": "IPL 2026",
    "goa-fest-news": "Goafest",
    "budget-news": "Budget",
    "trends-watch-news": "Trends Watch",
    "influence-zone-news": "Influence Zone",
    "womens-day-news": "Women's Day",
    "tech-talk-news": "Tech Talk",
    "e4m-blogs-news": "E4M Blogs",
    "icc-world-cup-news": "ICC World Cup",
    "announcements-news": "Announcements",
    "budget-2025-news": "Budget 2025",
    "ipl-2025-news": "IPL 2025",
    "broadcasting-news": "Television",
    "advertising": "Advertising",
    "marketing": "Marketing",
    "digital": "Digital",
    "media": "Media",
    "television": "Television",
    "print": "Print",
    "ooh": "Out Of Home",
    "people-movement": "People Movement",
    "pr-news": "Public Relations",
    "brands": "Brands",
    "agency": "Advertising",
    "latest-news": "Latest News",
    "guest-column-news": "Guest Column",
    "guest-column": "Guest Column",
    "spotlight-news": "Spotlight",
    "spotlight": "Spotlight",
    "brand-speak-news": "Brand Speak",
    "brand-speak": "Brand Speak",
    "interviews-news": "Interviews",
    "interviews": "Interviews",
    "all-news": "Overall",
    "all": "Overall",
}
