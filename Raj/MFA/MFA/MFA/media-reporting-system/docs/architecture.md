# Media Reporting System - Architecture Documentation

## 1. System Overview

The **Media Reporting System** is a professional, open-source media intelligence and reporting platform engineered to monitor media industry publications, detect news articles and advertisements, track layout and editorial changes, and generate executive reports.

Phase 0 establishes the strict local foundation, component boundaries, and contracts.

---

## 2. Architecture Principles

1. **Loose Coupling**: Frontend and backend are completely decoupled. They interact solely via standardized REST JSON contracts defined by Pydantic models in Python and TypeScript interfaces in React.
2. **Local-First & Free/Open-Source**: Zero reliance on proprietary cloud services, paid APIs, or third-party hosted databases. Runs entirely on local developer workstations using open-source tools.
3. **No Premature Complexity**: Microservices, Celery, and distributed caches are deliberately omitted during Phase 0 to ensure fast iteration and low operational footprint.
4. **Layered Separation of Concerns**:
   - Presentation: React + TypeScript
   - Application API: FastAPI
   - Business & Ingestion Logic: Scraper module
   - Persistence Layer: PostgreSQL + SQLAlchemy + Alembic (Phase 4)
   - Asset Storage: Local filesystem (storage directory)

---

## 3. High-Level Component Diagram

```
+-----------------------------------------------------------+
|                    React Frontend                         |
|   (Vite + TypeScript + Corporate Analytics Interface)      |
+-----------------------------+-----------------------------+
                              |
                     REST API | (CORS-enabled /api)
                              v
+-----------------------------------------------------------+
|                    FastAPI Backend                        |
|  - API Router (/api/health, /api/dashboard)               |
|  - Schemas (Pydantic v2 Contract Validation)              |
|  - Services (Mock Generator in Phase 0 -> DB Services)     |
+-----------------------------+-----------------------------+
                              |
        +---------------------+---------------------+
        |                                           |
        v (Phase 4)                                 v (Phase 2 & 3)
+-----------------------+                   +-----------------------+
|  PostgreSQL Database  |                   |   Scraper Pipeline    |
| - Articles            |                   | - Requests            |
| - Advertisements      |                   | - BeautifulSoup       |
| - Changes & Diffs     |                   | - Playwright          |
+-----------------------+                   +-----------+-----------+
                                                        |
                                                        v (Asset Storage)
                                            +-----------------------+
                                            | Local Storage Engine  |
                                            | - Screenshots         |
                                            | - Ad Banners          |
                                            | - Article Images      |
                                            +-----------------------+
```

---

## 4. API Specification (Phase 0)

### `GET /api/health`
- **Purpose**: Verify backend uptime and service health.
- **Response**:
```json
{
  "status": "ok",
  "service": "media-reporting-system",
  "version": "0.1.0",
  "phase": "PHASE 0 - FOUNDATION"
}
```

### `GET /api/dashboard`
- **Purpose**: Supplies the aggregate metrics, monitored source statuses, news feed items, and campaign tracking for dashboard visualization.
- **Contract**:
  - `system_status`: Object containing operational status, subtitle, date, and environment.
  - `kpis`: Monitored count, today's articles, newly detected count, ad count, and trends.
  - `websites`: List of target portals (ET BrandEquity, Exchange4media).
  - `latest_news`: List of sample news items with title, summary, source, tag, and timestamp.
  - `advertisements_summary`: Recent detected advertisements.
