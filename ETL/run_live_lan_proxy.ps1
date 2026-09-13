[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$NginxRoot = Join-Path $PSScriptRoot "tools\nginx"
$Nginx = Join-Path $NginxRoot "nginx.exe"
$Config = "conf/live_dashboard.conf"
$PidFile = Join-Path $NginxRoot "logs\live_dashboard.pid"

if (-not (Test-Path -LiteralPath $Nginx)) {
    throw "Nginx was not found at $Nginx"
}

New-Item -ItemType Directory -Force -Path (Join-Path $NginxRoot "temp\live_client_body") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $NginxRoot "temp\live_proxy") | Out-Null

$Prefix = ($NginxRoot -replace "\\", "/") + "/"
& $Nginx -p $Prefix -c $Config -t
if ($LASTEXITCODE -ne 0) {
    throw "Nginx configuration validation failed."
}

$Running = $false
if (Test-Path -LiteralPath $PidFile) {
    try {
        $NginxPid = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
        $Running = [bool](Get-Process -Id $NginxPid -ErrorAction Stop)
    } catch {
        Remove-Item -LiteralPath $PidFile -Force
    }
}

if ($Running) {
    & $Nginx -p $Prefix -c $Config -s reload
    if ($LASTEXITCODE -ne 0) {
        throw "Nginx reload failed."
    }
    Write-Host "Nginx LAN proxy reloaded."
} else {
    Start-Process -FilePath $Nginx -ArgumentList @("-c", $Config) `
        -WorkingDirectory $NginxRoot -WindowStyle Hidden
    Start-Sleep -Seconds 1
    if (-not (Test-Path -LiteralPath $PidFile)) {
        throw "Nginx did not start. Check tools\nginx\logs\live_dashboard_error.log"
    }
    Write-Host "Nginx LAN proxy started."
}

Write-Host "Local network dashboard: http://192.168.50.126:8090/war-room"
