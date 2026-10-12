# FanCode Schedule Scraper Documentation — Phase 3

> **Status**: IMPLEMENTED & TESTED  
> **Target URL**: `https://www.fancode.com/schedule`

---

## 1. Overview & Strategy

The Schedule Scraper discovers and extracts scheduled, live, and upcoming fixtures from FanCode's schedule hub and persists normalized records into SQLite.

### Scraper Pipeline
```
Playwright Browser Context
           ↓
Network Interception (/api/, /schedule, /matches, /events)
           ↓
JSON Parsing (ScheduleParser) → [Fallback: DOM extraction]
           ↓
Normalization (Status, Datetime, Teams, Identity)
           ↓
Transactional Persistence (MatchesRepository, SportsRepository, ToursRepository)
           ↓
Scrape Run Tracking (ScrapeRunsRepository)
```

---

## 2. Actual Observed Data Sources

- **Primary Source [OBSERVED]**: FanCode is built on Next.js/React. Upon loading `/schedule`, the client initiates `fetch`/`xhr` calls returning JSON payloads containing fixture data.
- **Secondary Source [OBSERVED / FALLBACK]**: Rendered DOM anchor and card elements referencing `/matches/` and `/match/` paths. If JSON extraction encounters zero matches or changes format, the parser automatically executes DOM card parsing.

---

## 3. Data Normalization & Identity Strategy

### Match Identity
Identity is established deterministically to guarantee idempotency across multiple runs:
1. `external_id`: String identifier (e.g. `matchId`, `eventId`).
2. Normalized `source_url`: If `external_id` is absent, the canonical URL is used.
3. Fallback: Slug derived from the event title + date string.

### Status Normalization
- `LIVE`: `"live"`, `"ongoing"`, `"in_progress"`
- `UPCOMING`: `"upcoming"`
- `SCHEDULED`: `"scheduled"`, `"fixture"`
- `COMPLETED`: `"completed"`, `"finished"`, `"result"`
- `CANCELLED`: `"cancelled"`, `"abandoned"`
- `POSTPONED`: `"postponed"`, `"delayed"`
- Fallback: `UNKNOWN` (never throws)

### Date & Time Handling
- Timestamps and ISO 8601 strings are normalized to UTC `datetime` objects.
- Time strings are extracted into `start_time` (e.g. `HH:MM`).

---

## 4. Database Persistence & Relationships

Using the Phase 2 repositories:
1. **Sports**: Matches with sport information find or create the corresponding `Sport` record.
2. **Tours**: Matches with tournament/series information find or create the corresponding `Tour` record.
3. **Matches**: Matches are upserted via `MatchesRepository.upsert()`. Re-running scrapes does not create duplicate entries.
4. **Scrape Runs**: Every execution records start time, completion status, items processed, items created, and errors.

---

## 5. CLI Execution

```powershell
# Scrape schedule and persist to database
python run_schedule.py

# Headed mode with custom limit
python run_schedule.py --headed --max-items 20

# Run without modifying database
python run_schedule.py --no-db
```
