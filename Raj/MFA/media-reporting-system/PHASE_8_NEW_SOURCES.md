# Phase 8 — Seven-Source Media Monitoring System Architecture

## Overview

The Media Reporting System has been expanded from a dual-portal monitor (ET BrandEquity, Exchange4media) to an enterprise seven-source intelligence suite tracking the Indian media, advertising, marketing, and broadcast landscape.

All seven sources operate under a unified pipeline:
```
Publisher Website (HTTP)
       │
       ▼
PageFetcher (Robots.txt compliance + Session reuse)
       │
       ▼
Source-Specific Scraper (Atomic card boundary isolation + JSON-LD + DOM anchors)
       │
       ▼
Validation Gate (Minimum 5 articles safeguard against false removals)
       │
       ▼
ChangeDetector (Lifecycle classification: NEW / UPDATED / UNCHANGED / REMOVED)
       │
       ▼
Database Persistence (SQLite: websites, sections, articles, article_versions, scrape_runs)
       │
       ▼
Advertisement Monitoring (Creative detection + dimension & brand inference)
       │
       ▼
Monitoring Engine & Scheduler (Failure isolation: one site failing never stops others)
       │
       ▼
FastAPI REST APIs & Responsive Interactive Dashboard
```

---

## The Seven Monitored Publications

| # | Publication | Website Key | Base URL | Primary Focus |
|---|---|---|---|---|
| 1 | **ET BrandEquity** | `et_brand_equity` | `https://brandequity.economictimes.indiatimes.com/` | Marketing, brand strategy, advertising |
| 2 | **Exchange4media** | `exchange4media` | `https://www.exchange4media.com/` | Media, broadcast, advertising news |
| 3 | **Campaign India** | `campaign_india` | `https://www.campaignindia.in/news` | Creative campaigns, agencies, digital |
| 4 | **BestMediaInfo** | `bestmediainfo` | `https://bestmediainfo.com/` | Television, marketing, broadcast trends |
| 5 | **Social Samosa** | `social_samosa` | `https://www.socialsamosa.com/` | Social media, viral campaigns, case studies |
| 6 | **Adgully** | `adgully` | `https://www.adgully.com/` | Marketing exclusives, advertising scoops |
| 7 | **MediaBrief** | `mediabrief` | `https://mediabrief.com/` | Media, OTT, streaming, entertainment |

---

## Source Scraper Details & Strategies

### 1. Campaign India (`scraper/campaign_india/`)
- **Package**: `scraper.campaign_india.CampaignIndiaScraper`
- **Configuration**: `CAMPAIGN_INDIA`, `CAMPAIGN_INDIA_SECTION_SLUG_MAP`
- **URL Pattern**: `/article/<slug>/<id>` or `/article/<slug>`
- **Extraction Strategy**:
  - Structured data: Scans `application/ld+json` for `NewsArticle` / `Article` schema.
  - DOM traversal: Identifies atomic cards containing unique article URLs.
  - Section mapping: Resolves from URL slug (`/advertising`, `/marketing`, `/media`, `/digital`, `/people`) or `.section`, `.category`, `.channel` badges.
  - Image handling: Extracts from `srcset`, `data-src`, `data-original`, and `src`.
  - Quality thresholds: Headlines >= 15 characters, summaries >= 20 characters.

### 2. BestMediaInfo (`scraper/bestmediainfo/`)
- **Package**: `scraper.bestmediainfo.BestMediaInfoScraper`
- **Configuration**: `BESTMEDIAINFO`, `BESTMEDIAINFO_SECTION_SLUG_MAP`
- **URL Pattern**: `/\d{4}/\d{2}/<slug>` or `/post/<slug>`
- **Extraction Strategy**:
  - Scans JSON-LD news items then traverses news card elements.
  - Section mapping: Mapped across Advertising, Marketing, Digital, Television, Media.
  - Summary extraction: Inspects `.summary`, `.desc`, `.synopsis`, `.story-content`, `.excerpt`.
  - Date normalization: Normalizes both ISO timestamps and formatted date strings to UTC ISO 8601.

### 3. Social Samosa (`scraper/social_samosa/`)
- **Package**: `scraper.social_samosa.SocialSamosaScraper`
- **Configuration**: `SOCIAL_SAMOSA`, `SOCIAL_SAMOSA_SECTION_SLUG_MAP`
- **URL Pattern**: WordPress dated paths `/\d{4}/\d{2}/<slug>/` or `/<slug>/`
- **Extraction Strategy**:
  - Scans WordPress `<article>` cards and JSON-LD schemas.
  - Section mapping: Social Media, Campaigns, Case Studies, Interviews, Features.
  - Summary extraction: Resolves from `.entry-summary`, `.post-excerpt`, or paragraph elements.
  - Image handling: Resolves lazy-loaded hero images via `data-src` and `data-lazy-src`.

### 4. Adgully (`scraper/adgully/`)
- **Package**: `scraper.adgully.AdgullyScraper`
- **Configuration**: `ADGULLY`, `ADGULLY_SECTION_SLUG_MAP`
- **URL Pattern**: `/<slug>-<numeric_id>.html` or `/[section]/<slug>-<id>.html`
- **Extraction Strategy**:
  - Atomic card boundary isolation prevents adjacent card leaks.
  - Section mapping: Marketing, Advertising, Media, Digital, Exclusives.
  - **Exclusive Flag**: Explicitly detects `EXCLUSIVE:` prefixes in headlines, `Exclusives` section paths, and editorial badges.
  - Content preservation: Preserves real publication timestamps independently of exclusive markers.

### 5. MediaBrief (`scraper/mediabrief/`)
- **Package**: `scraper.mediabrief.MediaBriefScraper`
- **Configuration**: `MEDIABRIEF`, `MEDIABRIEF_SECTION_SLUG_MAP`
- **URL Pattern**: WordPress paths `/<article-slug>/` or `/\d{4}/\d{2}/<article-slug>/`
- **Extraction Strategy**:
  - Scans structured rich cards across categories: Advertising, Marketing, Media, Digital, Exclusive.
  - **Exclusive Flag**: Detects `Exclusive` badges and category tags.
  - **Critical Rule Followed**: Does NOT destroy the true `published_at` timestamp when an article is labeled as Exclusive.

---

## Architectural Guarantees & Safeguards

### 1. Failure Isolation
- In `backend/monitoring/engine.py`, each website is refreshed in an isolated `try/except` block inside `run_monitoring_cycle()`.
- If one publisher is experiencing network downtime, 502/503 HTTP errors, or anti-bot protections, its error is logged, its status marked `FAILED` in `MonitoringStatus`, and the remaining 6 publishers continue processing without interruption.

### 2. False Removal Safeguards
- In `backend/app/services/change_detector.py`, safe removal detection requires at least **5 articles** in a scrape batch.
- If a scraper fails or returns fewer than 5 items due to partial network failure, existing active articles are preserved and NOT purged or marked REMOVED.

### 3. Deduplication & Content Hash
- Articles are deduplicated per-batch by canonical URL.
- When an article appears multiple times on a page, the scraper retains the version with the richest metadata (hero image, published timestamp, full synopsis).
- Two distinct SHA-256 hashes are used:
  - `Article.content_hash`: Scraper-level hash (`website_key||section||headline||url||image_url||summary`).
  - `ChangeDetector.content_hash`: Change-detection hash (`headline|summary|image_url|section|published_at`), ignoring volatile run metadata.

### 4. Zero Cross-Contamination
- `_validate_articles` in `backend/monitoring/engine.py` asserts that every article in a batch belongs to the expected `website_key`. Cross-site leaks are blocked immediately before reaching the database.

---

## REST API Endpoints

All endpoints support GET for articles and POST `/refresh` for live on-demand re-scraping:

| Publication | Articles Endpoint | Refresh Endpoint |
|---|---|---|
| ET BrandEquity | `GET /api/monitoring/et-brand-equity/articles` | `POST /api/monitoring/et-brand-equity/refresh` |
| Exchange4media | `GET /api/monitoring/exchange4media/articles` | `POST /api/monitoring/exchange4media/refresh` |
| Campaign India | `GET /api/monitoring/campaign-india/articles` | `POST /api/monitoring/campaign-india/refresh` |
| BestMediaInfo | `GET /api/monitoring/bestmediainfo/articles` | `POST /api/monitoring/bestmediainfo/refresh` |
| Social Samosa | `GET /api/monitoring/social-samosa/articles` | `POST /api/monitoring/social-samosa/refresh` |
| Adgully | `GET /api/monitoring/adgully/articles` | `POST /api/monitoring/adgully/refresh` |
| MediaBrief | `GET /api/monitoring/mediabrief/articles` | `POST /api/monitoring/mediabrief/refresh` |

### Unified Endpoints (All 7 Sources)
- `GET /api/dashboard`: Overview across all 7 sources with KPI summary and interleaved news.
- `GET /api/monitoring/status`: Operational health across all 7 sources.
- `POST /api/monitoring/run-now`: Triggers a full 7-source scrape cycle immediately.
- `GET /api/monitoring/changes?website=<key>&timeframe=today`: Tracks changes across all 7 sources.
- `GET /api/reports/daily`, `/api/reports/weekly`, `/api/reports/custom`: Cross-publisher intelligence reports.

---

## Verification & Testing

### Automated Test Suite (`tests/test_phase8_new_sources.py`)
Includes **80 comprehensive automated tests**:
- 15 tests for Campaign India (URL regex, ID, section, headline, image, summary, date, exclusive, atomic card, dedup, mock scrape)
- 15 tests for BestMediaInfo
- 15 tests for Social Samosa
- 15 tests for Adgully
- 15 tests for MediaBrief (including date preservation with exclusive badge)
- 5 integration tests verifying all 7 sources in engine, status, metadata, and router registry

### Commands to Run

```powershell
# Run the complete Phase 8 test suite
cd D:\MFA\media-reporting-system
$env:PYTHONPATH='backend;.'
python -m unittest tests/test_phase8_new_sources.py -v

# Run the integration check
python backend/test_integration.py

# Run all project tests
python -m unittest discover tests -v

# Start the application server
python run_server.py
```
