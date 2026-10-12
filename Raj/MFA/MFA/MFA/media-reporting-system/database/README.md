# Media Reporting System - Database Architecture

This directory is reserved for database migration scripts, table schemas, and seed fixtures.

## Phase 0 Status

> **IMPORTANT**: In **Phase 0 — Foundation**, NO PostgreSQL instance is installed, configured, or connected. All current responses are served via in-memory mock data fixtures.

---

## Planned Architecture (Phase 4)

In **Phase 4 — Database and History**, the following will be implemented:
- **Database Engine**: PostgreSQL (Open Source Relational Database)
- **ORM / Toolkit**: SQLAlchemy 2.0 (declarative models)
- **Migration Framework**: Alembic for schema migrations
- **Core Entities**:
  - `monitored_sources`: Website configurations, base URLs, scraping parameters, active status
  - `articles`: Scraped news items (headline, full-text, summary, author, published timestamp, hash)
  - `advertisements`: Tracked campaigns, detected advertiser brands, banner formats, page locations
  - `article_versions / content_changes`: Content diffs, headline updates, visual alterations
  - `crawl_logs`: Health metrics, response codes, duration, error records

---

## Directory Structure

```
database/
├── migrations/          # Alembic schema version scripts (Phase 4)
├── seeds/               # Initial seed data for monitored media outlets
└── README.md
```
