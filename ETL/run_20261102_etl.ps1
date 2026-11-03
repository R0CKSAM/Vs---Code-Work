$ErrorActionPreference = 'Stop'
$archive = 'Z:\Veto Logs Backup\DO NOT DELETE'
$work = Join-Path $archive 'Temp\VetoETL\ITVINTERN03\daily_20261102'
$raw = Join-Path $archive 'Temp\VetoETL\raw\Veto Logs Backup'
New-Item -ItemType Directory -Path $work,$raw -Force | Out-Null
$env:VG_ETL_LAKE_ROOT = $archive
$env:VG_ETL_FINAL_CLEAN_ROOT = Join-Path $work 'final_clean'
Remove-Item Env:VG_ETL_ROW_START_EPOCH -ErrorAction SilentlyContinue
Remove-Item Env:VG_ETL_ROW_END_EPOCH -ErrorAction SilentlyContinue
& (Join-Path $PSScriptRoot 'run_daily_pipeline.ps1') -Date '2026-11-02' -LocalRoot $work -RawRoot $raw -OverviewLakeRoot $archive -SkipLakeArchive -KeepProcessedInputs -StrictPipeline -SkipPostVerifyDelay -DeepProfileTempDir (Join-Path $work 'duckdb')
if ($LASTEXITCODE -ne 0) { throw "November 2 ETL failed: $LASTEXITCODE" }
