param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$base = [IO.Path]::GetFullPath($PSScriptRoot)
$temp = Join-Path $base 'output\temp'
$work = Join-Path $temp 'asrun_priority_20261012_1700'
$stream = Join-Path $temp 'stream_lake_priority_20261012_1600'
$archive = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE'
$retained = Join-Path $archive 'Temp\VetoETL\retained_intermediates\cleanup_20261014'
$journal = Join-Path $temp 'verified_cleanup_20261014.jsonl'
$verifiedDestinations = @{}

function Assert-Within([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path)
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $full.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path outside allowed root: $full"
    }
    $cursor = $full
    while ($cursor.Length -ge $rootFull.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing reparse point: $cursor"
            }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}

function Record($Value) {
    $line = $Value | ConvertTo-Json -Compress -Depth 5
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            Add-Content -LiteralPath $journal -Value $line -Encoding UTF8
            return
        } catch [IO.IOException] {
            if ($attempt -eq 19) { throw }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Get-BufferedHash([string]$Path) {
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::Read, 4MB, [IO.FileOptions]::SequentialScan)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '')
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Preserve-And-Remove([string]$Source, [string]$Destination, [string]$ExpectedHash, [switch]$Copy) {
    $sourcePath = Assert-Within $Source $temp
    $destinationRoot = if ($Copy -or $ExpectedHash) { $archive } else { Join-Path $base 'asrun_demo\output' }
    $destinationPath = Assert-Within $Destination $destinationRoot
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { return }
    if (-not $Apply) { Write-Output "PLAN $sourcePath -> $destinationPath"; return }
    $before = Get-Item -LiteralPath $sourcePath
    $size = $before.Length
    $ticks = $before.LastWriteTimeUtc.Ticks
    Write-Output "VERIFY $sourcePath ($size bytes)"
    if ($Copy -and -not (Test-Path -LiteralPath $destinationPath)) {
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destinationPath)) -Force | Out-Null
        $partial = $destinationPath + '.copying'
        if (Test-Path -LiteralPath $partial) { throw "Review unfinished copy: $partial" }
        Copy-Item -LiteralPath $sourcePath -Destination $partial
        if ((Get-BufferedHash $sourcePath) -ne
            (Get-BufferedHash $partial)) { throw "Copy mismatch: $sourcePath" }
        Move-Item -LiteralPath $partial -Destination $destinationPath
    }
    $saved = Get-Item -LiteralPath $destinationPath
    if ($size -ne $saved.Length) { throw "Size mismatch: $sourcePath" }
    $sourceHash = Get-BufferedHash $sourcePath
    $key = "$destinationPath|$($saved.Length)|$($saved.LastWriteTimeUtc.Ticks)"
    if (-not $verifiedDestinations.ContainsKey($key)) {
        $verifiedDestinations[$key] = Get-BufferedHash $destinationPath
    }
    if ($sourceHash -ne $verifiedDestinations[$key] -or ($ExpectedHash -and $sourceHash -ne $ExpectedHash)) {
        throw "SHA256 mismatch: $sourcePath"
    }
    $after = Get-Item -LiteralPath $sourcePath
    if ($after.Length -ne $size -or $after.LastWriteTimeUtc.Ticks -ne $ticks) { throw "Source changed: $sourcePath" }
    Record @{status='verified'; source=$sourcePath; retained=$destinationPath; bytes=$size; sha256=$sourceHash; at=(Get-Date).ToString('o')}
    Remove-Item -LiteralPath $sourcePath
    Record @{status='removed_local_copy'; source=$sourcePath; retained=$destinationPath; bytes=$size; at=(Get-Date).ToString('o')}
    Write-Output "REMOVED VERIFIED COPY: $sourcePath"
}

if ((Get-Content -LiteralPath (Join-Path $work 'asrun_state.json') -Raw | ConvertFrom-Json).status -ne 'complete') {
    throw 'ASRUN is not complete'
}

# The staged dashboard must exactly match the published copy before removal.
$staged = Join-Path $work 'dashboard'
foreach ($file in Get-ChildItem -LiteralPath $staged -File -Recurse) {
    $relative = $file.FullName.Substring($staged.Length + 1)
    Preserve-And-Remove $file.FullName (Join-Path (Join-Path $base 'asrun_demo\output') $relative) ''
}

# Keep rollback content off D:, not discarded.
$previous = Join-Path $work 'previous_dashboard'
foreach ($file in Get-ChildItem -LiteralPath $previous -File -Recurse) {
    $relative = $file.FullName.Substring($previous.Length + 1)
    Preserve-And-Remove $file.FullName (Join-Path $retained "previous_dashboard\$relative") '' -Copy
}

$receipts = @{}
foreach ($statePath in @((Join-Path $work 'fast_archive_state.json'), (Join-Path $stream 'priority_state.json'))) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.status -ne 'complete') { throw "Incomplete archive: $statePath" }
    foreach ($file in $state.files) { $receipts[$file.destination] = $file.verification.sha256 }
}
$roots = @((Join-Path $work 'combined_lake'))
foreach ($root in @($work, $stream)) {
    foreach ($date in @('2026-10-10', '2026-10-11')) { $roots += Join-Path $root "$date\lake" }
}
foreach ($root in $roots) {
    foreach ($file in Get-ChildItem -LiteralPath $root -Filter '*.parquet' -File -Recurse) {
        $relative = $file.FullName.Substring($root.Length + 1)
        $destination = Join-Path $archive $relative
        if (-not $receipts.ContainsKey($destination)) {
            Write-Output "KEEP (no archive receipt): $($file.FullName)"
            continue
        }
        Preserve-And-Remove $file.FullName $destination $receipts[$destination]
    }
}
Write-Output 'Complete. Canonical data, final-clean, spill partitions, parsed caches, receipts and live output retained.'
