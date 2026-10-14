[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'RevenueLive/notneeded'))
$zipPath = Join-Path $root 'mysql-8.4.11-winx64.zip'
$expandedRoot = Join-Path $root 'mysql-runtime'
$audit = Join-Path $PSScriptRoot 'output/validation/duplicate_mysql_zip_20261014'
function Assert-Safe([string]$Path, [string]$AllowedRoot) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($AllowedRoot.TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside reviewed scope.' }
    $cursor = $full
    while ($cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked path: $cursor" }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
Assert-Safe $zipPath $root
$zipStat = Get-Item -LiteralPath $zipPath
$zip = [IO.Compression.ZipFile]::OpenRead($zipPath)
$records = @()
try {
    foreach ($entry in $zip.Entries) {
        if ($entry.FullName.EndsWith('/')) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $expandedRoot $entry.FullName))
        Assert-Safe $target $expandedRoot
        $stat = Get-Item -LiteralPath $target
        if ($stat.PSIsContainer -or $stat.Length -ne $entry.Length) { throw "Missing or different extracted file: $target" }
        $algorithm = [Security.Cryptography.SHA256]::Create()
        $packed = $entry.Open()
        $local = [IO.FileStream]::new($target,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read,8MB,[IO.FileOptions]::SequentialScan)
        try {
            $packedHash = [BitConverter]::ToString($algorithm.ComputeHash($packed))
            $localHash = [BitConverter]::ToString($algorithm.ComputeHash($local))
            if ($packedHash -ne $localHash) { throw "Content differs: $target" }
        } finally { $packed.Dispose(); $local.Dispose(); $algorithm.Dispose() }
        $records += [pscustomobject]@{path=$target;bytes=$stat.Length;ticks=$stat.LastWriteTimeUtc.Ticks;sha256=$localHash.Replace('-','').ToLowerInvariant()}
        if ($records.Count % 50 -eq 0) { Write-Output "Verified $($records.Count) ZIP entries" }
    }
} finally { $zip.Dispose() }
if ($records.Count -ne 296) { throw 'Unexpected archive file count; refusing deletion.' }
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$reportPath = Join-Path $audit 'verification.json'
$report = [pscustomobject]@{archive=$zipPath;bytes=$zipStat.Length;status='verified_duplicate';files=$records}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
if ($Apply) {
    foreach ($record in $records) {
        Assert-Safe $record.path $expandedRoot
        $current = Get-Item -LiteralPath $record.path
        if ($current.Length -ne $record.bytes -or $current.LastWriteTimeUtc.Ticks -ne $record.ticks) { throw 'Extracted file changed; preserving ZIP.' }
    }
    Assert-Safe $zipPath $root
    $currentZip = Get-Item -LiteralPath $zipPath
    if ($currentZip.Length -ne $zipStat.Length -or $currentZip.LastWriteTimeUtc.Ticks -ne $zipStat.LastWriteTimeUtc.Ticks) { throw 'ZIP changed; preserving ZIP.' }
    Remove-Item -LiteralPath $zipPath -Force
    $report.status = 'deleted_zip_all_extracted_files_retained'
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}
Write-Output "$($report.status): $($report.bytes) bytes; $reportPath"
