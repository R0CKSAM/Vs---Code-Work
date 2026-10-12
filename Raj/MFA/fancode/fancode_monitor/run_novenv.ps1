param(
    [switch]$Headed,
    [string]$BaseUrl = "https://www.fancode.com"
)

$ErrorActionPreference = "Stop"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   FanCode Monitor - Phase 0 (no-venv runner)" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

# 1. Python check
Write-Host ""
Write-Host "[1/4] Python version:" -ForegroundColor Yellow
& python --version

# 2. Install packages to user site (avoids admin + avoids venv)
Write-Host ""
Write-Host "[2/4] Installing requirements (--user)..." -ForegroundColor Yellow
& python -m pip install --user --upgrade pip
& python -m pip install --user -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "      --user install failed, trying without flag..." -ForegroundColor Magenta
    & python -m pip install -r requirements.txt
}

# 3. Install Playwright browser
Write-Host ""
Write-Host "[3/4] Installing Playwright Chromium..." -ForegroundColor Yellow
& python -m playwright install chromium

# 4. Run tests
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Unit Tests" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
& python -m pytest tests/unit -v
$unitExit = $LASTEXITCODE

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   E2E Tests" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
if ($Headed) {
    Write-Host "   (HEADED)" -ForegroundColor Magenta
    & python -m pytest tests/e2e -v --headed --base-url $BaseUrl
} else {
    & python -m pytest tests/e2e -v --base-url $BaseUrl
}
$e2eExit = $LASTEXITCODE

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Summary" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
if ($unitExit -eq 0) { Write-Host "   PASSED  Unit tests" -ForegroundColor Green }
else                  { Write-Host "   FAILED  Unit tests (exit $unitExit)" -ForegroundColor Red }
if ($e2eExit -eq 0)   { Write-Host "   PASSED  E2E tests" -ForegroundColor Green }
else                   { Write-Host "   FAILED  E2E tests (exit $e2eExit)" -ForegroundColor Red }
Write-Host ""

if ($unitExit -eq 0 -and $e2eExit -eq 0) { exit 0 } else { exit 1 }
