# FanCode Sports Scraper Documentation — Phase 4

> **Status**: IMPLEMENTED & TESTED  
> **Target URL**: `https://www.fancode.com`

---

## 1. Overview & Strategy

The Sports Scraper discovers sporting disciplines hosted on FanCode (e.g. Cricket, Football, Kabaddi, Basketball, Badminton, Hockey, Tennis) and persists them idempotently into the SQLite database.

### Scraper Pipeline
```
Playwright Browser Context
           ↓
Network Interception (/sports, /api/)
           ↓
JSON Parsing (SportsParser) → [Fallback: DOM navigation links]
           ↓
Normalization (derive_sport_slug, derive_sport_identity)
           ↓
Transactional Persistence (SportsRepository.upsert)
           ↓
Scrape Run Tracking (ScrapeRunsRepository, run_type="sports")
```

---

## 2. Actual Observed Data Sources

- **Primary Source [OBSERVED]**: Navigation bars and category tabs on FanCode render links corresponding to sport hubs (`/cricket`, `/football`, `/kabaddi`, `/basketball`, etc.).
- **Secondary Source [OBSERVED]**: JSON API payloads intercepted during page navigation containing sports lists with sport identifiers and icons.

---

## 3. Data Normalization & Identity Strategy

- **Identity Priority**:
  1. `external_id`: String (e.g. `sport-1`).
  2. Normalized `source_url`: (e.g. `https://www.fancode.com/cricket`).
  3. Derived slug: Lowercased, alphanumeric slug generated from name.
- **Deduplication**: Case differences or trailing slashes are unified before database insertion.

---

## 4. CLI Execution

```powershell
python run_sports.py
python run_sports.py --headed --max-items 10
```
