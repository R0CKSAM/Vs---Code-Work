# Media Reporting System - Development Guide

This guide details how to install, run, and develop the Media Reporting System locally in **Phase 3 — Exchange4media Scraper & Dashboard Integration**.

---

## 1. System Requirements

- **Operating System**: Windows, macOS, or Linux
- **Python**: 3.10 or higher
- **Node.js**: Not required for daily development (Zero-Node UI is bundled directly in FastAPI static files).

---

## 2. Backend Setup & Execution

### Navigate to the Backend Directory
```bash
cd media-reporting-system/backend
```

### Install Dependencies (System Python)
```bash
python -m pip install -r requirements.txt
```

### Run FastAPI Server
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify backend execution:
- Interactive Web App: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Exchange4media Real Articles: [http://127.0.0.1:8000/api/monitoring/exchange4media/articles](http://127.0.0.1:8000/api/monitoring/exchange4media/articles)
- ET BrandEquity Real Articles: [http://127.0.0.1:8000/api/monitoring/et-brand-equity/articles](http://127.0.0.1:8000/api/monitoring/et-brand-equity/articles)
- Aggregated Dual Dashboard JSON: [http://127.0.0.1:8000/api/dashboard](http://127.0.0.1:8000/api/dashboard)
- Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- Swagger Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 3. Running Scrapers (CLI Pipeline)

To scrape fresh articles from either portal or both:

```bash
cd media-reporting-system

# 1. Scrape Exchange4media
python media_reporting_scraper_foundation.py --site exchange4media --mode homepage --no-browser-fallback

# 2. Scrape ET BrandEquity
python media_reporting_scraper_foundation.py --site et_brand_equity --mode homepage --no-browser-fallback

# 3. Scrape Both Portals sequentially
python media_reporting_scraper_foundation.py --site all --mode homepage --no-browser-fallback
```

This writes to `scraper_output/exchange4media.json` and `scraper_output/et_brand_equity.json`. The FastAPI backend dynamically detects and serves updated JSON files immediately without requiring a backend restart.

---

## 4. Direct Automated Verification (Zero Server Needed)

To verify services, schemas, and dashboard aggregation directly:
```bash
cd media-reporting-system/backend
python test_integration.py
```

To run scraper unit tests:
```bash
cd media-reporting-system
python scraper/test_scraper.py
```

---

## 5. Frontend-to-Backend Integration Verification

1. When the backend is running on `127.0.0.1:8000`, visiting `http://127.0.0.1:8000/` displays a green **"FastAPI Connected"** indicator in the top header.
2. The Dashboard and News Feed display **real headlines from both ET BrandEquity and Exchange4media**, hero images, summaries, publication timestamps, and SHA-256 content hashes.
3. The News table supports filtering by source ("All Websites", "ET BrandEquity (Live)", "Exchange4media (Live)"), dynamic section dropdown, keyword search, and pagination.
4. Clicking any row opens an **Article Detail Drawer** with full metadata, content hash, and an external button to open the real article on the respective publisher's website.
5. **Failure Isolation**: If either scraper JSON is deleted or unavailable, the other publisher continues operating without breaking the UI or throwing 500 errors.

