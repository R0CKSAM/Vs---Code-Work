[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$DestinationRoot)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$tempRoot = Join-Path $root 'output\temp'
$destination = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
$expected = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\retained_intermediates'
if ($destination -ne $expected) { throw 'Unexpected retention destination; no files moved.' }
$stream = Join-Path $tempRoot 'stream_lake_priority_20261012_1600'
$asrun = Join-Path $tempRoot 'asrun_priority_20261012_1700'
foreach ($stateFile in @((Join-Path $stream 'priority_state.json'), (Join-Path $asrun 'asrun_state.json'), (Join-Path $asrun 'fast_archive_state.json'))) {
    if ((Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json).status -ne 'complete') { throw "Incomplete priority job: $stateFile" }
}
$audit = Join-Path $tempRoot 'priority_stage_relocation_20261012.json'
if (Test-Path -LiteralPath $audit) { throw 'Relocation audit already exists; inspect before restarting.' }
$state = @{status='running';started_at=(Get-Date).ToString('o');moved_bytes=0L;files=@();destination=$destination}
function Save-Audit {
    $state | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath "$audit.tmp" -Encoding UTF8
    Move-Item -LiteralPath "$audit.tmp" -Destination $audit -Force
}
Save-Audit
try {
    foreach ($run in @($stream,$asrun)) {
        foreach ($day in @('2026-10-10','2026-10-11')) {
            $folder = [IO.Path]::GetFullPath((Join-Path $run "$day\parquet"))
            $allowed = [IO.Path]::GetFullPath($run).TrimEnd('\') + '\'
            if (-not $folder.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Source escaped priority directory.' }
            foreach ($file in Get-ChildItem -LiteralPath $folder -Filter '*.parquet' -File -Recurse) {
                $source = [IO.Path]::GetFullPath($file.FullName)
                if (-not $source.StartsWith($folder+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'File escaped staging root.' }
                if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing reparse-point source.' }
                $relative = $source.Substring($tempRoot.Length+1)
                $target = [IO.Path]::GetFullPath((Join-Path $destination $relative))
                if (-not $target.StartsWith($destination+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Destination escaped retention root.' }
                if (Test-Path -LiteralPath $target) { throw "Destination already exists: $target" }
                $state.current_file=$source
                Save-Audit
                Write-Output "[$(Get-Date -Format o)] Copy and verify $relative ($($file.Length) bytes)"
                New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
                $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
                $partial = "$target.copying"
                if (Test-Path -LiteralPath $partial) { throw "Partial copy exists: $partial" }
                Copy-Item -LiteralPath $source -Destination $partial
                if ((Get-Item -LiteralPath $partial).Length -ne $file.Length -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $hash) { throw "Copy verification failed: $source" }
                $current = Get-Item -LiteralPath $source
                if ($current.Length -ne $file.Length -or $current.LastWriteTimeUtc -ne $file.LastWriteTimeUtc) { throw "Source changed while copying: $source" }
                Move-Item -LiteralPath $partial -Destination $target
                # Both absolute paths are bounded above; the retained hash-verified copy exists.
                Remove-Item -LiteralPath $source
                $state.moved_bytes += $file.Length
                $state.files += @{source=$source;destination=$target;bytes=$file.Length;sha256=$hash}
                Save-Audit
                Write-Output "[$(Get-Date -Format o)] Moved and retained; total relocated $([math]::Round($state.moved_bytes/1GB,2)) GiB"
            }
        }
    }
    $state.status='complete'
    $state.finished_at=(Get-Date).ToString('o')
    Save-Audit
} catch {
    $state.status='failed'
    $state.error=$_.Exception.Message
    Save-Audit
    throw
}
