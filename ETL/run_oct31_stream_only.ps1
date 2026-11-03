$ErrorActionPreference = 'Stop'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'venv\Scripts\python.exe'
$archive = 'Z:\Veto Logs Backup\DO NOT DELETE'
$work = Join-Path $archive 'Temp\VetoETL\ITVINTERN03\stream_20261031'
$receipt = Get-Content (Join-Path $PSScriptRoot 'output\state\downloads\2026-10-31_stream.json') -Raw | ConvertFrom-Json
if ($receipt.status -ne 'complete' -or $receipt.verified -ne $true -or $receipt.local_count -ne $receipt.remote_count -or $receipt.local_bytes -ne $receipt.remote_bytes) { throw 'October 31 STREAM download is not verified.' }
New-Item -ItemType Directory -Path $work -Force | Out-Null
$env:VG_ETL_LAKE_ROOT = $archive
$env:VG_ETL_FINAL_CLEAN_ROOT = Join-Path $work 'final_clean'
Remove-Item Env:VG_ETL_ROW_START_EPOCH -ErrorAction SilentlyContinue
Remove-Item Env:VG_ETL_ROW_END_EPOCH -ErrorAction SilentlyContinue
$pipelineArgs = @(
    (Join-Path $PSScriptRoot 'src\orchestrator\run_pipeline.py'),
    '--base', $work, '--etl1-daily-date', '2026-10-31', '--etl1-sources', 'stream',
    '--etl1-daily-raw-root', (Join-Path $PSScriptRoot 'data\raw\Veto Logs Backup'),
    '--state-name', 'oct31_stream_only', '--etl1-workers', '12', '--etl1-compression', 'snappy',
    '--stage-threads', '12', '--stage-memory', '24GB', '--stage-max-temp-size', '200GB',
    '--stage-compression', 'snappy', '--deep-profile-temp-dir', (Join-Path $work 'duckdb'),
    '--lake-repair-lookback-days', '0',
    '--skip-watch', '--skip-overview', '--skip-deep-profile', '--skip-device-snapshot',
    '--skip-device-decode-profile', '--skip-concurrency', '--skip-latency',
    '--skip-identity-mart', '--skip-content-mart', '--skip-audience', '--skip-master',
    '--skip-data-validation'
)
# Source-day rows are fully reconciled by the orchestrator. IST coverage
# is checked separately because the previous source day comes from another PC.
& $python @pipelineArgs
if ($LASTEXITCODE -ne 0) { throw 'October 31 STREAM lake build failed.' }
& $python (Join-Path $PSScriptRoot 'src\tools\validate_daily_delivery.py') --lake $archive --date 2026-10-31 --sources stream --mode structural --output-dir (Join-Path $PSScriptRoot 'output\validation\oct31_stream_only')
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Source-day lake build finished. Full IST coverage is pending validation; inspect the report and the October 30 delivery from the other PC.'
    exit 2
}
Write-Host 'October 31 STREAM lake and structural validation complete. Stopping; no other source/date is queued.'
