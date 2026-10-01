param(
    [ValidateSet('Start','Stop','Restart','Status','Backup')][string]$Action='Status',
    [int]$Port=8820,
    [string]$ListenAddress='127.0.0.1',
    [string]$DataDir='',
    [string]$PublicUrl=''
)
$ErrorActionPreference='Stop'
$Python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) { throw 'Run setup.ps1 first.' }
if ($DataDir) { $env:DATA_DIR=[System.IO.Path]::GetFullPath($DataDir) }
if ($PublicUrl) { $env:APP_URL=$PublicUrl.TrimEnd('/') }
Push-Location $PSScriptRoot
try {
    $configuration=& $Python -c 'import json; from config import Settings; s=Settings.from_env(); print(json.dumps(dict(data=str(s.data_dir),url=s.app_url,mysql=s.db_url.get_backend_name()=="mysql")))'
    if ($LASTEXITCODE -ne 0) { throw 'Invalid deployment configuration.' }
    $settings=$configuration | ConvertFrom-Json
} finally { Pop-Location }
$Data=$settings.data
$PublicUrl=$settings.url
$Logs=Join-Path $Data 'logs'
$HealthHeaders=@{}
if ($PublicUrl) { $HealthHeaders['Host']=([Uri]$PublicUrl).Authority }
$Url="http://127.0.0.1:$Port"
function Get-Status {
    try { $s=Invoke-RestMethod "$Url/health" -Headers $HealthHeaders -TimeoutSec 2; if ($s.service -eq 'revenuelive') { return $true } } catch {}
    return $false
}
if ($Action -eq 'Backup') {
    $env:REVENUE_DATA_DIR=$Data
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
    if ($PublicUrl) {
        if ($PublicUrl -notmatch '^https://[^/]+/?$') { throw 'PublicUrl must be one HTTPS origin without a path.' }
        if ($ListenAddress -notin @('127.0.0.1','localhost','::1')) { throw 'HTTPS proxy mode requires a loopback listener.' }
        $root=[System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
        $resolvedData=[System.IO.Path]::GetFullPath($Data).TrimEnd('\')
        if ($resolvedData -ieq $root -or $resolvedData.StartsWith($root+'\',[System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Keep production data outside the source directory.'
        }
        if (!(Test-Path -LiteralPath $resolvedData -PathType Container)) { throw 'Create the protected data directory first.' }
        $env:REVENUE_HTTPS='1'
        $env:REVENUE_PUBLIC_URL=$PublicUrl.TrimEnd('/')
        $env:REVENUE_TRUSTED_PROXY='127.0.0.1'
    } elseif ($env:REVENUE_HTTPS -eq '1' -or $env:REVENUE_PUBLIC_URL -or $env:REVENUE_TRUSTED_PROXY) {
        throw 'Production environment variables are set; supply -PublicUrl explicitly.'
    }
    $env:REVENUE_DATA_DIR=$Data
    New-Item -ItemType Directory -Path $Logs -Force | Out-Null
    $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
    $arguments='"{0}" --host {1} --port {2}' -f (Join-Path $PSScriptRoot 'app.py'),$ListenAddress,$Port
    Start-Process $Python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs "$stamp.out.log") -RedirectStandardError (Join-Path $Logs "$stamp.err.log") | Out-Null
    $deadline=(Get-Date).AddSeconds(30)
    while (!(Get-Status) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (!(Get-Status)) { throw "Startup failed. Check $Logs" }
    Write-Host "RevenueLive backend ready: $Url"
    if (!$settings.mysql) { Write-Host "Initial admin credentials: $Data\initial_admin.txt" }
}
