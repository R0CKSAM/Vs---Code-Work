[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("Start", "Stop", "Restart", "Status")]
    [string]$Action = "Status",
    [ValidateRange(10, 120)]
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$EtlRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $EtlRoot
$AppRoot = Join-Path $EtlRoot "extras\apps\leaderBoardGen"
$App = Join-Path $AppRoot "scoreboard_app.py"
$Python = Join-Path $WorkspaceRoot "venv\Scripts\python.exe"
$UploadDirectory = Join-Path $AppRoot "data\uploads"
$Port = 8080
$LocalUrl = "http://127.0.0.1:$Port/scoreboard"
$LanUrl = "http://192.168.50.126:$Port/scoreboard"
$HealthUrl = "http://127.0.0.1:$Port/healthz"

function Get-ScoreboardListenerPids {
    return @(
        netstat -ano -p tcp | ForEach-Object {
            if ($_ -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                [int]$Matches[1]
            }
        } | Sort-Object -Unique
    )
}

function Test-Scoreboard {
    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        return $health.ok -eq $true -and $health.service -eq "scoreboard-web"
    } catch {
        return $false
    }
}

function Wait-Scoreboard([bool]$Running) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Test-Scoreboard) -eq $Running) { return $true }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Start-Scoreboard {
    if (Test-Scoreboard) {
        Write-Host "Scoreboard is already running: $LanUrl"
        return
    }
    if ((Get-ScoreboardListenerPids).Count -gt 0) {
        throw "Port $Port is occupied by another process. It was not stopped."
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python environment was not found: $Python"
    }
    if (-not (Test-Path -LiteralPath $App)) {
        throw "Scoreboard application was not found: $App"
    }
    New-Item -ItemType Directory -Path $UploadDirectory -Force | Out-Null
    $env:SCOREBOARD_WEB_UPLOAD_DIR = $UploadDirectory
    $arguments = "`"$App`" --web --host 0.0.0.0 --port $Port"
    Start-Process -FilePath $Python -ArgumentList $arguments `
        -WorkingDirectory $AppRoot -WindowStyle Hidden
    if (-not (Wait-Scoreboard $true)) {
        throw "Scoreboard did not start on port $Port."
    }
    Write-Host "Scoreboard running: $LocalUrl" -ForegroundColor Green
    Write-Host "LAN scoreboard: $LanUrl" -ForegroundColor Green
}

function Stop-Scoreboard {
    if (-not (Test-Scoreboard)) {
        if ((Get-ScoreboardListenerPids).Count -gt 0) {
            throw "Port $Port is occupied by a non-scoreboard process. It was not stopped."
        }
        Write-Host "Scoreboard is already stopped."
        return
    }
    foreach ($listenerPid in (Get-ScoreboardListenerPids)) {
        Stop-Process -Id $listenerPid -Force -ErrorAction Stop
    }
    if (-not (Wait-Scoreboard $false)) {
        throw "Scoreboard did not stop within $TimeoutSeconds seconds."
    }
    Write-Host "Scoreboard stopped."
}

switch ($Action) {
    "Start" { Start-Scoreboard }
    "Stop" { Stop-Scoreboard }
    "Restart" { Stop-Scoreboard; Start-Scoreboard }
    "Status" {
        if (Test-Scoreboard) {
            Write-Host "Scoreboard is running: $LanUrl" -ForegroundColor Green
        } elseif ((Get-ScoreboardListenerPids).Count -gt 0) {
            Write-Host "Port $Port is occupied, but the scoreboard health check failed." -ForegroundColor Yellow
        } else {
            Write-Host "Scoreboard is stopped."
        }
    }
}
