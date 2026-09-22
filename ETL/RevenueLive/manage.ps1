param([ValidateSet('Start','Stop','Restart','Status','Backup')][string]$Action='Status', [int]$Port=8820, [string]$ListenAddress='0.0.0.0', [switch]$Demo)
$ErrorActionPreference='Stop'
$Python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$Data=Join-Path $PSScriptRoot 'data'
if ($Demo) {
    $Data=Join-Path $PSScriptRoot 'demo_data'
    if (!$PSBoundParameters.ContainsKey('Port')) { $Port=8822 }
}
$Logs=Join-Path $PSScriptRoot 'logs'
$Url="http://127.0.0.1:$Port"
function Get-Status {
    try { $s=Invoke-RestMethod "$Url/health" -TimeoutSec 2; if ($s.service -eq 'revenuelive') { return $true } } catch {}
    return $false
}
if ($Action -eq 'Backup') {
    if ($Demo) { throw 'Backup is for the real data instance; demo is reproducible.' }
    & $Python (Join-Path $PSScriptRoot 'backup.py')
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed.' }
    exit
}
if ($Action -eq 'Status') { Write-Host "RevenueLive running: $(Get-Status) | $Url"; exit }
if ($Action -in @('Stop','Restart')) {
    if (Get-Status) {
        New-Item -ItemType File -Path (Join-Path $Data "stop_$Port") -Force | Out-Null
        $deadline=(Get-Date).AddSeconds(20)
        while ((Get-Status) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
        if (Get-Status) { throw 'RevenueLive has not stopped; no other process was touched.' }
        Write-Host 'RevenueLive stopped.'
    }
}
if ($Action -in @('Start','Restart')) {
    if (Get-Status) { Write-Host "Already running: $Url"; exit }
    if (!(Test-Path $Python)) { throw 'Run setup.ps1 first.' }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is occupied." }
    New-Item -ItemType Directory -Path $Logs -Force | Out-Null
    $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
    $arguments='"{0}" --host {1} --port {2}' -f (Join-Path $PSScriptRoot 'app.py'),$ListenAddress,$Port
    if ($Demo) { $arguments+=' --demo' }
    Start-Process $Python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs "$stamp.out.log") -RedirectStandardError (Join-Path $Logs "$stamp.err.log") | Out-Null
    $deadline=(Get-Date).AddSeconds(30)
    while (!(Get-Status) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (!(Get-Status)) { throw "Startup failed. Check $Logs" }
    Write-Host "RevenueLive ready: $Url | LAN: http://<host-ip>:$Port"
    Write-Host "Initial admin credentials: $Data\initial_admin.txt"
}
