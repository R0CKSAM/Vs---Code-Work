$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath('C:\Users\Intern\AppData\Local\CrashDumps')
$destinationRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'output\diagnostics\crash_dumps_20261014'))
$audit = Join-Path $destinationRoot 'relocation.jsonl'

function Hash-File([string]$Path) {
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::Read, 4MB, [IO.FileOptions]::SequentialScan)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $sha.Dispose(); $stream.Dispose() }
}

foreach ($name in @('python3.13.exe.17288.dmp', 'python3.13.exe.9632.dmp')) {
    $source = [IO.Path]::GetFullPath((Join-Path $sourceRoot $name))
    $destination = [IO.Path]::GetFullPath((Join-Path $destinationRoot $name))
    if ([IO.Path]::GetDirectoryName($source) -ne $sourceRoot -or
        [IO.Path]::GetDirectoryName($destination) -ne $destinationRoot) { throw 'Unsafe target path' }
    foreach ($path in @($sourceRoot, $destinationRoot, $source)) {
        if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing reparse point: $path"
        }
    }
    $before = Get-Item -LiteralPath $source
    $bytes = $before.Length
    $ticks = $before.LastWriteTimeUtc.Ticks
    Write-Output "Copying $name ($bytes bytes)"
    if (-not (Test-Path -LiteralPath $destination)) {
        if ([IO.DriveInfo]::new('D').AvailableFreeSpace -lt ($bytes + 20GB)) { throw 'Insufficient destination headroom' }
        Copy-Item -LiteralPath $source -Destination $destination
    }
    if ((Get-Item -LiteralPath $destination).Length -ne $bytes) { throw 'Copy size mismatch; original preserved' }
    Write-Output "Verifying $name"
    $hash = Hash-File $source
    if ($hash -ne (Hash-File $destination)) { throw 'Checksum mismatch; original preserved' }
    $after = Get-Item -LiteralPath $source
    if ($after.Length -ne $bytes -or $after.LastWriteTimeUtc.Ticks -ne $ticks) { throw 'Source changed; original preserved' }
    @{status='verified'; source=$source; destination=$destination; bytes=$bytes; sha256=$hash} |
        ConvertTo-Json -Compress | Add-Content -LiteralPath $audit -Encoding UTF8
    Remove-Item -LiteralPath $source
    @{status='relocated'; source=$source; destination=$destination; bytes=$bytes} |
        ConvertTo-Json -Compress | Add-Content -LiteralPath $audit -Encoding UTF8
    Write-Output "Relocated $name; C free GiB=$([math]::Round([IO.DriveInfo]::new('C').AvailableFreeSpace/1GB,2))"
}
