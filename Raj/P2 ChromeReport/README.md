# Chrome Dashboard Automation

This project is now designed around one command:

```powershell
python update.py
```

That command scans `data/` for new weekly `.xlsm` files, appends new rows into historical CSV datasets, updates `processed_files.json`, and regenerates one fully standalone offline `dashboard.html`.

## Workflow

The updater:

1. scans `data/` for weekly Excel macro workbooks
2. skips files already recorded in `processed_files.json`
3. reads these sheets:
   - `DistributionDetails`
   - `NBHD`
   - `OTS Summary`
4. extracts the week from filenames like `Chrome Track 2.0 Wk-24, 2026 (India TV).xlsm`
5. converts that into `Wk-24'26`
6. appends each cleaned sheet into historical CSV files
7. melts `OTS Summary` from wide format into `Week | Market | Channel | OTS`
8. rebuilds `dashboard.html`

## Historical Outputs

These files are append-only:

- `distribution_history.csv`
- `nbhd_history.csv`
- `ots_history.csv`
- `processed_files.json`

The standalone dashboard is written to:

- `dashboard.html`

Logs are written to:

- `logs/dashboard_automation.log`

## Install

```powershell
python -m pip install -r requirements.txt
```

## Dashboard Features

`dashboard.html` is generated with:

- embedded data
- embedded CSS
- embedded JavaScript
- embedded Plotly runtime
- Jinja2 templating
- offline charts
- KPI cards
- week, market, and channel filters
- free-text search
- paginated tables
- Excel export for the filtered table
- responsive layout

No Flask, FastAPI, Node.js, database, or server is required.

## Notes

- The parser auto-detects the real header row in the provided workbook structure and reuses that logic for future files with the same layout.
- Processed-file tracking is content-hash based, so duplicate copies are skipped even if renamed.
- Historical datasets are never overwritten by the ingestion step; new workbook rows are appended only.
