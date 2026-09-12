param(
    [string]$UpdateZip = "",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $UpdateZip) {
    $UpdateZip = Join-Path $PSScriptRoot "VetoScoreboardCodeUpdate.zip"
}
$updatePath = [System.IO.Path]::GetFullPath($UpdateZip)
if (-not (Test-Path -LiteralPath $updatePath)) {
    throw "Place VetoScoreboardCodeUpdate.zip in this folder, then run this updater again."
}

$runtimeFiles = @("scoreboard_app.py", "scoreboard_web.py", "scoreboard_web.html")
$dataRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "data"))
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
$staging = Join-Path $dataRoot ("update_staging_" + [guid]::NewGuid().ToString("N"))
$backup = Join-Path $dataRoot ("code_backups\" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($updatePath)
    try {
        $manifestEntry = $archive.Entries | Where-Object { $_.FullName.Replace("\", "/") -eq "manifest.json" } | Select-Object -First 1
        if (-not $manifestEntry) { throw "Update manifest is missing." }
        $manifestFile = Join-Path $staging "manifest.json"
        $input = $manifestEntry.Open()
        $output = [System.IO.File]::Create($manifestFile)
        try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
        $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
        if ($manifest.schema -ne 1) { throw "Unsupported update manifest version." }

        foreach ($file in $runtimeFiles) {
            $entry = $archive.Entries | Where-Object { $_.FullName.Replace("\", "/") -eq $file } | Select-Object -First 1
            if (-not $entry) { throw "Update is missing $file." }
            $stagedFile = Join-Path $staging $file
            $input = $entry.Open()
            $output = [System.IO.File]::Create($stagedFile)
            try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
            $property = $manifest.files.PSObject.Properties[$file]
            if (-not $property) { throw "No checksum was supplied for $file." }
            $actual = (Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash
            if ($actual -ne $property.Value) { throw "Checksum verification failed for $file." }
        }
    } finally {
        $archive.Dispose()
    }

    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach ($file in $runtimeFiles) {
        $current = Join-Path $PSScriptRoot $file
        if (Test-Path -LiteralPath $current) {
            Copy-Item -LiteralPath $current -Destination (Join-Path $backup $file) -Force
        }
    }
    & (Join-Path $PSScriptRoot "stop_scoreboard.ps1")
    try {
        foreach ($file in $runtimeFiles) {
            Copy-Item -LiteralPath (Join-Path $staging $file) -Destination (Join-Path $PSScriptRoot $file) -Force
        }
        Copy-Item -LiteralPath (Join-Path $staging "manifest.json") -Destination (Join-Path $dataRoot "installed_code_manifest.json") -Force
    } catch {
        foreach ($file in $runtimeFiles) {
            $saved = Join-Path $backup $file
            if (Test-Path -LiteralPath $saved) {
                Copy-Item -LiteralPath $saved -Destination (Join-Path $PSScriptRoot $file) -Force
            }
        }
        throw
    }
} finally {
    if (Test-Path -LiteralPath $staging) {
        $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
        $dataPrefix = $dataRoot.TrimEnd("\") + "\"
        if (($resolvedStaging + "\").StartsWith($dataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
        }
    }
}

Write-Host "Scoreboard code updated successfully." -ForegroundColor Green
Write-Host "Backup: $backup"
if (-not $NoStart) {
    & (Join-Path $PSScriptRoot "start_scoreboard.ps1")
}
