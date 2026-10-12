"""
Media Reporting System - Indian Television Article Scraper
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
from scraper.indiantelevision.config import (
    INDIAN_TELEVISION,
    INDIAN_TELEVISION_SECTION_SLUG_MAP,
    WebsiteConfig,
)
from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import (
    extract_exclusive_flag,
    extract_publication_time_with_method,
    extract_relative_time_label,
    parse_date_to_iso,
)
from scraper.utils.url import (
    extract_indiantelevision_section_slug,
    is_valid_indiantelevision_article_url,
    normalize_url,
)

logger = logging.getLogger("media-scraper")


class IndianTelevisionScraper:
    """
    Dedicated article scraper for Indian Television (indiantelevision.com).
    Extracts validated articles from homepage news cards, section listings, or individual pages.
    """

    def __init__(
        self,
        config: WebsiteConfig = INDIAN_TELEVISION,
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
        if card_element:
            for selector in [".mvp-cd-cat", ".mvp-post-cat", ".cat-links", ".cat-name", ".category", "span.tag"]:
                badge = card_element.select_one(selector)
                if badge:
                    badge_text = clean_text(badge.get_text())
                    if badge_text and len(badge_text) >= 2 and not is_navigation_text(badge_text):
                        return badge_text.title()

        slug = extract_indiantelevision_section_slug(url)
        if slug and slug in INDIAN_TELEVISION_SECTION_SLUG_MAP:
            return INDIAN_TELEVISION_SECTION_SLUG_MAP[slug]

        if slug:
            return slug.replace("-", " ").title()

        return "Television"

    def find_atomic_card(self, anchor, target_url: str, base_url: str):
        curr = anchor
        best_container = anchor

        while curr and curr.parent and curr.parent.name not in ["body", "html", "[document]"]:
            parent = curr.parent
            distinct_article_urls = set()
            for a in parent.find_all("a", href=True):
                href = a.get("href", "")
                norm = normalize_url(href, base_url)
                if is_valid_indiantelevision_article_url(norm):
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

        if card_element:
            for h in card_element.find_all(["h1", "h2", "h3", "h4", "h5", "h6", ".mvp-stand-title", ".post-title"]):
                text = clean_text(h.get_text(" ", strip=True))
                if len(text) >= 15 and not is_navigation_text(text):
                    return text

        title_attr = anchor.get("title")
        if title_attr:
            cleaned = clean_text(title_attr)
            if len(cleaned) >= 15 and not is_navigation_text(cleaned):
                return cleaned

        anchor_text = clean_text(anchor.get_text(" ", strip=True))
        if len(anchor_text) >= 15 and not is_navigation_text(anchor_text):
            return anchor_text

        return None

    def extract_image_url(self, card_element, base_url: str) -> Optional[str]:
        if not card_element:
            return None

        for img in card_element.find_all("img"):
            for attr in ["data-src", "data-lazy-src", "data-original", "src"]:
                val = img.get(attr)
                if val:
                    val = clean_image_url(val, base_url)
                    if val and not val.endswith((".svg", ".gif", "logo.png")):
                        return normalize_url(val, base_url)

            srcset = img.get("srcset")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                if parts:
                    best = parts[-1]
                    best = clean_image_url(best, base_url)
                    if best:
                        return normalize_url(best, base_url)

        return None

    def extract_summary(self, card_element) -> Optional[str]:
        if not card_element:
            return None

        for selector in [".mvp-feat1-feat-text p", ".mvp-widget-feat2-left-text p", ".mvp-flex-story-text p", "p", ".excerpt", ".summary"]:
            p = card_element.select_one(selector)
            if p:
                text = clean_text(p.get_text(" ", strip=True))
                if len(text) >= 20 and not is_navigation_text(text):
                    return text

        return None

    def extract_author(self, card_element) -> Optional[str]:
        if not card_element:
            return None

        for selector in [".mvp-author-info-date a", ".author-name", ".mvp-authors-name", ".byline a", ".author a"]:
            el = card_element.select_one(selector)
            if el:
                author_name = clean_text(el.get_text())
                if author_name and len(author_name) > 2 and not is_navigation_text(author_name):
                    return author_name

        return None

    def extract_date_info(self, card_element, base_url: str) -> tuple[Optional[str], Optional[str]]:
        if not card_element:
            return None, None

        iso_time, _method = extract_publication_time_with_method(card_element, base_url=base_url)
        relative_label = extract_relative_time_label(card_element)

        if not relative_label:
            date_span = card_element.select_one(".mvp-cd-date, .mvp-post-date, .post-date, time")
            if date_span:
                txt = clean_text(date_span.get_text())
                if txt and ("ago" in txt.lower() or "yesterday" in txt.lower()):
                    relative_label = txt

        return iso_time, relative_label

    def _enrich_article(self, article: Article) -> Article:
        """Fetch article detail page to extract published_at, full summary, author, and high-res image."""
        try:
            html = self.fetcher.fetch(article.url, browser_fallback=self.browser_fallback)
            if not html:
                return article

            soup = BeautifulSoup(html, "html.parser")

            # Check Yoast schema graph
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                try:
                    data = json.loads(script.string or "")
                    nodes = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    for node in nodes:
                        if not isinstance(node, dict):
                            continue
                        ntype = node.get("@type", "")
                        types = ntype if isinstance(ntype, list) else [ntype]
                        if any(t in ["NewsArticle", "Article", "BlogPosting"] for t in types):
                            if not article.published_at:
                                pub = node.get("datePublished") or node.get("dateCreated")
                                if pub:
                                    parsed = parse_date_to_iso(pub)
                                    if parsed:
                                        article.published_at = parsed

                            if not article.summary:
                                desc = node.get("description")
                                if desc:
                                    article.summary = clean_text(desc)

                            if not article.image_url:
                                img = node.get("image")
                                if isinstance(img, dict):
                                    article.image_url = clean_image_url(img.get("url") or img.get("contentUrl") or "", self.config.url)
                                elif isinstance(img, str):
                                    article.image_url = clean_image_url(img, self.config.url)
                except Exception:
                    continue

            # Fallback DOM meta tags
            if not article.published_at:
                for meta_name in ["article:published_time", "publishdate", "datePublished", "pubdate"]:
                    meta = soup.find("meta", {"property": meta_name}) or soup.find("meta", {"name": meta_name})
                    if meta and meta.get("content"):
                        parsed = parse_date_to_iso(meta.get("content"))
                        if parsed:
                            article.published_at = parsed
                            break

            if not article.image_url:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    article.image_url = clean_image_url(og_img.get("content"), self.config.url)

            if not article.summary:
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", {"name": "description"})
                if og_desc and og_desc.get("content"):
                    desc = clean_text(og_desc.get("content"))
                    if desc and len(desc) >= 30 and not is_navigation_text(desc):
                        article.summary = desc

            article.finalize()
        except Exception as exc:
            logger.debug("Failed to enrich Indian Television article %s: %s", article.url, exc)

        return article

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
                nodes = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in nodes:
                    if not isinstance(item, dict):
                        continue
                    itype = item.get("@type", "")
                    types = itype if isinstance(itype, list) else [itype]
                    if any(t in ("NewsArticle", "Article", "BlogPosting") for t in types):
                        url = normalize_url(item.get("url") or "", base_url)
                        if is_valid_indiantelevision_article_url(url):
                            headline = clean_text(item.get("headline") or item.get("name") or "")
                            if len(headline) >= 15:
                                img = item.get("image")
                                img_url = None
                                if isinstance(img, str):
                                    img_url = clean_image_url(img, base_url)
                                elif isinstance(img, dict):
                                    img_url = clean_image_url(img.get("url") or img.get("contentUrl") or "", base_url)
                                elif isinstance(img, list) and img:
                                    first = img[0]
                                    img_url = clean_image_url(first if isinstance(first, str) else first.get("url", ""), base_url)

                                summary = clean_text(item.get("description") or "") or None
                                pub_date = parse_date_to_iso(item.get("datePublished") or item.get("dateCreated") or "")
                                sec = item.get("articleSection") or default_section
                                is_excl = extract_exclusive_flag(headline)

                                article = Article(
                                    website=self.config.name,
                                    website_key=self.config.key,
                                    section=sec if sec and sec != "Overall" else self.detect_section(url),
                                    headline=headline,
                                    url=url,
                                    image_url=img_url,
                                    summary=summary,
                                    published_at=pub_date,
                                    is_exclusive=is_excl,
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

            if not is_valid_indiantelevision_article_url(canonical_url):
                continue

            candidates_count += 1
            card_elem = self.find_atomic_card(anchor, canonical_url, base_url)
            headline = self.extract_headline(anchor, card_elem)

            if not headline or len(headline) < 15:
                continue

            image_url = self.extract_image_url(card_elem, base_url)
            summary = self.extract_summary(card_elem)
            published_at, pub_label = self.extract_date_info(card_elem, base_url)
            section = self.detect_section(canonical_url, card_elem)
            is_exclusive = extract_exclusive_flag(headline, card_elem)

            if canonical_url in articles_by_url:
                duplicates_count += 1
                existing = articles_by_url[canonical_url]
                if not existing.image_url and image_url:
                    existing.image_url = image_url
                if not existing.summary and summary:
                    existing.summary = summary
                if not existing.published_at and published_at:
                    existing.published_at = published_at
                if not existing.publication_label and pub_label:
                    existing.publication_label = pub_label
                if not existing.is_exclusive and is_exclusive:
                    existing.is_exclusive = is_exclusive
                if existing.section in ("Overall", "Television") and section not in ("Overall", "Television"):
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
                publication_label=pub_label,
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
                if curr.section in ("Overall", "Television") and art.section not in ("Overall", "Television"):
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
        logger.info("Fetching Indian Television homepage: %s", self.config.url)
        html = self.fetcher.fetch(self.config.url, browser_fallback=self.browser_fallback)

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

        if len(all_articles) < 15 and self.config.sections:
            logger.info("Homepage returned %d articles. Scraping primary sections...", len(all_articles))
            for section_cfg in self.config.sections[:3]:
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

        final_articles, extra_dups = self.deduplicate_articles(all_articles)
        total_duplicates += extra_dups

        if enrich:
            from scraper.base.enrichment import enrich_article
            enrich_limit = len(final_articles) if max_enrich is None else max_enrich
            for article in final_articles[:enrich_limit]:
                if not article.summary or not article.image_url or not article.published_at:
                    time.sleep(self.delay_seconds)
                    try:
                        self._enrich_article(article)
                    except Exception:
                        enrich_article(article, self.fetcher)
                    pages_fetched += 1

        stats = {
            "pages_fetched": pages_fetched,
            "candidates": total_candidates,
            "valid_articles": len(final_articles),
            "duplicates_removed": total_duplicates,
        }

        return final_articles, stats
