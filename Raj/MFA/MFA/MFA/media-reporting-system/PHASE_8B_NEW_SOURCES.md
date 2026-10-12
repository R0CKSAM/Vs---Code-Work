# Phase 8B — Media Reporting System: Nine Sources Integration

## Executive Summary

Phase 8B expands the Media Reporting System pipeline at `D:\MFA\media-reporting-system` from 7 to **9 monitored media publications**:
1. **ET Brand Equity** (`et_brand_equity`)
2. **Exchange4media** (`exchange4media`)
3. **Campaign India** (`campaign_india`)
4. **BestMediaInfo** (`bestmediainfo`)
5. **Social Samosa** (`social_samosa`)
6. **Adgully** (`adgully`)
7. **MediaBrief** (`mediabrief`)
8. **Storyboard18** (`storyboard18`) — *New in Phase 8B*
9. **Indian Television** (`indiantelevision`) — *New in Phase 8B*

Zero breaking changes or regressions were introduced to existing scraper code, authentication, permissions, or database schema.

---

## 1. Newly Added Media Sources

### 1.1 Storyboard18 (`storyboard18`)
- **Portal URL**: `https://www.storyboard18.com/`
- **Focus**: Brand marketing, creative agency strategies, advertising technology, and cultural trends.
- **Article URL Structure**: `https://www.storyboard18.com/<category>/<slug>-<article_id>.htm` (e.g. `https://www.storyboard18.com/brand-marketing/from-vogue-to-gq-conde-nast-bets-big-on-ai-to-expand-readership-111547.htm`).
- **Scraper Package**: `scraper/storyboard18/`
  - `config.py`: `STORYBOARD18` `WebsiteConfig`, sections (`Brand & Marketing`, `Advertising`, `Agency`, `Digital`), slug mappings.
  - `scraper.py`: `Storyboard18Scraper` featuring atomic card isolation, Next.js `<noscript><img ...>` extraction, JSON-LD schema parsing, and SHA-256 content deduplication.
  - `__init__.py`: Package exports for clean imports.

### 1.2 Indian Television (`indiantelevision`)
- **Portal URL**: `https://indiantelevision.com/`
- **Focus**: Broadcast television, cable/DTH distribution, regulatory policy (TRAI/MIB), and digital streaming.
- **Article URL Structure**: `https://indiantelevision.com/<category>/<slug>/` (e.g. `https://indiantelevision.com/mam/mruci-re-elects-vikram-sakhuja-and-dhruba-mukherjee-as-chairman-and-vice-chairman/`).
- **Scraper Package**: `scraper/indiantelevision/`
  - `config.py`: `INDIAN_TELEVISION` `WebsiteConfig`, sections (`Television`, `MAM`, `iWorld`, `Cable TV`, `DTH`, `Movies`, `Regulators`), slug mappings.
  - `scraper.py`: `IndianTelevisionScraper` featuring WordPress `zox-news` theme DOM parsers, Yoast SEO schema graph extraction, relative timestamp parsers (`2 hours ago`), and SHA-256 content hashing.
  - `__init__.py`: Package exports for clean imports.

---

## 2. Architecture & File Updates

| Component | Files Modified / Created | Details |
| :--- | :--- | :--- |
| **URL Utilities** | `scraper/utils/url.py` | Added `is_valid_storyboard18_article_url`, `extract_storyboard18_article_id`, `extract_storyboard18_section_slug`, `is_valid_indiantelevision_article_url`, `extract_indiantelevision_article_id`, `extract_indiantelevision_section_slug`. |
| **Scraper Modules** | `scraper/storyboard18/` (3 files)<br>`scraper/indiantelevision/` (3 files)<br>`scraper/__init__.py` | Implemented full scraper classes and configs; re-exported in package root. |
| **Monitoring Engine** | `backend/monitoring/engine.py` | Added both sources to `MONITORED_WEBSITES`, scraper dispatch, and ad detection base URLs. |
| **Status Store** | `backend/monitoring/status.py` | Added `'storyboard18'` and `'indiantelevision'` to `_WEBSITE_KEYS` in-memory state tracking. |
| **Change Detection** | `backend/app/services/change_detector.py` | Registered default website metadata for both sources. |
| **Data Orchestration** | `backend/app/services/mock_data.py` | Loaded 9 sources, aggregated 9-source KPIs (`websites_monitored=9`), and interleaved 9-source news stream. |
| **API Endpoints** | `backend/app/api/endpoints/storyboard18_articles.py`<br>`backend/app/api/endpoints/indiantelevision_articles.py`<br>`backend/app/api/endpoints/__init__.py`<br>`backend/app/api/endpoints/news.py` | Added `/monitoring/storyboard18/articles`, `/monitoring/storyboard18/refresh`, `/monitoring/indiantelevision/articles`, `/monitoring/indiantelevision/refresh`, registered in `api_router`, and added `WEBSITE_ALIASES`. |
| **CLI Runner** | `media_reporting_scraper_foundation.py` | Added `--site storyboard18`, `--site indiantelevision`, and full 9-source execution via `--site all`. |
| **Frontend Styling** | `backend/app/static/styles.css` | Added badges `.tag-sb18` (orange) and `.tag-itv` (emerald green) in light and dark modes. |
| **Frontend Logic** | `backend/app/static/app.js` | Updated `matchesSource`, `getSourceTagClass`, `sourcesMeta` filter chips (`SB18`, `ITV`), `extraSources`, `slugMap`, `allEndpoints`, dropdowns, and slide-over drawer inspection. |
| **Frontend Markup** | `backend/app/static/index.html` | Updated sidebar footer counter to `9 Sources online`, header subtitle to `9 monitored publications`, and bumped cache buster. |
| **Data Snapshots** | `scraper_output/storyboard18.json`<br>`scraper_output/indiantelevision.json` | Created 10 verified articles per source with summaries, publication dates, and content hashes. |
| **Test Suite** | `tests/test_phase8b_two_sources.py` | 35 comprehensive automated tests covering URL validation, DOM parsers, deduplication, mocked scraping, and full 9-source backend integration. |

---

## 3. Final Source Health Table (All 9 Publications)

| # | Publication | Key | Base URL | Status | Section Detection | Exclusive Detection | Image Extraction |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| 1 | **ET BrandEquity** | `et_brand_equity` | `https://brandequity.economictimes.indiatimes.com/` | **ACTIVE** | URL Slug + Breadcrumb | Yes (`[Exclusive]`) | Yes (ET CDN) |
| 2 | **Exchange4media** | `exchange4media` | `https://www.exchange4media.com/` | **ACTIVE** | Path Slug + Card Tag | Yes (`e4m Exclusive`) | Yes (E4M S3) |
| 3 | **Campaign India** | `campaign_india` | `https://www.campaignindia.in/news` | **ACTIVE** | Path Slug + Category | Yes (Regex Flag) | Yes (Campaign CDN) |
| 4 | **BestMediaInfo** | `bestmediainfo` | `https://bestmediainfo.com/` | **ACTIVE** | Slug Map + Breadcrumbs | Yes (`Exclusive:`) | Yes (BMI Uploads) |
| 5 | **Social Samosa** | `social_samosa` | `https://www.socialsamosa.com/` | **ACTIVE** | WP Taxonomies + Badges | Yes (Headline Flag) | Yes (WP Media) |
| 6 | **Adgully** | `adgully` | `https://www.adgully.com/` | **ACTIVE** | Category Slug + Tag | Yes (`EXCLUSIVE`) | Yes (Static CDN) |
| 7 | **MediaBrief** | `mediabrief` | `https://mediabrief.com/` | **ACTIVE** | Slug Map + Cat Links | Yes (`EXCLUSIVE:`) | Yes (WP Uploads) |
| 8 | **Storyboard18** | `storyboard18` | `https://www.storyboard18.com/` | **ACTIVE** | Category Slug + DOM Badge | Yes (`EXCLUSIVE:`) | Yes (Next.js / Noscript) |
| 9 | **Indian Television** | `indiantelevision` | `https://indiantelevision.com/` | **ACTIVE** | WP Section + `.mvp-cd-cat` | Yes (`EXCLUSIVE:`) | Yes (Yoast / Zox Thumb) |

---

## 4. Verification & Automated Test Results

The test suite at `tests/test_phase8b_two_sources.py` provides:
- **15 Tests for Storyboard18**: URL validation (valid, advertising, roots, blocked, domain root), ID extraction, section slug extraction, category mapping, headline extraction, Next.js image noscript handling, summary extraction, publication date parsing, editorial exclusive detection, SHA-256 deduplication, mocked homepage crawl.
- **15 Tests for Indian Television**: URL validation (valid MAM, television, category roots, non-article pages, domain root), ID extraction, section slug extraction, iWorld/Gaming detection, headline extraction, `.wp-post-image` extraction, excerpt parsing, relative date extraction (`3 hours ago`), editorial exclusive detection, deduplication, mocked homepage crawl.
- **5 Multi-Portal Integration Tests**: Verified 9 monitored websites in `backend/monitoring/engine.py`, 9 keys in `backend/monitoring/status.py`, 9 entries in `DEFAULT_WEBSITE_METADATA`, data loading across both new sources, and `websites_monitored=9` in dashboard responses.
