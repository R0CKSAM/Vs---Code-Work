"""
Media Reporting System - Social Samosa Article Scraper
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
from scraper.social_samosa.config import (
    SOCIAL_SAMOSA,
    SOCIAL_SAMOSA_SECTION_SLUG_MAP,
    WebsiteConfig,
)
from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import (
    extract_exclusive_flag,
    extract_publication_time_with_method,
    extract_relative_time_label,
    parse_date_to_iso,
    parse_relative_date_to_iso,
)
from scraper.utils.url import (
    extract_social_samosa_section_slug,
    is_valid_social_samosa_article_url,
    normalize_url,
)

logger = logging.getLogger("media-scraper")


class SocialSamosaScraper:
    """
    Dedicated article scraper for Social Samosa (socialsamosa.com).
    Extracts validated articles from homepage news cards, section listings, or individual pages.
    """

    def __init__(
        self,
        config: WebsiteConfig = SOCIAL_SAMOSA,
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
        slug = extract_social_samosa_section_slug(url)
        if slug and slug in SOCIAL_SAMOSA_SECTION_SLUG_MAP:
            return SOCIAL_SAMOSA_SECTION_SLUG_MAP[slug]

        if card_element:
            for selector in [".post-category", ".cat-links", ".category", ".cat-name", ".badge", "span.tag"]:
                badge = card_element.select_one(selector)
                if badge:
                    badge_text = clean_text(badge.get_text())
                    if badge_text and len(badge_text) > 2 and not is_navigation_text(badge_text):
                        return badge_text.title()

        if slug:
            return slug.replace("-", " ").title()

        return "Overall"

    def find_atomic_card(self, anchor, target_url: str, base_url: str):
        curr = anchor
        best_container = anchor

        while curr and curr.parent and curr.parent.name not in ["body", "html", "[document]"]:
            parent = curr.parent
            distinct_article_urls = set()
            for a in parent.find_all("a", href=True):
                href = a.get("href", "")
                norm = normalize_url(href, base_url)
                if is_valid_social_samosa_article_url(norm):
                    distinct_article_urls.add(norm)

            if len(distinct_article_urls) > 1:
                break

            curr = parent
            if curr.name in ["article", "li", "figure", "div", "section"]:
                best_container = curr

        return best_container

    def extract_headline(self, anchor, card_element=None) -> Optional[str]:
        heading_inside = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading_inside:
            text = clean_text(heading_inside.get_text(" ", strip=True))
            if len(text) >= 15 and not is_navigation_text(text):
                return text

        title_attr = clean_text(anchor.get("title"))
        if title_attr and len(title_attr) >= 15 and not is_navigation_text(title_attr):
            return title_attr

        anchor_text = clean_text(anchor.get_text(" ", strip=True))
        if len(anchor_text) >= 15 and not is_navigation_text(anchor_text):
            return anchor_text

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
        candidates = [
            img.get("data-src"),
            img.get("data-original"),
            img.get("data-lazy-src"),
            img.get("src"),
        ]
        srcset = img.get("srcset")
        if srcset:
            parts = [c.strip().split()[0] for c in srcset.split(",") if c.strip()]
            if parts:
                candidates.insert(0, parts[-1])

        for candidate in candidates:
            clean = clean_image_url(candidate, base_url=base_url)
            if clean:
                return clean
        return None

    def extract_image_url(self, anchor, card_element=None, base_url: str = "") -> Optional[str]:
        for img in anchor.find_all("img"):
            clean = self._parse_img_tag(img, base_url)
            if clean:
                return clean

        if card_element and card_element != anchor:
            for img in card_element.find_all("img"):
                clean = self._parse_img_tag(img, base_url)
                if clean:
                    return clean

        return None

    def extract_summary(self, card_element, headline: str = "") -> Optional[str]:
        if not card_element:
            return None

        for selector in [".post-excerpt", ".excerpt", ".desc", ".summary", ".synopsis", "p"]:
            for elem in card_element.select(selector):
                text = clean_text(elem.get_text(" ", strip=True))
                if not text or len(text) < 20 or len(text) > 2000:
                    continue
                if is_navigation_text(text):
                    continue
                if headline and text.lower() == headline.lower():
                    continue
                cleaned = re.sub(
                    r"\s+(?:Exclusive|Exclusive Content|just now|\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago)\s*$",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
                if headline and (cleaned == headline or cleaned.lower() == headline.lower() or len(cleaned) < 15):
                    continue
                if re.match(r"^(\d+)\s*(mins?|hours?|days?)\s*ago$", text, re.IGNORECASE):
                    continue
                return text

        return None

    def extract_published_date(self, card_element) -> Optional[str]:
        if not card_element:
            return None
        iso, _ = extract_publication_time_with_method(card_element)
        return iso

    def extract_articles_from_html(
        self,
        html: str,
        page_url: str = "",
        default_section: str = "Overall",
    ) -> tuple[list[Article], int, int]:
        soup = BeautifulSoup(html, "html.parser")
        base_url = page_url or self.config.url

        json_ld_articles: dict[str, Article] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("@type")
                    if item_type in ("NewsArticle", "Article", "BlogPosting"):
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
                        url = normalize_url(cand.get("url") or "", base_url)
                        if is_valid_social_samosa_article_url(url):
                            headline = clean_text(cand.get("headline") or cand.get("name") or "")
                            if len(headline) >= 15:
                                img = cand.get("image")
                                img_url = None
                                if isinstance(img, str):
                                    img_url = clean_image_url(img, base_url)
                                elif isinstance(img, dict):
                                    img_url = clean_image_url(img.get("url") or "", base_url)
                                elif isinstance(img, list) and img:
                                    first = img[0]
                                    img_url = clean_image_url(
                                        first if isinstance(first, str) else first.get("url", ""),
                                        base_url,
                                    )

                                summary = clean_text(cand.get("description") or "") or None
                                pub_date = parse_date_to_iso(cand.get("datePublished") or "")
                                sec = cand.get("articleSection") or default_section

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

        articles_by_url: dict[str, Article] = dict(json_ld_articles)
        candidates_count = len(json_ld_articles)
        duplicates_count = 0

        for anchor in soup.find_all("a", href=True):
            raw_href = anchor.get("href", "").strip()
            canonical_url = normalize_url(raw_href, base_url=base_url)

            if not is_valid_social_samosa_article_url(canonical_url):
                continue

            candidates_count += 1
            card_elem = self.find_atomic_card(anchor, canonical_url, base_url)

            headline = self.extract_headline(anchor, card_element=card_elem)
            if not headline or len(headline) < 15:
                slug_match = re.search(r"/([a-z0-9-]+)/?$", canonical_url)
                if slug_match:
                    derived = clean_text(slug_match.group(1).replace("-", " ").title())
                    if len(derived) >= 15 and not is_navigation_text(derived):
                        headline = derived
            if not headline or len(headline) < 15:
                continue

            section = self.detect_section(canonical_url, card_element=card_elem)
            if section == "Overall" and default_section != "Overall":
                section = default_section

            image_url = self.extract_image_url(anchor, card_element=card_elem, base_url=base_url)
            summary = self.extract_summary(card_elem, headline=headline)
            published_at = self.extract_published_date(card_elem)
            publication_label = extract_relative_time_label(card_elem, headline=headline)
            if not published_at and publication_label:
                published_at = parse_relative_date_to_iso(publication_label)
            is_exclusive = extract_exclusive_flag(card_elem, headline=headline)

            if canonical_url in articles_by_url:
                duplicates_count += 1
                existing = articles_by_url[canonical_url]
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

    def deduplicate_articles(self, articles: Iterable[Article]) -> tuple[list[Article], int]:
        unique_map: dict[str, Article] = {}
        duplicates_removed = 0

        for art in articles:
            if art.url in unique_map:
                duplicates_removed += 1
                curr = unique_map[art.url]
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
        logger.info("Fetching Social Samosa homepage: %s", self.config.url)
        all_articles: list[Article] = []
        total_candidates = 0
        total_duplicates = 0
        pages_fetched = 0

        html = self.fetcher.fetch(self.config.url, browser_fallback=self.browser_fallback)
        if html:
            pages_fetched += 1
            homepage_articles, candidates, duplicates = self.extract_articles_from_html(
                html, page_url=self.config.url
            )
            all_articles.extend(homepage_articles)
            total_candidates += candidates
            total_duplicates += duplicates

        for section_cfg in self.config.sections:
            seen_in_sec: set[str] = set()
            for page_num in range(1, 3):
                sec_url = section_cfg.url if page_num == 1 else f"{section_cfg.url.rstrip('/')}/page/{page_num}"
                try:
                    time.sleep(self.delay_seconds)
                    sec_html = self.fetcher.fetch(sec_url, browser_fallback=self.browser_fallback)
                    pages_fetched += 1
                    if sec_html:
                        sec_arts, cands, dups = self.extract_articles_from_html(
                            sec_html, page_url=sec_url, default_section=section_cfg.name
                        )
                        new_urls = [a.url for a in sec_arts if a.url not in seen_in_sec]
                        seen_in_sec.update(a.url for a in sec_arts)
                        all_articles.extend(sec_arts)
                        total_candidates += cands
                        total_duplicates += dups
                        if not sec_arts or (page_num > 1 and len(new_urls) == 0):
                            break
                    else:
                        break
                except Exception as exc:
                    logger.warning("Failed scraping %s page %d: %s", section_cfg.name, page_num, exc)
                    break

        final_articles, extra_dups = self.deduplicate_articles(all_articles)
        total_duplicates += extra_dups

        if enrich:
            from scraper.base.enrichment import enrich_article
            enrich_limit = len(final_articles) if max_enrich is None else max_enrich
            enrichment_candidates = sorted(final_articles, key=lambda art: bool(art.published_at))
            for article in enrichment_candidates[:enrich_limit]:
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
