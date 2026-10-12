"""
Media Reporting System - Best Media Info Newsletter Parser
Extracts newsletter heading, editorial articles, original links, images, and advertisements
from Best Media Info HTML newsletters.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from mailer.base_parser import MailerParser
from mailer.models import ParsedAdvertisement, ParsedArticle, ParsedMailer


class BestMediaInfoParser(MailerParser):
    """
    Parser for HTML emails from Best Media Info (bmi@bestmediainfo.in).
    Extracts structured editorial intelligence and separate advertisement intelligence.
    """

    default_source_name = "Best Media Info"
    default_base_url = "https://bestmediainfo.com"

    IGNORE_HREFS = {
        "#", "", "javascript:void(0)", "mailto:bmi@bestmediainfo.in",
    }

    IGNORE_DOMAINS = {
        "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
        "youtube.com", "whatsapp.com", "t.me", "telegram.me",
    }

    def parse_email_html(
        self, html_content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ParsedMailer:
        soup = BeautifulSoup(html_content, "html.parser")
        meta = metadata or {}

        # 1. Metadata: Sender, Subject, Date
        sender_name = meta.get("sender_name") or "Best Media Info"
        sender_email = meta.get("sender_email") or "bmi@bestmediainfo.in"
        email_subject = meta.get("email_subject") or meta.get("subject")
        received_datetime = meta.get("received_datetime") or meta.get("date")

        # Fallback inspection of HTML for sender/subject/date if not passed in meta
        if not email_subject:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                email_subject = self.clean_text(title_tag.string)

        date_tag = soup.find(class_=re.compile(r"date|received-time|header-date", re.I))
        if date_tag and not received_datetime:
            received_datetime = self.clean_text(date_tag.get_text())

        # 2. Extract Newsletter Heading
        newsletter_heading = self._extract_newsletter_heading(soup, email_subject)

        # 3. Extract Articles & Advertisements
        articles, advertisements = self._extract_content(soup)

        # Compute deterministic content hash for duplicate detection
        content_hash = self.compute_content_hash(html_content, metadata)

        return ParsedMailer(
            source_name=self.default_source_name,
            sender_name=sender_name,
            sender_email=sender_email,
            email_subject=email_subject or newsletter_heading,
            received_datetime=received_datetime,
            newsletter_heading=newsletter_heading,
            articles=articles,
            advertisements=advertisements,
            content_hash=content_hash,
        )

    def _extract_newsletter_heading(
        self, soup: BeautifulSoup, fallback_subject: Optional[str]
    ) -> str:
        """Finds the prominent top newsletter banner/lead heading."""
        # Check explicit heading classes
        for selector in [
            ".newsletter-heading", ".main-heading", ".lead-headline",
            "#newsletter-heading", ".digest-title", ".top-heading"
        ]:
            heading_el = soup.select_one(selector)
            if heading_el and self.clean_text(heading_el.get_text()):
                return self.clean_text(heading_el.get_text())

        # Check first prominent h1/h2 or header block that is not a site logo
        for h in soup.find_all(["h1", "h2"]):
            text = self.clean_text(h.get_text())
            if text and len(text) > 15 and "best media info" not in text.lower():
                return text

        # Check strong text in the header table area
        header_area = soup.find("header") or soup.find(class_=re.compile(r"header|top-bar", re.I))
        if header_area:
            strong_el = header_area.find(["strong", "b"])
            if strong_el:
                txt = self.clean_text(strong_el.get_text())
                if len(txt) > 20:
                    return txt

        return fallback_subject or "Best Media Info Daily Intelligence"

    def _extract_content(
        self, soup: BeautifulSoup
    ) -> Tuple[List[ParsedArticle], List[ParsedAdvertisement]]:
        articles: List[ParsedArticle] = []
        advertisements: List[ParsedAdvertisement] = []
        seen_urls: Set[str] = set()
        seen_ad_keys: Set[str] = set()

        # Phase A: Check for structured article cards / tables
        article_containers = soup.find_all(
            ["div", "table", "td", "article", "section"],
            class_=re.compile(r"article|story|news-item|post|card|digest-item", re.I),
        )

        # If no explicit semantic containers, search across all content blocks
        if not article_containers or len(article_containers) < 2:
            article_containers = self._discover_candidate_blocks(soup)

        article_order = 1
        ad_order = 1

        for block in article_containers:
            # Check if this block is an advertisement
            if self._is_ad_block(block):
                ad = self._parse_ad_block(block, ad_order)
                if ad:
                    ad_key = f"{ad.advertiser}|{ad.target_url}|{ad.image_url}"
                    if ad_key not in seen_ad_keys:
                        advertisements.append(ad)
                        seen_ad_keys.add(ad_key)
                        ad_order += 1
                continue

            # Otherwise attempt to extract an editorial article
            art = self._parse_article_block(block, article_order)
            if art and art.title and art.source_url:
                if art.source_url not in seen_urls:
                    articles.append(art)
                    seen_urls.add(art.source_url)
                    article_order += 1

        # Phase B: Look for standalone banner ads that might be in separate ad tables/containers
        ad_containers = soup.find_all(
            ["div", "table", "td", "tr", "p", "a"],
            class_=re.compile(r"ad|advertisement|banner|sponsor", re.I),
        )
        for ad_el in ad_containers:
            ad = self._parse_ad_block(ad_el, ad_order)
            if ad and (ad.target_url or ad.image_url):
                ad_key = f"{ad.advertiser}|{ad.target_url}|{ad.image_url}"
                if ad_key not in seen_ad_keys:
                    advertisements.append(ad)
                    seen_ad_keys.add(ad_key)
                    ad_order += 1

        return articles, advertisements

    def _discover_candidate_blocks(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        """Discovers article blocks by locating story headline links."""
        candidates = []
        # Find all links that contain headings or substantial story titles
        links = soup.find_all("a", href=True)
        for link in links:
            href = link.get("href", "").strip()
            if not self._is_valid_article_href(href):
                continue

            # Find parent row/table or container that groups image + title + description
            parent = link.find_parent(["td", "tr", "div", "li"])
            if parent and parent not in candidates:
                candidates.append(parent)
            elif link not in candidates:
                candidates.append(link)
        return candidates

    def _is_valid_article_href(self, href: str) -> bool:
        if not href or href in self.IGNORE_HREFS:
            return False
        if href.startswith(("mailto:", "tel:", "#")):
            return False
        parsed = urlparse(href)
        domain = parsed.netloc.lower()
        if any(d in domain for d in self.IGNORE_DOMAINS):
            return False
        if "unsubscribe" in href.lower() or "view-in-browser" in href.lower():
            return False
        return True

    def _is_ad_block(self, el: BeautifulSoup) -> bool:
        """Determines whether a container element represents an advertisement."""
        classes = " ".join(el.get("class", [])) if hasattr(el, "get") else ""
        el_id = el.get("id", "") if hasattr(el, "get") else ""
        text = (classes + " " + el_id).lower()

        if any(k in text for k in ["ad-banner", "advertisement", "sponsor", "advt", "ad_slot"]):
            return True

        # Check for link tracking / banner signals
        link = el if el.name == "a" else el.find("a", href=True)
        if link:
            href = (link.get("href") or "").lower()
            if any(k in href for k in ["googleads", "doubleclick", "/ad/", "/ads/", "adclick"]):
                return True

        # Check for explicit label inside text
        label = el.find(string=re.compile(r"^(advertisement|sponsored|advt\.?)$", re.I))
        if label:
            return True

        return False

    def _parse_article_block(
        self, block: BeautifulSoup, order: int
    ) -> Optional[ParsedArticle]:
        # 1. Title & URL: Look for primary article link
        title_el = None
        source_url = ""

        # Priority A: Heading tag with link or link inside heading
        for h in block.find_all(["h2", "h3", "h4", "h5", "strong"]):
            link = h.find("a", href=True) or (h.find_parent("a", href=True))
            if link and self._is_valid_article_href(link.get("href")):
                title_text = self.clean_text(h.get_text())
                if len(title_text) >= 15:
                    title_el = h
                    source_url = self.resolve_url(link.get("href"))
                    break

        # Priority B: Any valid link with significant text
        if not title_el:
            for a in block.find_all("a", href=True):
                txt = self.clean_text(a.get_text())
                href = a.get("href", "")
                if len(txt) >= 20 and self._is_valid_article_href(href):
                    title_text = txt
                    source_url = self.resolve_url(href)
                    title_el = a
                    break

        if not title_el:
            return None

        title = self.clean_text(title_el.get_text())

        # Exclude navigation/ad text accidentally picked up
        if any(w in title.lower() for w in ["read more", "click here", "advertisement", "subscribe"]):
            return None

        # 2. Image: Find associated article image
        image_url = None
        img = block.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if src and not any(k in src.lower() for k in ["spacer", "pixel", "icon", "logo", "1x1"]):
                image_url = self.resolve_url(src)

        # 3. Description: Find summary text/paragraph
        description = None
        desc_candidates = []
        for p in block.find_all(["p", "div", "span"]):
            # Skip if it is the title element itself
            if p == title_el or title_el in p.parents or p in title_el.parents:
                continue
            txt = self.clean_text(p.get_text())
            # Skip empty, read more buttons, or duplicate of title
            if txt and txt != title and len(txt) > 20 and not txt.startswith("Read More"):
                desc_candidates.append(txt)

        if desc_candidates:
            # Pick the longest or first descriptive paragraph
            description = desc_candidates[0]

        return ParsedArticle(
            title=title,
            description=description or "",
            image_url=image_url,
            source_url=source_url,
            source_name=self.default_source_name,
            order=order,
        )

    def _parse_ad_block(
        self, block: BeautifulSoup, order: int
    ) -> Optional[ParsedAdvertisement]:
        # Find link
        link = block if block.name == "a" else block.find("a", href=True)
        target_url = ""
        if link and link.get("href"):
            target_url = self.resolve_url(link.get("href"))

        # Find image
        img = block if block.name == "img" else block.find("img")
        image_url = None
        alt_text = ""
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                image_url = self.resolve_url(src)
            alt_text = self.clean_text(img.get("alt", ""))

        # Advertiser & title
        advertiser = alt_text or "Sponsored Partner"
        title = alt_text or self.clean_text(block.get_text()) or "Featured Advertisement"

        # If title is too long, truncate or clean
        if len(title) > 100:
            title = title[:97] + "..."

        if not target_url and not image_url:
            return None

        return ParsedAdvertisement(
            advertiser=advertiser,
            title=title,
            image_url=image_url,
            target_url=target_url,
            order=order,
        )
