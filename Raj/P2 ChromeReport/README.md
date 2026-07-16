# TV Channel Frequency Comparison Dashboard

Production-ready week-wise TV channel frequency comparison dashboard built with FastAPI, Pandas, PyArrow, Bootstrap 5, AG Grid Community, and Axios.

## Folder Structure

```text
project/
│
├── data/
│   ├── Week1.xlsx
│   ├── Week2.xlsx
│   ├── Week3.xlsx
│   └── ...
│
├── backend/
│   ├── main.py
│   ├── api.py
│   ├── processor.py
│   └── utils.py
│
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── output/
│   └── master_frequency.parquet
│
├── requirements.txt
└── README.md
```

## What the Application Does

- Automatically scans the `data/` folder for weekly Excel files without hardcoded filenames
- Detects weeks in chronological order and maps `Frequency` into dynamic `W1`, `W2`, `W3`, and future week columns
- Builds a merged master dataset using the business key:
  - `Market`
  - `MSO`
  - `City`
  - `Head End`
  - `Channel Name`
  - `CR No`
- Calculates:
  - `Total Changes`
  - latest `Status` arrow
- Stores the processed dataset as `output/master_frequency.parquet`
- Serves metadata, filtered pages, grouped results, and exports through FastAPI
- Renders a responsive AG Grid frontend with server-side loading

## Installation

### 1. Create a Python environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

## Running the Backend

Start the FastAPI server from the project root:

```powershell
python -m uvicorn backend.main:app --reload
```

Open the dashboard in your browser:

```text
http://127.0.0.1:8000/
```

## Data Processing Workflow

The backend automatically checks whether the Parquet output is stale.

If weekly Excel files are newer than `output/master_frequency.parquet`, the backend rebuilds the Parquet file on startup.

### Manual refresh after adding new files

Once the API is running, you can also refresh from the UI using the **Refresh Dataset** button, or call:

```powershell
curl -X POST http://127.0.0.1:8000/refresh
```

## Adding New Weekly Files

1. Drop the new weekly Excel files into the `data/` folder
2. Use a filename pattern like:
   - `Week5.xlsx`
   - `Week12.xlsx`
   - `Week52.xlsx`
3. Refresh the dataset

The system will:

- auto-detect the new files
- re-order them chronologically
- create new week columns dynamically
- rebuild the Parquet output
- expose the new week columns in the frontend automatically

No code changes are required for 52+ weeks.

## API Overview

### `GET /metadata`

Returns:

- available weeks
- markets
- MSOs
- cities
- head ends
- channel names
- CR numbers
- MSO types
- transmission bands

### `GET /data`

Supports:

- server-side pagination
- multi-select filtering
- backend grouping
- sorting
- searching
- summary counts for the filtered result set

Important query parameters:

- `page`
- `page_size`
- `filters` as JSON
- `group_by` as JSON array
- `sort_model` as JSON array
- `search`

### `GET /export/csv`

Exports the currently filtered dataset as CSV.

### `GET /export/excel`

Exports the currently filtered dataset as Excel.

## Frontend Features

- Bootstrap 5 executive white theme
- AG Grid Community with:
  - sticky header
  - pinned first columns
  - column resize
  - column reorder
  - column show/hide
  - sorting
  - floating filters
  - quick search
  - infinite row model
  - virtual scrolling
  - pagination
- Searchable multi-select filter cards
- Dynamic backend grouping
- Export buttons
- Automatic week column generation

## Week Cell Formatting

Week cells are formatted relative to the previous week:

- `↑223` with light red background if current week is higher
- `↓221` with light green background if current week is lower
- `→221` with white background if unchanged

The `Status` column shows only:

- `↑`
- `↓`
- `→`

based on the latest two weeks.

## Performance Notes

This project is optimized for large datasets by using:

- Parquet storage
- PyArrow-backed read/write
- server-side pagination
- backend filtering
- backend grouping
- lazy loading through AG Grid infinite row model
- in-memory DataFrame caching after Parquet load

The browser never receives the full dataset.

## Implementation Notes

- `backend/processor.py` handles dynamic Excel scanning and Parquet generation
- `backend/api.py` handles metadata, query, export, and refresh endpoints
- `backend/main.py` creates the FastAPI app and serves the frontend
- `frontend/app.js` manages filters, grouping, AG Grid datasource, and exports
- `frontend/styles.css` implements the executive white theme

## Recommended Production Next Steps

For production deployment, consider:

- adding authentication
- moving Parquet refresh into a scheduled job
- adding request logging and metrics
- enabling reverse proxy caching
- introducing DuckDB or Polars for heavier grouping workloads
- containerizing with Docker
