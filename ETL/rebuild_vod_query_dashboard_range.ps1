param(
    [datetime]$StartDate = [datetime]'2026-08-01',
    [datetime]$EndDate = (Get-Date).Date.AddDays(-1),
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$Python = '.\venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Stop'
if ($EndDate.Date -lt $StartDate.Date) {
    throw 'EndDate must be on or after StartDate.'
}

$exports = Join-Path $PSScriptRoot 'output\exports'
$extractor = Join-Path $PSScriptRoot 'src\tools\export_vod_query_events.py'
$builder = Join-Path $PSScriptRoot 'src\tools\build_vod_query_dashboard.py'
$runId = [guid]::NewGuid().ToString('N')
$stagedHistory = Join-Path $exports "vod_stream_query_events_$runId.csv"
$stagedDashboard = Join-Path $exports "vod_stream_query_analysis_dashboard_$runId.html"
$stagedWorkbook = Join-Path $exports "Davis_Cup_Performance_$runId.xlsx"
$dailyFiles = [System.Collections.Generic.List[string]]::new()

try {
    for ($date = $StartDate.Date; $date -le $EndDate.Date; $date = $date.AddDays(1)) {
        $dateKey = $date.ToString('yyyy-MM-dd')
        $partition = Join-Path $LakeRoot (
            'year={0}\month={1}\day={2}' -f
            $date.ToString('yyyy'), $date.ToString('MM'), $date.ToString('dd')
        )
        if (-not (Test-Path -LiteralPath $partition -PathType Container) -or
            -not (Get-ChildItem -LiteralPath $partition -File -Filter '*.parquet')) {
            throw "Raw STREAM partition not found for ${dateKey}: $partition"
        }
        $dailyCsv = Join-Path $exports "vod_stream_query_events_$dateKey.csv"
        & $Python $extractor --input $partition --date $dateKey --out $dailyCsv --compact
        if ($LASTEXITCODE -ne 0) {
            throw "VOD event extraction failed for $dateKey."
        }
        $dailyFiles.Add($dailyCsv)
    }

    $builderArgs = @(
        $builder,
        '--events', $stagedHistory,
        '--out', $stagedDashboard,
        '--davis-xlsx', $stagedWorkbook
    )
    foreach ($dailyCsv in $dailyFiles) {
        $builderArgs += @('--append', $dailyCsv)
    }
    & $Python @builderArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'VOD dashboard range build failed.'
    }

    Move-Item -LiteralPath $stagedHistory -Destination (Join-Path $exports 'vod_stream_query_events.csv') -Force
    Move-Item -LiteralPath $stagedDashboard -Destination (Join-Path $exports 'vod_stream_query_analysis_dashboard.html') -Force
    Move-Item -LiteralPath $stagedWorkbook -Destination (Join-Path $exports 'Davis_Cup_Performance.xlsx') -Force
    Write-Host "VOD dashboard rebuilt from $($StartDate.ToString('yyyy-MM-dd')) through $($EndDate.ToString('yyyy-MM-dd'))."
}
finally {
    foreach ($path in @($stagedHistory, $stagedDashboard, $stagedWorkbook)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}
