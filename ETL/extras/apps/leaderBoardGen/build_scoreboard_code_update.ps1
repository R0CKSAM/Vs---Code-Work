param([string]$Destination = "")

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$etlRoot = (Resolve-Path (Join-Path $source "..\..\..")).Path
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $etlRoot "output\portable"))
if (-not $Destination) {
    $Destination = Join-Path $outputRoot "VetoScoreboardCodeUpdate.zip"
}
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$outputPrefix = $outputRoot.TrimEnd("\") + "\"
if (-not $destinationPath.StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must stay under $outputRoot"
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$staging = Join-Path $outputRoot (".code-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging -Force | Out-Null
$runtimeFiles = @("scoreboard_app.py", "scoreboard_web.py", "scoreboard_web.html")

try {
    $hashes = [ordered]@{}
    foreach ($file in $runtimeFiles) {
        $sourceFile = Join-Path $source $file
        if (-not (Test-Path -LiteralPath $sourceFile)) { throw "Missing runtime file: $file" }
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $staging $file) -Force
        $hashes[$file] = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash
    }
    $manifest = [ordered]@{
        schema = 1
        created_utc = (Get-Date).ToUniversalTime().ToString("o")
        files = $hashes
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $staging "manifest.json") -Encoding UTF8

    if (Test-Path -LiteralPath $destinationPath) {
        Remove-Item -LiteralPath $destinationPath -Force
    }
    $payload = Get-ChildItem -LiteralPath $staging -File | Select-Object -ExpandProperty FullName
    Compress-Archive -LiteralPath $payload -DestinationPath $destinationPath -CompressionLevel Optimal
} finally {
    if (Test-Path -LiteralPath $staging) {
        $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
        if (($resolvedStaging + "\").StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
        }
    }
}

$updateHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
Write-Host "Code update: $destinationPath" -ForegroundColor Green
Write-Host "SHA256: $updateHash"
