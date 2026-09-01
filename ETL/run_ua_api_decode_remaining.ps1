param(
    [double]$SleepMinSeconds = 10.0,
    [double]$SleepMaxSeconds = 20.0,
    [int]$InitialDelayMinutes = 15,
    [int]$ApiLimit = 950
)

$ErrorActionPreference = "Stop"
$EtlRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $EtlRoot
$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"
$Lookup = Join-Path $EtlRoot "output\device_decode\ua_decode_lookup_both_all.parquet"
$CrosscheckCache = Join-Path $EtlRoot "data\cache\device_decode\whatmyuseragent_local_verified_crosscheck_cache.parquet"
$SanityOut = Join-Path $EtlRoot "output\device_decode\api_sanity\production_remaining"
$SanityScript = Join-Path $EtlRoot "src\tools\api_sanity_check_ua_statuses.py"
$LookupScript = Join-Path $EtlRoot "src\tools\decode_distinct_ua_lookup.py"
$EnvFile = Join-Path $EtlRoot ".env"

if (Test-Path -LiteralPath $EnvFile) {
    foreach ($Line in Get-Content -LiteralPath $EnvFile) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#") -or -not $Trimmed.Contains("=")) {
            continue
        }
        $Name, $Value = $Trimmed.Split("=", 2)
        $Name = $Name.Trim()
        $Value = $Value.Trim().Trim('"').Trim("'")
        if ($Name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            Set-Item -LiteralPath "Env:$Name" -Value $Value
        }
    }
}

if (-not $env:WHATMYUA_KEY) {
    $env:WHATMYUA_KEY = [Environment]::GetEnvironmentVariable("WHATMYUA_KEY", "User")
}

Write-Host "UA API decode: unknown first, then locally decoded UAs" -ForegroundColor Cyan
Write-Host "This run is resumable. Successful API rows are never requested twice."
Write-Host "Failed or rate-limited rows remain eligible on the next run."
if ($env:WHATMYUA_KEY) {
    Write-Host "WHATMYUA_KEY detected; authenticated API quota will be used." -ForegroundColor Green
} else {
    Write-Host "WHATMYUA_KEY is not set; the public API quota will be used." -ForegroundColor Yellow
}

if ($InitialDelayMinutes -gt 0) {
    $ResumeAt = (Get-Date).AddMinutes($InitialDelayMinutes)
    Write-Host "API returned 429 earlier. Cooling down until $($ResumeAt.ToString('HH:mm:ss'))..." -ForegroundColor Yellow
    Start-Sleep -Seconds ($InitialDelayMinutes * 60)
}

& $Python $SanityScript `
    --lookup $Lookup `
    --statuses "unknown,decoded_local" `
    --api-cache $CrosscheckCache `
    --out-dir $SanityOut `
    --output-prefix "ua_unknown_then_local_api" `
    --api-limit $ApiLimit `
    --api-sleep-min-seconds $SleepMinSeconds `
    --api-sleep-max-seconds $SleepMaxSeconds `
    --api-flush-every 5

if ($LASTEXITCODE -ne 0) {
    throw "UA API decode failed with exit code $LASTEXITCODE"
}

Write-Host "Rebuilding production UA lookup from local and API caches..." -ForegroundColor Cyan
& $Python $LookupScript --api-limit 0
if ($LASTEXITCODE -ne 0) {
    throw "UA lookup rebuild failed with exit code $LASTEXITCODE"
}

Write-Host "UA API decoding and lookup rebuild completed." -ForegroundColor Green
