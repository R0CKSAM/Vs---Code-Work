# Office AI Background Remover Launcher
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$env:PORT = "6805"
$env:HOST = "0.0.0.0"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Office AI Background Remover" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Target URL: http://192.168.50.134:6805" -ForegroundColor Green
Write-Host " Local URL:  http://127.0.0.1:6805" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\.venv\Scripts\python.exe") {
    & ".\.venv\Scripts\python.exe" "app.py"
} else {
    & python "app.py"
}
