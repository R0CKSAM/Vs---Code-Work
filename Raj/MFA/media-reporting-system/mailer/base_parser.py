"""
Media Reporting System - Base Mailer Parser Interface
Defines the abstract parser interface and shared HTML extraction utilities.
"""
from __future__ import annotations

import hashlib
import html
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from mailer.models import ParsedAdvertisement, ParsedArticle, ParsedMailer


class MailerParser(ABC):
    """
    Abstract Base Class for email newsletter parsers.
    Independent from email transport (file, Gmail, Outlook, IMAP).
    """

    default_source_name: str = "Media Newsletter"
    default_base_url: str = ""

    @abstractmethod
    def parse_email_html(
        self, html_content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ParsedMailer:
        """
        Parses raw email HTML and returns a structured ParsedMailer object.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Shared Helper Utilities
    # -------------------------------------------------------------------------
    @staticmethod
    def compute_content_hash(html_content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Computes a deterministic SHA-256 hash for duplicate detection.
        Combines normalized metadata (if available) with HTML structure.
        """
        meta_str = ""
        if metadata:
            sender = str(metadata.get("sender_email") or metadata.get("sender") or "").strip().lower()
            subject = str(metadata.get("email_subject") or metadata.get("subject") or "").strip()
            date = str(metadata.get("received_datetime") or metadata.get("date") or "").strip()
            meta_str = f"{sender}|{subject}|{date}|"

        # Normalize body whitespace for reliable hashing
        norm_body = re.sub(r"\s+", " ", html_content.strip())
        full_payload = meta_str + norm_body
        return hashlib.sha256(full_payload.encode("utf-8", errors="ignore")).hexdigest()

    @staticmethod
    def clean_text(text: Optional[str]) -> str:
        """Unescapes HTML entities, strips tags, and cleans whitespace."""
        if not text:
            return ""
        # Unescape HTML entities (&amp;, &nbsp;, etc.)
        t = html.unescape(text)
        t = t.replace("\xa0", " ").replace("\u200b", "")
        # Remove extra whitespaces/newlines
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    def resolve_url(self, href: Optional[str], base_url: Optional[str] = None) -> str:
        """Resolves relative URLs against the source base URL."""
        if not href:
            return ""
        href = href.strip()
        base = base_url or self.default_base_url
        if base and not href.startswith(("http://", "https://", "mailto:", "tel:")):
            return urljoin(base, href)
        return href

    @staticmethod
    def is_advertisement_signal(
        tag_or_link: BeautifulSoup,
        href: Optional[str] = None,
        img_src: Optional[str] = None,
        alt: Optional[str] = None,
    ) -> bool:
        """
        Contextual heuristic to identify advertisement banners from editorial articles.
        Checks explicit ad classes, tracking URLs, dimensions, alt text, and sponsor labels.
        """
        text_corpus = " ".join([
            str(href or "").lower(),
            str(img_src or "").lower(),
            str(alt or "").lower(),
            " ".join(tag_or_link.get("class", [])) if hasattr(tag_or_link, "get") else "",
            str(tag_or_link.get("id", "")) if hasattr(tag_or_link, "get") else "",
        ]).lower()

        ad_keywords = [
            "advertisement", "sponsor", "advt", "/ad/", "/ads/", "doubleclick",
            "adserver", "banner-ad", "ad_banner", "googleads", "leadlink",
            "sponsored-content", "ad-order", "advertiser"
        ]

        for kw in ad_keywords:
            if kw in text_corpus:
                return True
        return False
