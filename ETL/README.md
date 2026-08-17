# ETL

Single-folder workflow for your Veto watch-hours pipeline and dashboards.

## Folder layout

- `run.py` : main command you run
- `run_daily_pipeline.ps1` : rclone-yesterday helper
- `DASHBOARD_DATA_CATALOG.md` : required first reference before designing a new dashboard or mart
- `src/` : all Python code
- `tools/` : optional bundled command-line tools, such as rclone
- `config/` : optional portable config files, such as `rclone.conf`
- `src/tools/asn/` : optional ASN lookup/refresh tools
- `data/` : local lake, ASN lookup data, and raw backup folders
- `output/` : generated watch-hours dashboard, overview dashboard, logs, and state
- `extras/` : standalone apps, one-off helpers/data, code backups, validation artifacts,
  archived outputs, and other files that are not part of the daily production runtime

## Quick run

```powershell
cd "<path-to-your-ETL-folder>"
python run.py
```

For portability, keep this folder self-contained:
- `ETL/run.py`
- `ETL/src/*`
- `ETL/config/rclone.conf` (if using bundled rclone)
- `ETL/output/state/gz_parquet_prefs.json` (001.py approved column list)
- `ETL/data/asn/*`
- `ETL/data/lake/*`
- `ETL/requirements.txt`

Preferred local data layout:
- `ETL\data\lake`
- `ETL\data\asn` (CSV/JSON lookup data only)
- `ETL\data\raw`

Optional hot/archive layout when D drive space is limited:

- Keep current partitions in `ETL\data\lake\source=fast|stream`.
- Keep historical partitions in `Z:\Veto Logs Backup\DO NOT DELETE\source=fast|stream`.
- Complementary files for the same source/date are merged across hot and
  archive roots. When the same filename exists in both places, only the copy
  with the broadest timestamp coverage (then row count/size) is selected.
- Do not move the active date while an ETL process or
  `output\state\pipeline.lock` is present.

This runs:

1) `001.py`  (raw `.gz` to parquet; defaults to `data\raw\Veto Logs Backup` when present)
2) `02.py`   (dedupe `_final_clean`)
3) `03.py`   (lake partitioning)
4) watch-hours dashboard
5) overview dashboard

## Main commands

```powershell
python run.py                 # full pipeline
python run.py etl             # only 001/02/03
python run.py dashboards      # rebuild profile + both dashboards from existing lake
python run.py watch           # rebuild watch-hours profile + dashboard
python run.py overview        # rebuild overview data + dashboard
python run.py sync-yesterday  # rclone yesterday, then pipeline
```

## Crash recovery and missed-day catch-up

`run_recovery_pipeline.ps1` is the scheduled entry point. It keeps a durable
checkpoint in `output\state\recovery_backlog.json`, runs missing dates oldest
first, and calls `run_daily_pipeline.ps1 -Date YYYY-MM-DD` for each date. A
crash never advances the checkpoint, so the same date resumes after restart.

Intermediate backlog dates skip final watch/overview rendering and lake
archiving. The last backlog date performs the full refresh and archive. ETL
dates run serially because the lake/profile writers are stateful; the existing
pipeline lock plus a recovery mutex prevents duplicate runs.

Each download is verified against a fresh remote snapshot using both file
count and total bytes. A date checkpoint is committed only when the same
recovery attempt creates fresh full-day validation evidence with exact FAST
and STREAM row reconciliation. Old validation reports cannot complete a new
attempt. PowerShell argument-shape guards prevent switches or dates from being
mistaken for remote roots or local paths.

Backlog recovery prefetches up to six source/date folders concurrently. With
three missing dates, that means FAST and STREAM for all three dates can run as
six independent jobs; every job keeps 16 transfers and 32 checkers. Once all
downloads validate, ETL dates remain serial so the stage state, lake promotion,
and cleanup checkpoints cannot race.

The daily workstation profile uses 11 workers for `001.py`, 11 DuckDB threads
and 24 GB for `02.py`/`03.py`, and Snappy for the temporary `001.py` parquet.
The retained final-clean/lake compression remains unchanged. Intermediate
dates build their required daily marts but defer the top-level watch, overview,
audience, and master dashboards; the newest backlog date performs the complete
dashboard refresh once.

Install or refresh the Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_recovery_task.ps1
```

The task runs at 7:00 AM and when `Intern` logs on after a restart. It uses an
interactive user trigger because mapped `Z:` is unavailable to SYSTEM before
login. Missed starts run as soon as possible, and failures retry every 15
minutes. Preview the detected backlog without processing data:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_recovery_pipeline.ps1 -DryRun
```

Explicit high-throughput recovery settings:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_recovery_pipeline.ps1 `
  -MaxParallelDownloads 6 -DownloadTransfers 16 -DownloadCheckers 32
```

Per-source download logs are written under `output\logs\downloads`; validated
count/byte results are stored under `output\state\downloads`.

Pass advanced pipeline options after `--`:

```powershell
python run.py dashboards -- --dry-run
python run.py all -- --base ".\veto Stream Logs"
python run.py all -- --base ".\data"
```

## Common options

- `--skip-etl`, `--skip-watch`, `--skip-overview`
- `--base` (defaults to env `VG_ETL_BASE`)
- `--output-root` (defaults to `output`)
- `--watch-profile` (defaults to `output\watch_hours\profile`)
- `--watch-out` (defaults to `output\watch_hours\veto_watch_hours.html`)
- `--overview-data-dir` (defaults to `output\overview`)
- `--overview-html` (defaults to `output\overview\overview_dashboard.html`)
- `--dry-run` to validate dashboards without writing
- `--publish-through YYYY-MM-DD` to publish a validated completed-day cutoff while newer dates are being repaired
- `--etl1-prefs-file` to choose the `001.py` column preference JSON
- `--stage-threads`, `--stage-memory`, and `--stage-max-temp-size` to raise 02/03 DuckDB resources for large repairs
- `--stage-compression snappy` for faster temporary final-clean writes when storage is available
- `--cleanup-daily-intermediates` to remove a validated daily run's raw `.gz` and stage parquet files after all outputs finish
- `--plan-daily-intermediate-cleanup` to validate and report reclaimable storage without deleting anything

## Path controls

Default Linode/rclone download location:

```powershell
python run.py sync-yesterday
# downloads both Linode folders, verifies local counts, then builds .\data\lake once
```

Default daily raw download layout:

```text
ETL\data\raw\Veto Logs Backup\Veto Stream Backup\MM\DD
ETL\data\raw\Veto Logs Backup\Veto fast Backup\MM\DD
```

Default remotes:

```text
veto:veto-stream-logs/veto-stream-logs/MM/DD
veto:veto-stream-logs/veto-fast-logs/MM/DD
```

After both source folders are verified, the single ETL run writes reusable outputs under `ETL\data`, including `*_parquet`, `*_final_clean.parquet`, and `ETL\data\lake`.

Choose a different local download/base folder:

```powershell
python run.py sync-yesterday -- -RawRoot "Y:\Veto Logs Backup\Raw"
python run.py sync-yesterday -- -LocalRoot "D:\Veto Logs Backup\Vs - Code Work\ETL\data"
```

Use the old one-remote behavior only when needed:

```powershell
python run.py sync-yesterday -- -SingleSourceMode -RemoteRoot "veto:veto-stream-logs/veto-stream-logs"
```

Daily download check flow:

- remote file count is captured once at start
- each source folder is synced separately
- after each sync, local file count must match that source's starting remote count
- verification retries `-VerifyRetries 3`; each mismatch reruns sync
- after verified, ETL waits `-PostVerifyDelaySeconds 60`
- after lake partitioning, the daily delivery gate verifies FAST/STREAM time coverage,
  internal gaps, overlapping files, and archive alternatives before profiling
- after the watch profile is merged, the gate reconciles source row totals and checks
  canonical channel volumes before any dashboard is published
- validation reports are written to `output\validation\daily_delivery`
- normal `sync-yesterday` runs then delete only the processed date's raw `.gz`, stage
  parquet, and final-clean files; the validated lake and a per-file manifest under
  `output\cleanup` are retained

Channel-volume findings are review warnings by default. Make them blocking for a
scheduled production run with `--strict-channel-validation`. Use
`--skip-data-validation` only for an intentional recovery or diagnostic run.

Optional remote stability wait for cautious scheduled runs:

```powershell
python run.py sync-yesterday -- -WaitForRemoteStable -StableChecks 2 -StableWaitMinutes 10
```

Fast/manual run switches:

```powershell
python run.py sync-yesterday -- -SkipVerifyAfterSync -SkipPostVerifyDelay
python run.py sync-yesterday -- -KeepProcessedInputs  # disable automatic cleanup for this run
python run.py sync-yesterday -- -SkipLakeArchive      # keep all lake partitions on D for this run
```

Cleanup is refused unless the full-day source checks and exact profile reconciliation
both pass. It is also disabled for partial/micro-batch runs. Once intermediates are
removed, dashboard and mart reruns still work from the lake, but rebuilding that lake
partition requires downloading the raw day again.

The scheduled daily launcher defaults to the tested fast workstation profile:

- 10 raw-conversion workers
- 10 DuckDB threads and a 22 GB memory ceiling for ETL stages, profiling, and marts
- up to 200 GB of DuckDB spill under `Z:\Veto Logs Backup\DO NOT DELETE\Temp` when available
- two hot IST lake dates on D; older validated partitions are verified and archived to
  `Z:\Veto Logs Backup\DO NOT DELETE` after a successful daily pipeline

The lake archive runs a dry plan before execution, preserves the more complete
copy of any repeated logical Parquet file, and moves displaced archive versions
under `delete temp\lake_conflicts` for rollback review. Override the defaults with
`-ArchiveLakeRoot` and `-HotLakeRetentionDays` (minimum 2).

All limits remain explicit PowerShell parameters. For example, a lower-resource run can use:

```powershell
python run.py sync-yesterday -- -Etl1Workers 2 -StageThreads 2 -StageMemory 6GB -DeepProfileThreads 2 -DeepProfileMemory 6GB -ConcurrencyThreads 2 -ConcurrencyMemory 6GB
```

Choose dashboard/profile output locations:

```powershell
python run.py dashboards -- --output-root ".\output"
python run.py dashboards -- --watch-out ".\output\watch_hours\veto_watch_hours.html"
python run.py dashboards -- --overview-html ".\output\overview\overview_dashboard.html"
```

## Environment overrides used by dashboard scripts

- `VG_ETL_BASE`
- `VG_ETL_ARCHIVE_LAKE_ROOTS` (semicolon-separated archive roots; the standard
  `Z:\Veto Logs Backup\DO NOT DELETE` root is detected automatically)
- `VG_DUCKDB_TEMP_DIR` (optional DuckDB spill directory; by default the pipeline uses `output\\cache\\duckdb_temp\\deep_profile` on the ETL drive)
- `VG_DASH_PROFILE_DIR`
- `VG_DASH_WATCH_OUT`
- `VG_DASH_OVERVIEW_BASE`
- `VG_DASH_COMPLETED_THROUGH` (optional validated completed-day cutoff, `YYYY-MM-DD`)

