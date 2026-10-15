[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\retained_intermediates'
$archive = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE'
$audit = Join-Path $PSScriptRoot 'output\validation\nas_stage_retirement_20261014'
$plan = Get-Content -LiteralPath (Join-Path $audit 'verified_plan.json') -Raw | ConvertFrom-Json
if ($plan.status -ne 'verified' -or $plan.files.Count -ne 225) { throw 'Invalid verification plan' }
if ((Get-Content -LiteralPath (Join-Path $PSScriptRoot 'output\temp\backlog_repair_20261014\state.json') -Raw | ConvertFrom-Json).phase -ne 'complete') { throw 'Recovery not complete' }

function Assert-Path([string]$Path, [string]$Allowed) {
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Allowed).TrimEnd('\')
    if (-not $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Out of scope: $full" }
    $cursor = $full
    while ($cursor -and $cursor.Length -ge $base.Length) {
        $item = Get-Item -LiteralPath $cursor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing reparse point: $cursor" }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}

function Assert-Unchanged($File, [string]$Allowed) {
    $path = Assert-Path $File.path $Allowed
    $item = Get-Item -LiteralPath $path -Force
    $ticks = [long]([decimal]$File.mtime_ns / 100) + 621355968000000000L
    if ($item.PSIsContainer -or $item.Length -ne $File.bytes -or $item.LastWriteTimeUtc.Ticks -ne $ticks) { throw "File changed after verification: $path" }
}

function Assert-Idle {
    $busy = Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.Name -match '^python' -and
        $_.CommandLine -match 'run_pipeline\.py|priority_asrun\.py|priority_stream_lake\.py|repair_october_backlog|build_asrun_demo\.py|[\\/](001|02|03)\.py'
    }
    if ($busy) { throw 'ETL/ASRUN processing is active; no retirement allowed.' }
}

Assert-Idle
foreach ($file in $plan.lake_files) { Assert-Unchanged $file $archive }
foreach ($file in $plan.files) {
    $relative = $file.path.Substring($root.Length).TrimStart('\')
    if ($relative -notmatch '^(asrun_priority_20261012_1700|stream_lake_priority_20261012_1600)\\2026-10-(10|11)\\parquet\\part_\d{7}\.parquet$') { throw "Unexpected deletion target: $relative" }
    Assert-Unchanged $file $root
}
if (-not $Apply) { Write-Output "DRY RUN VERIFIED: $($plan.files.Count) files, $($plan.bytes) bytes"; exit 0 }
$lock = [IO.File]::Open((Join-Path $audit 'retire.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$reportPath = Join-Path $audit ('cleanup_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
$report = @{status='removing';verified_plan=(Join-Path $audit 'verified_plan.json');removed_files=@();removed_bytes=0L;lake='retained';preserved=$plan.preserved}
function Save-Report { $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8 }
try {
    Save-Report
    foreach ($file in $plan.files) {
        Assert-Idle
        foreach ($lake in $plan.lake_files) { Assert-Unchanged $lake $archive }
        Assert-Unchanged $file $root
        $report.current_file = $file.path
        Save-Report
        Remove-Item -LiteralPath $file.path -Force
        $report.removed_files += $file.path
        $report.removed_bytes += [long]$file.bytes
        Save-Report
        if ($report.removed_files.Count % 25 -eq 0) { Write-Output "Removed $($report.removed_files.Count)/225 verified stage files" }
    }
    $report.status='complete'
    Save-Report
    Write-Output "COMPLETE: $($report.removed_files.Count) files; $($report.removed_bytes) bytes; audit=$reportPath"
} catch {
    $report.status='failed'
    $report.error=$_.Exception.Message
    Save-Report
    throw
} finally { $lock.Dispose() }
