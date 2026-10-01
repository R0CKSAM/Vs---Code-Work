param(
    [ValidateSet('Start','Stop','Restart','Status','Backup')][string]$Action='Status',
    [Parameter(Mandatory=$true)][string]$DataDir,
    [string]$PublicUrl='',
    [string]$BackupDir='',
    [int]$Port=8820
)
$ErrorActionPreference='Stop'
$exe=Join-Path $PSScriptRoot 'RevenueLive.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'RevenueLive.exe is missing from this release.' }
$data=[System.IO.Path]::GetFullPath($DataDir).TrimEnd('\')
$release=[System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if ($data -ieq $release -or $data.StartsWith($release+'\',[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep the data directory outside the application release.'
}
if (-not (Test-Path -LiteralPath $data -PathType Container)) {
    throw 'Create the protected data directory before starting RevenueLive.'
}
$url="http://127.0.0.1:$Port"
function Test-Running {
    try {
        $health=Invoke-RestMethod -Uri "$url/health" -TimeoutSec 2
        return $health.service -eq 'revenuelive'
    } catch { return $false }
}
if ($Action -eq 'Status') {
    Write-Host "RevenueLive running: $(Test-Running) | $url"
    exit 0
}
if ($Action -eq 'Backup') {
    if (-not $BackupDir) { throw 'Supply -BackupDir on an encrypted, access-restricted volume.' }
    $backup=[System.IO.Path]::GetFullPath($BackupDir)
    if (-not (Test-Path -LiteralPath $backup -PathType Container)) { throw 'Create the protected backup directory first.' }
    $env:REVENUE_DATA_DIR=$data
    $env:REVENUE_BACKUP_DIR=$backup
    & $exe --backup
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed. No complete backup marker was written.' }
    exit 0
}
if ($Action -in @('Stop','Restart')) {
    if (Test-Running) {
        New-Item -ItemType File -Path (Join-Path $data "stop_$Port") -Force | Out-Null
        $deadline=(Get-Date).AddSeconds(20)
        while ((Test-Running) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
        if (Test-Running) { throw 'RevenueLive did not stop. No process was forcibly terminated.' }
        Write-Host 'RevenueLive stopped.'
    }
}
if ($Action -in @('Start','Restart')) {
    if ($PublicUrl -notmatch '^https://[^/]+/?$') { throw 'Supply -PublicUrl as an HTTPS origin, for example https://revenue.example.com.' }
    if (Test-Running) { throw "Port $Port is already serving RevenueLive." }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is occupied." }
    $logs=Join-Path $data 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $env:REVENUE_DATA_DIR=$data
    $env:REVENUE_PUBLIC_URL=$PublicUrl.TrimEnd('/')
    $env:REVENUE_HTTPS='1'
    $env:REVENUE_TRUSTED_PROXY='127.0.0.1'
    $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
    $arguments=@('--host','127.0.0.1','--port',"$Port")
    Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$stamp.out.log") -RedirectStandardError (Join-Path $logs "$stamp.err.log") | Out-Null
    $deadline=(Get-Date).AddSeconds(30)
    while (-not (Test-Running) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Running)) { throw "Startup failed. Check $logs." }
    Write-Host "RevenueLive backend ready: $url. Use the HTTPS reverse-proxy URL for users."
}
