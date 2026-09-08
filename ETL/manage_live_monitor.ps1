[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("Start", "Stop", "Restart", "Status")]
    [string]$Action = "Status",
    [ValidateRange(10, 300)]
    [int]$TimeoutSeconds = 90
)

if ($args.Count -gt 0) {
    throw "Unexpected positional arguments. Use -Action Start, Stop, Restart, or Status."
}

$ErrorActionPreference = "Stop"
$EtlRoot = $PSScriptRoot
$Launcher = Join-Path $EtlRoot "run_live_monitor.ps1"
$StateDir = Join-Path $EtlRoot "output\live_monitor"
$StopRequest = Join-Path $StateDir "stop.request"
$HealthUri = "http://127.0.0.1:8790/healthz"

function Test-LiveMonitor {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUri -TimeoutSec 2
        return $response.StatusCode -in @(200, 503)
    } catch {
        # A degraded /healthz response can throw in Windows PowerShell. The port
        # check below distinguishes it from a stopped service.
        $listener = netstat -ano | Select-String -Pattern '^\s*TCP\s+127\.0\.0\.1:8790\s+.*LISTENING\s+\d+\s*$'
        return $null -ne $listener
    }
}

function Wait-LiveMonitor {
    param([Parameter(Mandatory = $true)][bool]$Running)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $matchingChecks = 0
    do {
        if ((Test-LiveMonitor) -eq $Running) {
            $matchingChecks++
            # A stopped service must remain down long enough to outlast the
            # launcher's five-second crash-restart interval.
            $requiredChecks = if ($Running) { 1 } else { 12 }
            if ($matchingChecks -ge $requiredChecks) { return $true }
        } else {
            $matchingChecks = 0
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Stop-LiveMonitor {
    if (-not (Test-LiveMonitor)) {
        Write-Host "Live monitor is already stopped."
        return
    }

    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    Set-Content -LiteralPath $StopRequest -Value (Get-Date).ToString("o") -Encoding ASCII
    Write-Host "Graceful live-monitor pause requested; waiting for active work to commit."
    if (Wait-LiveMonitor -Running $false) {
        Write-Host "Live monitor stopped cleanly."
        return
    }

    Write-Warning "Graceful stop timed out; stopping only the process listening on port 8790."
    $listenerLines = netstat -ano | Select-String -Pattern '^\s*TCP\s+127\.0\.0\.1:8790\s+.*LISTENING\s+(\d+)\s*$'
    $listenerPids = @(
        $listenerLines | ForEach-Object {
            if ($_.Line -match 'LISTENING\s+(\d+)\s*$') { [int]$Matches[1] }
        } | Sort-Object -Unique
    )
    foreach ($listenerPid in $listenerPids) {
        Stop-Process -Id $listenerPid -Force -ErrorAction Stop
    }
    if (-not (Wait-LiveMonitor -Running $false)) {
        throw "Live monitor did not stop within $TimeoutSeconds seconds."
    }
    Write-Host "Live monitor stopped after the graceful timeout fallback."
}

function Start-LiveMonitor {
    if (Test-LiveMonitor) {
        if (Test-Path -LiteralPath $StopRequest) {
            Remove-Item -LiteralPath $StopRequest -Force
        }
        Write-Host "Live monitor is already running."
        return
    }
    if (-not (Test-Path -LiteralPath $Launcher)) {
        throw "Live-monitor launcher is missing: $Launcher"
    }

    if (Test-Path -LiteralPath $StopRequest) {
        Remove-Item -LiteralPath $StopRequest -Force
    }
    $quotedLauncher = '"' + $Launcher + '"'
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $quotedLauncher" `
        -WorkingDirectory $EtlRoot -WindowStyle Hidden
    if (-not (Wait-LiveMonitor -Running $true)) {
        throw "Live monitor did not become available within $TimeoutSeconds seconds."
    }
    Write-Host "Live monitor started: http://127.0.0.1:8790/"
}

switch ($Action) {
    "Start" { Start-LiveMonitor }
    "Stop" { Stop-LiveMonitor }
    "Restart" {
        Stop-LiveMonitor
        Start-LiveMonitor
    }
    "Status" {
        if (Test-LiveMonitor) {
            Write-Host "Live monitor is running: http://127.0.0.1:8790/"
        } else {
            Write-Host "Live monitor is stopped."
        }
    }
}
