# Veto Live Monitor

This replaces the experimental `ETL/cloner` state model with a durable,
restartable near-live pipeline.

## Run

From the `ETL` directory:

```powershell
.\run_live_monitor.ps1
```

Open `http://127.0.0.1:8790`. Stop with `Ctrl+C`. A non-zero unexpected exit is
automatically restarted after five seconds. Use `-NoRestart` while debugging.

Manage a background instance without killing an in-flight database transaction:

```powershell
.\manage_live_monitor.ps1 -Action Start
.\manage_live_monitor.ps1 -Action Status
.\manage_live_monitor.ps1 -Action Stop
```

The 6:00 AM recovery task pauses this monitor only when daily ETL dates are
pending, then starts it again from a guaranteed cleanup block after ETL ends.

The nginx LAN endpoint requires a browser username and password. Change its
credentials at any time without storing the password in shell history:

```powershell
.\set_live_dashboard_credentials.ps1
```

The generated password file is local-only and ignored by Git. `/healthz`
remains available without a login so automated monitoring can verify service
availability.

The channel dropdown defaults to **All channels** and uses the same canonical
host/path channel mapping as the batch ETL. Each selection reports exact
distinct `cliIP` values per minute for that mapped channel.

Validate configuration without starting ingestion:

```powershell
..\venv\Scripts\python.exe -m src.live_monitor.cli doctor
```

Environment overrides:

- `VETO_LIVE_REMOTE`
- `VETO_LIVE_SPOOL`
- `VETO_LIVE_STATE_DIR`
- `VETO_RCLONE_EXE`
- `VETO_LIVE_WATCHED_PATHS` (comma-separated request-path tokens)
- `VETO_LIVE_HTTP_HOST` and `VETO_LIVE_HTTP_PORT`
- `VETO_LIVE_MAX_LAG_SECONDS` (default 600)

## Recovery guarantees

- SQLite WAL replaces the growing JSON checkpoint.
- Channel-mapping versions invalidate and rebuild derived aggregates atomically;
  raw cached gzip files are not downloaded again.
- File metrics and completion state commit in the same transaction.
- Interrupted `processing` rows are immediately requeued after restart.
- The dashboard starts before local-spool reconciliation, so restart remains
  observable even when a date folder contains many files.
- A process-wide file lock prevents two writers from corrupting totals.
- Completed files that later change are quarantined instead of double-counted.
- Parse failures retry with bounded exponential backoff.
- Recent files stream from today's listing without waiting for a full-list sort.
- The S3 recent-object index is split across ten server-side Akamai filename
  prefixes, then rclone downloads the resulting exact key list concurrently.
- Historical reconciliation covers the finalized previous day and does not
  compete with the current-day live poll.
- Historical backfill waits for the first successful recent sync, so startup
  always prioritizes the near-live window.
- Published JSON is flushed, synced, and atomically replaced.
- `/healthz` returns HTTP 503 when processed events exceed the lag threshold.
- Viewer identities are irreversible BLAKE2 fingerprints; raw IPs are not stored.

Raw spool files are never deleted automatically. Retention must be configured as
an explicit operational policy after the backup requirements are confirmed.

The S3 day prefix is flat and large. Rclone must enumerate it before filtering,
so source-side hourly prefixes or S3 event notifications are required for
guaranteed sub-minute ingestion. With the existing layout, the monitor orders
recent objects first after enumeration and reports its actual data lag.
