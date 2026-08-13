param(
    [Parameter(Mandatory = $true)]
    [datetime]$Date,
    [ValidateSet("both", "fast", "stream")]
    [string]$Sources = "both",
    [string]$TempDir = "Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\duckdb\deep_profile",
    [string]$MaxTempSize = "200GB"
)

$ErrorActionPreference = "Stop"
$EtlRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path $EtlRoot -Parent
$BaseRoot = Join-Path $EtlRoot "data"
$PipelineRoot = Join-Path $EtlRoot "src\pipeline"
$Python = Join-Path $WorkspaceRoot "venv\Scripts\python.exe"
$Orchestrator = Join-Path $EtlRoot "src\orchestrator\run_pipeline.py"

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
    if (-not (Test-Path -LiteralPath $parquetDir)) {
        throw "Stage parquet folder not found: $parquetDir"
    }
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
$env:VG_ETL_THREADS = "2"
$env:VG_ETL_MEMORY = "6GB"
$env:VG_ETL_DUCKDB_TEMP = Join-Path $TempDir "pipeline_stage"
$env:VG_ETL_DUCKDB_MAX_TEMP = $MaxTempSize
$env:VG_DUCKDB_TEMP_DIR = $TempDir
$env:VG_DUCKDB_MAX_TEMP_SIZE = $MaxTempSize

Write-Host "Resuming $dayText from stage for $($sourceKeys -join ', ')."
& $Python (Join-Path $PipelineRoot "02.py")
if ($LASTEXITCODE -ne 0) { throw "02.py failed with exit code $LASTEXITCODE" }

& $Python (Join-Path $PipelineRoot "03.py")
if ($LASTEXITCODE -ne 0) { throw "03.py failed with exit code $LASTEXITCODE" }

$pipelineArgs = @(
    $Orchestrator,
    "--base", $BaseRoot,
    "--skip-etl",
    "--etl1-daily-date", $dayText,
    "--etl1-sources", $Sources,
    "--deep-profile-temp-dir", $TempDir,
    "--deep-profile-max-temp-size", $MaxTempSize,
    "--concurrency-memory", "4GB",
    "--identity-memory", "4GB",
    "--content-memory", "4GB",
    "--skip-device-decode-profile"
)
& $Python @pipelineArgs
if ($LASTEXITCODE -ne 0) { throw "Remaining pipeline failed with exit code $LASTEXITCODE" }

Write-Host "Stage resume completed for $dayText."
