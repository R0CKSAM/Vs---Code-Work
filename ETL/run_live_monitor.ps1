param(
    [switch]$NoSync,
    [int]$Workers = 0,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$EtlRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path -Parent $EtlRoot) "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}

$arguments = @("-m", "src.live_monitor.cli", "run")
if ($NoSync) { $arguments += "--no-sync" }
if ($Workers -gt 0) { $arguments += @("--workers", [string]$Workers) }

$StopRequest = Join-Path $EtlRoot "output\live_monitor\stop.request"
$LauncherPidFile = Join-Path $EtlRoot "output\live_monitor\launcher.pid"
if (Test-Path -LiteralPath $StopRequest) {
    Remove-Item -LiteralPath $StopRequest -Force
}

$existingPid = $null
if (Test-Path -LiteralPath $LauncherPidFile) {
    try {
        $existingPid = [int](Get-Content -LiteralPath $LauncherPidFile -Raw).Trim()
        if ($existingPid -ne $PID -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            throw "Live-monitor launcher is already running with PID $existingPid."
        }
    } catch [System.FormatException] {
        $existingPid = $null
    }
}
Set-Content -LiteralPath $LauncherPidFile -Value $PID -Encoding ASCII

try {
    Set-Location -LiteralPath $EtlRoot
    do {
        & $Python @arguments
        $exitCode = $LASTEXITCODE
        if ($NoRestart -or $exitCode -eq 0) { exit $exitCode }
        Write-Warning "Live monitor exited with code $exitCode. Restarting in 5 seconds..."
        Start-Sleep -Seconds 5
    } while ($true)
} finally {
    if (Test-Path -LiteralPath $LauncherPidFile) {
        $recordedPid = (Get-Content -LiteralPath $LauncherPidFile -Raw).Trim()
        if ($recordedPid -eq [string]$PID) {
            Remove-Item -LiteralPath $LauncherPidFile -Force
        }
    }
}
