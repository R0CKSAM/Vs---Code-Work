param(
    [switch]$Headed
)

$ErrorActionPreference = "Continue"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   FanCode Monitor - Phase 2 Setup & Test Runner" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

# 1. Install missing packages with python -m pip --user
Write-Host "`n[1/3] Installing SQLAlchemy, FastAPI, and Uvicorn via python -m pip..." -ForegroundColor Yellow

$pkgs = @("sqlalchemy>=2.0.0", "fastapi>=0.100.0", "uvicorn>=0.22.0")

foreach ($p in $pkgs) {
    Write-Host "   Installing $p..." -ForegroundColor DarkGray
    & python -m pip install $p --user --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   OK: $p" -ForegroundColor Green
    } else {
        Write-Host "   Trying without --user for $p..." -ForegroundColor Yellow
        & python -m pip install $p --quiet 2>&1
    }
}

# Verify imports
Write-Host "`n[2/3] Verifying imports..." -ForegroundColor Yellow
$modules = @("sqlalchemy", "fastapi", "uvicorn")
$allOk = $true
foreach ($m in $modules) {
    $res = & python -c "import $m; print('  OK:', '$m')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   $res" -ForegroundColor Green
    } else {
        Write-Host "   MISSING: $m" -ForegroundColor Red
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-Host "`nFailed to import required libraries. Please check error output above." -ForegroundColor Red
    exit 1
}

# Initialize Database
Write-Host "`n[3/3] Initializing SQLite database..." -ForegroundColor Yellow
& python -m app.database

# Run pytest
Write-Host "`n===========================================================" -ForegroundColor Cyan
Write-Host "   Running Complete Regression Suite" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

$testArgs = @("-v")
if ($Headed) {
    $testArgs += "--headed"
}

& python -m pytest @testArgs
$exitCode = $LASTEXITCODE

Write-Host "`n===========================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "   ALL TESTS PASSED!" -ForegroundColor Green
} else {
    Write-Host "   SOME TESTS FAILED (exit code $exitCode)" -ForegroundColor Red
}
Write-Host "===========================================================" -ForegroundColor Cyan
exit $exitCode
