param(
    [string]$Destination = "",
    [switch]$IncludeOfflineWheels,
    [switch]$IncludeFfmpeg,
    [switch]$IncludeUploads,
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$etlRoot = (Resolve-Path (Join-Path $source "..\..\..")).Path
if (-not $Destination) {
    $Destination = Join-Path $etlRoot "output\portable\VetoScoreboardMaker"
}
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $etlRoot "output\portable"))
$outputPrefix = $outputRoot.TrimEnd("\") + "\"
if (-not ($destinationPath + "\").StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must stay under $outputRoot"
}

New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
foreach ($directory in @("data\uploads", "data\projects", "logs", "wheels", "packages")) {
    New-Item -ItemType Directory -Path (Join-Path $destinationPath $directory) -Force | Out-Null
}

foreach ($file in @("scoreboard_app.py", "scoreboard_web.py", "scoreboard_media.py", "scoreboard_web.html", "players_stats_background.png", "qualifier_rounds_background.png", "head2head_background.png", "country_flags.zip", "country_flags.json", "QUALIFIER_ROUNDS.txt", "import_davis_players.py", "davis_cup_2026_round2.csv", "DAVIS_PLAYER_IMPORT.md", "publish_davis_presets.py", "prepare_korea_preview.py", "fill_davis_photos.py", "fill_qualifier_results.py", "davis_2026_round1_results.json", "scoreboard_match_templates.py", "scoreboard_output_probe.py", "match_stadium.png", "match_davis_logo.png")) {
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $destinationPath $file) -Force
}
$support = Join-Path $source "portable_support"
foreach ($file in @(
    "requirements.txt", "scoreboard_settings.ps1", "setup_scoreboard.ps1",
    "start_scoreboard.ps1", "stop_scoreboard.ps1", "enable_lan_access.ps1",
    "apply_code_update.ps1", "README.txt"
)) {
    Copy-Item -LiteralPath (Join-Path $support $file) -Destination (Join-Path $destinationPath $file) -Force
}
function New-PowerShellShortcut([string]$Name, [string]$Script, [string]$Description) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $destinationPath $Name))
    $shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `".\$Script`""
    $shortcut.WorkingDirectory = "."
    $shortcut.Description = $Description
    $shortcut.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
    $shortcut.Save()
}
New-PowerShellShortcut "SETUP_AND_START.lnk" "setup_scoreboard.ps1" "Install and start Veto Scoreboard Maker"
New-PowerShellShortcut "START_SCOREBOARD.lnk" "start_scoreboard.ps1" "Start Veto Scoreboard Maker"
New-PowerShellShortcut "STOP_SCOREBOARD.lnk" "stop_scoreboard.ps1" "Stop Veto Scoreboard Maker"
New-PowerShellShortcut "APPLY_CODE_UPDATE.lnk" "apply_code_update.ps1" "Apply a verified Veto Scoreboard code update"
New-PowerShellShortcut "ENABLE_LAN_ACCESS_RUN_AS_ADMIN.lnk" "enable_lan_access.ps1" "Enable LAN firewall access for Veto Scoreboard Maker"

$python = (Resolve-Path (Join-Path $etlRoot "..\venv\Scripts\python.exe")).Path
if ($IncludeOfflineWheels) {
    $wheelDirectory = Join-Path $destinationPath "wheels"
    Get-ChildItem -LiteralPath $wheelDirectory -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "Downloading Windows dependency wheels for Python 3.14..." -ForegroundColor Cyan
    & $python -m pip download --disable-pip-version-check --only-binary=:all: --platform win_amd64 --python-version 314 --implementation cp --dest $wheelDirectory --requirement (Join-Path $destinationPath "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not download dependency wheels." }
}

$packageDirectory = Join-Path $destinationPath "packages"
Get-ChildItem -LiteralPath $packageDirectory -File -ErrorAction SilentlyContinue | Remove-Item -Force

if ($IncludeUploads) {
    $uploadSource = Join-Path $source "data\uploads"
    $uploadTarget = Join-Path $destinationPath "data\uploads"
    if (Test-Path -LiteralPath $uploadSource) {
        Get-ChildItem -LiteralPath $uploadSource -File | Copy-Item -Destination $uploadTarget -Force
    }
    $projectSource = Join-Path $source "data\projects"
    if (Test-Path -LiteralPath $projectSource) {
        Get-ChildItem -LiteralPath $projectSource -File -Filter '*.json' |
            Copy-Item -Destination (Join-Path $destinationPath "data\projects") -Force
    }
}

if ($IncludeFfmpeg) {
    $ffmpeg = & $python -c "import importlib.util,pathlib; p=pathlib.Path(r'$source')/'scoreboard_app.py'; s=importlib.util.spec_from_file_location('scoreboard_app',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.locate_ffmpeg() or '')"
    $ffmpeg = ($ffmpeg | Select-Object -Last 1).Trim()
    if (-not $ffmpeg -or -not (Test-Path -LiteralPath $ffmpeg)) {
        throw "FFmpeg is not installed on this PC, so it cannot be bundled."
    }
    $ffmpegTarget = Join-Path $destinationPath "tools\ffmpeg\bin"
    New-Item -ItemType Directory -Path $ffmpegTarget -Force | Out-Null
    Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $ffmpegTarget "ffmpeg.exe") -Force
}

if ($CreateZip) {
    $zip = "$destinationPath.zip"
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -LiteralPath $destinationPath -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Portable ZIP: $zip" -ForegroundColor Green
}
Write-Host "Portable folder: $destinationPath" -ForegroundColor Green
