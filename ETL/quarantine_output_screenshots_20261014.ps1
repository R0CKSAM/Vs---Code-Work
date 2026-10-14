[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'output'))
$destination = Join-Path $root 'delete_mefolder'
$audit = Join-Path $root 'validation/output_quarantine_20261014'
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$images = @()
foreach ($relative in @('', 'temp', 'scoreboard_web', 'recorder_tv_test')) {
    $directory = Join-Path $root $relative
    $images += Get-ChildItem -LiteralPath $directory -File | Where-Object { $_.Extension -in @('.png','.jpg','.jpeg','.webp','.gif','.bmp') }
}
$patterns = Join-Path $audit "image_names_$stamp.txt"
[IO.File]::WriteAllLines($patterns, [string[]]@($images.Name | Sort-Object -Unique), (New-Object Text.UTF8Encoding($false)))
$rgArgs = @('-o','-i','-F','--no-heading','--no-line-number','-f',$patterns,
    '--glob','*.py','--glob','*.ps1','--glob','*.js','--glob','*.html','--glob','*.css',
    '--glob','*.json','--glob','*.md','--glob','*.txt','--glob','*.yaml','--glob','*.yml',
    '--glob','!venv/**','--glob','!**/node_modules/**','--glob','!**/.git/**',
    '--glob','!ETL/output/delete_mefolder/**','--glob','!ETL/output/validation/output_quarantine_20261014/**')
Push-Location $workspace
try { $references = @(& rg @rgArgs .); $code = $LASTEXITCODE } finally { Pop-Location }
if ($code -notin @(0,1)) { throw "Reference scan incomplete; no moves allowed (rg=$code)" }
$references | Set-Content -LiteralPath (Join-Path $audit "references_$stamp.txt") -Encoding UTF8
$referenced = @{}
foreach ($line in $references) {
    $name = $line.Substring($line.LastIndexOf(':')+1)
    $referenced[$name.ToLowerInvariant()] = $true
}

function Assert-Scoped([string]$Path, [string]$Parent) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith([IO.Path]::GetFullPath($Parent).TrimEnd('\')+'\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside root: $full" }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $cursor" }
        }
        $cursor = Split-Path $cursor -Parent
    }
}

$processes = @(Get-CimInstance Win32_Process)
$records = [Collections.Generic.List[object]]::new()
$manifest = Join-Path $audit "screenshots_$stamp.json"
foreach ($item in $images) {
    $relative = $item.FullName.Substring($root.Length+1)
    $target = Join-Path $destination $relative
    $record = [PSCustomObject]@{source=$item.FullName; destination=$target; bytes=$item.Length; status='preserved'; reason=''; sha256=''}
    $records.Add($record)
    if ($referenced.ContainsKey($item.Name.ToLowerInvariant())) { $record.reason='Referenced by code, tests or reports'; continue }
    if ($item.LastWriteTimeUtc -gt (Get-Date).ToUniversalTime().AddDays(-1)) { $record.reason='Modified within 24 hours'; continue }
    if (@($processes | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($item.FullName,[StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count) { $record.reason='Referenced by running process'; continue }
    Assert-Scoped $item.FullName $root
    Assert-Scoped $target $destination
    if (Test-Path -LiteralPath $target) { $record.reason='Destination exists'; continue }
    $record.status='planned'
    $record.reason='Old unreferenced screenshot in an explicitly reviewed screenshot location'
    if ($Apply) {
        $record.sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
        $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding UTF8
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        $current = Get-Item -LiteralPath $item.FullName
        if ($current.Length -ne $item.Length -or $current.LastWriteTimeUtc -ne $item.LastWriteTimeUtc) { throw "Source changed: $($item.FullName)" }
        Assert-Scoped $target $destination
        Move-Item -LiteralPath $item.FullName -Destination $target
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $record.sha256) { throw "Hash mismatch: $target" }
        $record.status='moved'
        $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding UTF8
    }
}
$records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding UTF8
$selected=@($records | Where-Object status -in @('planned','moved'))
$records | Group-Object status | Select-Object Name,Count | Format-Table
Write-Output ("Selected {0} screenshots, {1:N2} MiB. No code, datasets, logs or checkpoints targeted." -f $selected.Count,(($selected | Measure-Object bytes -Sum).Sum/1MB))
Write-Output "Manifest: $manifest"
