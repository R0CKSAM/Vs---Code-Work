[CmdletBinding()]
param(
    [string]$OutDir = "Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube",
    [int]$IntervalSeconds = 60,
    [int]$RollMinutes = 15,
    [int]$RestartDelaySeconds = 60
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $root "..\..")
$python = Join-Path $repoRoot "venv\Scripts\python.exe"
$script = Join-Path $root "YT4.py"
$channels = Join-Path $root "channels.txt"
$log = Join-Path $root "logs\yt4-forever.log"
$runnerLog = Join-Path $root "logs\yt4-runner-output.log"

New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing Python runner: $python"
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

while ($true) {
    "$(Get-Date -Format o) launching YT4 -> $OutDir" | Add-Content -LiteralPath $log
    Push-Location $root
    try {
        & $python @argsList *>> $runnerLog
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    "$(Get-Date -Format o) YT4 exited with code $exitCode; restarting in $RestartDelaySeconds seconds" | Add-Content -LiteralPath $log
    Start-Sleep -Seconds $RestartDelaySeconds
}
