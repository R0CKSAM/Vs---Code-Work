"""
Media Reporting System - Text and Media Cleaning Utilities
"""
from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

# Common navigation phrases and menu anchors to reject as headlines
NAVIGATION_LABELS = {
    "home",
    "news",
    "more",
    "view all",
    "read more",
    "see all",
    "click here",
    "see details",
    "subscribe",
    "login",
    "log in",
    "sign in",
    "sign up",
    "register",
    "trending",
    "special reports",
    "videos",
    "video",
    "podcasts",
    "podcast",
    "conclaves",
    "events",
    "awards",
    "webinars",
    "newsletters",
    "follow us",
    "share",
    "whatsapp",
    "facebook",
    "twitter",
    "linkedin",
    "back to top",
    "menu",
    "close",
    "search",
    "contact us",
    "about us",
    "brand equity",
    "et brandequity",
    "the people report",
    "business of brands",
    "the pitch report",
    "marketing",
    "advertising",
    "digital",
    "media",
    "research",
}

# Image substrings indicating icons, logos, or tracking pixels to discard
DISCARD_IMAGE_PATTERNS = [
    re.compile(r"\.svg(\?.*)?$", re.IGNORECASE),
    re.compile(r"(?:logo|icon|pixel|spacer|blank|sprite|arrow|avatar|placeholder)", re.IGNORECASE),
    re.compile(r"img-size-0", re.IGNORECASE),
    re.compile(r"width=1&height=1", re.IGNORECASE),
]


def clean_text(value: Optional[str]) -> str:
    """Cleans raw text by unescaping HTML entities and collapsing multiple whitespaces."""
    if not value:
        return ""
    unescaped = html.unescape(value)
    return re.sub(r"\s+", " ", unescaped).strip()


def is_navigation_text(text: str) -> bool:
    """Checks if a string is a navigation label rather than an article title."""
    cleaned = clean_text(text).lower()
    if not cleaned or len(cleaned) < 12:
        return True
    return cleaned in NAVIGATION_LABELS


def is_valid_image_url(url: Optional[str]) -> bool:
    """Validates whether an image URL points to a real story image rather than an icon/pixel."""
    if not url:
        return False

    url_str = url.strip()
    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        return False

    for pattern in DISCARD_IMAGE_PATTERNS:
        if pattern.search(url_str):
            return False

    return True


def clean_image_url(url: Optional[str], base_url: str = "") -> Optional[str]:
    """Resolves and validates an article image URL, rejecting icons, logos, and tracking pixels."""
    if not url:
        return None

    url_str = url.strip()
    if base_url:
        url_str = urljoin(base_url, url_str)

    if not is_valid_image_url(url_str):
        return None

    return url_str
