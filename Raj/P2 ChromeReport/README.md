# P2 ChromeReport

Offline dashboard automation for weekly Chrome report workbooks.

This project is designed so that one command:

```powershell
python update.py
```

processes new weekly Excel files, updates historical datasets, and regenerates a standalone dashboard that can be opened directly in a browser without any server.

## What This Project Does

The project automates the weekly reporting flow for:

- Distribution data
- Neighbourhood comparison data
- OTS comparison data
- Weekly frequency and rank comparison views
- Standalone HTML dashboard generation

The generated dashboard:

- works offline
- contains embedded data
- contains embedded CSS
- contains embedded JavaScript
- does not require Flask, FastAPI, Node.js, or a database

Main output:

- [output/chrome_report_dashboard.html](D:/Vs%20-%20Code%20Work/Raj/P2%20ChromeReport/output/chrome_report_dashboard.html)

## Main Commands

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Process new weekly files and update the dashboard:

```powershell
python update.py
```

Rebuild the standalone dashboard from existing data/history only:

```powershell
python app.py
```

## Project Structure

```text
P2 ChromeReport/
│
├── app.py
├── update.py
├── weekly_workbook_builder.py
├── processed_files.json
├── README.md
├── requirements.txt
│
├── dashboard_automation/
│   ├── config, pipeline, logging, ingestion helpers
│
├── data/
│   ├── weekly .xlsm source files
│   └── combined weekly .xlsx files used by dashboard build
│
├── distribution summary/
│   └── distribution workbook support files
│
├── NBHD Data/
│   └── weekly neighbourhood Excel files
│
├── OTS/
│   └── weekly OTS Excel files
│
├── history/
│   ├── distribution_history.csv
│   ├── nbhd_history.csv
│   └── ots_history.csv
│
├── output/
│   ├── frequency_report.json
│   └── chrome_report_dashboard.html
│
├── static/
│   ├── style.css
│   ├── neighbourhood.js
│   ├── ots.js
│   ├── comparison.js
│   └── nbhd_benchmark.js
│
├── templates/
│   └── dashboard template files
│
├── logs/
│   └── dashboard_automation.log
│
└── extra/
    └── optional leftovers / archived extra files
```

## Update Workflow

### 1. Add New Weekly Files

Put new weekly source `.xlsm` files into:

- `data/`

Example:

```text
Chrome Track 2.0 Wk-27, 2026 (India TV).xlsm
```

### 2. Run the Updater

```powershell
python update.py
```

### 3. What the Updater Does

The updater:

1. scans `data/` for weekly `.xlsm` files
2. skips files already listed in `processed_files.json`
3. extracts week labels from the filename
4. reads required sheets from the workbook
5. appends cleaned rows into history CSV files
6. updates processed file tracking
7. rebuilds the standalone dashboard

## Week Format

Filename:

```text
Chrome Track 2.0 Wk-24, 2026 (India TV).xlsm
```

Generated week label:

```text
Wk-24'26
```

## Input Sheets and Transformations

### DistributionDetails

- source: workbook sheet `DistributionDetails`
- adds `Week` column
- appends to historical distribution data

### NBHD

- source: workbook sheet `NBHD`
- adds `Week` column
- appends to historical neighbourhood data

### OTS Summary

- source: workbook sheet `OTS Summary`
- wide format is unpivoted into:
  - `Week`
  - `Market`
  - `Channel`
  - `OTS`
- appends to historical OTS data

## Historical Data Files

These files are append-based and should be preserved:

- `history/distribution_history.csv`
- `history/nbhd_history.csv`
- `history/ots_history.csv`
- `processed_files.json`

Important:

- historical files are not meant to be manually overwritten
- new weekly data should be appended through `python update.py`

## Dashboard Outputs

### Standalone HTML

Generated at:

- `output/chrome_report_dashboard.html`

This file:

- opens by double-click
- works without internet
- contains embedded report data
- is suitable for sharing with users who only need to view the dashboard

### JSON Data Bundle

Generated at:

- `output/frequency_report.json`

This is used as the dashboard data bundle for the standalone HTML generation flow.

## Dashboard Features

The current dashboard includes:

- KPI cards
- responsive layout
- standalone offline HTML output
- Table 1 frequency/rank/band switching
- Table 2 neighbourhood comparison
- Table 3 OTS comparison
- weekly frequency and rank comparison table
- report sections for selected tables
- interactive filters
- searchable dropdown filters
- filter-dependent week selection
- full-screen table modes
- pagination
- sticky headers
- conditional formatting
- Excel-like column resizing where implemented

## Important Source Files

### `update.py`

Main automation entry point.

Use this when you want to:

- process newly arrived weekly files
- update history
- regenerate the dashboard in one step

### `app.py`

Standalone dashboard builder and report assembler.

Use this when you want to:

- rebuild the dashboard from existing data/history
- refresh HTML/JSON output without reprocessing source `.xlsm` files

### `weekly_workbook_builder.py`

Builds or refreshes combined weekly workbook files used by reporting logic.

### `static/`

Contains dashboard behavior and styling:

- `style.css` for UI styling and responsive layout
- `neighbourhood.js` for Table 2 logic
- `ots.js` for Table 3 logic
- `comparison.js` for weekly comparison table logic
- `nbhd_benchmark.js` for additional neighbourhood benchmark behavior

### `templates/`

Contains dashboard template files used when generating standalone HTML.

## Logs

Automation logs are written to:

- `logs/dashboard_automation.log`

If `python update.py` fails, check this file first.

## Sharing the Project

### Share Only the Dashboard

If someone only needs to view the report:

- send `output/chrome_report_dashboard.html`

They can open it directly in a browser.

### Share the Full Project

If someone needs to update the dashboard themselves:

share the full project folder with:

- `app.py`
- `update.py`
- `weekly_workbook_builder.py`
- `dashboard_automation/`
- `data/`
- `history/`
- `output/`
- `static/`
- `templates/`
- `processed_files.json`
- `requirements.txt`
- `README.md`

Recommended:

- zip the project before sharing
- exclude `__pycache__/`
- exclude unnecessary extra large temporary files if not needed

## Typical Usage

### Fresh Setup on Another Machine

1. copy the full project folder
2. install Python
3. install dependencies:

```powershell
python -m pip install -r requirements.txt
```

4. run:

```powershell
python update.py
```

### Weekly Update Cycle

1. put new `.xlsm` file in `data/`
2. run:

```powershell
python update.py
```

3. open:

- `output/chrome_report_dashboard.html`

## Notes

- processed files are tracked in `processed_files.json`
- week extraction is based on workbook filename pattern
- standalone dashboard generation is fully local
- the dashboard is intended to preserve existing UI behavior while adding automation
- if source folder contents change but you only need to refresh output, use `python app.py`

## Requirements

Current Python package requirements:

- `jinja2>=3.1,<4`
- `openpyxl>=3.1,<4`
- `pandas>=3.0,<4`
- `plotly>=6.0,<7`
