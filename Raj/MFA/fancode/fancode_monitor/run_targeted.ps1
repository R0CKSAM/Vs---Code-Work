param(
    [switch]$Headed,
    [string]$BaseUrl = "https://www.fancode.com"
)

$ErrorActionPreference = "Continue"   # don't abort on non-fatal errors
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   FanCode Monitor - Phase 0 (targeted install runner)" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan

# ── Helper: run pip for a single package, show result ────────────────────────
function Install-Package {
    param([string]$Pkg, [string[]]$ExtraArgs = @())
    Write-Host "   pip install $Pkg $ExtraArgs" -ForegroundColor DarkGray
    & python -m pip install $Pkg @ExtraArgs --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   OK: $Pkg" -ForegroundColor Green
    } else {
        Write-Host "   WARN: $Pkg may have had an issue (exit $LASTEXITCODE)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[1/4] Python:" -ForegroundColor Yellow
& python --version

# ── Step 2: install ONLY the missing packages one-by-one ─────────────────────
# We skip greenlet and playwright (already installed, files are locked).
# --no-deps prevents pip from touching greenlet as a dependency.
Write-Host ""
Write-Host "[2/4] Installing missing packages individually..." -ForegroundColor Yellow

# Pure-Python packages - no binary deps, no permission issues
Install-Package "pydantic-settings>=2.1.0" @("--user")
Install-Package "iniconfig>=1.0.1"         @("--user")
Install-Package "pluggy<2,>=1.5"           @("--user")
Install-Package "text-unidecode>=1.3"      @("--user")
Install-Package "python-slugify>=6.0.0"    @("--user")
Install-Package "pytest-base-url>=1.0.0"   @("--user", "--no-deps")

# pytest itself (pure Python)
Install-Package "pytest>=7.4.0"            @("--user")

# pytest-playwright with --no-deps so pip never touches greenlet
Install-Package "pytest-playwright>=0.4.3" @("--user", "--no-deps")

Write-Host ""
Write-Host "   Verifying imports..." -ForegroundColor Yellow
$checks = @(
    "pydantic_settings",
    "playwright",
    "pytest",
    "pytest_playwright"
)
$allOk = $true
foreach ($mod in $checks) {
    $result = & python -c "import $mod; print('  OK:', '$mod')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   $result" -ForegroundColor Green
    } else {
        Write-Host "   MISSING: $mod" -ForegroundColor Red
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-Host ""
    Write-Host "   One or more imports failed. Cannot continue." -ForegroundColor Red
    exit 1
}

# ── Step 3: Playwright Chromium browser ───────────────────────────────────────
Write-Host ""
Write-Host "[3/4] Installing Playwright Chromium browser..." -ForegroundColor Yellow
& python -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Playwright browser install may have failed - check above" -ForegroundColor Yellow
}

# ── Step 4: Copy .env ─────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "   .env created from .env.example" -ForegroundColor Green
}

# ── Step 5: Run tests ─────────────────────────────────────────────────────────
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

$e2eCmd = @("tests/e2e", "-v", "--base-url", $BaseUrl)
if ($Headed) {
    Write-Host "   Mode: HEADED (browser window will open)" -ForegroundColor Magenta
    $e2eCmd += "--headed"
} else {
    Write-Host "   Mode: headless" -ForegroundColor Gray
}
& python -m pytest @e2eCmd
$e2eExit = $LASTEXITCODE

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "   Summary" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
if ($unitExit -eq 0) { Write-Host "   PASSED  Unit tests" -ForegroundColor Green }
else                  { Write-Host "   FAILED  Unit tests  (exit $unitExit)" -ForegroundColor Red }
if ($e2eExit -eq 0)   { Write-Host "   PASSED  E2E tests" -ForegroundColor Green }
else                   { Write-Host "   FAILED  E2E tests   (exit $e2eExit)" -ForegroundColor Red }
Write-Host ""

if ($unitExit -eq 0 -and $e2eExit -eq 0) { exit 0 } else { exit 1 }
