[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'output'))
$destination = Join-Path $root 'delete_mefolder'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$cutoff = (Get-Date).ToUniversalTime().AddHours(-1)
$processes = @(Get-CimInstance Win32_Process)
$testRunning = @($processes | Where-Object { $_.CommandLine -match '\bpytest\b' }).Count -gt 0

function Assert-Scoped([string]$Path, [string]$Parent) {
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
    if (-not $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside approved directory: $full" }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing reparse point: $cursor"
            }
        }
        $cursor = Split-Path $cursor -Parent
    }
}

function Inventory([string]$Path) {
    $queue = [Collections.Generic.Queue[string]]::new()
    $queue.Enqueue($Path)
    $bytes = 0L
    $count = 0L
    $latest = [datetime]::MinValue
    while ($queue.Count -gt 0) {
        foreach ($entry in [IO.Directory]::EnumerateFileSystemEntries($queue.Dequeue())) {
            $item = Get-Item -LiteralPath $entry -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Contains link: $entry" }
            if ($item.Name -eq '.git') { throw "Contains Git checkout; preserve: $entry" }
            if ($item.LastWriteTimeUtc -gt $latest) { $latest = $item.LastWriteTimeUtc }
            if ($item.PSIsContainer) { $queue.Enqueue($entry) }
            else { $count++; $bytes += $item.Length }
        }
    }
    return @{bytes=$bytes; files=$count; latest=$latest}
}

$candidates = @()
$candidates += Get-ChildItem -LiteralPath $root -Directory | Where-Object { $_.Name -like 'pytest*' } | ForEach-Object { $_.Name }
$candidates += @('test-tmp', 'test_tmp',
    'temp/asrun_identity_chunk_test', 'temp/concurrency_memory_test',
    'temp/login_boot_20261007', 'temp/revenuelive-live-review-browser',
    'temp/revenuelive-preview-ui-check', 'temp/revenuelive_login_20261006',
    'diagnostics/crash_dumps_20261014')
$results = [Collections.Generic.List[object]]::new()
if ($Apply) {
    Assert-Scoped $destination $root
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
}
$journal = Join-Path $destination "moves_$stamp.jsonl"
foreach ($relative in $candidates) {
    $source = [IO.Path]::GetFullPath((Join-Path $root $relative))
    $target = [IO.Path]::GetFullPath((Join-Path $destination $relative))
    $record = [ordered]@{source=$source; destination=$target; status='checking'; bytes=0; files=0}
    try {
        Assert-Scoped $source $root
        Assert-Scoped $target $destination
        if (-not (Test-Path -LiteralPath $source -PathType Container)) { continue }
        if (Test-Path -LiteralPath $target) { throw 'Destination already exists; no overwrite permitted' }
        if ($testRunning -and $relative -notlike 'diagnostics/*') { throw 'Tests are running; preserve test artifacts' }
        $freshProcesses = @(Get-CimInstance Win32_Process)
        if (@($freshProcesses | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($source, [StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count) {
            throw 'Referenced by an active process'
        }
        $inventory = Inventory $source
        if ($inventory.latest -gt $cutoff) { throw 'Recently modified; preserve until idle' }
        $record.bytes = $inventory.bytes
        $record.files = $inventory.files
        $record.status = 'planned'
        Write-Output ("{0}: {1:N3} GiB, {2} files" -f $relative, ($record.bytes/1GB), $record.files)
        if ($Apply) {
            $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $journal -Encoding UTF8
            New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
            Assert-Scoped $source $root
            Assert-Scoped $target $destination
            Move-Item -LiteralPath $source -Destination $target
            if ((Test-Path -LiteralPath $source) -or -not (Test-Path -LiteralPath $target)) { throw 'Move verification failed' }
            $after = Inventory $target
            if ($after.files -ne $record.files -or $after.bytes -ne $record.bytes) { throw 'Post-move inventory mismatch; review retained destination' }
            $record.status = 'moved'
        }
    } catch {
        $record.status = 'needs-review'
        $record['reason'] = $_.Exception.Message
        Write-Output "PRESERVED / REVIEW: $relative : $($_.Exception.Message)"
    }
    $results.Add([PSCustomObject]$record)
    if ($Apply) { $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $journal -Encoding UTF8 }
}
if ($Apply) {
    $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $destination "inventory_$stamp.json") -Encoding UTF8
}
$selected = @($results | Where-Object { $_.status -in @('planned','moved') })
Write-Output ("SUMMARY: {0} folders, {1:N3} GiB; apply={2}. No files deleted." -f $selected.Count,(($selected | Measure-Object bytes -Sum).Sum/1GB),$Apply)
