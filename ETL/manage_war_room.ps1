[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("Start", "Stop", "Restart", "Status")]
    [string]$Action = "Status",
    [ValidateRange(10, 300)]
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$EtlRoot = $PSScriptRoot
$BackendManager = Join-Path $EtlRoot "manage_live_monitor.ps1"
$ProxyLauncher = Join-Path $EtlRoot "run_live_lan_proxy.ps1"
$NginxRoot = Join-Path $EtlRoot "tools\nginx"
$Nginx = Join-Path $NginxRoot "nginx.exe"
$NginxConfig = "conf/live_dashboard.conf"
$PublicPort = 8090
$PublicUrl = "http://192.168.50.126:$PublicPort/war-room"
$HealthUrl = "http://127.0.0.1:$PublicPort/healthz"

function Get-PortListenerPids([int]$Port) {
    return @(
        netstat -ano -p tcp | ForEach-Object {
            if ($_ -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                [int]$Matches[1]
            }
        } | Sort-Object -Unique
    )
}

function Test-WarRoomProxy {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        return $response.StatusCode -in @(200, 503)
    } catch {
        return (Get-PortListenerPids $PublicPort).Count -gt 0
    }
}

function Wait-WarRoomProxy([bool]$Running) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Test-WarRoomProxy) -eq $Running) { return $true }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Invoke-BackendManager([string]$BackendAction) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BackendManager `
        -Action $BackendAction -TimeoutSeconds $TimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "Live-monitor backend action '$BackendAction' failed with exit code $LASTEXITCODE."
    }
}

function Start-WarRoom {
    Invoke-BackendManager "Start"
    if (-not (Test-WarRoomProxy)) {
        & $ProxyLauncher
    }
    if (-not (Wait-WarRoomProxy $true)) {
        throw "War-room proxy did not start on port $PublicPort."
    }
    Write-Host "War room running: $PublicUrl" -ForegroundColor Green
}

function Stop-WarRoom {
    $listenerPids = Get-PortListenerPids $PublicPort
    if ($listenerPids.Count -gt 0) {
        $prefix = ($NginxRoot -replace "\\", "/") + "/"
        & $Nginx -p $prefix -c $NginxConfig -s quit
        if ($LASTEXITCODE -ne 0 -or -not (Wait-WarRoomProxy $false)) {
            foreach ($listenerPid in (Get-PortListenerPids $PublicPort)) {
                Stop-Process -Id $listenerPid -Force -ErrorAction Stop
            }
        }
    }
    Invoke-BackendManager "Stop"
    if (Test-WarRoomProxy) {
        throw "War-room proxy is still listening on port $PublicPort."
    }
    Write-Host "War room stopped."
}

switch ($Action) {
    "Start" { Start-WarRoom }
    "Stop" { Stop-WarRoom }
    "Restart" { Stop-WarRoom; Start-WarRoom }
    "Status" {
        Invoke-BackendManager "Status"
        if (Test-WarRoomProxy) {
            Write-Host "Nginx proxy is running: $PublicUrl" -ForegroundColor Green
        } else {
            Write-Host "Nginx proxy is stopped (public port $PublicPort)." -ForegroundColor Yellow
        }
    }
}
