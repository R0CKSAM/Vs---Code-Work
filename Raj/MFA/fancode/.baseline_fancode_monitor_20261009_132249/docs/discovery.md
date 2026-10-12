# FanCode Discovery Report — Phase 1

> **Status**: INITIAL DISCOVERY SPECIFICATION & ARCHITECTURE  
> **Target Base URL**: `https://www.fancode.com`

---

## 1. FanCode Base URL
`https://www.fancode.com`

---

## 2. Pages Discovered
During discovery runs, the crawler starts from the seed homepage and traces publicly accessible navigation links:

| Section / Path | Canonical / Pattern | Page Type | Evidence Status |
|---|---|---|---|
| `/` | `https://www.fancode.com/` | `HOME` | [OBSERVED] |
| `/schedule` | `https://www.fancode.com/schedule` | `SCHEDULE` | [OBSERVED] |
| `/live` or `/live-now` | `https://www.fancode.com/live` | `LIVE` | [OBSERVED] |
| `/cricket` | `https://www.fancode.com/cricket` | `SPORT` | [OBSERVED] |
| `/football` | `https://www.fancode.com/football` | `SPORT` | [OBSERVED] |
| `/tours/...` | `https://www.fancode.com/tours/{slug}` | `TOUR` | [OBSERVED] |
| `/series/...` | `https://www.fancode.com/series/{slug}` | `SERIES` | [OBSERVED] |
| `/matches/...` | `https://www.fancode.com/matches/{id}` | `MATCH` | [OBSERVED] |
| `/video/...` | `https://www.fancode.com/video/{id}` | `VIDEO` | [OBSERVED] |

---

## 3. Page Classifications
The deterministic classifier maps URLs into structured categories based on path regexes and page titles:
- `HOME`: Root landing page
- `SCHEDULE`: Fixtures, upcoming matches, daily timetable
- `LIVE`: Live streaming and ongoing events
- `SPORT`: Sport-specific category hubs (Cricket, Football, Kabaddi, etc.)
- `TOUR` / `SERIES`: Tournament and tour landing hubs
- `MATCH`: Match/event detail cards and live scorecards
- `VIDEO`: Video on demand, highlights, clips
- `TEAM`: Team detail profiles
- `PLAYER`: Player roster & statistics
- `UNKNOWN`: Unclassified or fallback pages

---

## 4. URL Patterns
### Observed URL Patterns
- Base home: `^https://www\.fancode\.com/?$`
- Top-level sport routes: `^https://www\.fancode\.com/(cricket|football|kabaddi)/?`
- Schedule listing: `^https://www\.fancode\.com/schedule/?`
- Match detail: `^https://www\.fancode\.com/match(es)?/.*`
- Video highlights: `^https://www\.fancode\.com/(video|watch)/.*`
- Tracking parameters observed and stripped: `utm_source`, `utm_medium`, `utm_campaign`, `ref`, `fbclid`, `gclid`

---

## 5. Relevant Selectors & Data Attributes
- Navigation links: `a[href]`
- Canonical links: `link[rel="canonical"]`
- Image elements: `img[src]`
- Title tag: `head > title`
- Dynamic containers: Client-side single page app (SPA) elements rendered with Next.js/React hydration roots (e.g. `#__next` or standard DOM root).

---

## 6. Network Requests Observed & JSON Endpoints
- Network events during page navigation trigger `fetch` and `xhr` requests.
- Internal API and CDN endpoints provide metadata and live scores.
- Resource filtering strips noisy static asset types (CSS, fonts, tracking pixels, ad networks like `doubleclick`, `googletagmanager`).
- Captured network events record: `method`, `url`, `resource_type`, `status`, and `is_json` indicator.

---

## 7. Pagination, Infinite-Scroll, & Dynamic Behavior
- **Dynamic rendering [OBSERVED]**: FanCode is heavily client-rendered with React/Next.js. Plain HTML requests do not contain complete rendered match data; a headless browser (Playwright) is required to evaluate JavaScript and allow content hydration.
- **Infinite scroll / Load more [ASSUMED for Phase 2]**: Match lists and schedules populate cards dynamically. Scrolling or interacting with tabs triggers network fetch calls.

---

## 8. Image URL Patterns
- Hero banners, team flags, and player thumbnails are served via CDNs or media subdomains (e.g. image URLs containing `fancode.com` asset prefixes or cloud CDNs).

---

## 9. IDs, Dates, and Status Fields Discovered
- **Match IDs**: Numeric or hyphenated alphanumeric identifiers embedded in match paths (e.g. `/matches/{match-id}`).
- **Match Status**: Indicated by labels such as "LIVE", "UPCOMING", "COMPLETED" in UI card text and badge components.
- **Dates**: Timestamp strings in localized or UTC formats present in DOM attributes and API responses.

---

## 10. Recommended Scraping Strategy
1. **Browser-based Extraction [RECOMMENDED]**:
   Continue utilizing Playwright Chromium with DOM content loaded and settle delays (`DISCOVERY_WAIT_AFTER_LOAD_MS`) to allow React hydration.
2. **Rate Limiting & Politeness [RECOMMENDED]**:
   Maintain `REQUEST_DELAY_SECONDS` (default: 1.5s) between requests.
3. **Structured Network Interception [RECOMMENDED]**:
   In Phase 2, inspect observed JSON network payloads (`NetworkMonitor`) directly where possible to extract raw structured JSON data without relying solely on brittle CSS selectors.
4. **URL Normalization [RECOMMENDED]**:
   Always strip query tracking parameters (`utm_*`, `ref`) while retaining routing/filter params.

---

## 11. Discovery Limitations
- Discovery enforces conservative boundaries (`DISCOVERY_MAX_PAGES`, `DISCOVERY_MAX_DEPTH`, `DISCOVERY_TIMEOUT_SECONDS`) to avoid infinite crawling or overloading the target site.
- Authenticated or paywalled content is strictly excluded in adherence to scraping and ethical boundaries.
- No anti-bot evasion, CAPTCHA bypass, or undocumented internal endpoints are used.
