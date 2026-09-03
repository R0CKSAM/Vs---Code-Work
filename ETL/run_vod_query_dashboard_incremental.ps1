param(
    [Nullable[datetime]]$Date = $null,
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$FallbackLakeRoot = (Join-Path $PSScriptRoot 'data\lake\source=stream'),
    [string]$Python = (Join-Path $PSScriptRoot '..\venv\Scripts\python.exe'),
    [string]$PipelineState = (Join-Path $PSScriptRoot 'output\state\pipeline_last_run.json'),
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
$exports = Join-Path $PSScriptRoot 'output\exports'
$dashboard = Join-Path $exports 'vod_stream_query_analysis_dashboard.html'
$dataDir = Join-Path $exports 'vod_stream_query_analysis_dashboard_data'
$davisWorkbook = Join-Path $exports 'Davis_Cup_Performance.xlsx'
$extractor = Join-Path $PSScriptRoot 'src\tools\export_vod_query_events.py'
$builder = Join-Path $PSScriptRoot 'src\tools\build_vod_query_dashboard.py'
$stagedFiles = [System.Collections.Generic.List[string]]::new()
$appendFiles = [System.Collections.Generic.List[string]]::new()
$dailyDestinations = @{}

function Get-LatestDashboardDate {
    param([string]$Path)

    $dates = Get-ChildItem -LiteralPath $Path -File -Filter '*.js' |
        Where-Object { $_.BaseName -match '^\d{4}-\d{2}-\d{2}$' } |
        ForEach-Object {
            [datetime]::ParseExact(
                $_.BaseName,
                'yyyy-MM-dd',
                [System.Globalization.CultureInfo]::InvariantCulture
            )
        }
    if (-not $dates) {
        throw "No dated dashboard payloads were found in $Path. Run rebuild_vod_query_dashboard_range.ps1 once."
    }
    return ($dates | Sort-Object -Descending | Select-Object -First 1).Date
}

function Get-CompletedEtlDate {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "ETL completion state was not found: $Path"
    }
    $state = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($state.status -notin @('complete', 'complete_with_warnings')) {
        throw "Latest ETL is not complete (status: $($state.status)). Dashboard was not changed."
    }
    if ([string]::IsNullOrWhiteSpace([string]$state.target_date)) {
        throw "ETL completion state has no target_date: $Path"
    }
    try {
        return [datetime]::ParseExact(
            [string]$state.target_date,
            'yyyy-MM-dd',
            [System.Globalization.CultureInfo]::InvariantCulture
        ).Date
    }
    catch {
        throw "Invalid ETL target_date '$($state.target_date)' in $Path"
    }
}

function Find-StreamPartition {
    param([datetime]$TargetDate)

    $relativePartition = 'year={0}\month={1}\day={2}' -f `
        $TargetDate.ToString('yyyy'), $TargetDate.ToString('MM'), $TargetDate.ToString('dd')
    foreach ($root in @($LakeRoot, $FallbackLakeRoot)) {
        if ([string]::IsNullOrWhiteSpace($root)) {
            continue
        }
        $candidate = Join-Path $root $relativePartition
        if ((Test-Path -LiteralPath $candidate -PathType Container) -and
            (Get-ChildItem -LiteralPath $candidate -File -Filter 'part_*.parquet' | Select-Object -First 1)) {
            return $candidate
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python was not found at $Python. Expected the workspace environment at ..\venv\Scripts\python.exe."
}
if (-not (Test-Path -LiteralPath $dataDir -PathType Container)) {
    throw "Dashboard lazy data is missing: $dataDir. Run rebuild_vod_query_dashboard_range.ps1 once to bootstrap it."
}

$dashboardDate = Get-LatestDashboardDate -Path $dataDir
$etlDate = if ($PSBoundParameters.ContainsKey('Date')) {
    $Date.Date
}
else {
    Get-CompletedEtlDate -Path $PipelineState
}

if ($etlDate -gt (Get-Date).Date.AddDays(-1)) {
    throw "Refusing to publish incomplete/current date $($etlDate.ToString('yyyy-MM-dd'))."
}
if ($dashboardDate -ge $etlDate) {
    Write-Host "VOD dashboard is already current through $($dashboardDate.ToString('yyyy-MM-dd')); completed ETL date is $($etlDate.ToString('yyyy-MM-dd'))."
    exit 0
}

$refreshDates = [System.Collections.Generic.List[datetime]]::new()
for ($day = $dashboardDate.AddDays(1); $day -le $etlDate; $day = $day.AddDays(1)) {
    $refreshDates.Add($day)
}
$dateLabels = ($refreshDates | ForEach-Object { $_.ToString('yyyy-MM-dd') }) -join ', '
Write-Host "Dashboard through $($dashboardDate.ToString('yyyy-MM-dd')); completed ETL through $($etlDate.ToString('yyyy-MM-dd'))."
Write-Host "Dates to append: $dateLabels"
if ($PlanOnly) {
    exit 0
}

try {
    foreach ($day in $refreshDates) {
        $dateKey = $day.ToString('yyyy-MM-dd')
        $dailyCsv = Join-Path $exports "vod_stream_query_events_$dateKey.csv"
        if (Test-Path -LiteralPath $dailyCsv -PathType Leaf) {
            Write-Host "Reusing daily extract: $dailyCsv"
            $appendFiles.Add($dailyCsv)
            continue
        }

        $rawPath = Find-StreamPartition -TargetDate $day
        if ($null -eq $rawPath) {
            throw "Raw STREAM partition not found for $dateKey in archive or fallback lake. Dashboard was not refreshed."
        }
        $stagedCsv = Join-Path $exports ".vod_stream_query_events_$dateKey.$([guid]::NewGuid().ToString('N')).tmp.csv"
        Write-Host "Extracting VOD activity for $dateKey from $rawPath"
        & $Python $extractor --input $rawPath --date $dateKey --out $stagedCsv --compact
        if ($LASTEXITCODE -ne 0) {
            throw "VOD event extraction failed for $dateKey."
        }
        $stagedFiles.Add($stagedCsv)
        $appendFiles.Add($stagedCsv)
        $dailyDestinations[$stagedCsv] = $dailyCsv
    }

    $builderArgs = @(
        $builder,
        '--out', $dashboard,
        '--davis-xlsx', $davisWorkbook,
        '--data-dir', $dataDir,
        '--data-url', 'vod_stream_query_analysis_dashboard_data',
        '--incremental'
    )
    foreach ($appendFile in $appendFiles) {
        $builderArgs += @('--append', $appendFile)
    }
    & $Python @builderArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'VOD dashboard refresh failed.'
    }

    foreach ($stagedCsv in $stagedFiles) {
        Move-Item -LiteralPath $stagedCsv -Destination $dailyDestinations[$stagedCsv] -Force
    }
    Write-Host "VOD dashboard is now current through $($etlDate.ToString('yyyy-MM-dd')): $dashboard"
}
finally {
    foreach ($stagedCsv in $stagedFiles) {
        if (Test-Path -LiteralPath $stagedCsv) {
            Remove-Item -LiteralPath $stagedCsv -Force
        }
    }
}
