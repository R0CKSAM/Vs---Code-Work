# OTT Sports Catalog Scraper — Hotstar + SonyLIV + ZEE5

## Files

| File | Purpose |
|------|---------|
| `catalog_base.py` | Shared types, Browser wrapper, save helper |
| `hotstar_catalog.py` | Hotstar JSON parser (updated from previous session) |
| `hotstar_explorer.py` | Hotstar interactive menu (updated from previous session) |
| `sonyliv_catalog.py` | SonyLIV scraper — `https://www.sonyliv.com/custompage/sports-2245` |
| `zee5_catalog.py` | ZEE5 scraper — `https://www.zee5.com/sports/games` |
| `run_all.py` | Runs all three, merges, prints summary |

---

## Setup

```bash
pip install playwright pandas
playwright install chromium
```

All 4 files must be in the **same folder**.

---

## Run

### All three platforms at once
```bash
python run_all.py
```

### One platform only
```bash
python run_all.py --platforms sonyliv
python run_all.py --platforms hotstar zee5
```

### Filter to one sport in the summary
```bash
python run_all.py --sport cricket
```

### Re-parse saved raw JSONL (no browser needed)
```bash
python run_all.py --raw-hotstar hotstar_raw.jsonl \
                  --raw-sonyliv sonyliv_raw.jsonl \
                  --raw-zee5    zee5_raw.jsonl
```

### Run each scraper standalone
```bash
python sonyliv_catalog.py
python zee5_catalog.py
```

---

## Output files

| File | Contains |
|------|---------|
| `hotstar_sports.csv` | Hotstar sports only |
| `sonyliv_sports.csv` | SonyLIV sports only |
| `zee5_sports.csv` | ZEE5 sports only |
| `ott_sports_merged.csv` | All three combined — same columns |
| `hotstar_raw.jsonl` | Raw Hotstar JSON responses |
| `sonyliv_raw.jsonl` | Raw SonyLIV JSON responses |
| `zee5_raw.jsonl` | Raw ZEE5 JSON responses |

---

## Output columns (all three CSVs share the same schema)

| Column | What it contains |
|--------|-----------------|
| `platform` | Hotstar / SonyLIV / ZEE5 |
| `rail` | Tray/row name (e.g. "Featured Cricket", "Live Now") |
| `page` | Page scraped (e.g. "/in/sports", "/sports/cricket") |
| `section` | Sub-section or bucket ID |
| `content_id` | Platform's unique ID for this title |
| `series_id` | Parent show/series ID (where available) |
| `title` | Title as shown on the platform |
| `series_title` | Parent show name (for episodes/clips) |
| `episode_title` | Episode-level title |
| `content_type` | Movie / Show / Episode / Match / Clip / Live / Trailer |
| `content_subtype` | e.g. "T20", "Serie A", "Reality" |
| `is_live` | True if currently airing live |
| `description` | Synopsis / description |
| `year` | Release year |
| `release_date` | Full release/broadcast date |
| `rating` | Age rating (U, U/A, A, 13+, etc.) |
| `duration_sec` | Duration in seconds |
| `duration_label` | Human label ("1h 30m") |
| `season_number` | Season number for shows |
| `episode_number` | Episode number |
| `episode_count` | Total episodes in series |
| `sport` | Detected sport (Cricket / Football / Tennis …) |
| `tournament` | Tournament/league name |
| `match_status` | upcoming / live / completed |
| `match_start_utc` | Match start timestamp |
| `teams` | "India vs Australia" |
| `primary_genre` | First genre tag |
| `genre_tags` | All genre/mood tags |
| `languages` | Available audio languages |
| `original_language` | Original language |
| `available_languages` | All audio options |
| `language_count` | Count of available languages |
| `is_free` | True = AVOD (free to watch) |
| `subscription_required` | True = needs paid plan |
| `pay_per_view` | True = one-time purchase |
| `found_in` | Breadcrumb trail ("Sports > Cricket > ICC CL") |
| `detail_url` | Direct link to the title |
| `poster_url` | Thumbnail/poster image URL |
| `scraped_at` | UTC timestamp of scrape |

---

## Terminal summary (what `run_all.py` prints)

```
══════════════════════════════════════════════════════════
  FULL SUMMARY — ALL PLATFORMS
══════════════════════════════════════════════════════════

  Total rows  : 2,341
  Unique IDs  : 1,879

  ── By Platform ──
    Hotstar       1,102 rows  (893 unique)
    SonyLIV         731 rows  (612 unique)
    ZEE5            508 rows  (374 unique)

  ── Content types ──
  content_type   Clip  Episode  Live  Match  Movie  Show  Trailer
  platform
  Hotstar         412      0      14    298      0    101    277
  SonyLIV         201     88      22    184     12     88    136
  ZEE5             98     44       8     92      6     44     80

  ── Top sports ──
    Cricket              812  [Hotstar, SonyLIV, ZEE5]
    Football             341  [Hotstar, SonyLIV, ZEE5]
    Tennis               198  [Hotstar, SonyLIV]
    Kabaddi              124  [Hotstar, ZEE5]
    ...

  ── Access model ──
    Free AVOD   :   893
    Sub required: 1,286
    Pay-per-view:    42

  ── Live content ──
    Live titles :    44
```
