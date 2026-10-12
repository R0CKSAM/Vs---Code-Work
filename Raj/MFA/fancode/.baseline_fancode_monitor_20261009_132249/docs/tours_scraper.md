# FanCode Tours Scraper Documentation — Phase 4

> **Status**: IMPLEMENTED & TESTED  
> **Target URL**: `https://www.fancode.com`

---

## 1. Overview & Strategy

The Tours Scraper extracts tournaments, series, and competitions from FanCode and persists them into the `tours` table, establishing foreign key relationships to `sports` and linking to existing `matches`.

### Scraper Pipeline
```
Playwright Browser Context
           ↓
Network Interception (/tour/, /series/, /competitions, /api/)
           ↓
JSON Parsing (ToursParser) → [Fallback: DOM series cards/links]
           ↓
Normalization (Status, Dates, Slugs)
           ↓
Transactional Persistence (ToursRepository.upsert, SportsRepository.upsert)
           ↓
Match Linkage (Associates tour_id on unlinked matches matching tour slug)
           ↓
Scrape Run Tracking (ScrapeRunsRepository, run_type="tours")
```

---

## 2. Actual Observed Data Sources

- **Primary Source [OBSERVED]**: Tour card links and series pathways matching `/tours/{slug}`, `/tour/{slug}`, and `/series/{slug}` on FanCode event hubs.
- **Secondary Source [OBSERVED]**: Intercepted JSON network responses carrying tournament metadata, schedules, banners, and team details.

---

## 3. Data Normalization & Identity Strategy

- **Identity Priority**:
  1. `external_id`: String (e.g. `tour-101`).
  2. Normalized `source_url`: (e.g. `https://www.fancode.com/tours/ipl-2026`).
  3. Derived slug: Lowercased, alphanumeric slug generated from name.
- **Match Linkage**: Matches present in the database without a `tour_id` are linked if their `source_url` or slug corresponds to the discovered tour's slug.

---

## 4. CLI Execution

```powershell
python run_tours.py
python run_tours.py --headed --max-items 10
```
