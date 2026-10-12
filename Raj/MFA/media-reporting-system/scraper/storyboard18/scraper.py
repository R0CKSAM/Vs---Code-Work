"""
Media Reporting System - Storyboard18 Article Scraper
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
from scraper.storyboard18.config import (
    STORYBOARD18,
    STORYBOARD18_SECTION_SLUG_MAP,
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
    extract_storyboard18_article_id,
    extract_storyboard18_section_slug,
    is_valid_storyboard18_article_url,
    normalize_url,
)

logger = logging.getLogger("media-scraper")


class Storyboard18Scraper:
    """
    Dedicated article scraper for Storyboard18 (storyboard18.com).
    Extracts verified news cards from homepage and section pages,
    enriches with publication metadata from JSON-LD and page DOM.
    """

    def __init__(
        self,
        config: WebsiteConfig = STORYBOARD18,
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
        slug = extract_storyboard18_section_slug(url)
        if slug and slug in STORYBOARD18_SECTION_SLUG_MAP:
            return STORYBOARD18_SECTION_SLUG_MAP[slug]

        if card_element:
            for selector in [
                ".text-caption", ".category", ".cat-name", ".section",
                ".photo-gallery-category", ".vdctgnme", "span.tag", "h4"
            ]:
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
                if is_valid_storyboard18_article_url(norm):
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
            img.get("src"),
            img.get("data-src"),
            img.get("data-original"),
            img.get("data-lazy-src"),
        ]
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            parts = [s.strip().split(" ")[0] for s in srcset.split(",") if s.strip()]
            if parts:
                candidates.insert(0, parts[-1])

        for c in candidates:
            if not c or c.startswith("data:image"):
                continue
            cleaned = clean_image_url(c, base_url=base_url)
            if cleaned and not any(bad in cleaned.lower() for bad in ["logo", "icon", "blank", "placeholder", "pixel", "avatar", "default"]):
                return cleaned
        return None

    def extract_image_url(self, card_element, anchor, base_url: str) -> Optional[str]:
        for scope in [anchor, card_element]:
            if not scope:
                continue
            for ns in scope.find_all("noscript"):
                ns_soup = BeautifulSoup(ns.decode_contents(), "html.parser")
                img = ns_soup.find("img")
                img_url = self._parse_img_tag(img, base_url)
                if img_url:
                    return img_url

            for img in scope.find_all("img"):
                img_url = self._parse_img_tag(img, base_url)
                if img_url:
                    return img_url
        return None

    def extract_summary(self, card_element, anchor) -> Optional[str]:
        if not card_element:
            return None
        for p in card_element.find_all(["p", "span.desc", "div.desc", "div.summary"]):
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) >= 20 and not is_navigation_text(text):
                return text
        return None

    def extract_card_date_and_label(self, card_element) -> tuple[Optional[str], Optional[str]]:
        if not card_element:
            return None, None
        date_iso, _method = extract_publication_time_with_method(card_element)
        if date_iso:
            label = extract_relative_time_label(card_element)
            return date_iso, label

        for selector in [".date", ".time", ".pub-date", "time", "span.story-date", ".meta-date"]:
            elem = card_element.select_one(selector)
            if elem:
                txt = clean_text(elem.get_text())
                d_iso = parse_date_to_iso(txt)
                if d_iso:
                    return d_iso, txt
        return None, None

    def extract_author(self, card_element) -> Optional[str]:
        if not card_element:
            return None
        for selector in [".author", ".byline", ".writer", "span.author-name", "a.author"]:
            elem = card_element.select_one(selector)
            if elem:
                txt = clean_text(elem.get_text())
                if txt and len(txt) > 2 and not is_navigation_text(txt):
                    txt = re.sub(r"^by\s+", "", txt, flags=re.IGNORECASE)
                    return txt
        return None

    def _enrich_article(self, article: Article) -> Article:
        if not article.url:
            return article
        try:
            html = self.fetcher.fetch(article.url, browser_fallback=self.browser_fallback)
            if not html:
                return article

            soup = BeautifulSoup(html, "html.parser")

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if isinstance(item, dict):
                            t = item.get("@type", "")
                            if t in ["NewsArticle", "Article", "BlogPosting"]:
                                if not article.published_at and item.get("datePublished"):
                                    parsed = parse_date_to_iso(item.get("datePublished"))
                                    if parsed:
                                        article.published_at = parsed
                                if not article.author:
                                    auth = item.get("author")
                                    if isinstance(auth, dict) and auth.get("name"):
                                        article.author = clean_text(auth.get("name"))
                                    elif isinstance(auth, list) and auth and isinstance(auth[0], dict):
                                        article.author = clean_text(auth[0].get("name"))
                                    elif isinstance(auth, str):
                                        article.author = clean_text(auth)
                                if not article.summary and item.get("description"):
                                    desc = clean_text(item.get("description"))
                                    if desc and len(desc) >= 30:
                                        article.summary = desc
                                if not article.image_url and item.get("image"):
                                    img = item.get("image")
                                    if isinstance(img, dict) and img.get("url"):
                                        article.image_url = clean_image_url(img.get("url"), self.config.url)
                                    elif isinstance(img, str):
                                        article.image_url = clean_image_url(img, self.config.url)
                except Exception:
                    pass

            if not article.published_at:
                for meta_name in ["datePublished", "article:published_time", "publishdate", "pubdate"]:
                    meta = soup.find("meta", {"itemprop": meta_name}) or soup.find("meta", {"property": meta_name}) or soup.find("meta", {"name": meta_name})
                    if meta and meta.get("content"):
                        parsed = parse_date_to_iso(meta.get("content"))
                        if parsed:
                            article.published_at = parsed
                            break

            if not article.author:
                for meta_name in ["author", "article:author", "byl"]:
                    meta = soup.find("meta", {"name": meta_name}) or soup.find("meta", {"property": meta_name})
                    if meta and meta.get("content"):
                        author_cand = clean_text(meta.get("content"))
                        if author_cand and not is_navigation_text(author_cand):
                            article.author = author_cand
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
            logger.debug("Failed to enrich Storyboard18 article %s: %s", article.url, exc)

        return article

    def extract_articles_from_html(
        self,
        html: str,
        page_url: Optional[str] = None,
        default_section: str = "Overall",
    ) -> tuple[list[Article], int, int]:
        base_url = page_url or self.config.url
        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD structured data
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
                        if is_valid_storyboard18_article_url(url):
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
        candidates_seen = len(json_ld_articles)
        duplicates_filtered = 0

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue
            normalized_url = normalize_url(href, base_url)
            if not is_valid_storyboard18_article_url(normalized_url):
                continue

            candidates_seen += 1
            card = self.find_atomic_card(a, normalized_url, base_url)
            headline = self.extract_headline(a, card)
            if not headline or len(headline) < 15:
                slug_match = re.search(r"/([a-z0-9-]+)-(?:\d{4,9})\.html", normalized_url) or re.search(r"/([a-z0-9-]+)\.html", normalized_url)
                if slug_match:
                    derived = clean_text(slug_match.group(1).replace("-", " ").title())
                    if len(derived) >= 15 and not is_navigation_text(derived):
                        headline = derived
            if not headline or len(headline) < 15:
                continue

            image_url = self.extract_image_url(card, a, base_url)
            summary = self.extract_summary(card, a)
            section = self.detect_section(normalized_url, card) or default_section
            published_at, pub_label = self.extract_card_date_and_label(card)
            if not published_at and pub_label:
                published_at = parse_relative_date_to_iso(pub_label)
            is_exclusive = bool(re.match(r"^\s*\[?exclusive\]?\s*[:\-]?", headline, re.IGNORECASE))
            if not is_exclusive:
                is_exclusive = extract_exclusive_flag(card, headline=headline)

            if normalized_url in articles_by_url:
                duplicates_filtered += 1
                curr = articles_by_url[normalized_url]
                if not curr.image_url and image_url:
                    curr.image_url = image_url
                if not curr.summary and summary:
                    curr.summary = summary
                if not curr.published_at and published_at:
                    curr.published_at = published_at
                if not curr.publication_label and pub_label:
                    curr.publication_label = pub_label
                if not curr.is_exclusive and is_exclusive:
                    curr.is_exclusive = is_exclusive
                if curr.section == "Overall" and section != "Overall":
                    curr.section = section
                curr.finalize()
                continue

            art = Article(
                website=self.config.name,
                website_key=self.config.key,
                section=section,
                headline=headline,
                url=normalized_url,
                image_url=image_url,
                summary=summary,
                published_at=published_at,
                publication_label=pub_label,
                is_exclusive=is_exclusive,
            ).finalize()
            articles_by_url[normalized_url] = art

        articles = list(articles_by_url.values())
        return articles, candidates_seen, duplicates_filtered

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

    def scrape_homepage(self, enrich: bool = False, max_enrich: Optional[int] = None) -> tuple[list[Article], dict]:
        logger.info("[SCRAPER] Scraping Storyboard18: %s", self.config.url)
        all_articles = []
        pages_fetched = 0
        candidates = 0
        duplicates = 0

        # 1. Fetch homepage
        html = self.fetcher.fetch(self.config.url, browser_fallback=self.browser_fallback)
        if html:
            pages_fetched += 1
            arts, cands, dups = self.extract_articles_from_html(html, self.config.url, "Overall")
            all_articles.extend(arts)
            candidates += cands
            duplicates += dups

        # 2. Fetch sections with pagination
        for sec in self.config.sections:
            max_pages = 3 if sec.name == "Latest News" else 2
            seen_in_sec: set[str] = set()
            for page_num in range(1, max_pages + 1):
                sec_url = sec.url if page_num == 1 else f"{sec.url.rstrip('/')}/page-{page_num}"
                try:
                    time.sleep(self.delay_seconds)
                    sec_html = self.fetcher.fetch(sec_url, browser_fallback=self.browser_fallback)
                    pages_fetched += 1
                    if sec_html:
                        arts, cands, dups = self.extract_articles_from_html(sec_html, sec_url, sec.name)
                        new_urls = [a.url for a in arts if a.url not in seen_in_sec]
                        seen_in_sec.update(a.url for a in arts)
                        all_articles.extend(arts)
                        candidates += cands
                        duplicates += dups
                        if not arts or (page_num > 1 and len(new_urls) == 0):
                            break
                    else:
                        break
                except Exception as exc:
                    logger.warning("Failed scraping %s page %d: %s", sec.name, page_num, exc)
                    break

        articles, extra_dups = self.deduplicate_articles(all_articles)
        duplicates += extra_dups

        if enrich and articles:
            from scraper.base.enrichment import enrich_article
            enrichment_candidates = sorted(articles, key=lambda art: bool(art.published_at))
            to_enrich = enrichment_candidates[:max_enrich] if max_enrich else enrichment_candidates
            logger.info("[SCRAPER] Enriching %d Storyboard18 articles", len(to_enrich))
            for art in to_enrich:
                time.sleep(self.delay_seconds)
                enrich_article(art, self.fetcher)
                pages_fetched += 1

        stats = {
            "pages_fetched": pages_fetched,
            "candidates": candidates,
            "valid_articles": len(articles),
            "duplicates_removed": duplicates,
        }
        logger.info("[SCRAPER] Storyboard18 scraping finished. Valid: %d", len(articles))
        return articles, stats
