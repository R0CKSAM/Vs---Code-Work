$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath('Z:\Veto Logs Backup\Dashboards').TrimEnd('\')
$extras = Join-Path $root 'extras'
$audit = Join-Path $PSScriptRoot 'output\validation\dashboard_library_20261015'
$manifest = Get-Content -LiteralPath (Join-Path $audit 'manifest.json') -Raw | ConvertFrom-Json
$names = @('CTV - Distribution', 'identity_poc', 'PEAK', 'stream_watch_hours_showcase.xlsx')

function Assert-Scope([string]$path) {
    $full = [IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Outside approved dashboard directory: $full"
    }
    return $full
}

if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Dashboard root must not be a reparse point.'
}
if (Test-Path -LiteralPath $extras) {
    if ((Get-Item -LiteralPath $extras).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Extras must not be a reparse point.'
    }
}

# Verify the active library still matches the already browser-tested publication.
foreach ($page in $manifest) {
    $path = Assert-Scope (Join-Path $root $page.file)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $page.sha256) {
        throw "Active dashboard changed: $($page.file)"
    }
    $stem = [IO.Path]::GetFileNameWithoutExtension($page.file)
    foreach ($asset in $page.dependencies) {
        $assetPath = Assert-Scope (Join-Path $root "dependency\$stem\$asset")
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "Missing active dependency: $assetPath"
        }
    }
}

$plan = @()
foreach ($name in $names) {
    $source = Assert-Scope (Join-Path $root $name)
    $destination = Assert-Scope (Join-Path $extras $name)
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing source: $source" }
    if (Test-Path -LiteralPath $destination) { throw "Destination already exists: $destination" }
    $item = Get-Item -LiteralPath $source
    $children = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $source -Recurse -Force) } else { @() }
    if (@(@($item) + $children | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw "Reparse point in candidate: $source"
    }
    $files = if ($item.PSIsContainer) { @($children | Where-Object { -not $_.PSIsContainer }) } else { @($item) }
    $inventory = @($files | ForEach-Object {
        [pscustomobject]@{
            Relative = $(if ($item.PSIsContainer) { $_.FullName.Substring($source.Length + 1) } else { '' })
            Bytes = $_.Length
            SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    })
    $plan += [pscustomobject]@{ Source = $source; Destination = $destination; Files = $inventory; Moved = $false; Verified = $false }
}
$record = Join-Path $audit ('extras_move_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
$plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $record -Encoding UTF8
New-Item -ItemType Directory -Path $extras -Force | Out-Null
foreach ($entry in $plan) {
    # All absolute targets and their complete contents were checked above; never overwrite.
    Move-Item -LiteralPath $entry.Source -Destination $entry.Destination
    $entry.Moved = $true
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $record -Encoding UTF8
    foreach ($file in $entry.Files) {
        $path = if ($file.Relative) { Join-Path $entry.Destination $file.Relative } else { $entry.Destination }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $file.SHA256) {
            throw "Post-move verification failed: $path"
        }
    }
    $entry.Verified = $true
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $record -Encoding UTF8
    Write-Output "Moved and verified: $($entry.Destination)"
}
Write-Output "Audit: $record"
