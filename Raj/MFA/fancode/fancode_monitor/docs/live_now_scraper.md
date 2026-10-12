# FanCode Live Now Scraper Documentation — Phase 6

> **Status**: IMPLEMENTED & TESTED  
> **Target Scope**: Public FanCode Live Portal (`https://www.fancode.com/live` / `/schedule?tab=live`)

---

## 1. Overview & Objective

The Live Now Scraper identifies fixtures that are actively taking place on FanCode and enriches existing database match records with real-time live states (e.g. `LIVE` status, scores, stream availability, live timestamps).

### Pipeline Architecture
```
FanCode Live URL (https://www.fancode.com/live)
           ↓
Playwright Browser Context
           ↓
Data Acquisition:
  ├── Primary: Intercepted Live/Match API JSON Responses (LiveNowNetworkInterceptor)
  ├── Secondary: Embedded Next.js State (`__NEXT_DATA__`)
  └── Fallback: Semantic DOM Card Extraction
           ↓
Defensive Parsing (LiveNowParser)
           ↓
Attribute Normalization & Deduplication (LiveNowNormalizer)
           ↓
Identity Matching against Database (MatchesRepository)
  ├── Matched: Non-destructive field enrichment (status, score, logos)
  └── Unmatched: Safely created only if high-confidence external ID exists; otherwise logged & skipped
           ↓
Audit Logging (ScrapeRunsRepository with run_type="live_now")
```

---

## 2. Live Page Discovery & URLs

### Discovered Live Routes
- **Primary Live Hub**: `https://www.fancode.com/live` (or `https://www.fancode.com/live-stream`)
- **Fallback Schedule Live Tab**: `https://www.fancode.com/schedule?tab=live`

When navigating to `/live`, the Next.js single-page application requests live events from FanCode backend services. If the primary route redirects or yields no matches, the scraper automatically attempts the schedule live tab.

---

## 3. Data Acquisition Methods

1. **Network Interception [PRIMARY]**:
   - `LiveNowNetworkInterceptor` captures public `fetch`/`XHR` JSON responses matching pattern `r"/api/|/live|/matches|/fixtures|/events|/scores|/streams"`.
   - Ad and analytics trackers (`google`, `segment`, `clarity`, etc.) are ignored.
   - Authentication secrets, tokens, or cookies are never stored.

2. **Embedded Next.js SSR State [SECONDARY]**:
   - In cases where API calls are pre-rendered server-side, `<script id="__NEXT_DATA__">` JSON is extracted and searched for live match arrays.

3. **DOM Fallback [TERTIARY]**:
   - If structured data payloads are empty, the rendered DOM is queried for live match cards (`.match-card`, `a[href*="/matches/"]`, elements with live badges).

---

## 4. Normalization & Identity Strategy

### Status Normalization
Maps live indicators to standard status enums:
- `LIVE`: `"live"`, `"in_progress"`, `"streaming"`, `"in_play"`, `"started"`, `"active"`, `"half_time"`, `"innings_break"`
- `UPCOMING`: `"upcoming"`
- `COMPLETED`: `"completed"`, `"finished"`
- `CANCELLED`: `"cancelled"`, `"abandoned"`
- `POSTPONED`: `"postponed"`
- `UNKNOWN`: Fallback for unrecognized values

### Match Identity Resolution
Matches are mapped to existing database records using strict priority:
1. `external_id`: FanCode's stable match or event ID (e.g. `crick-live-101`).
2. Normalized `source_url`: Canonical URL without tracking query parameters.
3. Fallback: Slug derived from the event title.

### Unmatched Record Handling
To prevent database pollution:
- If a live record contains a verified `external_id` and `title`, a new record is created in `matches`.
- If an item lacks strong identity signals, it is recorded as **unmatched** and skipped (counted in `items_skipped`), preventing spurious entries.

---

## 5. Non-Destructive Field Enrichment

When a live item maps to an existing database match:
- `status` is updated to `LIVE` (or actual source status).
- `score_summary` is updated with the current score.
- Missing attributes (`venue`, team names, logos, `image_url`) are filled in if present on the live card.
- **Critical Invariant**: Pre-existing non-null values are **never** overwritten with `None`.

---

## 6. CLI Execution

```powershell
# Scrape Live Now and enrich database matches
python run_live_now.py

# Limit to top 10 items
python run_live_now.py --max-items 10

# Run in headed mode for visual observation
python run_live_now.py --headed

# Save raw intercepted payloads for debugging (data/raw/live_now/)
python run_live_now.py --save-raw

# Dry-run without database writes
python run_live_now.py --no-db
```

---

## 7. Configuration Reference

| Setting | Type | Default | Description |
|---|---|---|---|
| `LIVE_NOW_URL` | `str` | `https://www.fancode.com/live` | Target Live Now page URL |
| `LIVE_NOW_TIMEOUT_SECONDS` | `int` | `45` | Navigation timeout in seconds |
| `LIVE_NOW_WAIT_AFTER_LOAD_MS` | `int` | `2000` | Settle time after DOMContentLoaded |
| `LIVE_NOW_MAX_ITEMS` | `int` | `50` | Maximum live items to parse |
| `LIVE_NOW_REQUEST_DELAY_SECONDS` | `float` | `1.0` | Polite delay between requests |
| `LIVE_NOW_SAVE_RAW` | `bool` | `False` | Persist captured JSON payloads |
| `LIVE_NOW_RAW_DIR` | `str` | `data/raw/live_now` | Output directory for raw payloads |

---

## 8. Known Limitations & Architectural Boundaries

1. **No Polling Loop**:
   - Phase 6 captures a single point-in-time snapshot of what is currently live. Continuous real-time polling loops belong to later worker architectures.
2. **No Change Detection / Notifications**:
   - Change detection, diffing, and email notifications belong to Phase 8 and Phase 9.
3. **Dynamic Score Structure**:
   - Scores are normalized into human-readable string summaries (`score_summary`) to handle diverse sport formats without over-constraining the schema.
