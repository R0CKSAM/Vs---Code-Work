[CmdletBinding()]
param(
    [string]$OutDir = "Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube",
    [int]$IntervalSeconds = 60,
    [int]$RollMinutes = 15
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $root "..\..")
$pythonw = Join-Path $repoRoot "venv\Scripts\pythonw.exe"
$script = Join-Path $root "YT4.py"
$channels = Join-Path $root "channels.txt"
$log = Join-Path $root "logs\yt4-launch.log"

New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Missing Python runner: $pythonw"
}
if (-not (Test-Path -LiteralPath $script)) {
    throw "Missing YT4 script: $script"
}
if (-not (Test-Path -LiteralPath $channels)) {
    throw "Missing channels file: $channels"
}

$argsList = @(
    $script,
    "--interval-seconds",
    "$IntervalSeconds",
    "--out-dir",
    $OutDir,
    "--url-file",
    $channels,
    "--measurement-mode",
    "auto",
    "--roll-minutes",
    "$RollMinutes"
)

"$(Get-Date -Format o) starting YT4 -> $OutDir" | Add-Content -LiteralPath $log
Start-Process -FilePath $pythonw -ArgumentList $argsList -WorkingDirectory $root -WindowStyle Hidden
