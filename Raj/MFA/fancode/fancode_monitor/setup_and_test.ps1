param(
    [switch]$Headed,
    [switch]$SkipInstall,
    [string]$BaseUrl = "https://www.fancode.com"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   FanCode Monitor - Phase 0 Setup and Test Runner" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Python version check ──────────────────────────────────────────────
Write-Host "[1/6] Checking Python version..." -ForegroundColor Yellow
try {
    $pyVersion = & python --version 2>&1
    Write-Host "      $pyVersion" -ForegroundColor Green
} catch {
    Write-Error "Python not found. Install Python 3.11+ and add it to PATH."
    exit 1
}

# ── Step 2: Virtual environment ───────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host ""
    Write-Host "[2/6] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    & python -m venv .venv
    Write-Host "      Virtual environment created." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[2/6] Virtual environment already exists (.venv)." -ForegroundColor Green
}

# ── Step 3: Activate venv ────────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/6] Activating virtual environment..." -ForegroundColor Yellow
$activateScript = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Error "Activation script not found: $activateScript"
    exit 1
}
& $activateScript
Write-Host "      Activated." -ForegroundColor Green

# ── Step 4: Install dependencies ─────────────────────────────────────────────
if (-not $SkipInstall) {
    Write-Host ""
    Write-Host "[4/6] Upgrading pip and installing requirements..." -ForegroundColor Yellow
    & python -m pip install --upgrade pip --quiet
    & python -m pip install -r requirements.txt
    Write-Host "      Dependencies installed." -ForegroundColor Green

    # ── Step 5: Install Playwright browser ───────────────────────────────────
    Write-Host ""
    Write-Host "[5/6] Installing Playwright Chromium browser..." -ForegroundColor Yellow
    & python -m playwright install chromium
    Write-Host "      Playwright Chromium installed." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[4/6] Skipping install (-SkipInstall flag set)." -ForegroundColor Yellow
    Write-Host "[5/6] Skipping Playwright install." -ForegroundColor Yellow
}

# ── Step 6: Copy .env if needed ──────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "[6/6] Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "      .env created." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[6/6] .env already exists." -ForegroundColor Green
}

# ── Step 7: Run tests ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Running Unit Tests" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

& python -m pytest tests/unit -v
$unitExit = $LASTEXITCODE

Write-Host ""
Write-Host "-----------------------------------------------------------"
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Running E2E Tests" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

if ($Headed) {
    Write-Host "   (HEADED mode - browser window will open)" -ForegroundColor Magenta
    & python -m pytest tests/e2e -v --headed --base-url $BaseUrl
} else {
    Write-Host "   (headless mode)" -ForegroundColor Gray
    & python -m pytest tests/e2e -v --base-url $BaseUrl
}
$e2eExit = $LASTEXITCODE

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Summary" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

if ($unitExit -eq 0) {
    Write-Host "   PASSED  Unit tests" -ForegroundColor Green
} else {
    Write-Host "   FAILED  Unit tests (exit code $unitExit)" -ForegroundColor Red
}

if ($e2eExit -eq 0) {
    Write-Host "   PASSED  E2E tests" -ForegroundColor Green
} else {
    Write-Host "   FAILED  E2E tests (exit code $e2eExit)" -ForegroundColor Red
}

Write-Host ""

if ($unitExit -eq 0 -and $e2eExit -eq 0) {
    Write-Host "   All tests passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "   Some tests failed. Check output above." -ForegroundColor Red
    exit 1
}
