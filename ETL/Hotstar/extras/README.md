# OTT Sports Catalog Scraper — Hotstar + SonyLIV + ZEE5  (audited)

## Files

| File | Purpose |
|------|---------|
| `catalog_base.py` | Shared helpers, parsers base class, Browser wrapper, `save()` |
| `sonyliv_catalog.py` | SonyLIV scraper / re-parser |
| `zee5_catalog.py` | ZEE5 scraper / re-parser |
| `run_all.py` | Runs the platforms, merges, prints summary |
| `test_catalog.py` | 29 regression tests (no browser/network needed) |
| `hotstar_catalog.py`, `hotstar_explorer.py` | **Not part of this audit** (not supplied) |

Keep all files in the **same folder**.

## Setup
```bash
pip install playwright pandas
playwright install chromium
python -m unittest test_catalog -v      # sanity check
```

## Run
```bash
python run_all.py                                   # all platforms, live
python run_all.py --platforms sonyliv zee5          # subset
python run_all.py --raw-sonyliv sonyliv_raw.jsonl --raw-zee5 zee5_raw.jsonl   # re-parse, no browser
python run_all.py --sport cricket                   # filter merged CSV + summary
python run_all.py --sports-only                     # drop rows with no detected sport
python zee5_catalog.py --debug                      # log every JSON response
```
`--overwrite` now really overwrites the raw JSONL (before, it always appended).
`run_all.py` exits with code 1 if no platform produced rows.

## Browser mode
The browser window is **visible by default**. ZEE5 returned HTTP 403 to a headless browser but 200 to a visible one on the same machine. `--headless` (Chrome new-headless mode, untested against ZEE5) hides the window; if you see `⚠ HTTP 403`, drop it. The crawl stops early after 2 consecutive blocked pages.

## If the CSV is empty
An empty `*_raw.jsonl` means the browser captured no JSON at all. Run one platform with
`--debug`: every JSON response is logged, and HTTP 401/403/429 are flagged as
probable bot-blocking / geo-restriction. Seed URLs other than the two in the brief
(`/custompage/sports-2245`, `/sports/games`) are guesses — confirm them in the log.

## Output columns
Same schema for every platform (`COMMON_COLUMNS`). Changes from v1: **`sport_source` added**.

| Column | Notes |
|--------|-------|
| `page` | The page the browser was on (e.g. `/sports/games`). If unknown (old raw files) it is `api:<path>`. |
| `found_in` | `"<page> > <rail>"` |
| `sport` | Canonical name (Cricket, Football, Kho Kho, MMA, Motorsport …) |
| `sport_source` | Where it was detected: `genre` > `title` > `rail` > `section` > `page`. `rail`/`page` are weaker signals. |
| `is_free`, `subscription_required`, `pay_per_view` | `True` / `False` / **blank = unknown**. Never guessed. |
| `duration_sec` | Numeric API field is **assumed to be seconds**; label text is parsed (`1h 30m`, `90m`, `1:30:00`). |
| `match_start_utc` | ISO-8601 `…Z` when the source gave an epoch or a time-zoned string; a zone-less string is kept raw (zone unknown). |
| `original_language` | Only when the API states it — not inferred from the language list. |

Other columns are unchanged from v1 (see `COMMON_COLUMNS` in `catalog_base.py`).

## Known limits (be aware before trusting numbers)
* **API field names are unverified against live traffic** — none could be tested (raw files were empty). Compare a real `--debug` run with `_row()` in each catalog file.
* Sport for rows with no genre/title hint falls back to the rail or page, which can be wrong for mixed rails — filter on `sport_source` if you need precision.
* Non-sport JSON that happens to contain `id` + `title` can produce junk rows; use `--sports-only`.
* Hotstar path is untested here; its old hard-coded `is_free=True` / `is_live=False` were removed (now unknown).
* Playwright itself was not run in the audit sandbox; the response handler was tested with stubs.
