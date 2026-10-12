"""Article-page metadata extraction shared by both publishers."""
import json

from bs4 import BeautifulSoup

from scraper.utils.cleaning import clean_image_url, clean_text
from scraper.utils.date_parser import extract_publication_time_with_method, parse_date_to_iso
from scraper.utils.url import normalize_url


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

    if not article.summary:
        summary = meta("og:description", "description", "twitter:description")
        if summary and summary != article.headline:
            article.summary = summary
    if not article.image_url:
        article.image_url = clean_image_url(meta("og:image", "twitter:image"), article.url)
    if not article.published_at:
        article.published_at = parse_date_to_iso(meta("article:published_time", "publish-date", "created-date") or "")
    if not article.published_at:
        # Use the shared strict extractor for visible timestamps, <time> tags,
        # microdata, and publisher-specific metadata. It deliberately ignores
        # modified/update timestamps and never substitutes the scrape time.
        article.published_at, _ = extract_publication_time_with_method(soup)

    def nodes(value):
        if isinstance(value, list):
            for item in value:
                yield from nodes(item)
        elif isinstance(value, dict):
            yield value
            yield from nodes(value.get("@graph", []))

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for item in nodes(data):
            kind = item.get("@type", [])
            if isinstance(kind, str):
                kind = [kind]
            if not any(t in kind for t in ("NewsArticle", "Article", "BlogPosting")):
                continue
            url = item.get("url") or item.get("mainEntityOfPage")
            if isinstance(url, dict):
                url = url.get("@id")
            if isinstance(url, str):
                item_url = normalize_url(url, article.url)
                accepted_urls = {normalize_url(article.url, article.url)}
                if canonical_url:
                    accepted_urls.add(canonical_url)
                if item_url not in accepted_urls:
                    continue
            if not article.published_at:
                article.published_at = parse_date_to_iso(item.get("datePublished") or "")
            if not article.summary and isinstance(item.get("description"), str):
                article.summary = clean_text(item["description"]) or None
            img = item.get("image")
            if isinstance(img, list):
                img = img[0] if img else None
            if isinstance(img, dict):
                img = img.get("url") or img.get("contentUrl")
            if not article.image_url and isinstance(img, str):
                article.image_url = clean_image_url(img, article.url)
    return article.finalize()
