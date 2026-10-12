"""
Media Reporting System - Date Parsing Utilities
Parses dates, timestamps, and metadata into normalized ISO 8601 strings.
Supports Indian Standard Time (IST, +05:30) and multi-format publisher patterns.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("media-date-parser")

IST_TZ = timezone(timedelta(hours=5, minutes=30))

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def clean_date_string(raw: str) -> str:
    """Strips common publisher prefixes and noise from date strings."""
    cleaned = raw.strip()
    # Remove prefixes
    cleaned = re.sub(
        r"^(published|posted|updated|last updated|date|published on|publish date|published at)\s*[:\-–|]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove trailing/embedded timezone tags like IST
    cleaned = re.sub(r"\s+IST\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*", " ", cleaned)
    return cleaned.strip()


def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Parses various date/time formats into a normalized ISO 8601 string.
    Returns None if date cannot be parsed reliably. Never guesses or fabricates.
    """
    if not date_str:
        return None

    raw = clean_date_string(date_str)
    if not raw:
        return None

    # 1. Try standard ISO 8601 formats (e.g., "2026-09-23T08:52:34+05:30", "2026-09-23T08:52:34Z")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt.isoformat()
    except Exception:
        pass

    # 2. Try RFC 2822 format (e.g., "Wed, 23 Sep 2026 08:52:34 +0530")
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt.isoformat()
    except Exception:
        pass

    # 3. Try "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
    m_sql = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$", raw)
    if m_sql:
        try:
            year, month, day = int(m_sql.group(1)), int(m_sql.group(2)), int(m_sql.group(3))
            hour = int(m_sql.group(4)) if m_sql.group(4) else 0
            minute = int(m_sql.group(5)) if m_sql.group(5) else 0
            second = int(m_sql.group(6)) if m_sql.group(6) else 0
            dt = datetime(year, month, day, hour, minute, second, tzinfo=IST_TZ)
            return dt.isoformat()
        except Exception:
            pass

    # 4. Try Month Day, Year [Time AM/PM] (e.g., "Jul 24, 2026 11:35 AM", "September 23, 2026, 05:30 PM", "Sep 23, 2026")
    m_mdy = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?$",
        raw,
        re.IGNORECASE,
    )
    if m_mdy:
        m_str = m_mdy.group(1).lower()
        if m_str in MONTH_MAP:
            try:
                month = MONTH_MAP[m_str]
                day = int(m_mdy.group(2))
                year = int(m_mdy.group(3))
                hour = int(m_mdy.group(4)) if m_mdy.group(4) else 0
                minute = int(m_mdy.group(5)) if m_mdy.group(5) else 0
                second = int(m_mdy.group(6)) if m_mdy.group(6) else 0
                ampm = m_mdy.group(7)
                if ampm:
                    ampm_upper = ampm.upper()
                    if ampm_upper == "PM" and hour < 12:
                        hour += 12
                    elif ampm_upper == "AM" and hour == 12:
                        hour = 0
                dt = datetime(year, month, day, hour, minute, second, tzinfo=IST_TZ)
                return dt.isoformat()
            except Exception:
                pass

    # 5. Try Day Month Year [Time AM/PM] (e.g., "24 Jul 2026, 11:35 AM", "23 September 2026 17:30", "23 Sep, 2026")
    m_dmy = re.match(
        r"^(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?$",
        raw,
        re.IGNORECASE,
    )
    if m_dmy:
        m_str = m_dmy.group(2).lower()
        if m_str in MONTH_MAP:
            try:
                day = int(m_dmy.group(1))
                month = MONTH_MAP[m_str]
                year = int(m_dmy.group(3))
                hour = int(m_dmy.group(4)) if m_dmy.group(4) else 0
                minute = int(m_dmy.group(5)) if m_dmy.group(5) else 0
                second = int(m_dmy.group(6)) if m_dmy.group(6) else 0
                ampm = m_dmy.group(7)
                if ampm:
                    ampm_upper = ampm.upper()
                    if ampm_upper == "PM" and hour < 12:
                        hour += 12
                    elif ampm_upper == "AM" and hour == 12:
                        hour = 0
                dt = datetime(year, month, day, hour, minute, second, tzinfo=IST_TZ)
                return dt.isoformat()
            except Exception:
                pass

    # 6. Try "DD-MM-YYYY [HH:MM[:SS]]" or "DD/MM/YYYY"
    m_slash = re.match(
        r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?$",
        raw,
        re.IGNORECASE,
    )
    if m_slash:
        try:
            day = int(m_slash.group(1))
            month = int(m_slash.group(2))
            year = int(m_slash.group(3))
            hour = int(m_slash.group(4)) if m_slash.group(4) else 0
            minute = int(m_slash.group(5)) if m_slash.group(5) else 0
            second = int(m_slash.group(6)) if m_slash.group(6) else 0
            ampm = m_slash.group(7)
            if ampm:
                ampm_upper = ampm.upper()
                if ampm_upper == "PM" and hour < 12:
                    hour += 12
                elif ampm_upper == "AM" and hour == 12:
                    hour = 0
            dt = datetime(year, month, day, hour, minute, second, tzinfo=IST_TZ)
            return dt.isoformat()
        except Exception:
            pass

    # 7. Try Relative times (e.g. "2 hours ago", "15 mins ago", "1 day ago", "yesterday")
    if raw.lower() == "yesterday":
        now = datetime.now(IST_TZ)
        dt = now - timedelta(days=1)
        return dt.isoformat()

    relative_match = re.search(
        r"(\d+)\s*(mins?|minutes?|hrs?|hours?|days?|weeks?)\s*ago", raw, re.IGNORECASE
    )
    if relative_match:
        qty = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        now = datetime.now(IST_TZ)
        if "min" in unit:
            dt = now - timedelta(minutes=qty)
        elif "hr" in unit or "hour" in unit:
            dt = now - timedelta(hours=qty)
        elif "day" in unit:
            dt = now - timedelta(days=qty)
        elif "week" in unit:
            dt = now - timedelta(weeks=qty)
        else:
            return None
        return dt.isoformat()

    return None


def extract_publication_time_with_method(
    soup_or_element: BeautifulSoup | Tag,
) -> Tuple[Optional[str], str]:
    """
    Extracts publication date/time from HTML using strict priority order:
    1. Explicit visible publication date/time on the article page
    2. <time datetime="...">
    3. OpenGraph / article metadata
    4. JSON-LD NewsArticle / Article: datePublished / dateCreated
    5. Publisher-specific structured metadata
    6. Returns (None, "UNAVAILABLE") if not found. Never invents dates.
    """
    if not soup_or_element:
        return None, "UNAVAILABLE"

    # Priority 1: Explicit visible publication date/time elements
    visible_selectors = [
        "span.publish-date",
        "span.publish_date",
        "div.publish-date",
        "div.publish_date",
        ".article-publish-date",
        ".artByline span.date",
        ".byline span.date",
        ".article-date",
        ".story-published",
        ".posted-on",
        ".pubdate",
        ".post-date",
        ".date-time",
        "span.time-ago",
        "span.ag-time",
    ]
    for selector in visible_selectors:
        el = soup_or_element.select_one(selector)
        if el:
            txt = el.get_text(" ", strip=True)
            iso = parse_date_to_iso(txt)
            if iso:
                return iso, "VISIBLE_TIME"

    # Priority 2: <time datetime="..."> or <time> text
    for time_tag in soup_or_element.find_all("time"):
        dt_val = time_tag.get("datetime")
        if dt_val:
            iso = parse_date_to_iso(dt_val)
            if iso:
                return iso, "HTML_TIME"
        txt = time_tag.get_text(" ", strip=True)
        if txt:
            iso = parse_date_to_iso(txt)
            if iso:
                return iso, "HTML_TIME"

    # Priority 3: OpenGraph / Article Meta Tags & Microdata
    meta_properties = [
        ("name", "publish-date"),
        ("name", "created-date"),
        ("property", "article:published_time"),
        ("name", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
        ("name", "published_date"),
        ("name", "datePublished"),
        ("property", "datePublished"),
        ("itemprop", "datePublished"),
        ("itemprop", "dateCreated"),
        ("property", "rdate"),
        ("name", "cXenseParse:recs:publishtime"),
    ]
    for attr, val in meta_properties:
        meta_tag = soup_or_element.find("meta", attrs={attr: val})
        if meta_tag and meta_tag.get("content"):
            iso = parse_date_to_iso(meta_tag["content"])
            if iso:
                return iso, "META"

    # Priority 4: JSON-LD Article / NewsArticle
    for script in soup_or_element.find_all("script", type="application/ld+json"):
        try:
            content = script.string or script.get_text() or ""
            if not content.strip():
                continue
            data = json.loads(content)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    if item.get("@type") in ("NewsArticle", "Article", "WebPage", "Report", "BlogPosting"):
                        date_val = item.get("datePublished") or item.get("dateCreated")
                        if date_val:
                            iso = parse_date_to_iso(str(date_val))
                            if iso:
                                return iso, "JSON_LD"
                    # Check nested graph items
                    if "@graph" in item and isinstance(item["@graph"], list):
                        for g in item["@graph"]:
                            if isinstance(g, dict) and g.get("@type") in ("NewsArticle", "Article", "WebPage", "BlogPosting"):
                                date_val = g.get("datePublished") or g.get("dateCreated")
                                if date_val:
                                    iso = parse_date_to_iso(str(date_val))
                                    if iso:
                                        return iso, "JSON_LD"
        except Exception:
            pass

    # Priority 5: Publisher-specific metadata classes / data attributes
    for el in soup_or_element.find_all(attrs={"data-date": True}):
        iso = parse_date_to_iso(el["data-date"])
        if iso:
            return iso, "PUBLISHER_METADATA"

    for el in soup_or_element.find_all(attrs={"data-published": True}):
        iso = parse_date_to_iso(el["data-published"])
        if iso:
            return iso, "PUBLISHER_METADATA"

    return None, "UNAVAILABLE"


RELATIVE_TIME_REGEX = re.compile(
    r"\b(just now|\d+\s*(?:sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago)\b",
    re.IGNORECASE,
)

STRICT_RELATIVE_TIME_EXACT = re.compile(
    r"^(just now|\d+\s*(?:sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago)$",
    re.IGNORECASE,
)


def extract_relative_time_label(
    soup_or_element: BeautifulSoup | Tag,
    headline: str = "",
) -> Optional[str]:
    """
    Extracts explicit relative publication label from card/container (e.g., '46 minutes ago', '9 hours ago', '2 days ago')
    WITHOUT fabricating a synthetic ISO timestamp.
    """
    if not soup_or_element:
        return None

    # 1. Check explicit time selectors
    time_selectors = [
        "span.time", "span.time-ago", "span.ag-time", "span.date",
        "span.publish-time", "span.published-time", "span.posted-time",
        ".story-time", ".art-time", ".time_ago", "span.posted-on",
        ".time", "time", ".post-date", ".date-time", "p.time"
    ]
    for selector in time_selectors:
        for el in soup_or_element.select(selector):
            txt = clean_date_string(el.get_text(" ", strip=True))
            if STRICT_RELATIVE_TIME_EXACT.match(txt):
                return txt

    # 2. Check child span/small/em/p elements
    for el in soup_or_element.find_all(["span", "small", "em", "p", "div"]):
        txt = clean_date_string(el.get_text(" ", strip=True))
        if STRICT_RELATIVE_TIME_EXACT.match(txt):
            return txt

    # 3. If element text is headline + relative time
    full_text = soup_or_element.get_text(" ", strip=True)
    if headline and headline.lower() in full_text.lower():
        # Look for trailing relative time
        m = re.search(
            r"(\d+\s*(?:sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago|just now)\s*$",
            full_text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()

    return None


def extract_exclusive_flag(
    soup_or_element: BeautifulSoup | Tag,
    headline: str = "",
) -> bool:
    """
    Identifies if an article is explicitly tagged as Exclusive content.
    Strictly checks source badges, tags, data attributes, or standalone Exclusive labels.
    Never guesses from arbitrary summary prose.
    """
    if not soup_or_element:
        return False

    # 1. Check explicit classes
    for selector in [".exclusive", ".exclusive-tag", ".exclusive-badge", ".badge-exclusive", ".exclusive-label", ".is-exclusive"]:
        el = soup_or_element.select_one(selector)
        if el:
            txt = el.get_text(" ", strip=True).lower()
            if "exclusive" in txt:
                return True

    # 2. Check data attributes
    if soup_or_element.get("data-exclusive") in ("true", "1", "exclusive", True):
        return True

    for el in soup_or_element.find_all(attrs={"data-exclusive": True}):
        if el.get("data-exclusive") in ("true", "1", "exclusive", True):
            return True

    # 3. Check badges, tags, labels with exact "Exclusive" / "Exclusive Content" text
    badge_selectors = [".badge", ".tag", ".sec-name", ".cat-name", ".label", ".category", "span", "div", "em", "strong", "a"]
    for selector in badge_selectors:
        for el in soup_or_element.select(selector):
            txt = el.get_text(" ", strip=True).strip()
            if txt.lower() in ("exclusive", "exclusive content", "[exclusive]"):
                return True

    # 4. Check if text begins or ends with standalone [Exclusive] tag outside headline
    full_text = soup_or_element.get_text(" ", strip=True)
    if headline:
        after_headline = full_text.replace(headline, "").strip()
        if after_headline.lower() in ("exclusive", "exclusive content", "[exclusive]"):
            return True

    return False
