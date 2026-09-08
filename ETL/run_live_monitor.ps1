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
if (Test-Path -LiteralPath $StopRequest) {
    Remove-Item -LiteralPath $StopRequest -Force
}

Set-Location -LiteralPath $EtlRoot
do {
    & $Python @arguments
    $exitCode = $LASTEXITCODE
    if ($NoRestart -or $exitCode -eq 0) { exit $exitCode }
    Write-Warning "Live monitor exited with code $exitCode. Restarting in 5 seconds..."
    Start-Sleep -Seconds 5
} while ($true)
