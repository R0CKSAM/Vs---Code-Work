# FanCode Match Detail Scraper Documentation — Phase 5

> **Status**: IMPLEMENTED & TESTED  
> **Target Scope**: Public FanCode Match Detail Pages (`/cricket/matches/...`, `/football/matches/...`, `/match/...`)

---

## 1. Overview & Objective

The Match Detail Scraper enriches existing Match records discovered during Phase 3 (Schedule) and Phase 4 (Sports & Tours) using their public FanCode match detail pages.

### Enrichment Pipeline
```
Existing Matches in Database
           ↓
Select Target Matches (missing venue, team details, score, or explicitly targeted)
           ↓
Playwright Browser Context: Open Match Detail Page
           ↓
Data Extraction:
  ├── Primary: Intercepted Match API / GraphQL / REST JSON responses
  ├── Secondary: Embedded Next.js Data (`__NEXT_DATA__`)
  └── Fallback: Semantic DOM Extraction (meta tags, headings, cards)
           ↓
Normalization (MatchDetailNormalizer)
           ↓
Field-Preserving Database Merge (MatchesRepository)
           ↓
Scrape Run Tracking (ScrapeRunsRepository)
```

---

## 2. Observed Match Detail URLs & Data Sources

### URL Patterns
FanCode match detail pages adhere to predictable URL patterns:
- `/cricket/matches/<tour-slug>/<match-slug>/<match-id>`
- `/football/matches/<tour-slug>/<match-slug>/<match-id>`
- `/matches/<match-id>`
- `/match/<match-id>`

### Data Sources
1. **Intercepted JSON Responses [PRIMARY]**:
   - As Next.js hydrates the page, background `fetch`/`XHR` calls to FanCode API endpoints (e.g., `/api/v1/match/`, `/graphql`, `/events/`) return structured match details, venue coordinates, lineups, and live/final scores.
2. **Embedded Next.js Data (`__NEXT_DATA__`) [SECONDARY]**:
   - The `<script id="__NEXT_DATA__">` tag contains SSR props (`props.pageProps.match`, `props.pageProps.initialState`) pre-rendered by the Next.js server.
3. **DOM Extraction [FALLBACK]**:
   - In instances where API calls are obfuscated or SSR payload keys vary, semantic HTML elements (`h1`, `h2`, `time`, `.venue`, meta tags) provide titles, team names, start times, and venue information.

---

## 3. Field Merge Strategy (Non-Destructive Enrichment)

Enrichment updates existing database rows while strictly preserving previously collected data.

### Rules of Engagement:
1. **Never Overwrite with `None`**:
   - If an existing record already has `venue = "Wankhede Stadium"` and the detail page returns `None` or omitted venue, the existing value is strictly retained.
2. **Selective Attribute Updates**:
   - When a detail page provides richer data (e.g. `team1_short_name = "MI"`, `venue = "Wankhede Stadium, Mumbai"`, or `status = "COMPLETED"`), those attributes are updated.
3. **Status Progression**:
   - Match status transitions gracefully (e.g., `SCHEDULED` → `LIVE` → `COMPLETED`).
4. **Idempotency & Deduplication**:
   - Records are updated by `id` or matched by `external_id` / `source_url`. No duplicate records are created.

```python
# Field Merge Strategy Logic
if detail.venue and not existing.venue:
    existing.venue = detail.venue
elif detail.venue and len(detail.venue) > len(existing.venue or ""):
    # Prefer more descriptive venue info
    existing.venue = detail.venue

if detail.team1_score is not None:
    existing.team1_score = detail.team1_score
if detail.team2_score is not None:
    existing.team2_score = detail.team2_score
if detail.status and detail.status != MatchStatus.UNKNOWN:
    existing.status = detail.status
```

---

## 4. Normalization Strategy

- **Teams**: Extends team names with short names / abbreviations (`MI`, `CSK`).
- **Venue**: Cleans whitespace, stadium name, and city formatting.
- **Dates & Times**: Normalizes ISO 8601 timestamps and relative date strings to UTC `datetime`.
- **Scores**: Preserves formatted score strings (e.g. `185/4 (20.0)`).
- **Match Identity**: Derives external IDs from URLs or Next.js state IDs to correlate with pre-existing schedule records.

---

## 5. CLI Execution

The match detail runner supports flexible command-line invocation:

```powershell
# Enrich up to 10 existing matches missing details
python run_match_detail.py --limit 10

# Enrich a specific match URL directly
python run_match_detail.py --url "https://www.fancode.com/cricket/matches/ipl-2025/csk-vs-mi/10492"

# Enrich by database Match ID
python run_match_detail.py --match-id 42

# Run in headed mode for visual debugging
python run_match_detail.py --limit 5 --headed

# Dry-run without committing database changes
python run_match_detail.py --limit 5 --no-db
```

---

## 6. Known Limitations & Future Considerations

1. **Live Ball-by-Ball Updates**:
   - Match detail scraping focuses on match-level metadata and static/final scores. Real-time ball-by-ball commentary and high-frequency polling are deferred to Phase 6 (Live Now Monitoring).
2. **Dynamic Next.js Payload Structures**:
   - Key paths within `__NEXT_DATA__` can vary between sports. The parser handles this defensively using safe key navigation (`safe_get`) across multiple known paths.
3. **Player-Level Statistics**:
   - Player rosters and detailed scorecards will be integrated in subsequent phases if required.
