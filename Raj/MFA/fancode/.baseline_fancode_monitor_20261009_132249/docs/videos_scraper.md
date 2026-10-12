# FanCode Videos & Highlights Scraper Documentation — Phase 7

> **Status**: IMPLEMENTED & TESTED  
> **Target Scope**: Public FanCode Video & Highlight Content (`https://www.fancode.com/video`, `/videos`, `/matches/{id}`)

---

## 1. Overview & Objective

The Videos & Highlights Scraper discovers and persists publicly available video content (match highlights, replays, clips, post-match conferences) on FanCode and associates them with existing match, tour, and sport records in SQLite.

### Pipeline Architecture
```
FanCode Video Hub / Match Page
           ↓
Playwright Browser Context
           ↓
Data Acquisition:
  ├── Primary: Intercepted Video API JSON Responses (VideoNetworkInterceptor)
  ├── Secondary: Embedded Next.js SSR State (`__NEXT_DATA__`)
  └── Fallback: Semantic DOM Card Extraction (.video-card, a[href*="/video/"])
           ↓
Defensive Parsing (VideosParser)
           ↓
Attribute Normalization & Deduplication (VideosNormalizer)
           ↓
Explicit Relational Association:
  ├── Match Linkage: Explicit matchId or match URL (MatchesRepository)
  ├── Tour Linkage: Explicit tour name or ID (ToursRepository)
  └── Sport Linkage: Explicit sport name or ID (SportsRepository)
           ↓
Idempotent Database Persistence (VideosRepository)
           ↓
Audit Logging (ScrapeRunsRepository with run_type="videos")
```

---

## 2. Discovered Video Routes & Data Sources

### URL Routes
- **Primary Video Hub**: `https://www.fancode.com/video` or `https://www.fancode.com/videos`
- **Video Detail/Watch**: `https://www.fancode.com/video/{videoId}` or `/watch/{videoId}`
- **Match Video Sections**: `https://www.fancode.com/matches/{matchId}` (highlights tab/carousel)

### Acquisition Strategy
1. **Network Interception [PRIMARY]**:
   - `VideoNetworkInterceptor` captures public `fetch`/`XHR` JSON responses matching pattern `r"/api/|/video|/videos|/highlights|/clips|/media|/vod|/content"`.
   - Analytics and ad trackers are ignored.
   - Authentication secrets or tokens are never requested or stored.
2. **Embedded Next.js SSR State [SECONDARY]**:
   - In instances where video items are pre-rendered, `<script id="__NEXT_DATA__">` contains the catalog in `props.pageProps`.
3. **DOM Fallback [TERTIARY]**:
   - Semantic HTML elements (`a[href*="/video/"]`, duration badges, video cards) provide fallback coverage when JSON payloads are unavailable.

---

## 3. Normalization & Identity Strategy

### Video Types
Categorized into standard uppercase types:
- `HIGHLIGHT` / `MATCH_HIGHLIGHT`
- `CLIP`
- `REPLAY`
- `POST_MATCH`
- `PRE_MATCH`
- `INTERVIEW`
- `FEATURE`
- `UNKNOWN` (fallback if category cannot be verified)

### Duration Normalization
Durations in milliseconds, seconds, `"MM:SS"`, `"HH:MM:SS"`, or `"45s"` strings are standardized into integer `duration_seconds` for database consistency.

### Video Identity & Deduplication
1. Stable FanCode video/media ID (`videoId`, `contentId`)
2. Normalized canonical video URL
3. Slug derived from title + ID
Deduplication preserves records with richer information (e.g. duration, thumbnail).

---

## 4. Match, Tour, and Sport Associations

Strict association rules prevent inaccurate relationship mapping:
- **Matches**: Linked **only** when an explicit match ID or canonical match URL is present in the video metadata. Title-based fuzzy matching is strictly prohibited.
- **Tours**: Linked via explicit tour ID or verified tournament name.
- **Sports**: Linked via explicit sport ID or sport category name.
- If association is absent or uncertain, foreign keys remain `NULL`.

---

## 5. Non-Destructive Database Persistence

Using [`VideosRepository.upsert`](file:///d:/MFA/fancode/fancode_monitor/app/database/repositories.py#L244):
- Multiple scrapes do not create duplicate video rows.
- Existing metadata (`thumbnail_url`, `duration_seconds`, `match_id`) is strictly preserved when subsequent scrapes return `None` or omitted fields.

---

## 6. CLI Execution

```powershell
# Scrape videos and persist to database
python run_videos.py

# Limit to top 20 items
python run_videos.py --max-items 20

# Discover highlights for a targeted match
python run_videos.py --match-id "match-901"

# Run in headed mode
python run_videos.py --headed

# Save raw intercepted payloads (data/raw/videos/)
python run_videos.py --save-raw

# Dry-run without database modifications
python run_videos.py --no-db
```

---

## 7. Configuration Reference

| Setting | Type | Default | Description |
|---|---|---|---|
| `VIDEO_SCRAPER_URL` | `str` | `https://www.fancode.com/video` | Target Videos page URL |
| `VIDEO_SCRAPER_TIMEOUT_SECONDS` | `int` | `45` | Navigation timeout in seconds |
| `VIDEO_SCRAPER_WAIT_AFTER_LOAD_MS` | `int` | `2000` | Settle time after DOMContentLoaded |
| `VIDEO_SCRAPER_MAX_ITEMS` | `int` | `50` | Maximum video items to parse |
| `VIDEO_SCRAPER_REQUEST_DELAY_SECONDS` | `float` | `1.0` | Polite delay between requests |
| `VIDEO_SCRAPER_SAVE_RAW` | `bool` | `False` | Persist captured JSON payloads |
| `VIDEO_SCRAPER_RAW_DIR` | `str` | `data/raw/videos` | Output directory for raw payloads |

---

## 8. Known Limitations & Boundaries

1. **No Media Downloading / Transcoding**:
   - Scrapes metadata, thumbnails, and public links only. Does not download video media files or bypass DRM.
2. **No Change Detection / Alerts**:
   - Change detection and email notifications belong to Phase 8 and Phase 9.
