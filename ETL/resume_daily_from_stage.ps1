param(
    [Parameter(Mandatory = $true)]
    [datetime]$Date,
    [ValidateSet("both", "fast", "stream")]
    [string]$Sources = "both",
    [string]$TempDir = "",
    [string]$ArchiveLake = "Z:\Veto Logs Backup\DO NOT DELETE",
    [string]$MaxTempSize = "200GB",
    [ValidateRange(1, 64)]
    [int]$DeepProfileThreads = 12,
    [string]$DeepProfileMemory = "22GB",
    [ValidateRange(1, 64)]
    [int]$MartThreads = 12,
    [string]$MartMemory = "22GB"
)

$ErrorActionPreference = "Stop"
$EtlRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path $EtlRoot -Parent
$BaseRoot = Join-Path $EtlRoot "data"
$PipelineRoot = Join-Path $EtlRoot "src\pipeline"
$Python = Join-Path $WorkspaceRoot "venv\Scripts\python.exe"
$Orchestrator = Join-Path $EtlRoot "src\orchestrator\run_pipeline.py"
$DefaultTempDir = Join-Path $EtlRoot "output\cache\duckdb_temp\deep_profile"

if (-not $TempDir) {
    $TempDir = $DefaultTempDir
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual-environment Python not found: $Python"
}

$dayText = $Date.ToString("yyyy-MM-dd")
$year = $Date.ToString("yyyy")
$month = $Date.ToString("MM")
$day = $Date.ToString("dd")
$sourceKeys = if ($Sources -eq "both") { @("stream", "fast") } else { @($Sources) }
$jobs = @()
$sourceIds = @()

foreach ($source in $sourceKeys) {
    $sourceId = "${source}_$($Date.ToString('yyyy_MM_dd'))"
    $parquetDir = Join-Path $BaseRoot "stage\parquet\source=$source\year=$year\month=$month\day=$day"
    $finalClean = Join-Path $BaseRoot "stage\final_clean\source=$source\year=$year\month=$month\day=$day\${sourceId}_final_clean.parquet"
    $jobs += @{
        source_id = $sourceId
        source_key = $source
        parquet_dir = $parquetDir
        final_clean_file = $finalClean
    }
    $sourceIds += $sourceId
}

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
$env:VG_ETL_BASE = $BaseRoot
$env:VG_ETL_PROCESS_SOURCES = $sourceIds -join ","
$env:VG_ETL_STAGE_JOBS = $jobs | ConvertTo-Json -Compress
$env:VG_ETL_REPLACE_DATES = $dayText
$env:VG_ETL_THREADS = $DeepProfileThreads.ToString()
$env:VG_ETL_MEMORY = $DeepProfileMemory
$env:VG_ETL_DUCKDB_TEMP = Join-Path $TempDir "pipeline_stage"
$env:VG_ETL_DUCKDB_MAX_TEMP = $MaxTempSize
$env:VG_DUCKDB_TEMP_DIR = $TempDir
$env:VG_DUCKDB_MAX_TEMP_SIZE = $MaxTempSize
$env:VG_DEVICE_SNAPSHOT_THREADS = $MartThreads.ToString()
$env:VG_DEVICE_SNAPSHOT_MEMORY_GB = ($MartMemory -replace '[^0-9]', '')

Write-Host "Resuming $dayText from completed lake partitions with $DeepProfileThreads profile threads and $MartThreads mart threads."

$pipelineArgs = @(
    $Orchestrator,
    "--base", $BaseRoot,
    "--skip-etl",
    "--etl1-daily-date", $dayText,
    "--etl1-sources", $Sources,
    "--archive-lake", $ArchiveLake,
    "--lake-repair-lookback-days", "0",
    "--deep-profile-mode", "incremental",
    "--deep-profile-window-days", "1",
    "--ua-profile-window-days", "1",
    "--device-decode-window-days", "1",
    "--concurrency-window-days", "1",
    "--latency-window-days", "1",
    "--deep-profile-threads", $DeepProfileThreads.ToString(),
    "--deep-profile-memory", $DeepProfileMemory,
    "--deep-profile-temp-dir", $TempDir,
    "--deep-profile-max-temp-size", $MaxTempSize,
    "--concurrency-threads", $MartThreads.ToString(),
    "--concurrency-memory", $MartMemory,
    "--latency-threads", $MartThreads.ToString(),
    "--latency-memory", $MartMemory,
    "--identity-threads", $MartThreads.ToString(),
    "--identity-memory", $MartMemory,
    "--content-threads", $MartThreads.ToString(),
    "--content-memory", $MartMemory,
    "--skip-device-decode-profile"
)
& $Python @pipelineArgs
if ($LASTEXITCODE -ne 0) { throw "Remaining pipeline failed with exit code $LASTEXITCODE" }

Write-Host "Stage resume completed for $dayText."
