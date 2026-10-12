"""
Media Reporting System - Exchange4media Article Scraper
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from scraper.base.article import Article
from scraper.base.fetcher import PageFetcher
from scraper.exchange4media.config import (
    E4M_SECTION_SLUG_MAP,
    EXCHANGE4MEDIA,
    WebsiteConfig,
)
from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import (
    extract_exclusive_flag,
    extract_relative_time_label,
    parse_date_to_iso,
)
from scraper.utils.url import (
    extract_e4m_section_slug,
    is_valid_e4m_article_url,
    normalize_url,
)

logger = logging.getLogger("media-scraper")


class Exchange4mediaScraper:
    """
    Dedicated article scraper for Exchange4media (exchange4media.com).
    Extracts validated articles from homepage news cards, section listings, or individual pages.
    """

    def __init__(
        self,
        config: WebsiteConfig = EXCHANGE4MEDIA,
        *,
        delay_seconds: float = 2.0,
        browser_fallback: bool = False,
        user_agent: Optional[str] = None,
    ) -> None:
        self.config = config
        self.delay_seconds = max(0.5, delay_seconds)
        self.browser_fallback = browser_fallback
        self.fetcher = PageFetcher(user_agent=user_agent) if user_agent else PageFetcher()

    def detect_section(self, url: str, card_element=None) -> str:
        """
        Detects the editorial section for an Exchange4media article using multiple signals:
        1. URL path slug (e.g. /advertising-news/... -> 'Advertising')
        2. Card category badge / label (e.g. .cat-name, .sec-title, .badge)
        3. Fallback to 'Overall'
        """
        slug = extract_e4m_section_slug(url)
        if slug and slug in E4M_SECTION_SLUG_MAP:
            return E4M_SECTION_SLUG_MAP[slug]

        if card_element:
            for selector in [".category-tag", ".cat-name", ".sec-name", ".badge", ".label", ".section"]:
                badge = card_element.select_one(selector)
                if badge:
                    badge_text = clean_text(badge.get_text())
                    if badge_text and len(badge_text) > 2 and not is_navigation_text(badge_text):
                        return badge_text.title()

        if slug:
            clean_slug = slug.replace("-news", "").replace("-", " ").title()
            return clean_slug

        return "Overall"

    def find_atomic_card(self, anchor, target_url: str, base_url: str):
        """
        Ascends from the anchor to find the largest enclosing container that contains
        EXCLUSIVELY links to this same article, guaranteeing that the container is atomic
        and will NEVER leak images or summaries from sibling articles.
        """
        curr = anchor
        best_container = anchor

        while curr and curr.parent and curr.parent.name not in ["body", "html", "[document]"]:
            parent = curr.parent
            distinct_article_urls = set()
            for a in parent.find_all("a", href=True):
                href = a.get("href", "")
                norm = normalize_url(href, base_url)
                if is_valid_e4m_article_url(norm):
                    distinct_article_urls.add(norm)

            # If parent contains multiple distinct article URLs, stop ascending
            if len(distinct_article_urls) > 1:
                break

            curr = parent
            if curr.name in ["article", "li", "figure", "div", "section"]:
                best_container = curr

        return best_container

    def extract_headline(self, anchor, card_element=None) -> Optional[str]:
        """
        Extracts and verifies the headline using a strict priority order:
        1. Headings (h1..h6) inside the anchor
        2. Anchor title attribute
        3. Anchor inner text
        4. Headings inside the atomic card container
        """
        # 1. Heading inside anchor
        heading_inside = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading_inside:
            text = clean_text(heading_inside.get_text(" ", strip=True))
            if len(text) >= 15 and not is_navigation_text(text):
                return text

        # 2. Anchor title attribute
        title_attr = clean_text(anchor.get("title"))
        if title_attr and len(title_attr) >= 15 and not is_navigation_text(title_attr):
            return title_attr

        # 3. Anchor text
        anchor_text = clean_text(anchor.get_text(" ", strip=True))
        if len(anchor_text) >= 15 and not is_navigation_text(anchor_text):
            return anchor_text

        # 4. Heading in atomic parent card
        if card_element and card_element != anchor:
            card_heading = card_element.find(["h1", "h2", "h3", "h4", "h5"])
            if card_heading:
                text = clean_text(card_heading.get_text(" ", strip=True))
                if len(text) >= 15 and not is_navigation_text(text):
                    return text

        return None

    def _parse_img_tag(self, img, base_url: str) -> Optional[str]:
        if not img:
            return None
        for attr in ["data-src", "data-original", "data-lazy-src", "data-img-src", "srcset", "src"]:
            raw_val = img.get(attr)
            if not raw_val:
                continue

            if attr == "srcset" or "," in raw_val:
                candidates = [c.strip().split()[0] for c in raw_val.split(",") if c.strip()]
                raw_val = candidates[-1] if candidates else ""

            cleaned = clean_image_url(raw_val, base_url=base_url or self.config.url)
            if cleaned:
                return cleaned
        return None

    def extract_image_url(self, anchor, card_element=None, base_url: str = "") -> Optional[str]:
        """
        Extracts hero image URL from the anchor or its atomic card container,
        prioritizing high-res attributes and sanitizing against icons/tracking gifs.
        """
        # 1. Check inside anchor first
        for img in anchor.find_all("img"):
            clean = self._parse_img_tag(img, base_url)
            if clean:
                return clean

        # 2. Check inside atomic card_element
        if card_element and card_element != anchor:
            for img in card_element.find_all("img"):
                clean = self._parse_img_tag(img, base_url)
                if clean:
                    return clean

        return None

    def extract_summary(self, card_element, headline: str = "") -> Optional[str]:
        """
        Extracts summary / synopsis from the atomic card container, ensuring it is not a
        duplicate of the headline, navigation boilerplate, or relative time label.
        """
        if not card_element:
            return None

        # Look for description / excerpt containers
        for selector in [".desc", ".summary", ".synopsis", ".story-content", "p"]:
            for elem in card_element.select(selector):
                text = clean_text(elem.get_text(" ", strip=True))
                if not text or len(text) < 20:
                    continue
                if is_navigation_text(text):
                    continue
                if headline and text.lower() == headline.lower():
                    continue
                # Clean trailing "Exclusive" or relative time from summary text if it's mostly headline
                cleaned = re.sub(r"\s+(?:Exclusive|Exclusive Content|just now|\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago)\s*$", "", text, flags=re.IGNORECASE).strip()
                if headline and (cleaned == headline or cleaned.lower() == headline.lower() or len(cleaned) < 15):
                    continue
                if re.match(r"^(\d+)\s*(mins?|hours?|days?)\s*ago$", text, re.IGNORECASE):
                    continue
                return text

        return None

    def extract_published_date(self, card_element) -> Optional[str]:
        """
        Extracts publication date from card timestamp elements and normalizes to ISO 8601.
        """
        if not card_element:
            return None

        from scraper.utils.date_parser import extract_publication_time_with_method
        iso, _ = extract_publication_time_with_method(card_element)
        return iso

    def extract_articles_from_html(
        self,
        html: str,
        page_url: str = "",
        default_section: str = "Overall",
    ) -> tuple[list[Article], int, int]:
        """
        Parses Exchange4media HTML and extracts all valid article items with atomic card isolation.
        Returns: (articles, candidates_detected, duplicates_in_page)
        """
        soup = BeautifulSoup(html, "html.parser")
        base_url = page_url or self.config.url

        # Check for JSON-LD structured data first
        json_ld_articles: dict[str, Article] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") in ("NewsArticle", "Article"):
                        url = normalize_url(item.get("url") or "", base_url)
                        if is_valid_e4m_article_url(url):
                            headline = clean_text(item.get("headline") or "")
                            if len(headline) >= 15:
                                img = item.get("image")
                                img_url = None
                                if isinstance(img, str):
                                    img_url = clean_image_url(img, base_url)
                                elif isinstance(img, dict):
                                    img_url = clean_image_url(img.get("url") or "", base_url)
                                elif isinstance(img, list) and img:
                                    first_img = img[0]
                                    img_url = clean_image_url(first_img if isinstance(first_img, str) else first_img.get("url", ""), base_url)

                                summary = clean_text(item.get("description") or "") or None
                                pub_date = parse_date_to_iso(item.get("datePublished") or "")
                                sec = item.get("articleSection") or default_section

                                article = Article(
                                    website=self.config.name,
                                    website_key=self.config.key,
                                    section=sec if sec and sec != "Overall" else self.detect_section(url),
                                    headline=headline,
                                    url=url,
                                    image_url=img_url,
                                    summary=summary,
                                    published_at=pub_date,
                                ).finalize()
                                json_ld_articles[url] = article
            except Exception:
                continue

        # DOM Extraction: Find news cards and article anchors
        articles_by_url: dict[str, Article] = dict(json_ld_articles)
        candidates_count = len(json_ld_articles)
        duplicates_count = 0

        # Anchor scan for article URLs
        for anchor in soup.find_all("a", href=True):
            raw_href = anchor.get("href", "").strip()
            canonical_url = normalize_url(raw_href, base_url=base_url)

            if not is_valid_e4m_article_url(canonical_url):
                continue

            candidates_count += 1

            # Identify the ATOMIC card container: strictly isolated to this single article
            card_elem = self.find_atomic_card(anchor, canonical_url, base_url)

            # Headline
            headline = self.extract_headline(anchor, card_element=card_elem)
            if not headline or len(headline) < 15:
                continue

            # Section
            section = self.detect_section(canonical_url, card_element=card_elem)
            if section == "Overall" and default_section != "Overall":
                section = default_section

            # Image
            image_url = self.extract_image_url(anchor, card_element=card_elem, base_url=base_url)

            # Summary
            summary = self.extract_summary(card_elem, headline=headline)

            # Published Date & Relative Label
            published_at = self.extract_published_date(card_elem)
            publication_label = extract_relative_time_label(card_elem, headline=headline)
            is_exclusive = extract_exclusive_flag(card_elem, headline=headline)

            # Check if we already have this article from JSON-LD or previous card
            if canonical_url in articles_by_url:
                duplicates_count += 1
                existing = articles_by_url[canonical_url]
                # Merge richer metadata if available
                if not existing.image_url and image_url:
                    existing.image_url = image_url
                if not existing.summary and summary:
                    existing.summary = summary
                if not existing.published_at and published_at:
                    existing.published_at = published_at
                if not existing.publication_label and publication_label:
                    existing.publication_label = publication_label
                if not existing.is_exclusive and is_exclusive:
                    existing.is_exclusive = is_exclusive
                if existing.section == "Overall" and section != "Overall":
                    existing.section = section
                existing.finalize()
                continue

            new_article = Article(
                website=self.config.name,
                website_key=self.config.key,
                section=section,
                headline=headline,
                url=canonical_url,
                image_url=image_url,
                summary=summary,
                published_at=published_at,
                publication_label=publication_label,
                is_exclusive=is_exclusive,
            ).finalize()

            articles_by_url[canonical_url] = new_article

        articles = list(articles_by_url.values())
        return articles, candidates_count, duplicates_count

    def deduplicate_articles(
        self, articles: Iterable[Article]
    ) -> tuple[list[Article], int]:
        """
        Deduplicates a collection of articles by canonical URL, retaining the record
        with the richest metadata (image, summary, published date).
        """
        unique_map: dict[str, Article] = {}
        duplicates_removed = 0

        for art in articles:
            if art.url in unique_map:
                duplicates_removed += 1
                curr = unique_map[art.url]
                # Merge better metadata
                if not curr.image_url and art.image_url:
                    curr.image_url = art.image_url
                if not curr.summary and art.summary:
                    curr.summary = art.summary
                if not curr.published_at and art.published_at:
                    curr.published_at = art.published_at
                if not curr.publication_label and art.publication_label:
                    curr.publication_label = art.publication_label
                if not curr.is_exclusive and art.is_exclusive:
                    curr.is_exclusive = art.is_exclusive
                if curr.section == "Overall" and art.section != "Overall":
                    curr.section = art.section
                curr.finalize()
            else:
                unique_map[art.url] = art

        return list(unique_map.values()), duplicates_removed

    def scrape_homepage(
        self,
        *,
        enrich: bool = False,
        max_enrich: Optional[int] = None,
    ) -> tuple[list[Article], dict]:
        """
        Scrapes Exchange4media homepage and extracts real articles.
        If homepage yields limited articles, queries top sections to guarantee a comprehensive feed.
        """
        logger.info("Fetching Exchange4media homepage: %s", self.config.url)
        html = self.fetcher.fetch(
            self.config.url, browser_fallback=self.browser_fallback
        )

        all_articles: list[Article] = []
        total_candidates = 0
        total_duplicates = 0
        pages_fetched = 0

        if html:
            pages_fetched += 1
            homepage_articles, candidates, duplicates = self.extract_articles_from_html(
                html, page_url=self.config.url
            )
            all_articles.extend(homepage_articles)
            total_candidates += candidates
            total_duplicates += duplicates

        # If homepage extraction was blocked or returned few articles, query main sections
        if len(all_articles) < 15:
            logger.info("Homepage returned %d articles. Scraping primary sections...", len(all_articles))
            for section_cfg in self.config.sections[:5]:
                try:
                    time.sleep(self.delay_seconds)
                    sec_html = self.fetcher.fetch(section_cfg.url, browser_fallback=self.browser_fallback)
                    pages_fetched += 1
                    if sec_html:
                        sec_arts, cands, dups = self.extract_articles_from_html(
                            sec_html, page_url=section_cfg.url, default_section=section_cfg.name
                        )
                        all_articles.extend(sec_arts)
                        total_candidates += cands
                        total_duplicates += dups
                except Exception as exc:
                    logger.warning("Failed scraping section %s: %s", section_cfg.name, exc)

        # Deduplicate
        final_articles, extra_dups = self.deduplicate_articles(all_articles)
        total_duplicates += extra_dups

        if enrich:
            from scraper.base.enrichment import enrich_article
            enrich_limit = len(final_articles) if max_enrich is None else max_enrich
            for article in final_articles[:enrich_limit]:
                if not article.summary or not article.image_url or not article.published_at:
                    time.sleep(self.delay_seconds)
                    enrich_article(article, self.fetcher)
                    pages_fetched += 1

        stats = {
            "pages_fetched": pages_fetched,
            "candidates": total_candidates,
            "valid_articles": len(final_articles),
            "duplicates_removed": total_duplicates,
        }

        return final_articles, stats
