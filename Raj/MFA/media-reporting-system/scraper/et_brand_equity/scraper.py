"""
Media Reporting System - ET BrandEquity Article Scraper
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
from scraper.et_brand_equity.config import ET_BRAND_EQUITY, SECTION_SLUG_MAP, WebsiteConfig
from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import (
    extract_exclusive_flag,
    extract_publication_time_with_method,
    extract_relative_time_label,
    parse_date_to_iso,
    parse_relative_date_to_iso,
)
from scraper.utils.url import (
    extract_section_slug_from_url,
    is_valid_et_article_url,
    normalize_url,
)

logger = logging.getLogger("media-scraper")


class ETBrandEquityScraper:
    """
    Dedicated article scraper for ET BrandEquity (brandequity.economictimes.indiatimes.com).
    Extracts validated articles from homepage news cards, section listings, or individual pages.
    """

    def __init__(
        self,
        config: WebsiteConfig = ET_BRAND_EQUITY,
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
        Detects the editorial section for an article using multiple signals:
        1. URL path slug (e.g. /news/marketing/... -> 'Marketing')
        2. Card category badge / label (e.g. .sec-name, .cat-name)
        3. Fallback to 'Overall'
        """
        slug = extract_section_slug_from_url(url)
        if slug and slug in SECTION_SLUG_MAP:
            return SECTION_SLUG_MAP[slug]

        if card_element:
            for selector in [".sec-name", ".cat-name", ".section-tag", ".category", ".tag"]:
                badge = card_element.select_one(selector)
                if badge:
                    badge_text = clean_text(badge.get_text())
                    if badge_text and len(badge_text) > 2 and not is_navigation_text(badge_text):
                        return badge_text.title()

        if slug:
            return slug.replace("-", " ").title()

        return "Overall"

    def find_atomic_card(self, anchor, target_url: str, page_url: str):
        """
        Ascends from the anchor to find the largest enclosing container that contains
        EXCLUSIVELY links to this same article, guaranteeing that the container is atomic
        and will NEVER leak images or summaries from sibling articles.
        """
        curr = anchor
        best_container = anchor

        while curr and curr.parent and curr.parent.name not in ["body", "html", "[document]"]:
            parent = curr.parent
            # Check all article links inside this parent
            distinct_article_urls = set()
            for a in parent.find_all("a", href=True):
                href = a.get("href", "")
                norm = normalize_url(href, page_url)
                if is_valid_et_article_url(norm):
                    distinct_article_urls.add(norm)

            # If parent contains other article URLs, parent is a multi-story container. Stop here!
            if len(distinct_article_urls) > 1:
                break

            # Parent only contains this article (or fragments of it)
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
        candidates = [
            img.get("data-original"),
            img.get("data-src"),
            img.get("data-lazy-src"),
            img.get("src"),
        ]
        srcset = img.get("srcset")
        if srcset:
            first_part = srcset.split(",")[0].strip().split(" ")[0]
            candidates.append(first_part)

        for candidate in candidates:
            clean_url = clean_image_url(candidate, base_url)
            if clean_url:
                return clean_url
        return None

    def extract_image(self, anchor, card_element, base_url: str) -> Optional[str]:
        """
        Finds the primary story image from the anchor or its surrounding ATOMIC card container.
        Prioritizes high-resolution and lazy-loaded attributes (data-original, data-src)
        over 1x1 placeholder GIFs, and rejects logos, icons, and SVG assets.
        """
        # 1. Search inside anchor
        for img in anchor.find_all("img"):
            candidate = self._parse_img_tag(img, base_url)
            if candidate:
                return candidate

        # 2. Search inside atomic card_element
        if card_element and card_element != anchor:
            for img in card_element.find_all("img"):
                candidate = self._parse_img_tag(img, base_url)
                if candidate:
                    return candidate

        for link in card_element.select('link[as="image"][href]'):
            candidate = clean_image_url(link.get("href"), base_url)
            if candidate:
                return candidate
        return None

    def extract_summary(self, anchor, card_element, headline: str) -> Optional[str]:
        """
        Extracts card synopsis or description from nearby paragraph elements within
        the atomic card container. Rejects headline echoes, navigation, relative dates, or standalone badges.
        """
        if not card_element:
            return None

        # Look for explicit description classes or paragraphs inside the atomic card
        for selector in [".desc", ".summary", ".synopsis", ".intro", ".top-story-panel__content > h3.desktop-view", "p"]:
            for elem in card_element.select(selector):
                text = clean_text(elem.get_text(" ", strip=True))
                if not text or len(text) < 15 or len(text) > 2000:
                    continue
                if text == headline or text.lower() == headline.lower():
                    continue
                cleaned = re.sub(r"\s+(?:Exclusive|Exclusive Content|just now|\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago)\s*$", "", text, flags=re.IGNORECASE).strip()
                if cleaned == headline or cleaned.lower() == headline.lower() or len(cleaned) < 15:
                    continue
                if is_navigation_text(text):
                    continue
                if re.match(r"^(\d+)\s*(mins?|hours?|days?)\s*ago$", text, re.IGNORECASE):
                    continue
                return text

        return None

    def extract_published_at(self, card_element) -> Optional[str]:
        """
        Attempts to extract and parse published timestamp using strict priority:
        1. Visible time element
        2. <time datetime="...">
        3. Meta tags
        4. JSON-LD
        Returns ISO 8601 string or None. Never guesses.
        """
        if not card_element:
            return None

        iso, _ = extract_publication_time_with_method(card_element)
        return iso

    def extract_articles_from_html(
        self,
        html: str,
        page_url: str,
        default_section: str = "Overall",
    ) -> tuple[list[Article], int, int]:
        """
        Parses HTML and extracts validated, deduplicated Article objects with strict
        atomic card boundary scoping.
        Returns (articles, candidate_count, duplicates_count).
        """
        soup = BeautifulSoup(html, "html.parser")
        base_url = page_url or self.config.url

        # 1. Check for JSON-LD structured data first
        json_ld_articles: dict[str, Article] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("@type")
                    if item_type in ("NewsArticle", "Article"):
                        cand_items = [item]
                    elif item_type == "ItemList":
                        cand_items = [
                            elem.get("item", elem)
                            for elem in item.get("itemListElement", [])
                            if isinstance(elem, dict)
                        ]
                    else:
                        cand_items = []

                    for cand in cand_items:
                        if not isinstance(cand, dict):
                            continue
                        cand_url = normalize_url(cand.get("url") or "", base_url)
                        if is_valid_et_article_url(cand_url):
                            headline = clean_text(cand.get("headline") or cand.get("name") or "")
                            if len(headline) >= 15:
                                img = cand.get("image")
                                img_url = None
                                if isinstance(img, str):
                                    img_url = clean_image_url(img, base_url)
                                elif isinstance(img, dict):
                                    img_url = clean_image_url(img.get("url") or "", base_url)
                                elif isinstance(img, list) and img:
                                    first_img = img[0]
                                    img_url = clean_image_url(
                                        first_img if isinstance(first_img, str) else first_img.get("url", ""),
                                        base_url,
                                    )

                                summary = clean_text(cand.get("description") or "") or None
                                pub_date = parse_date_to_iso(cand.get("datePublished") or "")
                                sec = cand.get("articleSection") or default_section

                                article = Article(
                                    website=self.config.name,
                                    website_key=self.config.key,
                                    section=sec if sec and sec != "Overall" else self.detect_section(cand_url),
                                    headline=headline,
                                    url=cand_url,
                                    image_url=img_url,
                                    summary=summary,
                                    published_at=pub_date,
                                ).finalize()
                                json_ld_articles[cand_url] = article
            except Exception:
                continue

        # 2. Anchor scan for article cards
        articles_by_url: dict[str, Article] = dict(json_ld_articles)
        candidate_count = len(json_ld_articles)
        duplicates_removed = 0

        anchors = soup.find_all("a", href=True)

        for anchor in anchors:
            raw_href = anchor.get("href")
            if not raw_href:
                continue

            normalized_url = normalize_url(raw_href, page_url)
            if not is_valid_et_article_url(normalized_url):
                continue

            candidate_count += 1

            # Identify the ATOMIC card container: strictly isolated to this single article
            card_element = self.find_atomic_card(anchor, normalized_url, page_url)

            headline = self.extract_headline(anchor, card_element)
            if not headline or len(headline) < 15:
                slug_match = re.search(r"/([a-z0-9-]+)/(\d{5,12})$", normalized_url)
                if slug_match:
                    derived = clean_text(slug_match.group(1).replace("-", " ").title())
                    if len(derived) >= 15 and not is_navigation_text(derived):
                        headline = derived
            if not headline or len(headline) < 15:
                continue

            section = self.detect_section(normalized_url, card_element)
            if section == "Overall" and default_section != "Overall":
                section = default_section

            image_url = self.extract_image(anchor, card_element, page_url)
            summary = self.extract_summary(anchor, card_element, headline)
            published_at = self.extract_published_at(card_element)
            publication_label = extract_relative_time_label(card_element, headline=headline)
            if not published_at and publication_label:
                published_at = parse_relative_date_to_iso(publication_label)
            is_exclusive = extract_exclusive_flag(card_element, headline=headline)

            if normalized_url in articles_by_url:
                duplicates_removed += 1
                curr = articles_by_url[normalized_url]
                if not curr.image_url and image_url:
                    curr.image_url = image_url
                if not curr.summary and summary:
                    curr.summary = summary
                if not curr.published_at and published_at:
                    curr.published_at = published_at
                if not curr.publication_label and publication_label:
                    curr.publication_label = publication_label
                if not curr.is_exclusive and is_exclusive:
                    curr.is_exclusive = is_exclusive
                if curr.section == "Overall" and section != "Overall":
                    curr.section = section
                curr.finalize()
                continue

            article = Article(
                website=self.config.name,
                website_key=self.config.key,
                section=section,
                headline=headline,
                url=normalized_url,
                image_url=image_url,
                summary=summary,
                published_at=published_at,
                publication_label=publication_label,
                is_exclusive=is_exclusive,
            )
            articles_by_url[normalized_url] = article.finalize()

        return list(articles_by_url.values()), candidate_count, duplicates_removed

    def deduplicate_articles(
        self,
        articles: Iterable[Article],
    ) -> tuple[list[Article], int]:
        """
        Deduplicates article records by normalized URL.
        When duplicates occur, keeps the instance with the most complete metadata
        (e.g., has image, summary, or specific section instead of 'Overall').
        """
        unique_map: dict[str, Article] = {}
        duplicates_count = 0

        for art in articles:
            if art.url in unique_map:
                duplicates_count += 1
                existing = unique_map[art.url]

                better_section = existing.section if existing.section != "Overall" else art.section
                better_image = existing.image_url or art.image_url
                better_summary = existing.summary or art.summary
                better_published = existing.published_at or art.published_at
                better_pub_label = existing.publication_label or art.publication_label
                better_is_exclusive = existing.is_exclusive or art.is_exclusive

                merged = Article(
                    website=existing.website,
                    website_key=existing.website_key,
                    section=better_section,
                    headline=existing.headline,
                    url=existing.url,
                    image_url=better_image,
                    summary=better_summary,
                    published_at=better_published,
                    scraped_at=existing.scraped_at,
                    publication_label=better_pub_label,
                    is_exclusive=better_is_exclusive,
                )
                unique_map[art.url] = merged.finalize()
            else:
                unique_map[art.url] = art

        return list(unique_map.values()), duplicates_count

    def enrich_article_from_page(self, article: Article) -> Article:
        from scraper.base.enrichment import enrich_article
        return enrich_article(article, self.fetcher)

    def scrape_homepage(
        self,
        enrich: bool = False,
        max_enrich: Optional[int] = None,
    ) -> tuple[list[Article], dict]:
        """
        Scrapes the ET BrandEquity homepage and deep editorial sections with pagination.
        Returns (articles, stats_dict).
        """
        logger.info("Fetching ET BrandEquity Homepage: %s", self.config.url)
        html = self.fetcher.fetch(
            self.config.url,
            browser_fallback=self.browser_fallback,
        )

        all_articles: list[Article] = []
        candidates = 0
        duplicates_removed = 0
        pages_fetched = 0

        if html:
            pages_fetched += 1
            home_articles, home_cands, home_dups = self.extract_articles_from_html(
                html,
                page_url=self.config.url,
                default_section="Overall",
            )
            all_articles.extend(home_articles)
            candidates += home_cands
            duplicates_removed += home_dups

        # The homepage contains only a rotating subset. Crawl every configured
        # section with pagination to retrieve all available articles.
        for section_cfg in self.config.sections:
            is_news = (
                getattr(section_cfg, "key", "") in ("latest-news", "news")
                or section_cfg.name in ("Latest News", "News")
                or "latest-news" in getattr(section_cfg, "url", "")
            )
            max_pages = 3 if is_news else 2
            seen_in_section: set[str] = set()
            for page_num in range(1, max_pages + 1):
                page_url = section_cfg.url if page_num == 1 else f"{section_cfg.url.rstrip('/')}/{page_num}"
                try:
                    time.sleep(self.delay_seconds)
                    section_html = self.fetcher.fetch(
                        page_url,
                        browser_fallback=self.browser_fallback,
                    )
                    pages_fetched += 1
                    if section_html:
                        sec_articles, sec_cands, sec_dups = self.extract_articles_from_html(
                            section_html,
                            page_url=page_url,
                            default_section=section_cfg.name,
                        )
                        new_urls = [a.url for a in sec_articles if a.url not in seen_in_section]
                        seen_in_section.update(a.url for a in sec_articles)
                        all_articles.extend(sec_articles)
                        candidates += sec_cands
                        duplicates_removed += sec_dups
                        if not sec_articles or (page_num > 1 and len(new_urls) == 0):
                            break
                    else:
                        break
                except Exception as exc:
                    logger.warning("Failed scraping %s page %d: %s", section_cfg.name, page_num, exc)
                    break

        articles, cross_page_duplicates = self.deduplicate_articles(all_articles)
        duplicates_removed += cross_page_duplicates

        # Optionally enrich top stories from individual article pages
        if enrich and articles:
            enrich_limit = len(articles) if max_enrich is None else max_enrich
            logger.info("Enriching metadata for up to %d articles...", enrich_limit)
            enrichment_candidates = sorted(articles, key=lambda art: bool(art.published_at))
            for art in enrichment_candidates[:enrich_limit]:
                time.sleep(self.delay_seconds)
                self.enrich_article_from_page(art)
                pages_fetched += 1

        stats = {
            "pages_fetched": pages_fetched,
            "candidates": candidates,
            "valid_articles": len(articles),
            "duplicates_removed": duplicates_removed,
        }

        return articles, stats
