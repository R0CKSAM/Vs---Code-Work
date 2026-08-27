param(
    [datetime]$Date = (Get-Date).Date.AddDays(-1),
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$Python = '.\venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Stop'
$dateKey = $Date.ToString('yyyy-MM-dd')
$year = $Date.ToString('yyyy')
$month = $Date.ToString('MM')
$day = $Date.ToString('dd')
$rawPath = Join-Path $LakeRoot "year=$year\month=$month\day=$day"
$exports = Join-Path $PSScriptRoot 'output\exports'
$dailyCsv = Join-Path $exports "vod_stream_query_events_$dateKey.csv"
$historyCsv = Join-Path $exports 'vod_stream_query_events.csv'
$dashboard = Join-Path $exports 'vod_stream_query_analysis_dashboard.html'

if (-not (Test-Path -LiteralPath $rawPath -PathType Container) -or
    -not (Get-ChildItem -LiteralPath $rawPath -File -Filter '*.parquet')) {
    throw "Raw STREAM partition not found for ${dateKey}: $rawPath"
}

& $Python (Join-Path $PSScriptRoot 'src\tools\export_vod_query_events.py') --input $rawPath --date $dateKey --out $dailyCsv --compact
if ($LASTEXITCODE -ne 0) { throw "VOD event extraction failed for $dateKey." }

& $Python (Join-Path $PSScriptRoot 'src\tools\build_vod_query_dashboard.py') --events $historyCsv --append $dailyCsv --out $dashboard
if ($LASTEXITCODE -ne 0) { throw "VOD dashboard refresh failed for $dateKey." }

Write-Host "VOD query dashboard refreshed through ${dateKey}: $dashboard"
