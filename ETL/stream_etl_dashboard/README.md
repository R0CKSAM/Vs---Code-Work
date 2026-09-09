# Stream ETL Dashboard

A separate near-real-time pipeline that copies Akamai gzip logs from an
S3-compatible rclone remote, transforms JSON-line events, stores aggregates in
SQLite, and serves live graphs and tables through FastAPI.

It does not read or write the parent project's `live_state.json` or
`live_checkpoint.json`.

## Setup (PowerShell)

```powershell
cd D:\cloner\stream_etl_dashboard
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Edit `.env` if the remote, local directory, streams, or port differ.

## Run

Run the ETL and API together:

```powershell
python run_all.py
```

Open `http://localhost:8788`.

For local replay without contacting S3:

```powershell
python -m app.worker --no-sync --once
python run_api.py
```

## Data flow

```text
S3/rclone -> local .gz files -> ETL worker -> data/analytics.db
                                              |
Browser <- graphs/tables <- FastAPI <---------+
```

SQLite uses WAL mode so the ETL can write while the API reads. Every processed
file is registered in `ingested_objects`, making restarts safe. Recent minutes
remain `Partial` for 90 seconds to account for late object arrival.

## Dashboard

- Summary cards for viewers, peak, requests, 4xx/5xx and lag
- Concurrency/traffic and error graphs for 1, 6, 12 or 24 hours
- Minute, geography and pipeline-object tables
- Five-second refresh and CSV export

