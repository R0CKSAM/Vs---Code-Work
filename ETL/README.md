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

Windows Python workers use a process-local platform-information fallback to
avoid Python 3.13 WMI stalls during pandas imports. This does not stop WMI,
change Windows security settings, or skip ETL/UA processing. The orchestrator
passes `src/runtime` to child workers through `PYTHONPATH`; set
`VG_ETL_DISABLE_WMI=0` to opt out after WMI is healthy. Step output is flushed
to its log as it arrives. The local workstation venv also has a scoped
`veto_etl_runtime.pth` bridge for children of the already-running recovery;
new deployments use the source-controlled orchestrator instead of that file.

Install or refresh the Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_recovery_task.ps1
```

The task runs at 6:00 AM and when `Intern` logs on after a restart. It uses an
interactive user trigger because mapped `Z:` is unavailable to SYSTEM before
login. Missed starts run as soon as possible, and failures retry every 15
minutes. When dates are pending, it gracefully pauses the near-live monitor
before source prefetch and restarts it after ETL, including after a failed ETL
attempt. Preview the detected backlog without processing data:

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
`-ArchiveLakeRoot` and `-HotLakeRetentionDays` (default and minimum 1). The
default archives the completed target-date partitions after the successful
pipeline and keeps only the next IST date on D as the hot spillover partition
for the following daily merge.

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
- `VG_ETL_FINAL_CLEAN_ROOT` (optional final-clean Parquet root; conversion batches
  remain local for speed. The daily PowerShell runner defaults this to
  `Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\final_clean` when that shared
  temp root is available. Direct Python runs retain the local default.)
- `VG_ETL_ARCHIVE_LAKE_ROOTS` (semicolon-separated archive roots; the standard
  `Z:\Veto Logs Backup\DO NOT DELETE` root is detected automatically)
- `VG_DUCKDB_TEMP_DIR` (optional DuckDB spill directory; by default the pipeline uses `output\\cache\\duckdb_temp\\deep_profile` on the ETL drive)
- `VG_DASH_PROFILE_DIR`
- `VG_DASH_WATCH_OUT`
- `VG_DASH_OVERVIEW_BASE`
- `VG_DASH_COMPLETED_THROUGH` (optional validated completed-day cutoff, `YYYY-MM-DD`)

## Daily Recovery Completion

Processing, disposable-input cleanup, and archive transfer are separate phases.
`run_recovery_pipeline.ps1` checks unfinished cleanup even with no ETL backlog,
then verifies archive transfers through the last successful date. Later spillover
partitions stay in the local lake. A failed archive keeps maintenance failed;
`recovery_backlog.json` records `archive_checked_through` only after success.
The pipeline's processing status alone is not proof of delivery to the archive.

Archive copies use Parquet metadata and SHA-256 checks before local removal.
Interrupted `.archiving` files are retried. Cleanup revalidates retained lake row
counts and uses a process lock. Recent interrupted cleanup manifests are retried
for seven days; older incidents require an explicit reviewed recovery.

Final-clean storage can be separate from the local data root. Cleanup records
that root in its manifest and removes only the exact processed source/date after
full PASS validation and retained-lake reconciliation. Do not manually clear the
shared final-clean directory while processing or a review is pending.
For a standalone `resume_failed_lake.py` recovery, supply `--final-clean-root`
with that NAS path (or set `VG_ETL_FINAL_CLEAN_ROOT` in the recovery environment).

A full-day, exactly reconciled REVIEW retains raw/stage inputs and records cleanup
as a warning, allowing permanent lake archival to continue. Missing coverage,
row mismatches and hard validation failures still block the pipeline. REVIEW is
not a PASS and its channel anomalies still require investigation.

For an operator-confirmed broadcast exception, run full validation with
`--channel-review-file <review.json>`. The JSON must contain the exact `date`,
`confirmed_by`, and `channels` entries with `source`, `channel`,
`target_raw_ts_chunks`, and `reason`. Confirmation applies only to that observed
date/channel/count, is included in the new report as `acknowledged_channels`,
and cannot bypass coverage or profile reconciliation. Keep the original REVIEW
report and the confirmation file. Never add a permanent channel exclusion just
to clear one day's warning.

The gzip converter aborts a batch on output-write failure instead of treating it
as a corrupt input and repeatedly retrying an uncleared buffer. Successful batch
manifests remain reusable after storage is repaired.

The live-monitor startup wait is five minutes, with launcher output captured in
`output/live_monitor`. The YouTube collector uses its scheduled login task and
one-minute crash retries; do not also enable its legacy Startup shortcut.

## VOD Dashboard Refresh

From `ETL`, run `./run_vod_query_dashboard_incremental.ps1`. The default end
date comes from completed daily checkpoints, so a newer failed ETL run does not
block earlier completed days. Use `-Date 2026-10-19` to cap the refresh and
`-PlanOnly` to preview it. Every new date requires completion evidence; PASS and
completed REVIEW days are accepted, but missing or failed dates are blocked.

Daily extracts are retained and published one day at a time. The extractor
prefilters VOD-capable hosts without dropping unmarked VOD-host requests or
non-success HTTP codes. DuckDB uses a 4 GB memory limit, six threads and at most
8 GB of spill under `output/temp/vod_query_work`, not the C: user temp folder.
Keep `vod_stream_query_analysis_dashboard_data` beside the exported HTML.

## Missing Source Delivery

Full-day conversion now checks Akamai raw filename timestamps before expensive
processing. Missing files near the target IST day's end stop processing early,
preserving inputs. Microbatches are exempt. Passing this necessary-input check
does not prove completeness: lake coverage and row reconciliation still apply.

For delayed S3 delivery, run from the repository root:

```powershell
.\venv\Scripts\python.exe ETL/src/tools/wait_for_complete_source.py --date 2026-10-20 --work-dir ETL/output/temp/source_wait_20261020 --interval-seconds 900 --max-hours 12
```

The watcher checks both sources every 15 minutes after each check, for up to
12 hours of polling. See `state.json` in its work directory. It starts at most
one normal recovery attempt once both sources have candidate tail files;
recovery can run beyond the polling window. Fresh completion evidence is
required, and a failed attempt is not repeatedly restarted. It cannot restore
logs missing from the source or replace final coverage validation. It does not
enable LiveMonitor. Use the same work directory to prevent duplicate watchers.

## Sequential Recovery And Storage

`run_recovery_pipeline.ps1` downloads only one day's STREAM/FAST sources at a
time, then processes, validates, refreshes dashboards and runs verified
cleanup/archive maintenance before starting the next date. It no longer
prefetches the entire backlog. The existing recovery mutex prevents duplicate
scheduled recovery runners; operator-disabled LiveMonitor stays disabled.

The runner checks source-tail availability before downloading and requires
50 GiB free on the local data volume and 100 GiB on the archive volume. After
download, at least 20 GiB must remain locally. These are minimum reserves, not
a guarantee that every workload will fit. Final-clean and DuckDB scratch keep
using the daily launcher's shared-storage configuration. Missing source logs,
unavailable storage or validation failures stop the queue and trigger the
existing failure notification instead of publishing incomplete data.

An optional `output/state/recovery_dependency.json` can specify `state_path`
and `success_statuses`. Recovery waits up to 24 hours for that repair to finish
before downloading anything. A missing required state or failed repair blocks
recovery. Without this dependency file, normal scheduling is unchanged.

### Core-Only Lake Priority

`src/tools/run_core_lake_priority.py` can take a verified downloaded day through
001/02/03 without rendering dashboards. It waits for the active pipeline to
finish; new pipeline runs yield to its PID-owned priority request. The existing
run is never interrupted. Full-day structural validation and exact raw-batch
final-clean/lake row reconciliation are required before retiring that day's
inputs. Missing coverage retains all raw/stage data and raises an alert.

The explicit cleanup flag `--allow-lake-only-validation` permits this core-only
workflow, while normal cleanup still requires full dashboard-profile validation.
A `lake_ready` receipt in `output/state/prepared_lake` is not a daily completion
checkpoint: dashboards remain pending. Later recovery verifies the retained
file fingerprints, row counts and download receipt before skipping redundant
raw download and 001/02/03 processing.

