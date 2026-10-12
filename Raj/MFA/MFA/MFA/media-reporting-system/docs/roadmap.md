# Media Reporting System - Project Roadmap

This document outlines the phased development plan for the Media Reporting System.

---

## 📌 Phase Overview

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
Foundations  UI Polish   ET Scraper   E4M Scraper  PostgreSQL

     ▲
     └──────► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9 ──► Phase 10
              Changes     Ad Monitor   Scheduling   Reports      Expansion    Production
```

---

## Detailed Phases

### ✅ PHASE 0: Foundation (CURRENT)
- Establish project directory structure: `backend/`, `frontend/`, `scraper/`, `database/`, `storage/`, `reports/`, `docs/`.
- Build FastAPI backend with `/api/health` and `/api/dashboard`.
- Build React + TypeScript + Vite frontend with corporate media intelligence dashboard layout.
- Configure CORS, client API service layer, and Pydantic schemas.
- Set up fallback mock data and zero-crash offline resilience.
- **Intentionally omitted**: No scrapers, no PostgreSQL, no real external website connections, no Docker/Celery/Redis.

---

### 🔜 PHASE 1: Professional UI
- Expand filter interactions (multi-source filtering, custom date pickers).
- Implement responsive drawer navigation and tablet/mobile optimization.
- Add advanced data tables with sorting, pagination, and article detail modal drawers.
- Build dedicated views for all sidebar sub-routes.

---

### 🔜 PHASE 2: ET BrandEquity Scraper
- Implement `scraper/et_brand_equity/` module using Requests and BeautifulSoup.
- Extract article headlines, summaries, authors, sections, publication timestamps, and canonical URLs.
- Introduce rate limiting, politeness delays, and user-agent rotation in `scraper/utils/`.

---

### 🔜 PHASE 3: Exchange4media Scraper
- Implement `scraper/exchange4media/` module.
- Parse category feeds (Digital, Marketing, Advertising, Broadcast, Agency).
- Normalize scraped article payloads to match shared Pydantic ingestion contracts.

---

### 🔜 PHASE 4: Database and History
- Introduce PostgreSQL relational database.
- Integrate SQLAlchemy 2.0 and Alembic migrations in `database/migrations/`.
- Persist articles, monitored website records, and crawl execution logs.
- Replace FastAPI mock data service with database query services.

---

### 🔜 PHASE 5: Change Detection
- Implement DOM content snapshotting and visual diff comparisons.
- Track editorial headline modifications, article updates, and homepage layout shifts.
- Record historical version snapshots per article.

---

### 🔜 PHASE 6: Advertisement Monitoring
- Integrate Playwright headless browser for full rendering of client-side ad scripts.
- Detect display ad units, sticky banners, masthead placements, and sponsored stories.
- Capture and store ad banner screenshots inside `storage/advertisements/`.

---

### 🔜 PHASE 7: 10-Minute Automated Monitoring
- Implement local automated scheduling for continuous 10-minute crawl cycles.
- Add failure recovery, network retry mechanisms, and crawl telemetry.
- Expose real-time worker status via `/api/system/scraper-status`.

---

### 🔜 PHASE 8: Reports
- Implement automated daily and weekly report generation.
- Produce formatted PDF intelligence briefings using Jinja2 and WeasyPrint.
- Produce structured Excel spreadsheets of tracked advertiser activity using `openpyxl`.
- Save outputs to `reports/generated/`.

---

### 🔜 PHASE 9: Additional Websites
- Expand scraper coverage to further advertising and marketing news portals (e.g. Campaign India, Afaqs).
- Enable dynamic onboarding of new RSS/HTML sources via the UI.

---

### 🔜 PHASE 10: Production Deployment
- Containerization with Docker and Docker Compose.
- Background worker architecture (Redis + Celery or RQ).
- Production reverse proxy (Nginx / Caddy), authentication, and role-based access controls.
