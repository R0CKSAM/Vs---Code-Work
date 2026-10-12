# Media Reporting System — Scraper Architecture

This directory houses the web crawling and content extraction engines for the Media Reporting System.

---

## Current Status: Phase 2A — ET BrandEquity Real Article Scraper (COMPLETED)

In **Phase 2A**, the scraper foundation was evolved into a dedicated, production-grade article scraper for **ET BrandEquity** (`https://brandequity.economictimes.indiatimes.com/`).

### Key Capabilities Added in Phase 2A:
1. **Accurate Article URL Filtering**: Identifies genuine ET BrandEquity news stories by matching numeric article identifiers while strictly excluding navigation links, section index pages, login, newsletters, webinars, and search anchors.
2. **Canonical URL Normalization**: Converts relative URLs to absolute URLs, removes URL fragments, and strips marketing tracking parameters (`utm_source`, `utm_medium`, `ref`, etc.) to prevent duplicate records.
3. **Automatic Section Detection**: Detects sections directly from URL paths (`/news/marketing/` → `Marketing`, `/news/digital/` → `Digital`, `/news/business-of-brands/` → `Business of Brands`, etc.) and card badges, falling back to `Overall`.
4. **Hero Image Extraction**: Prioritizes `data-original` and `data-src` over placeholder GIFs, rejecting SVG icons, logos, and tracking pixels.
5. **Card Summary & Synopsis Extraction**: Extracts clean ~2-line card descriptions while discarding duplicates of headlines and timestamp strings.
6. **Published Date/Time Parsing**: Extracts and normalizes dates from `<time>`, card badges, and meta tags into ISO 8601 UTC strings (`published_at`), distinct from `scraped_at`.
7. **Deterministic SHA-256 Content Hash**: Computes checksums on article content fields (`website_key||section||headline||url||image_url||summary`), strictly omitting `scraped_at` so identical articles yield stable hashes across repeat scrapes.
8. **Deduplication Engine**: Merges duplicate mentions across the homepage, retaining the entry with the richest metadata.
9. **Quality Reporting**: Outputs comprehensive run statistics (candidates, valid articles, duplicates removed, field percentage breakdown) and 10 sample articles.

---

## Directory Structure

```
scraper/
├── base/
│   ├── article.py             # Article dataclass & SHA-256 hashing
│   └── fetcher.py             # PageFetcher with Requests & robots.txt verification
├── et_brand_equity/
│   ├── config.py              # WebsiteConfig & section slug maps
│   └── scraper.py             # ET BrandEquity card parser & metadata enrichment
├── utils/
│   ├── url.py                 # Normalization & article URL validator
│   ├── cleaning.py            # Text cleaning & image URL sanitizer
│   └── date_parser.py         # ISO 8601 date parsing for RFC 2822, relative dates
├── __init__.py
└── README.md
```

---

## Running the Scraper

Run directly using system Python from the project root (`d:/MFA/media-reporting-system`):

### 1. Default Homepage Scraping (Pure Requests + BeautifulSoup)
```powershell
python media_reporting_scraper_foundation.py --site et_brand_equity --mode homepage --no-browser-fallback
```

### 2. Homepage Scraping with Top Article Metadata Enrichment
```powershell
python media_reporting_scraper_foundation.py --site et_brand_equity --mode homepage --enrich --max-enrich 10
```

### 3. Section Scraping
```powershell
python media_reporting_scraper_foundation.py --site et_brand_equity --mode sections --delay 2.0
```

---

## Output Format

Output is saved to `scraper_output/et_brand_equity.json`:

```json
{
  "generated_at": "2026-09-23T07:45:00.000000+00:00",
  "website": "et_brand_equity",
  "count": 25,
  "articles": [
    {
      "website": "ET BrandEquity",
      "website_key": "et_brand_equity",
      "section": "Marketing",
      "headline": "Brands want Reddit. They just don’t get it!",
      "url": "https://brandequity.economictimes.indiatimes.com/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838",
      "image_url": "https://etimg.etb2bimg.com/thumb/msid-134424838...jpg",
      "summary": "Discover how brands are navigating the unique challenges...",
      "published_at": "2026-09-23T03:22:34+00:00",
      "scraped_at": "2026-09-23T07:45:00.000000+00:00",
      "content_hash": "68c3c0e9ada2ba2ec7191d4be4cf5780b4c274cb38f55f8236dd6b978e93ebaf"
    }
  ]
}
```

---

## Next Phase: Phase 2B — Dashboard Integration
In Phase 2B, the verified `scraper_output/et_brand_equity.json` will be connected to the FastAPI backend and displayed on the interactive React dashboard.
