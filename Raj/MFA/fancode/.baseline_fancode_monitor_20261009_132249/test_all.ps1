param(
    [switch]$Headed,
    [switch]$DiscoveryOnly,
    [switch]$UnitOnly,
    [string]$BaseUrl = "https://www.fancode.com"
)

$ErrorActionPreference = "Continue"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   FanCode Monitor - Test Suite Runner (Phases 0 & 1)" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

$testArgs = @("-v")

if ($Headed) {
    $testArgs += "--headed"
}

if ($UnitOnly) {
    Write-Host "`n▶ Running Unit Tests Only..." -ForegroundColor Yellow
    $testArgs += "tests/unit"
} elseif ($DiscoveryOnly) {
    Write-Host "`n▶ Running Discovery E2E Tests Only..." -ForegroundColor Yellow
    $testArgs += "tests/e2e/test_discovery.py"
} else {
    Write-Host "`n▶ Running Complete Test Suite..." -ForegroundColor Yellow
    $testArgs += "tests"
}

& python -m pytest @testArgs
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "   ALL TESTS PASSED (exit code 0)" -ForegroundColor Green
} else {
    Write-Host "   TESTS FAILED (exit code $exitCode)" -ForegroundColor Red
}
Write-Host "===========================================================" -ForegroundColor Cyan
exit $exitCode
