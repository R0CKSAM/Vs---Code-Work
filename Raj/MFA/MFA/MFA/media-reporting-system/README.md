# Media Reporting System

Current repair notes and operating instructions: [News and advertisement data repair](docs/scraping_repair_2026-09-24.md). The phase descriptions below are historical; the application now uses SQLite, scheduled monitoring, and browser-based ad collection.

A professional, local, free and open-source media monitoring and reporting platform.

> **Current Phase: PHASE 3 — EXCHANGE4MEDIA REAL ARTICLE SCRAPER & DASHBOARD INTEGRATION (COMPLETED)**  
> Real articles scraped from both **ET BrandEquity** and **Exchange4media** are parsed, validated, and integrated into FastAPI and the live browser dashboard.  
> *Note: Advertisements, content diffs, automated scheduler, and PostgreSQL remain preview/mock or future phases.*

---

## 1. Purpose

The **Media Reporting System** is designed to provide automated monitoring, intelligence gathering, and reporting across major media, marketing, and advertising portals.

Target portals:
1. **ET BrandEquity** (`https://brandequity.economictimes.indiatimes.com/`) — **ACTIVE & INTEGRATED (Phase 2)**
2. **Exchange4media** (`https://www.exchange4media.com/`) — **ACTIVE & INTEGRATED (Phase 3)**

---

## 2. Technology Stack

- **Frontend**: Zero-Node.js vanilla HTML5/ES6/CSS corporate dashboard served directly by FastAPI (`backend/app/static/`) or standalone React/TypeScript Vite build (`frontend/`).
- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **Scraper Pipeline (Phases 2 & 3)**: Requests, BeautifulSoup4, URL normalizer, deterministic SHA-256 content hashing (`scraper/`)
- **Future Database (Phase 4)**: PostgreSQL (with SQLAlchemy 2.0 & Alembic)

---

## 3. Project Structure

```
media-reporting-system/
├── backend/                  # FastAPI backend service
│   ├── app/
│   │   ├── api/              # API router and endpoints (/health, /dashboard, /monitoring/*)
│   │   ├── core/             # Configuration and CORS settings
│   │   ├── models/           # Database entity models (Phase 4)
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── services/         # ET & E4M services & mock data generator
│   │   ├── static/           # Zero-Node browser UI (app.js, style.css, index.html)
│   │   ├── utils/            # Shared utilities
│   │   └── main.py           # FastAPI entry point
│   ├── requirements.txt      # Python dependencies
│   ├── test_integration.py   # Direct verification test suite
│   └── README.md
├── scraper/                  # Scraper Pipeline
│   ├── base/                 # Article model, PageFetcher (Requests + robots.txt)
│   ├── et_brand_equity/      # ET BrandEquity configuration and scraper
│   ├── exchange4media/       # Exchange4media configuration and scraper
│   ├── utils/                # URL normalizers, text cleaners, date parsers
│   └── test_scraper.py       # Scraper unit verification suite
├── scraper_output/           # Real scraper output JSON files
│   ├── et_brand_equity.json  # 25 verified ET articles
│   └── exchange4media.json   # 25 verified E4M articles
├── media_reporting_scraper_foundation.py # CLI scraper runner
├── frontend/                 # React + TypeScript + Vite frontend
├── docs/                     # Architecture, Development, and Roadmap documentation
└── README.md                 # Master project documentation
```

---

## 4. How to Run Locally

### Start the Backend (FastAPI with System Python)
```bash
# 1. Navigate to backend directory
cd backend

# 2. Install dependencies directly into system Python
python -m pip install -r requirements.txt

# 3. Start the server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Accessing the Application:
- **Interactive Web Dashboard (Zero Node.js Required)**: **`http://127.0.0.1:8000/`**
- **Exchange4media Real Articles Endpoint**: `http://127.0.0.1:8000/api/monitoring/exchange4media/articles`
- **ET BrandEquity Real Articles Endpoint**: `http://127.0.0.1:8000/api/monitoring/et-brand-equity/articles`
- **Unified Dashboard Aggregation**: `http://127.0.0.1:8000/api/dashboard`
- **Health Check Endpoint**: `http://127.0.0.1:8000/api/health`
- **Interactive API Documentation (Swagger)**: `http://127.0.0.1:8000/docs`

---

## 5. Dual Publisher Scraping & Integration Architecture

```
  ET BrandEquity Website              Exchange4media Website
             ↓                                   ↓
  scraper/et_brand_equity/             scraper/exchange4media/
             ↓                                   ↓
  scraper_output/                      scraper_output/
    et_brand_equity.json                 exchange4media.json
             ↓                                   ↓
  backend/app/services/                backend/app/services/
    et_brand_equity_service.py           exchange4media_service.py
             \                                   /
              v                                 v
        GET /api/dashboard & GET /api/monitoring/*
                             ↓
              Enterprise Dashboard Browser UI
                  (http://127.0.0.1:8000/)
```

---

## 6. What is Intentionally Deferred in Phase 3

- ❌ **PostgreSQL**: Retained as file-based JSON until Phase 4.
- ❌ **Content & Visual Change Detection**: Scheduled for Phase 5.
- ❌ **Ad Scraping & Screenshot Capture**: Scheduled for Phase 6.
- ❌ **Automated Cron / 10-Minute Scheduler**: Scheduled for Phase 7.
- ❌ **Automated PDF/Excel Reports**: Scheduled for Phase 8.

---

## 7. Roadmap Status

- **PHASE 0**: Foundation (Completed)
- **PHASE 1**: Professional UI Expansion (Completed)
- **PHASE 2A**: ET BrandEquity Real Article Scraper (Completed)
- **PHASE 2B**: ET BrandEquity Dashboard Integration (Completed)
- **PHASE 3**: Exchange4media Scraper & Dashboard Integration (Completed)
- **PHASE 4**: PostgreSQL Database and Historical Archival (Next)
- **PHASE 5**: Content & Visual Change Detection
- **PHASE 6**: Advertisement Monitoring & Screenshot Capture
- **PHASE 7**: 10-Minute Automated Monitoring Engine
- **PHASE 8**: Automated PDF/Excel Reports
- **PHASE 9**: Additional Media Websites Onboarding
- **PHASE 10**: Production Hardening & Deployment
