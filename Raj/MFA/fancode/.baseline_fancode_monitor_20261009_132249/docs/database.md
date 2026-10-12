# FanCode Database & Persistence Architecture — Phase 2

> **Technology**: SQLite + SQLAlchemy 2.x  
> **Default Path**: `data/fancode.db` (configurable via `DATABASE_URL`)  
> **Timestamp Strategy**: Timezone-aware UTC (`datetime.now(timezone.utc)`)

---

## 1. Overview & Architecture

Phase 2 introduces a persistent relational storage layer without impacting Phase 0 or Phase 1 functionality.
The persistence layer resides under `app/database/`:

```
app/database/
├── __init__.py      # Package exports (Base, engine, session context, init_db)
├── connection.py    # Engine lifecycle, sessionmaker, SQLite foreign-key hooks, UTC helpers
├── models.py        # SQLAlchemy 2.x declarative ORM models
├── repositories.py  # Encapsulated repository data access methods with deterministic upserts
├── migrations.py    # Schema verification and table creation management
├── seed.py          # Development & test reference data seeding
└── __main__.py      # CLI database initialization (python -m app.database)
```

Additionally, a minimal diagnostic web surface is introduced under `app/api/`:
```
app/api/
├── __init__.py
├── app.py           # Minimal FastAPI application
└── health.py        # GET /health and GET /health/db diagnostic endpoints
```

---

## 2. Database Entities & Tables

### A. `sports`
Top-level sporting category (Cricket, Football, Kabaddi, etc.).
- `id`: Integer primary key, autoincrement.
- `external_id`: String (nullable, indexed).
- `name`: String (indexed).
- `slug`: String (indexed).
- `source_url`: String (indexed).
- `description`, `image_url`, `is_active`.
- `first_seen_at`, `last_seen_at`, `created_at`, `updated_at`.

### B. `tours`
Tournament, tour, or series (e.g. Indian Premier League, Caribbean Premier League).
- `id`: Integer primary key, autoincrement.
- `external_id`: String (nullable, indexed).
- `sport_id`: Foreign key to `sports.id` (nullable, ondelete SET NULL).
- `name`, `slug` (indexed), `source_url` (indexed).
- `start_date`, `end_date`, `status` (indexed).
- `first_seen_at`, `last_seen_at`, `created_at`, `updated_at`.

### C. `matches`
Match fixture and live event.
- `id`: Integer primary key, autoincrement.
- `external_id`: String (nullable, indexed).
- `tour_id`: Foreign key to `tours.id` (nullable, ondelete SET NULL).
- `sport_id`: Foreign key to `sports.id` (nullable, ondelete SET NULL).
- `title`, `slug` (indexed), `source_url` (indexed).
- `match_date`, `start_time`, `status` (indexed), `venue`.
- `team_a_name`, `team_a_external_id`, `team_b_name`, `team_b_external_id`.
- `team_a_logo_url`, `team_b_logo_url`, `score_summary`, `image_url`.
- `first_seen_at`, `last_seen_at`, `created_at`, `updated_at`.

### D. `videos`
Highlights, clips, replays.
- `id`: Integer primary key, autoincrement.
- `external_id`: String (nullable, indexed).
- `title`, `slug`, `source_url`.
- `sport_id`, `tour_id`, `match_id`: Foreign keys (all nullable).
- `thumbnail_url`, `published_at`, `duration_seconds`, `video_type`.
- Timestamps.

### E. `pages`
Discovered FanCode URLs and metadata.
- `id`: Integer primary key, autoincrement.
- `url`: Discovered link string.
- `canonical_url`: Normalized canonical URL (**UNIQUE**, indexed).
- `page_type`: Categorization (e.g. `HOME`, `SCHEDULE`, `LIVE`, `SPORT`, `MATCH`).
- `title`, `http_status`, `content_type`, `is_json`.
- `last_checked_at`, `content_hash`, `metadata_json` (JSON type).
- Timestamps.

### F. `change_events`
Audit log recording entity attribute modifications (foundation for Phase 8).
- `id`: Integer primary key, autoincrement.
- `entity_type`: String (e.g. `match`, `tour`).
- `entity_id`: Integer.
- `external_id`: String.
- `change_type`: String (`NEW`, `UPDATED`, `STATUS_CHANGED`, `REMOVED`).
- `field_name`, `old_value`, `new_value`, `source_url`.
- `detected_at`, `notified_at`, `created_at`.

### G. `scrape_runs`
Audit and metrics record for discovery or scraping jobs.
- `id`: Integer primary key, autoincrement.
- `run_type`: String (`discovery`, `schedule`, etc.).
- `started_at`, `finished_at`, `status` (`running`, `success`, `failed`).
- `pages_discovered`, `records_processed`, `records_created`, `records_updated`, `changes_detected`, `errors_count`.
- `error_message`, `metadata_json`.

---

## 3. Identity & Deterministic Upsert Strategy

To prevent duplicates from minor URL differences or missing external identifiers:
1. **Primary Lookup**: If `external_id` is supplied, query by `external_id`.
2. **Fallback Lookup**: If `external_id` is absent, query by canonical/source URL (normalized via `url_normalizer.normalize()`).
3. **Update on Match**:
   - If a matching entity exists, update non-null attributes.
   - Refresh `last_seen_at` and `updated_at` to the current UTC timestamp.
4. **Insert on Absence**:
   - Create the entity with both `first_seen_at` and `last_seen_at` set to `utc_now()`.

---

## 4. Migration & Schema Evolution Strategy

- **Phase 2 Approach**: Utilizes `Base.metadata.create_all()` with explicit verification (`verify_schema()`).
- **PostgreSQL / Alembic Compatibility**: Models are declared strictly using standard SQLAlchemy 2.x types (`Mapped[...]`, `mapped_column(...)`, `DateTime(timezone=True)`). No proprietary dialects are used. When transitioning to PostgreSQL, updating `DATABASE_URL=postgresql://...` and generating Alembic migrations will require zero model alterations.

---

## 5. Security & Data Protection Policy

- **No sensitive data stored**: Auth tokens, cookies, Authorization headers, session state, and passwords are never written to the database.
- **Audited payloads**: Metadata JSON columns only contain operational stats (counts, depths, public flags).

---

## 6. How to Initialize & Test

### Initialize the Database
```powershell
python -m app.database
```

### Run All Unit and E2E Tests
```powershell
python -m pytest -v --headed
```
