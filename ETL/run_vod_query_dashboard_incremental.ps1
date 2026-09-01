param(
    [datetime]$Date = (Get-Date).Date.AddDays(-1),
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$FallbackLakeRoot = (Join-Path $PSScriptRoot 'data\lake\source=stream'),
    [string]$Python = (Join-Path $PSScriptRoot '..\venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$dateKey = $Date.ToString('yyyy-MM-dd')
$relativePartition = 'year={0}\month={1}\day={2}' -f `
    $Date.ToString('yyyy'), $Date.ToString('MM'), $Date.ToString('dd')
$rawPath = $null
foreach ($root in @($LakeRoot, $FallbackLakeRoot)) {
    if ([string]::IsNullOrWhiteSpace($root)) {
        continue
    }
    $candidate = Join-Path $root $relativePartition
    if ((Test-Path -LiteralPath $candidate -PathType Container) -and
        (Get-ChildItem -LiteralPath $candidate -File -Filter '*.parquet')) {
        $rawPath = $candidate
        break
    }
}
$exports = Join-Path $PSScriptRoot 'output\exports'
$dailyCsv = Join-Path $exports "vod_stream_query_events_$dateKey.csv"
$stagedCsv = Join-Path $exports ".vod_stream_query_events_$dateKey.$([guid]::NewGuid().ToString('N')).tmp.csv"
$dashboard = Join-Path $exports 'vod_stream_query_analysis_dashboard.html'
$dataDir = Join-Path $exports 'vod_stream_query_analysis_dashboard_data'
$davisWorkbook = Join-Path $exports 'Davis_Cup_Performance.xlsx'
$extractor = Join-Path $PSScriptRoot 'src\tools\export_vod_query_events.py'
$builder = Join-Path $PSScriptRoot 'src\tools\build_vod_query_dashboard.py'

if ($null -eq $rawPath) {
    throw "Raw STREAM partition not found for ${dateKey} in archive or fallback lake."
}
if (-not (Test-Path -LiteralPath $dataDir -PathType Container)) {
    throw "Dashboard lazy data is missing: $dataDir. Run rebuild_vod_query_dashboard_range.ps1 once to bootstrap it."
}

try {
    & $Python $extractor --input $rawPath --date $dateKey --out $stagedCsv --compact
    if ($LASTEXITCODE -ne 0) {
        throw "VOD event extraction failed for $dateKey."
    }

    & $Python $builder `
        --append $stagedCsv `
        --out $dashboard `
        --davis-xlsx $davisWorkbook `
        --data-dir $dataDir `
        --data-url 'vod_stream_query_analysis_dashboard_data' `
        --incremental
    if ($LASTEXITCODE -ne 0) {
        throw "VOD dashboard refresh failed for $dateKey."
    }

    Move-Item -LiteralPath $stagedCsv -Destination $dailyCsv -Force
    Write-Host "VOD dashboard appended ${dateKey}; existing day payloads were reused: $dashboard"
}
finally {
    if (Test-Path -LiteralPath $stagedCsv) {
        Remove-Item -LiteralPath $stagedCsv -Force
    }
}
