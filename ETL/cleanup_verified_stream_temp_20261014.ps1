[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'output/temp/stream_lake_priority_20261012_1600'))
$archive = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE'
$audit = Join-Path $PSScriptRoot 'output/validation/stream_temp_retirement_20261014'
$relativeFiles = @(
    '2026-10-10/lake/source=stream/year=2026/month=10/day=10/part_stream_2026_10_10_0.parquet',
    '2026-10-10/lake/source=stream/year=2026/month=10/day=11/part_stream_2026_10_10_0.parquet',
    '2026-10-11/lake/source=stream/year=2026/month=10/day=11/part_stream_2026_10_11_0.parquet'
)

function Assert-Path([string]$Path, [string]$AllowedRoot) {
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    if (-not $full.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path outside approved scope: $full"
    }
    $cursor = $full
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $cursor" }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Assert-NoConsumer {
    $consumers = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -and (
            $_.CommandLine.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $_.CommandLine -match 'priority_stream_lake\.py|cleanup_verified_backlog_stage\.py'
        )
    })
    if ($consumers.Count) { throw "A process still references the temporary STREAM lake: $($consumers.ProcessId -join ', ')" }
}

$state = Get-Content -LiteralPath (Join-Path $root 'priority_state.json') -Raw | ConvertFrom-Json
if ($state.status -ne 'complete') { throw 'Priority STREAM publication is not complete.' }
Assert-NoConsumer
$plan = @()
foreach ($relative in $relativeFiles) {
    $source = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not (Test-Path -LiteralPath $source)) { Write-Output "Already absent: $source"; continue }
    $destination = [IO.Path]::GetFullPath((Join-Path $archive ($relative -split '/lake/', 2)[1]))
    Assert-Path $source $root
    Assert-Path $destination $archive
    $records = @($state.files | Where-Object { $_.source -eq $source -and $_.destination -eq $destination })
    if ($records.Count -ne 1 -or $records[0].verification.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Missing historical verification: $source"
    }
    $local = Get-Item -LiteralPath $source
    $remote = Get-Item -LiteralPath $destination
    if ($local.Length -ne $remote.Length -or $local.Length -ne $records[0].verification.metadata.bytes) {
        throw "Size mismatch; preserving source: $source"
    }
    $plan += [pscustomobject]@{
        source=$source; destination=$destination; bytes=$local.Length
        source_ticks=$local.LastWriteTimeUtc.Ticks; archive_ticks=$remote.LastWriteTimeUtc.Ticks
        expected_sha256=$records[0].verification.sha256; status='planned'
    }
}
$plan | Select-Object source,bytes,status | Format-Table -AutoSize
if (-not $Apply) { Write-Output 'Dry run only; use -Apply for fresh hash verification and deletion.'; exit 0 }
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $audit 'cleanup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$report = Join-Path $audit ('cleanup_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
function Save-Report { ConvertTo-Json -InputObject @($plan) -Depth 5 | Set-Content -LiteralPath $report -Encoding UTF8 }
try {
    Save-Report
    # Verify every pair before deleting any file. Keep the originals if one fails.
    foreach ($item in $plan) {
        Write-Output "Hashing local: $($item.source)"
        $localHash = (Get-FileHash -LiteralPath $item.source -Algorithm SHA256).Hash
        Write-Output "Hashing archive: $($item.destination)"
        $archiveHash = (Get-FileHash -LiteralPath $item.destination -Algorithm SHA256).Hash
        if ($localHash -ne $archiveHash -or $localHash -ne $item.expected_sha256) {
            throw "SHA-256 mismatch; no files deleted: $($item.source)"
        }
        $item.status = 'hash_verified'
        Save-Report
        Write-Output "Verified: $($item.bytes) bytes"
    }
    Assert-NoConsumer
    foreach ($item in $plan) {
        Assert-Path $item.source $root
        Assert-Path $item.destination $archive
        $local = Get-Item -LiteralPath $item.source
        $remote = Get-Item -LiteralPath $item.destination
        if ($local.Length -ne $item.bytes -or $remote.Length -ne $item.bytes -or
            $local.LastWriteTimeUtc.Ticks -ne $item.source_ticks -or $remote.LastWriteTimeUtc.Ticks -ne $item.archive_ticks) {
            throw 'A verified file changed; stopping cleanup.'
        }
        Remove-Item -LiteralPath $item.source -Force
        $item.status = 'deleted_local_archive_retained'
        Save-Report
        Write-Output "Removed local copy: $($item.source)"
    }
    Write-Output ('COMPLETE: reclaimed file bytes=' + ($plan | Measure-Object bytes -Sum).Sum)
    Write-Output "Audit: $report"
} finally {
    $lock.Dispose()
}
