[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dates = @('2026-10-09', '2026-10-10', '2026-10-11', '2026-10-12')
$audit = Join-Path $root 'output/validation/raw_retirement_20261014'
$rawRoot = Join-Path $root 'data/raw/Veto Logs Backup'
$stageRoot = Join-Path $root 'data/stage'
$python = Join-Path (Split-Path $root) 'venv/Scripts/python.exe'
New-Item -ItemType Directory -Path $audit -Force | Out-Null
trap {
    $message = $_.Exception.Message
    Write-Output "CLEANUP FAILED: $message"
    & $python (Join-Path $root 'src/runtime/etl_notifications.py') --step 'Oct 9-12 raw cleanup' --error $message --log-path (Join-Path $audit 'cleanup.out.log')
    exit 1
}
$cleanupLock = [IO.File]::Open((Join-Path $audit 'retirement.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$repair = Get-Content (Join-Path $root 'output/temp/backlog_repair_20261014/state.json') -Raw | ConvertFrom-Json
foreach ($day in @('2026-10-09','2026-10-10','2026-10-12')) {
    if (-not @($repair.completed | Where-Object { $_.date -eq $day -and $_.reconciled_ts_rows -gt 0 }).Count) {
        throw "Required downstream repair has not been validated: $day"
    }
}

function Assert-ScopedPath([string]$Path, [string]$AllowedRoot) {
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    if (-not $full.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Cleanup path outside approved root: $full"
    }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $cursor" }
        }
        $cursor = Split-Path $cursor -Parent
    }
}

# Stage retirement receipts preserve the reconciled counts for priority batches
# that were imported through a separate ETL state file.
$evidence = Get-Content (Join-Path $root 'data/.etl_03_state.json') -Raw | ConvertFrom-Json
foreach ($day in $dates) {
    $receipt = Join-Path $root "output/validation/stage_retirement_20261014/$day.json"
    if (Test-Path -LiteralPath $receipt) {
        $retired = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
        if ($retired.status -ne 'complete') { throw "Incomplete stage retirement: $day" }
        foreach ($check in $retired.checks) {
            $key = "$($check.source)_$($day.Replace('-', '_'))_final_clean.parquet"
            $evidence | Add-Member -Force -NotePropertyName $key -NotePropertyValue @{
                status = 'ok'; source_key = $check.source; rows = $check.rows
            }
        }
    }
}
$evidencePath = Join-Path $audit 'retained_row_evidence.json'
# Python expects UTF-8 without BOM for this state file.
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))

$totalBytes = 0L
$totalFiles = 0L
foreach ($day in $dates) {
    $state = Get-Content (Join-Path $root "output/state/daily_runs/$day.json") -Raw | ConvertFrom-Json
    if ($state.status -ne 'complete') { throw "Core run incomplete: $day" }
    & $python (Join-Path $root 'src/tools/cleanup_daily_intermediates.py') `
        --base (Join-Path $root 'data') --lake (Join-Path $root 'data/lake') `
        --archive-lake '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE' `
        --etl3-state $evidencePath --raw-root $rawRoot --date $day `
        --validation-report $state.validation_report --audit-dir $audit
    if ($LASTEXITCODE -ne 0) { throw "Lake validation failed: $day" }
    $planFile = Get-ChildItem -LiteralPath $audit -Filter "cleanup_${day}_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $plan = Get-Content -LiteralPath $planFile.FullName -Raw | ConvertFrom-Json
    if ($plan.status -ne 'dry-run-complete') { throw "Dry run did not complete: $day" }
    $manifestPath = Join-Path $audit ("removal_${day}_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    $manifest = @{status='verified'; date=$day; groups=$plan.groups; validation_manifest=$planFile.FullName; lake='retained'; authorization='User requested removal of Oct 9-12 raw and stage after completed repairs'}
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    foreach ($group in $plan.groups) {
        $base = if ($group.category -eq 'raw_gz') { $rawRoot } else { $stageRoot }
        Assert-ScopedPath $group.root $base
        if (-not (Test-Path -LiteralPath $group.root)) { continue }
        # Check directory links without retaining a million FileInfo objects.
        $pending = [Collections.Generic.Queue[string]]::new()
        $pending.Enqueue($group.root)
        while ($pending.Count -gt 0) {
            $directory = $pending.Dequeue()
            foreach ($child in [IO.Directory]::EnumerateDirectories($directory)) {
                Assert-ScopedPath $child $group.root
                $pending.Enqueue($child)
            }
        }
        Write-Output "$day $($group.source) $($group.category): $($group.file_count) files, $([math]::Round($group.bytes/1GB,2)) GiB; $($group.root)"
        if (-not $Apply) { continue }
        $manifest.status = 'removing'
        $manifest.current_group = $group.root
        $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
        if ($group.delete_strategy -eq 'files') {
            foreach ($file in $group.files) {
                Assert-ScopedPath $file $group.root
                Remove-Item -LiteralPath $file -Force
            }
        } else {
            # The dry run rejects non-gzip files in raw and unexpected final-clean
            # files. Delete only its exact date-scoped roots, never their parents.
            Assert-ScopedPath $group.root $base
            Remove-Item -LiteralPath $group.root -Recurse -Force
        }
        $group | Add-Member -NotePropertyName deleted -NotePropertyValue $true -Force
        $totalBytes += [long]$group.bytes
        $totalFiles += [long]$group.file_count
        $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    }
    $manifest.status = if ($Apply) { 'complete' } else { 'dry-run-complete' }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Output "$day $($manifest.status)"
}
if ($Apply) {
    $holdPath = Join-Path $root 'output/state/retention_hold.json'
    if (Test-Path -LiteralPath $holdPath) {
        $hold = Get-Content -LiteralPath $holdPath -Raw | ConvertFrom-Json
        Copy-Item -LiteralPath $holdPath -Destination (Join-Path $audit ('retention_hold_before_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json'))
        $hold.dates = @($hold.dates | Where-Object { $_ -notin $dates })
        $hold.reason = 'Oct 9-12 hold released after explicit user-approved cleanup and retained lake revalidation on 2026-10-14.'
        $hold | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $holdPath -Encoding UTF8
    }
    Write-Output "Completed: $totalFiles files, $([math]::Round($totalBytes/1GB,2)) GiB removed; lake and other dates retained."
}
