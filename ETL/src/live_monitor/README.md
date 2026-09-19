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

## Davis Cup schedule labels

Edit `ETL/config/live_monitor/davis_cup_2026_schedule.json` to label a Davis
Cup CDN asset in the War Room as `GRP n/Mn | HOST vs OPP`. The parser applies
the match label by the request's IST calendar date, scheduled start time,
production CDN host, and 32-character asset ID in the request path. A shared
asset switches labels at the next scheduled start on that date. This is
schedule-based attribution, not verification of the video content; overruns
and overnight sessions require confirmed schedule updates. Pre-start traffic
remains Other. This forward-only schedule does not invalidate or
rebuild historical live-monitor aggregates.

The War Room Channel menu supports search, multiple selections, Select visible,
and Clear. Combined selections use a read-only database snapshot to deduplicate
IPs, devices, and sessions across channels rather than summing their counts.
Selected-channel results are cached for ten seconds; only one selection query
runs at a time to limit competition with ingestion.

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

## War Room performance and feed labels

- Davis Cup channels use the first five characters of the six configured asset
  IDs: `f98c8`, `3b966`, `bf34b`, `d1ff5`, `a9b4f`, `834dd`. The schedule JSON
  remains the URL source of truth. Feed identity no longer changes at match time.
- Legacy `GRP ...` labels are combined in read-only snapshot views. Exact IP,
  device and session counts are deduplicated across their aliases. This does not
  reset the file ledger or rebuild historical aggregates. Requests previously
  classified as `Other` cannot be reassigned without replaying their raw logs.
- Snapshot queries explicitly bound minute data to the configured live window.
  Each minute series is aggregated once across channels, not once per channel.
  Parser/scanner writes are serialized in-process to avoid SQLite writer races.
- `/api/state?channel=f98c8` returns only that channel's series and breakdowns,
  plus the channel menu. Gzip and ETag responses reduce repeated transfer and
  rendering. `/api/state` still supports the complete export payload.
- Partial successful downloads are queued even when a transfer batch fails.
  Database queue errors no longer trigger an unrelated full S3 listing. UTC
  source-day selection is separate from IST display times, and unchanged files
  retain their modification timestamps during rclone copies.
- `snapshot_build_seconds` in the published JSON measures actual build cost.
  These changes do not guarantee sub-minute CDN delivery or eliminate upstream
  source latency. No source/lake deletion or production database vacuum is used.

## Legacy delivery paths and staging

- War Room recognizes the legacy YRF `/hls/live/<id>/<channel>/` paths for
  YRF Music, SAGA Music, Saga Music Haryanvi and Sikh Ratnavali. Matching requires
  the exact YRF delivery host and a known channel directory, not a query value.
- Epic rendition folders such as `epic-kids-o_360p` and the observed Bharat
  root manifest `master_360.m3u8` use host-specific rules. Staging hosts produce
  separate `Epic ... (staging)` channels, not the corresponding production
  channel. `All channels` still includes both, as it does all CDN requests.
- HTTP errors remain in request, byte and error metrics. The existing audience
  definition is distinct requesting IPs, not player-confirmed successful viewers.
  An error-only visible range now carries an explicit warning. Failed manifest
  requests do not contribute to the segment-based watch-time estimate.
- These additions apply on ingestion. Already-committed `Other` rows are not
  guessed into a channel or replayed into the existing ledger; their request
  paths are not stored in aggregates. They remain until the rolling window moves
  past them. The `Other` selection identifies this historical/unresolved scope.
- Labelling a failed URL does not repair the CDN origin or redirect external
  players. Check the actual production playlist before replacing recorder URLs.
