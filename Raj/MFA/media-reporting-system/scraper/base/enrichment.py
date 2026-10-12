"""Article-page metadata extraction shared by both publishers."""
import json
import re

from bs4 import BeautifulSoup

from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import extract_publication_time_with_method, parse_date_to_iso
from scraper.utils.url import normalize_url


def _looks_like_blocked_or_mismatched_page(soup: BeautifulSoup, requested_url: str) -> bool:
    """Reject challenge pages and publisher redirects before copying metadata."""
    title_text = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = clean_text(h1.get_text(" ", strip=True)) if h1 else ""
    lower_blob = f"{title_text} {h1_text}".lower()
    if (
        "just a moment" in lower_blob
        or "checking your browser" in lower_blob
        or "attention required" in lower_blob
        or h1_text.lower() in {"www.exchange4media.com", "exchange4media.com"}
    ):
        return True

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        canonical_url = normalize_url(canonical["href"], requested_url)
        original_url = normalize_url(requested_url, requested_url)
        if canonical_url and canonical_url != original_url:
            return True

    return False


def enrich_article(article, fetcher):
    html = fetcher.fetch(article.url, browser_fallback=True)
    # Some lightweight/custom fetchers expose only fetch_requests(). A mock or
    # other non-text response is not valid markup, so use that direct method as
    # a compatibility fallback instead of passing an arbitrary object to bs4.
    if not isinstance(html, (str, bytes)):
        direct_fetch = getattr(fetcher, "fetch_requests", None)
        html = direct_fetch(article.url) if callable(direct_fetch) else None
    if not html:
        return article
    soup = BeautifulSoup(html, "html.parser")
    if _looks_like_blocked_or_mismatched_page(soup, article.url):
        return article
    canonical = soup.find("link", rel="canonical")
    canonical_url = (
        normalize_url(canonical["href"], article.url)
        if canonical and canonical.get("href")
        else None
    )

    def meta(*names):
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return clean_text(tag["content"])
        return None

    def normalized_section(value):
        section = clean_text(value or "")
        section = re.sub(r"[-_]+", " ", section)
        section = re.sub(r"\s+", " ", section).strip()
        if not section or len(section) > 100:
            return None
        if section.lower() == article.headline.lower():
            return None
        return section

    # The individual article page is authoritative. Listing cards are discovery
    # inputs only and may contain shortened headlines, stale images, or relative
    # timestamps. Correct conflicting listing values instead of filling blanks.
    page_heading = soup.find("h1")
    page_headline = clean_text(page_heading.get_text(" ", strip=True)) if page_heading else ""
    if page_headline and len(page_headline) >= 15 and not is_navigation_text(page_headline):
        article.headline = page_headline

    page_summary = meta("og:description", "description", "twitter:description")
    if page_summary and page_summary.lower() != article.headline.lower():
        article.summary = page_summary

    page_image = clean_image_url(meta("og:image", "twitter:image"), article.url)
    if page_image:
        article.image_url = page_image

    page_published_at = parse_date_to_iso(
        meta(
            "article:published_time",
            "publish-date",
            "created-date",
            "og:published_time",
            "published_date",
            "publishdate",
            "pubdate",
            "date",
            "datePublished",
            "cXenseParse:recs:publishtime",
            "rdate",
            "sailthru.date",
            "parsely-pub-date",
        ) or ""
    )
    if not page_published_at:
        # Strict extraction ignores modified timestamps and never substitutes
        # scrape time for publication time.
        page_published_at, _ = extract_publication_time_with_method(soup)
    if page_published_at:
        article.published_at = page_published_at

    page_section = normalized_section(meta("article:section"))
    if page_section:
        article.section = page_section

    page_author = meta("author", "article:author", "byl")
    if page_author and not is_navigation_text(page_author):
        article.author = page_author

    def nodes(value):
        if isinstance(value, list):
            for item in value:
                yield from nodes(item)
        elif isinstance(value, dict):
            yield value
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    yield from nodes(nested)

    structured_section = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for item in nodes(data):
            kind = item.get("@type", [])
            if isinstance(kind, str):
                kind = [kind]
            if "BreadcrumbList" in kind and not structured_section:
                crumbs = item.get("itemListElement") or []
                names = []
                for crumb in crumbs:
                    if not isinstance(crumb, dict):
                        continue
                    name = crumb.get("name")
                    nested_item = crumb.get("item")
                    if not name and isinstance(nested_item, dict):
                        name = nested_item.get("name")
                    name = clean_text(name or "")
                    if name:
                        names.append(name)
                # The final crumb is the article itself; the preceding crumb is
                # the publisher's most specific section/category.
                if len(names) >= 2:
                    candidate = names[-2]
                    if candidate.lower() not in ("home", "homepage"):
                        structured_section = normalized_section(candidate)
            if not any(t in kind for t in ("NewsArticle", "Article", "BlogPosting", "WebPage")):
                continue

            structured_headline = clean_text(item.get("headline") or item.get("name") or "")
            if (
                not page_headline
                and len(structured_headline) >= 15
                and not is_navigation_text(structured_headline)
            ):
                article.headline = structured_headline
            article_section = item.get("articleSection")
            if isinstance(article_section, list):
                article_section = article_section[0] if article_section else None
            article_section = normalized_section(article_section)
            if article_section:
                structured_section = article_section
            structured_published = parse_date_to_iso(item.get("datePublished") or item.get("dateCreated") or "")
            if structured_published and not article.published_at:
                article.published_at = structured_published
            if isinstance(item.get("description"), str) and not page_summary:
                structured_summary = clean_text(item["description"])
                if structured_summary and structured_summary.lower() != article.headline.lower():
                    article.summary = structured_summary
            if not page_author:
                author = item.get("author")
                if isinstance(author, list):
                    author = author[0] if author else None
                if isinstance(author, dict):
                    author = author.get("name")
                structured_author = clean_text(author or "")
                if structured_author and not is_navigation_text(structured_author):
                    article.author = structured_author
            img = item.get("image")
            if isinstance(img, list):
                img = img[0] if img else None
            if isinstance(img, dict):
                img = img.get("url") or img.get("contentUrl")
            if isinstance(img, str) and not page_image:
                structured_image = clean_image_url(img, article.url)
                if structured_image:
                    article.image_url = structured_image

    # Priority fallback: Scan byline and header containers for written date text
    if not article.published_at:
        byline_candidates = soup.select(
            ".story-details, .story-content, .artByline, .author-details, .byline, "
            ".article-byline, .entry-meta, .post-meta, .article-meta, header"
        )
        for bc in byline_candidates:
            text = bc.get_text(" ", strip=True)
            iso = parse_date_to_iso(text)
            if iso:
                article.published_at = iso
                break

    if not page_section and structured_section:
        article.section = structured_section
    return article.finalize()


def enrich_article_dict(art_dict: dict, fetcher) -> dict:
    """Convenience helper to enrich a plain article dictionary with detail page metadata."""
    url = art_dict.get("url")
    if not url:
        return art_dict

    try:
        html = fetcher.fetch(url, browser_fallback=True) if hasattr(fetcher, "fetch") else None
        if not html and hasattr(fetcher, "fetch_requests"):
            html = fetcher.fetch_requests(url)
        if not html:
            return art_dict

        soup = BeautifulSoup(html, "html.parser")
        if _looks_like_blocked_or_mismatched_page(soup, url):
            return art_dict

        # 1. Headline
        if not art_dict.get("headline") or len(str(art_dict.get("headline", ""))) < 15:
            h1 = soup.find("h1")
            if h1:
                hl = clean_text(h1.get_text(" ", strip=True))
                if len(hl) >= 15 and not is_navigation_text(hl):
                    art_dict["headline"] = hl

        # 2. Published date
        if not art_dict.get("published_at"):
            def _meta(*names):
                for name in names:
                    tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
                    if tag and tag.get("content"):
                        return clean_text(tag["content"])
                return None

            pub_iso = parse_date_to_iso(
                _meta(
                    "article:published_time", "publish-date", "created-date",
                    "og:published_time", "published_date", "publishdate", "pubdate",
                    "date", "datePublished", "cXenseParse:recs:publishtime", "rdate"
                ) or ""
            )
            if not pub_iso:
                pub_iso, _ = extract_publication_time_with_method(soup)
            if not pub_iso:
                byline_candidates = soup.select(
                    ".story-details, .story-content, .artByline, .author-details, .byline, "
                    ".article-byline, .entry-meta, .post-meta, .article-meta, header"
                )
                for bc in byline_candidates:
                    txt = bc.get_text(" ", strip=True)
                    pub_iso = parse_date_to_iso(txt)
                    if pub_iso:
                        break

            if pub_iso:
                art_dict["published_at"] = pub_iso

        # 3. Image
        if not art_dict.get("image_url"):
            og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if og_img and og_img.get("content"):
                c_img = clean_image_url(og_img["content"], url)
                if c_img:
                    art_dict["image_url"] = c_img

        # 4. Summary
        if not art_dict.get("summary"):
            desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
            if desc and desc.get("content"):
                sum_txt = clean_text(desc["content"])
                if sum_txt and sum_txt.lower() != str(art_dict.get("headline", "")).lower():
                    art_dict["summary"] = sum_txt

    except Exception:
        pass

    return art_dict
