$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot "scoreboard_settings.ps1")

$pythonPathFile = Join-Path $PSScriptRoot "data\python_path.txt"
$python = if (Test-Path -LiteralPath $pythonPathFile) {
    (Get-Content -LiteralPath $pythonPathFile -Raw).Trim()
} else { "" }
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
    throw "Run SETUP_AND_START.lnk first."
}

$healthUrl = "http://127.0.0.1:$ScoreboardPort/healthz"
$dashboardUrl = "http://127.0.0.1:$ScoreboardPort/scoreboard"
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
    if ($health.service -eq "scoreboard-web") {
        Start-Process $dashboardUrl
        Write-Host "Scoreboard is already running at $dashboardUrl"
        exit 0
    }
} catch {}

New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot "data\uploads") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot "logs") -Force | Out-Null
$packageTarget = Join-Path $PSScriptRoot "python_packages"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$packageTarget;$env:PYTHONPATH" } else { $packageTarget }
$env:SCOREBOARD_WEB_UPLOAD_DIR = Join-Path $PSScriptRoot "data\uploads"
$appPath = Join-Path $PSScriptRoot "scoreboard_app.py"
$arguments = @(
    "`"$appPath`"",
    "--web", "--host", $ScoreboardHost, "--port", "$ScoreboardPort"
)
$stdout = Join-Path $PSScriptRoot "logs\scoreboard.out.log"
$stderr = Join-Path $PSScriptRoot "logs\scoreboard.err.log"
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath (Join-Path $PSScriptRoot "data\scoreboard.pid") -Value $process.Id -Encoding ASCII

$started = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($health.service -eq "scoreboard-web") { $started = $true; break }
    } catch {}
}
if (-not $started) {
    throw "Scoreboard did not start. Check logs\scoreboard.err.log."
}
Start-Process $dashboardUrl
Write-Host "Scoreboard started: $dashboardUrl" -ForegroundColor Green
Write-Host "LAN URL: http://<this-PC-IP>:$ScoreboardPort/scoreboard"
