param(
    [datetime]$StartDate = [datetime]'2026-08-01',
    [datetime]$EndDate = (Get-Date).Date.AddDays(-1),
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$FallbackLakeRoot = (Join-Path $PSScriptRoot 'data\lake\source=stream'),
    [string]$Python = (Join-Path $PSScriptRoot '..\venv\Scripts\python.exe')
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
$stagedData = Join-Path $exports "vod_stream_query_analysis_dashboard_$($runId)_data"
$liveData = Join-Path $exports 'vod_stream_query_analysis_dashboard_data'
$backupData = Join-Path $exports "vod_stream_query_analysis_dashboard_data.backup-$runId"
$stagedWorkbook = Join-Path $exports "Davis_Cup_Performance_$runId.xlsx"
$dailyFiles = [System.Collections.Generic.List[string]]::new()

try {
    for ($date = $StartDate.Date; $date -le $EndDate.Date; $date = $date.AddDays(1)) {
        $dateKey = $date.ToString('yyyy-MM-dd')
        $relativePartition = 'year={0}\month={1}\day={2}' -f `
            $date.ToString('yyyy'), $date.ToString('MM'), $date.ToString('dd')
        $partition = $null
        foreach ($root in @($LakeRoot, $FallbackLakeRoot)) {
            if ([string]::IsNullOrWhiteSpace($root)) {
                continue
            }
            $candidate = Join-Path $root $relativePartition
            if ((Test-Path -LiteralPath $candidate -PathType Container) -and
                (Get-ChildItem -LiteralPath $candidate -File -Filter '*.parquet')) {
                $partition = $candidate
                break
            }
        }
        if ($null -eq $partition) {
            throw "Raw STREAM partition not found for ${dateKey} in archive or fallback lake."
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
        '--davis-xlsx', $stagedWorkbook,
        '--data-dir', $stagedData,
        '--data-url', 'vod_stream_query_analysis_dashboard_data'
    )
    foreach ($dailyCsv in $dailyFiles) {
        $builderArgs += @('--append', $dailyCsv)
    }
    & $Python @builderArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'VOD dashboard range build failed.'
    }

    if (Test-Path -LiteralPath $liveData) {
        Move-Item -LiteralPath $liveData -Destination $backupData
    }
    try {
        Move-Item -LiteralPath $stagedData -Destination $liveData
    }
    catch {
        if (Test-Path -LiteralPath $backupData) {
            Move-Item -LiteralPath $backupData -Destination $liveData
        }
        throw
    }
    Move-Item -LiteralPath $stagedHistory -Destination (Join-Path $exports 'vod_stream_query_events.csv') -Force
    Move-Item -LiteralPath $stagedDashboard -Destination (Join-Path $exports 'vod_stream_query_analysis_dashboard.html') -Force
    Move-Item -LiteralPath $stagedWorkbook -Destination (Join-Path $exports 'Davis_Cup_Performance.xlsx') -Force
    if (Test-Path -LiteralPath $backupData) {
        Remove-Item -LiteralPath $backupData -Recurse -Force
    }
    Write-Host "VOD dashboard rebuilt from $($StartDate.ToString('yyyy-MM-dd')) through $($EndDate.ToString('yyyy-MM-dd'))."
}
finally {
    foreach ($path in @($stagedHistory, $stagedDashboard, $stagedWorkbook)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    foreach ($path in @($stagedData, $backupData)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}
