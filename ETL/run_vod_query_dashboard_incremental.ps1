param(
    [Nullable[datetime]]$Date = $null,
    [string]$LakeRoot = 'Z:\Veto Logs Backup\DO NOT DELETE\source=stream',
    [string]$FallbackLakeRoot = (Join-Path $PSScriptRoot 'data\lake\source=stream'),
    [string]$Python = (Join-Path $PSScriptRoot '..\venv\Scripts\python.exe'),
    [string]$PipelineState = (Join-Path $PSScriptRoot 'output\state\pipeline_last_run.json'),
    [string]$DailyStateDir = (Join-Path $PSScriptRoot 'output\state\daily_runs'),
    [string]$IncidentStateDir = (Join-Path $PSScriptRoot 'output\state\cdn_incident_closeout'),
    [string]$ExportsDir = (Join-Path $PSScriptRoot 'output\exports'),
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
$exports = $ExportsDir
$dashboard = Join-Path $exports 'vod_stream_query_analysis_dashboard.html'
$dataDir = Join-Path $exports 'vod_stream_query_analysis_dashboard_data'
$davisWorkbook = Join-Path $exports 'Davis_Cup_Performance.xlsx'
$extractor = Join-Path $PSScriptRoot 'src\tools\export_vod_query_events.py'
$builder = Join-Path $PSScriptRoot 'src\tools\build_vod_query_dashboard.py'
$stagedFiles = [System.Collections.Generic.List[string]]::new()

function Get-LatestDashboardDate {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $dashboard -PathType Leaf)) {
        throw "Dashboard HTML is missing: $dashboard. Run rebuild_vod_query_dashboard_range.ps1 once."
    }
    $html = Get-Content -LiteralPath $dashboard -Raw
    $indexMatch = [regex]::Match($html, '(?m)^const dashboardIndex=(.+);\r?$')
    if (-not $indexMatch.Success) {
        throw 'Published dashboard date index could not be read. Dashboard was not changed.'
    }
    $publishedDates = ($indexMatch.Groups[1].Value | ConvertFrom-Json).dates
    $dates = Get-ChildItem -LiteralPath $Path -File -Filter '*.js' |
        Where-Object { $_.BaseName -match '^\d{4}-\d{2}-\d{2}$' -and $_.BaseName -in $publishedDates } |
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

    $completedDates = [System.Collections.Generic.List[datetime]]::new()
    if (Test-Path -LiteralPath $DailyStateDir -PathType Container) {
        foreach ($file in (Get-ChildItem -LiteralPath $DailyStateDir -File -Filter '*.json')) {
            $checkpoint = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
            if ($checkpoint.status -eq 'complete' -and $checkpoint.validation_status -in @('PASS', 'REVIEW') -and
                $checkpoint.date -eq $file.BaseName -and $file.BaseName -match '^\d{4}-\d{2}-\d{2}$') {
                $completedDates.Add([datetime]::ParseExact($file.BaseName, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture))
            }
        }
    }
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $state = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        if ($state.status -in @('complete', 'complete_with_warnings') -and $state.target_date -match '^\d{4}-\d{2}-\d{2}$') {
            $completedDates.Add([datetime]::ParseExact($state.target_date, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture))
        }
    }
    if (-not $completedDates.Count) {
        throw 'No completed ETL date found in pipeline state or daily checkpoints. Dashboard was not changed.'
    }
    return ($completedDates | Sort-Object -Descending | Select-Object -First 1).Date
}

function Assert-CompletedDay {
    param([datetime]$TargetDate)
    $key = $TargetDate.ToString('yyyy-MM-dd')
    $path = Join-Path $DailyStateDir "$key.json"
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $checkpoint = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($checkpoint.date -eq $key -and $checkpoint.status -eq 'complete' -and
            $checkpoint.validation_status -in @('PASS', 'REVIEW')) {
            return
        }
    }
    if (Test-Path -LiteralPath $PipelineState -PathType Leaf) {
        $state = Get-Content -LiteralPath $PipelineState -Raw | ConvertFrom-Json
        if ($state.target_date -eq $key -and $state.status -in @('complete', 'complete_with_warnings')) {
            return
        }
    }
    throw "No completed ETL evidence for $key. Dashboard was not refreshed beyond this date."
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

function Test-ApprovedGap {
    param([datetime]$TargetDate)
    $key = $TargetDate.ToString('yyyy-MM-dd')
    $receiptPath = Join-Path $IncidentStateDir "$key.json"
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) { return $false }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if ($receipt.date -ne $key -or $receipt.status -ne 'processed_with_confirmed_source_gap' -or
        $receipt.full_day_complete -ne $false -or $receipt.dashboard_eligible -ne $false) {
        throw "Invalid source-gap receipt for $key; refusing to skip it."
    }
    $approval = Get-Content -LiteralPath $receipt.approval -Raw | ConvertFrom-Json
    if ($approval.kind -ne 'operator_confirmed_cdn_loss' -or $key -notin $approval.dates -or
        'stream' -notin $approval.sources -or $approval.dashboard_policy -ne 'exclude_partial_days' -or
        -not $approval.reason -or -not $approval.confirmed_at) {
        throw "Unapproved source gap for $key."
    }
    return $true
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python was not found at $Python. Expected the workspace environment at ..\venv\Scripts\python.exe."
}
if (-not (Test-Path -LiteralPath $dataDir -PathType Container)) {
    throw "Dashboard lazy data is missing: $dataDir. Run rebuild_vod_query_dashboard_range.ps1 once to bootstrap it."
}

$dashboardDate = Get-LatestDashboardDate -Path $dataDir
$completedDate = Get-CompletedEtlDate -Path $PipelineState
$etlDate = if ($PSBoundParameters.ContainsKey('Date')) {
    $Date.Date
}
else {
    $completedDate
}

if ($etlDate -gt $completedDate) {
    throw "Requested date exceeds completed ETL date $($completedDate.ToString('yyyy-MM-dd'))."
}

if ($etlDate -gt (Get-Date).Date.AddDays(-1)) {
    throw "Refusing to publish incomplete/current date $($etlDate.ToString('yyyy-MM-dd'))."
}
$refreshDates = [System.Collections.Generic.List[datetime]]::new()
$excludedDates = [System.Collections.Generic.List[string]]::new()
if (Test-Path -LiteralPath $IncidentStateDir) {
    foreach ($receipt in (Get-ChildItem -LiteralPath $IncidentStateDir -Filter '*.json' -File)) {
        if ($receipt.BaseName -notmatch '^\d{4}-\d{2}-\d{2}$') { continue }
        $incidentDay = [datetime]::ParseExact($receipt.BaseName, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
        if ($incidentDay -le $etlDate -and (Test-ApprovedGap -TargetDate $incidentDay)) {
            $excludedDates.Add($receipt.BaseName)
        }
    }
}
$publishedHtml = Get-Content -LiteralPath $dashboard -Raw
$publishedIndex = ([regex]::Match($publishedHtml, '(?m)^const dashboardIndex=(.+);\r?$').Groups[1].Value | ConvertFrom-Json)
# Backfill approved source-gap days even when later dates are already published.
foreach ($gap in $excludedDates) {
    if ($gap -notin $publishedIndex.dates) {
        $refreshDates.Add([datetime]::ParseExact($gap, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture))
    }
}
for ($day = $dashboardDate.AddDays(1); $day -le $etlDate; $day = $day.AddDays(1)) {
    if ($day.ToString('yyyy-MM-dd') -in $excludedDates) {
        Write-Host "Including available data for approved CDN-gap day $($day.ToString('yyyy-MM-dd')); missing hours are not zero traffic."
        continue
    }
    Assert-CompletedDay -TargetDate $day
    $refreshDates.Add($day)
}
$refreshDates = @($refreshDates | Sort-Object -Unique)
$dateLabels = ($refreshDates | ForEach-Object { $_.ToString('yyyy-MM-dd') }) -join ', '
Write-Host "Dashboard through $($dashboardDate.ToString('yyyy-MM-dd')); completed ETL through $($etlDate.ToString('yyyy-MM-dd'))."
Write-Host "Dates to append: $dateLabels"
if ($PlanOnly) {
    exit 0
}

function Publish-DailyCsv {
    param([string]$Csv)
    $gapArgs = @()
    foreach ($excluded in $excludedDates) { $gapArgs += @('--partial-date', $excluded) }
    & $Python $builder --out $dashboard --davis-xlsx $davisWorkbook --data-dir $dataDir `
        --data-url 'vod_stream_query_analysis_dashboard_data' --incremental --append $Csv @gapArgs
    if ($LASTEXITCODE -ne 0) {
        throw "VOD dashboard refresh failed for $Csv. Completed daily extracts were retained for retry."
    }
}

try {
    foreach ($day in $refreshDates) {
        $dateKey = $day.ToString('yyyy-MM-dd')
        $dailyCsv = Join-Path $exports "vod_stream_query_events_$dateKey.csv"
        if (Test-Path -LiteralPath $dailyCsv -PathType Leaf) {
            Write-Host "Reusing daily extract: $dailyCsv"
            Publish-DailyCsv -Csv $dailyCsv
            continue
        }

        $rawPath = Find-StreamPartition -TargetDate $day
        if ($null -eq $rawPath) {
            throw "Raw STREAM partition not found for $dateKey in archive or fallback lake. Dashboard was not refreshed."
        }
        $stagedCsv = Join-Path $exports ".vod_stream_query_events_$dateKey.$([guid]::NewGuid().ToString('N')).tmp.csv"
        $stagedFiles.Add($stagedCsv)
        Write-Host "Extracting VOD activity for $dateKey from $rawPath"
        & $Python $extractor --input $rawPath --date $dateKey --out $stagedCsv --compact
        if ($LASTEXITCODE -ne 0) {
            throw "VOD event extraction failed for $dateKey."
        }
        Move-Item -LiteralPath $stagedCsv -Destination $dailyCsv -Force
        Publish-DailyCsv -Csv $dailyCsv
        Write-Host "Published VOD dashboard through $dateKey."
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
