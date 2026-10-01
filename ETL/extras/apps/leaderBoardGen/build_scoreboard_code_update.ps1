param([string]$Destination = "")

$ErrorActionPreference = "Stop"
$source = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\PRODUCTION\Veto OTT')).Path
$etlRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
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
$runtimeFiles = @("scoreboard_app.py", "scoreboard_web.py", "scoreboard_media.py", "scoreboard_web.html", "scoreboard_competition_theme.py", "billie_background.png", "billie_players_stats_final.png", "player_list_background.png", "prediction_background_front.png", "qualifier_band.png", "semi_finals_background.png", "players_stats_background.png", "qualifier_rounds_background.png", "head2head_background.png", "country_flags.zip", "country_flags.json", "QUALIFIER_ROUNDS.txt", "import_davis_players.py", "davis_cup_2026_round2.csv", "DAVIS_PLAYER_IMPORT.md", "publish_davis_presets.py", "prepare_korea_preview.py", "fill_davis_photos.py", "fill_qualifier_results.py", "davis_2026_round1_results.json", "scoreboard_match_templates.py", "scoreboard_output_probe.py", "match_stadium.png", "match_davis_logo.png")

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
    Copy-Item -LiteralPath (Join-Path $source 'apply_code_update.ps1') -Destination $staging
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'portable_support\PROJECTS_UPDATE.txt') -Destination $staging

    if (Test-Path -LiteralPath $destinationPath) {
        throw "Destination already exists: $destinationPath"
    }
    Add-Type -AssemblyName System.IO.Compression
    $payload = Get-ChildItem -LiteralPath $staging -File
    $tempZip = Join-Path $staging "payload.zip"
    $zipStream = [System.IO.FileStream]::new($tempZip, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $archive = [System.IO.Compression.ZipArchive]::new($zipStream,
            [System.IO.Compression.ZipArchiveMode]::Create, $true)
        try {
            foreach ($file in $payload) {
                $entry = $archive.CreateEntry($file.Name, [System.IO.Compression.CompressionLevel]::Optimal)
                $input = [System.IO.FileStream]::new($file.FullName, [System.IO.FileMode]::Open,
                    [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                $output = $entry.Open()
                try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
            }
        } finally { $archive.Dispose() }
    } finally { $zipStream.Dispose() }
    Move-Item -LiteralPath $tempZip -Destination $destinationPath -ErrorAction Stop
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
