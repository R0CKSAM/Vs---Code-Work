"""
Media Reporting System - URL Utilities
Handles URL normalization, tracking query stripping, and ET BrandEquity article URL validation.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

# Query parameters commonly used for analytics and tracking that should be stripped
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "amp",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "ncid",
    "msclkid",
}

# Subpaths on ET BrandEquity that are never single news articles
BLOCKED_PATH_KEYWORDS = {
    "/login",
    "/register",
    "/newsletter",
    "/newsletters",
    "/search",
    "/subscribe",
    "/subscription",
    "/privacy",
    "/privacy-policy",
    "/terms",
    "/terms-conditions",
    "/contact",
    "/contact-us",
    "/events",
    "/event",
    "/videos",
    "/video",
    "/webinars",
    "/webinar",
    "/awards",
    "/award",
    "/brand-speaks",
    "/tag/",
    "/topic/",
    "/authors/",
    "/author/",
    "/rss",
    "/podcast",
    "/podcasts",
    "/whitepapers",
    "/advertise-with-us",
}

# Regex to detect an article ID (typically 7-10 consecutive digits) at the end of an ET URL path
ET_ARTICLE_ID_PATTERN = re.compile(r"/(\d{7,10})(?:/|\.cms)?$")


def normalize_url(url: str, base_url: str = "") -> str:
    """
    Normalizes a URL by:
    - Resolving relative paths against base_url
    - Trimming whitespace
    - Lowercasing scheme and netloc
    - Removing trailing hash fragments
    - Stripping known marketing/tracking query parameters
    - Normalizing trailing slash for root or keeping canonical article slug
    """
    if not url:
        return ""

    url = url.strip()
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)

    # Clean query parameters
    cleaned_params = []
    if parsed.query:
        for k, v in parse_qsl(parsed.query, keep_blank_values=False):
            if k.lower() not in TRACKING_PARAMS:
                cleaned_params.append((k, v))

    # Reassemble URL without fragments
    clean_query = urlencode(cleaned_params) if cleaned_params else ""
    clean_url = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        "",  # params
        clean_query,
        "",  # fragment
    ))

    return clean_url


def is_valid_et_article_url(url: str) -> bool:
    """
    Determines whether a URL represents a genuine single article on ET BrandEquity.
    
    Validation criteria:
    - Host must belong to ET BrandEquity (brandequity.economictimes.indiatimes.com)
    - Path must contain /news/
    - Must NOT be an excluded path (e.g. newsletters, events, login)
    - Must have a numerical article identifier at the end of the path
    """
    if not url:
        return False

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    if netloc and "brandequity.economictimes.indiatimes.com" not in netloc:
        return False

    path = parsed.path.lower()

    # Must be under /news/
    if "/news/" not in path:
        return False

    # Skip blocked paths
    for blocked in BLOCKED_PATH_KEYWORDS:
        if blocked in path:
            return False

    # Check for presence of article numeric ID
    # Valid article format: /news/<section>/<slug>/<id> or /news/<section>/<sub-section>/<slug>/<id>
    # Category pages like /news/marketing or /news/the-people-report do not have an ID.
    match = ET_ARTICLE_ID_PATTERN.search(parsed.path)
    return match is not None


def extract_et_article_id(url: str) -> Optional[str]:
    """Extracts numeric article ID from an ET BrandEquity article URL."""
    parsed = urlparse(url)
    match = ET_ARTICLE_ID_PATTERN.search(parsed.path)
    return match.group(1) if match else None


def extract_section_slug_from_url(url: str) -> Optional[str]:
    """
    Extracts the section slug from an ET BrandEquity URL path.
    Example:
      /news/marketing/brands-want-reddit.../134424838 -> 'marketing'
      /news/business-of-brands/dixon-eyes.../134427673 -> 'business-of-brands'
      /news/the-people-report/dentsu-india.../134426873 -> 'the-people-report'
      /news/research/advertising/.../134427982 -> 'advertising' or 'research'
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")

    # Expect: ['news', '<section>', ...]
    if len(parts) >= 3 and parts[0].lower() == "news":
        # Check if parts[1] is 'research' and parts[2] is a subcategory
        if parts[1].lower() == "research" and len(parts) >= 4 and not parts[2].isdigit():
            return parts[2].lower()
        return parts[1].lower()

    return None


# ---------------------------------------------------------------------------
# Exchange4media URL Detection & Utilities
# ---------------------------------------------------------------------------
E4M_ARTICLE_PATTERN = re.compile(r"/[a-z0-9_-]+-news/[a-z0-9_-]+-(?:\d{4,9})\.html", re.IGNORECASE)
E4M_GENERIC_ARTICLE_PATTERN = re.compile(r"/[a-z0-9_-]+-news/[a-z0-9_-]+\.html$", re.IGNORECASE)
E4M_ARTICLE_ID_PATTERN = re.compile(r"-(\d{4,9})\.html$", re.IGNORECASE)

E4M_BLOCKED_PATH_KEYWORDS = {
    "/events",
    "/event",
    "/awards",
    "/award",
    "/roundtable",
    "/webinar",
    "/webinars",
    "/magazine",
    "/epaper",
    "/e-summits",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/privacy-policy",
    "/terms",
    "/terms-and-conditions",
    "/advertise-with-us",
    "/newsletter",
    "/newsletters",
    "/subscribe",
    "/subscription",
    "/login",
    "/register",
    "/authors/",
    "/author/",
    "/tag/",
    "/topic/",
    "/video/",
    "/videos/",
    "/photo-gallery",
    "/rss",
    "/sitemap",
}


def is_valid_e4m_article_url(url: str) -> bool:
    """
    Determines whether a URL represents a genuine single article on Exchange4media.
    
    Validation criteria:
    - Host must belong to Exchange4media (exchange4media.com)
    - Path must NOT be an excluded path (events, awards, contact, login, etc.)
    - Path must contain an editorial section (e.g. -news/) and end with .html
    - Must not be a section listing root (e.g. /advertising-news or /marketing-news/)
    """
    if not url:
        return False

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    if netloc and "exchange4media.com" not in netloc:
        return False

    path = parsed.path.lower()

    # Skip blocked paths
    for blocked in E4M_BLOCKED_PATH_KEYWORDS:
        if blocked in path:
            return False

    # Check for article path: must contain a section slug and end with .html
    if "-news/" in path and path.endswith(".html"):
        # Ensure it has an article slug between the section and .html
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[-1].endswith(".html") and len(parts[-1]) > 8:
            return True

    # Fallback pattern check
    if E4M_ARTICLE_PATTERN.search(parsed.path) or E4M_GENERIC_ARTICLE_PATTERN.search(parsed.path):
        return True

    return False


def extract_e4m_article_id(url: str) -> Optional[str]:
    """Extracts numeric article ID from an Exchange4media article URL if present."""
    parsed = urlparse(url)
    match = E4M_ARTICLE_ID_PATTERN.search(parsed.path)
    return match.group(1) if match else None


def extract_e4m_section_slug(url: str) -> Optional[str]:
    """
    Extracts the section slug from an Exchange4media URL path.
    Example:
      /advertising-news/pitch-madison-report-142839.html -> 'advertising-news'
      /marketing-news/brand-strategy-update-142840.html -> 'marketing-news'
      /digital-news/ad-spends-ai-142841.html -> 'digital-news'
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")

    if len(parts) >= 2:
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# Campaign India URL Detection & Utilities
# ---------------------------------------------------------------------------
CAMPAIGN_INDIA_BLOCKED_PATHS = {
    "/login", "/register", "/newsletter", "/newsletters", "/search",
    "/subscribe", "/subscription", "/privacy", "/privacy-policy",
    "/terms", "/terms-conditions", "/contact", "/contact-us",
    "/events", "/event", "/awards", "/award", "/author/", "/authors/",
    "/tag/", "/topic/", "/rss", "/podcast", "/podcasts",
    "/advertise-with-us", "/jobs", "/bulletin",
}

CAMPAIGN_INDIA_ID_PATTERN = re.compile(r"/(\d{4,9})(?:/|\.html)?$", re.IGNORECASE)


def is_valid_campaign_india_article_url(url: str) -> bool:
    """Validates if a URL is a genuine Campaign India article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "campaignindia.in" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/news", "/news/", "/article", "/article/"):
        return False
    for blocked in CAMPAIGN_INDIA_BLOCKED_PATHS:
        if blocked in path:
            return False
    if "/article/" in path:
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and len(parts[-1]) >= 3:
            return True
    if CAMPAIGN_INDIA_ID_PATTERN.search(parsed.path):
        return True
    parts = path.strip("/").split("/")
    if len(parts) >= 1 and len(parts[-1]) >= 15 and "-" in parts[-1]:
        return True
    return False


def extract_campaign_india_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    match = CAMPAIGN_INDIA_ID_PATTERN.search(parsed.path)
    if match:
        return match.group(1)
    parts = parsed.path.strip("/").split("/")
    return parts[-1] if parts and len(parts[-1]) >= 5 else None


def extract_campaign_india_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) >= 3 and parts[0].lower() == "article":
        return parts[1].lower()
    return None


# ---------------------------------------------------------------------------
# BestMediaInfo URL Detection & Utilities
# ---------------------------------------------------------------------------
BESTMEDIAINFO_BLOCKED_PATHS = {
    "/about-us", "/contact-us", "/privacy-policy", "/terms-and-conditions",
    "/advertise-with-us", "/tag/", "/category/", "/author/", "/page/",
    "/search", "/events", "/awards", "/login", "/register", "/feed", "/rss",
}


def is_valid_bestmediainfo_article_url(url: str) -> bool:
    """Validates if a URL is a genuine BestMediaInfo article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "bestmediainfo.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/home", "/index.php"):
        return False
    for blocked in BESTMEDIAINFO_BLOCKED_PATHS:
        if blocked in path:
            return False
    parts = path.strip("/").split("/")
    # Handle YYYY/MM/slug format or /post/slug or general article slug
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4:
        return True
    if len(parts) >= 2 and parts[0] in ("post", "news", "marketing", "advertising", "digital"):
        return True
    if len(parts) >= 1 and len(parts[-1]) >= 15 and "-" in parts[-1]:
        return True
    return False


def extract_bestmediainfo_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if not parts or parts == [""]:
        return None
    match = re.search(r"-(\d{3,9})$", parts[-1])
    if match:
        return match.group(1)
    return parts[-1]


def extract_bestmediainfo_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and not parts[0].isdigit():
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# Social Samosa URL Detection & Utilities
# ---------------------------------------------------------------------------
SOCIAL_SAMOSA_BLOCKED_PATHS = {
    "/about-us", "/contact-us", "/privacy-policy", "/terms", "/terms-conditions",
    "/advertise-with-us", "/tag/", "/category/", "/author/", "/feed",
    "/page/", "/events", "/awards", "/subscribe", "/search",
    "/ss-super-40", "/agencycon", "/samosa-talks",
}


def is_valid_social_samosa_article_url(url: str) -> bool:
    """Validates if a URL is a genuine Social Samosa article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "socialsamosa.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/feed", "/wp-content", "/wp-admin"):
        return False
    for blocked in SOCIAL_SAMOSA_BLOCKED_PATHS:
        if blocked in path:
            return False
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4:
        return True
    if len(parts) >= 1 and len(parts[-1]) >= 12 and parts[-1].count("-") >= 2:
        return True
    return False


def extract_social_samosa_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    return parts[-1] if parts and parts[-1] else None


def extract_social_samosa_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and not parts[0].isdigit():
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# Adgully URL Detection & Utilities
# ---------------------------------------------------------------------------
ADGULLY_BLOCKED_PATHS = {
    "/about-us", "/contact-us", "/privacy-policy", "/terms",
    "/terms-and-conditions", "/advertise-with-us", "/tag/",
    "/category/", "/author/", "/events", "/awards", "/search",
    "/subscribe", "/login", "/register", "/rss",
}

ADGULLY_ARTICLE_ID_PATTERN = re.compile(r"-(\d{4,9})(?:\.html)?$", re.IGNORECASE)


def is_valid_adgully_article_url(url: str) -> bool:
    """Validates if a URL is a genuine Adgully article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "adgully.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/index.html", "/index.php"):
        return False
    for blocked in ADGULLY_BLOCKED_PATHS:
        if blocked in path:
            return False
    if path.endswith(".html") and len(path) >= 15:
        return True
    if ADGULLY_ARTICLE_ID_PATTERN.search(parsed.path):
        return True
    parts = path.strip("/").split("/")
    if len(parts) >= 1 and len(parts[-1]) >= 15 and "-" in parts[-1]:
        return True
    return False


def extract_adgully_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    match = ADGULLY_ARTICLE_ID_PATTERN.search(parsed.path)
    if match:
        return match.group(1)
    parts = parsed.path.strip("/").replace(".html", "").split("/")
    return parts[-1] if parts else None


def extract_adgully_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# MediaBrief URL Detection & Utilities
# ---------------------------------------------------------------------------
MEDIABRIEF_BLOCKED_PATHS = {
    "/about-us", "/contact-us", "/privacy-policy", "/terms",
    "/terms-and-conditions", "/advertise-with-us", "/tag/",
    "/category/", "/author/", "/feed", "/page/", "/podcasts/",
    "/events/", "/subscribe", "/search",
}


def is_valid_mediabrief_article_url(url: str) -> bool:
    """Validates if a URL is a genuine MediaBrief article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "mediabrief.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/feed", "/wp-admin", "/wp-content"):
        return False
    for blocked in MEDIABRIEF_BLOCKED_PATHS:
        if blocked in path:
            return False
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4:
        return True
    if len(parts) >= 1 and len(parts[-1]) >= 12 and parts[-1].count("-") >= 2:
        return True
    return False


def extract_mediabrief_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    return parts[-1] if parts and parts[-1] else None


def extract_mediabrief_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and not parts[0].isdigit():
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# Storyboard18 URL Detection & Utilities
# ---------------------------------------------------------------------------
STORYBOARD18_BLOCKED_PATHS = {
    "/about_us", "/contact-us", "/privacy-policy", "/terms",
    "/disclaimer", "/sitemap", "/rss", "/photos", "/videos",
    "/latest-news", "/special-coverage", "/brand-makers", "/how-it-works",
    "/trending", "/interviews", "/youngguns", "/the-visionaries",
    "/storyboard18-awards", "/power-of-purpose", "/des", "/tags/",
    "/category/", "/author/", "/page/", "/search",
}

STORYBOARD18_ARTICLE_ID_PATTERN = re.compile(r"-(\d{4,10})\.htm$", re.IGNORECASE)


def is_valid_storyboard18_article_url(url: str) -> bool:
    """Validates if a URL is a genuine Storyboard18 article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "storyboard18.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/latest-news", "/index.html"):
        return False
    for blocked in STORYBOARD18_BLOCKED_PATHS:
        if path == blocked or path.startswith(blocked):
            return False
    if STORYBOARD18_ARTICLE_ID_PATTERN.search(parsed.path):
        return True
    if path.endswith(".htm") and len(path) >= 15:
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and "-" in parts[-1]:
            return True
    return False


def extract_storyboard18_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    match = STORYBOARD18_ARTICLE_ID_PATTERN.search(parsed.path)
    if match:
        return match.group(1)
    parts = parsed.path.strip("/").replace(".htm", "").split("/")
    return parts[-1] if parts else None


def extract_storyboard18_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[0].lower()
    return None


# ---------------------------------------------------------------------------
# Indian Television URL Detection & Utilities
# ---------------------------------------------------------------------------
INDIANTELEVISION_BLOCKED_PATHS = {
    "/about-us", "/contact-us", "/privacy-policy", "/terms",
    "/terms-and-conditions", "/disclaimer", "/feed", "/feed/",
    "/category/", "/tag/", "/author/", "/page/", "/wp-admin",
    "/wp-content", "/wp-includes", "/xmlrpc.php", "/search",
}


def is_valid_indiantelevision_article_url(url: str) -> bool:
    """Validates if a URL is a genuine Indian Television article."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc and "indiantelevision.com" not in netloc:
        return False
    path = parsed.path.lower()
    if path in ("", "/", "/index.php", "/index.html"):
        return False
    for blocked in INDIANTELEVISION_BLOCKED_PATHS:
        if path == blocked or path.startswith(blocked):
            return False
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) == 2:
        section, slug = parts[0], parts[1]
        if len(slug) >= 8 and "-" in slug and not slug.isdigit():
            return True
    elif len(parts) >= 3 and parts[0] == "category":
        return False
    elif len(parts) == 1 and len(parts[0]) >= 15 and "-" in parts[0]:
        return True
    return False


def extract_indiantelevision_article_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    return parts[-1] if parts else None


def extract_indiantelevision_section_slug(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return parts[0].lower()
    return None



