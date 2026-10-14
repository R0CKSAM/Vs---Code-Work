[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'data/raw/Veto Logs Backup/Veto Stream Backup/10/11_parquet'))
$archiveRoot = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\retained_intermediates'
$destinationRoot = Join-Path $archiveRoot 'legacy_stream_20261011_parquet'
$audit = Join-Path $PSScriptRoot 'output/validation/legacy_stream_cache_relocation_20261014'

function Assert-Scoped([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $full.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside scope: $full" }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $cursor" }
        }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Assert-Idle {
    $consumers = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -and (
            $_.CommandLine.IndexOf('11_parquet', [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $_.CommandLine -match 'priority_stream_lake\.py|[\\/]001\.py'
        )
    })
    if ($consumers.Count) { throw "Cache may be in use by PID $($consumers.ProcessId -join ',')" }
}

function Get-BufferedHash([string]$Path) {
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read, 8MB, [IO.FileOptions]::SequentialScan)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

Assert-Idle
if (-not (Test-Path -LiteralPath $archiveRoot -PathType Container)) { throw 'NAS archive unavailable.' }
$state = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'output/state/daily_runs/2026-10-11.json') -Raw | ConvertFrom-Json
if ($state.status -ne 'complete' -or $state.validation_status -ne 'PASS') { throw 'October 11 ETL not validated.' }
$files = @(Get-ChildItem -LiteralPath $sourceRoot -Force)
foreach ($file in $files) {
    if ($file.PSIsContainer -or $file.Name -notmatch '^(part_\d{7}\.parquet|conversion_errors\.csv)$') { throw "Unexpected cache content: $($file.Name)" }
    Assert-Scoped $file.FullName $sourceRoot
    Assert-Scoped (Join-Path $destinationRoot $file.Name) $archiveRoot
}
Write-Output ('Plan: {0} files, {1:N3} GiB; exact backup retained at {2}' -f $files.Count,(($files | Measure-Object Length -Sum).Sum/1GB),$destinationRoot)
if (-not $Apply) { Write-Output 'Dry run only.'; exit 0 }
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $audit 'relocation.lock'),'OpenOrCreate','ReadWrite','None')
$report = Join-Path $audit ('relocation_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
$records = @($files | ForEach-Object { [pscustomobject]@{
    source=$_.FullName;destination=(Join-Path $destinationRoot $_.Name);bytes=$_.Length;
    source_ticks=$_.LastWriteTimeUtc.Ticks;sha256=$null;status='planned'
}})
function Save-Report { ConvertTo-Json -InputObject @($records) -Depth 5 | Set-Content -LiteralPath $report -Encoding UTF8 }
try {
    New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null
    Save-Report
    $number = 0
    foreach ($record in $records) {
        Assert-Idle
        Assert-Scoped $record.source $sourceRoot
        Assert-Scoped $record.destination $archiveRoot
        $number++
        Write-Output "[$number/$($records.Count)] Copy and verify: $(Split-Path $record.source -Leaf)"
        $hash = Get-BufferedHash $record.source
        if (Test-Path -LiteralPath $record.destination) {
            if ((Get-BufferedHash $record.destination) -ne $hash) { throw 'Existing archive differs; refusing overwrite.' }
        } else {
            $temporary = $record.destination + '.copying'
            Assert-Scoped $temporary $archiveRoot
            if (Test-Path -LiteralPath $temporary) { throw "Review interrupted copy before retrying: $temporary" }
            Copy-Item -LiteralPath $record.source -Destination $temporary
            if ((Get-Item -LiteralPath $temporary).Length -ne $record.bytes -or (Get-BufferedHash $temporary) -ne $hash) { throw 'Copied file verification failed; local original retained.' }
            Move-Item -LiteralPath $temporary -Destination $record.destination
        }
        $local = Get-Item -LiteralPath $record.source
        if ($local.Length -ne $record.bytes -or $local.LastWriteTimeUtc.Ticks -ne $record.source_ticks) { throw 'Local file changed; refusing removal.' }
        $record.sha256 = $hash; $record.status = 'archive_verified'
        Save-Report
        Assert-Scoped $record.source $sourceRoot
        Remove-Item -LiteralPath $record.source -Force
        $record.status = 'moved_verified'
        Save-Report
    }
    Write-Output ('COMPLETE: moved verified bytes=' + ($records | Measure-Object bytes -Sum).Sum)
    Write-Output "Audit: $report"
} finally { $lock.Dispose() }
