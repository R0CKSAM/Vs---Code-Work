[CmdletBinding()]
param(
    [datetime]$StartDate = '2026-10-30',
    [datetime]$ThroughDate = '2026-11-01',
    [switch]$SkipOctober31,
    [switch]$VerifiedFirst
)
$ErrorActionPreference = 'Stop'
$archiveRoot = 'Z:\Veto Logs Backup\DO NOT DELETE'
$workingRoot = Join-Path $archiveRoot 'Temp\VetoETL\data'
$env:VG_ETL_LAKE_ROOT = $archiveRoot
New-Item -ItemType Directory -Path $workingRoot -Force | Out-Null
if ($StartDate -gt $ThroughDate -or $ThroughDate.Date -ge (Get-Date).Date) {
    throw 'Lake priority requires an ordered range of completed dates.'
}
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'venv\Scripts\python.exe'
$statePath = Join-Path $PSScriptRoot 'output\state\lake_priority_progress.json'
$hold = Join-Path $PSScriptRoot 'output\state\lake_priority_hold.json'
if (-not (Test-Path -LiteralPath $hold)) { throw 'An explicit lake-priority hold is required.' }
$state = @{ status='running'; through=$ThroughDate.ToString('yyyy-MM-dd'); completed_dates=@(); current_date=$null }
function Save-Progress {
    $state['updated_at'] = (Get-Date).ToString('o')
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$statePath.tmp" -Encoding UTF8
    Move-Item -LiteralPath "$statePath.tmp" -Destination $statePath -Force
}
try {
    $dates = @()
    for ($candidate=$StartDate.Date; $candidate -le $ThroughDate.Date; $candidate=$candidate.AddDays(1)) { $dates += $candidate }
    if ($VerifiedFirst) { $dates = @($dates | Sort-Object @{Expression={ if ($_.ToString('yyyy-MM-dd') -eq '2026-11-01') { 0 } else { 1 } }}, @{Expression={$_}}) }
    foreach ($day in $dates) {
        if ($SkipOctober31 -and $day.ToString('yyyy-MM-dd') -eq '2026-10-31') { continue }
        $state['current_date']=$day.ToString('yyyy-MM-dd')
        Save-Progress
        if ($SkipOctober31 -and $day.ToString('yyyy-MM-dd') -eq '2026-11-01') {
            $state['stage']='building_required_spillover'
            Save-Progress
            & $python (Join-Path $PSScriptRoot 'src\tools\build_nov1_spillover.py')
            if ($LASTEXITCODE -ne 0) { throw 'Required November 1 spillover build failed.' }
        }
        $state['stage']='daily_lake'
        Save-Progress
        & $python (Join-Path $PSScriptRoot 'src\tools\recovery_capacity_guard.py') --data $workingRoot --archive $archiveRoot --data-reserve-gib 20
        if ($LASTEXITCODE -ne 0) { throw 'Insufficient storage reserve for the next lake date.' }
        & (Join-Path $PSScriptRoot 'run_daily_pipeline.ps1') -Date $day -LakeOnly -StrictPipeline -SkipPostVerifyDelay -LocalRoot $workingRoot -RawRoot (Join-Path $PSScriptRoot 'data\raw\Veto Logs Backup') -OverviewLakeRoot $archiveRoot -SkipLakeArchive
        if ($LASTEXITCODE -ne 0) { throw "Lake-only pipeline failed for $day" }
        $run = Get-Content (Join-Path $PSScriptRoot 'output\state\lake_priority_last_run.json') -Raw | ConvertFrom-Json
        $validation = @($run.steps | Where-Object { $_.step -eq 'daily_delivery_structural_validation' -and $_.status -eq 'ok' })
        if ($run.target_date -ne $state.current_date -or $run.status -ne 'complete' -or $validation.Count -ne 1) {
            throw 'Lake completion lacks successful structural validation.'
        }
        $state['completed_dates'] += $state.current_date
        Save-Progress
    }
    $state['status']='complete'
    $state['current_date']=$null
} catch {
    $state['status']='failed'
    $state['error']=$_.Exception.Message
    throw
} finally { Save-Progress }
