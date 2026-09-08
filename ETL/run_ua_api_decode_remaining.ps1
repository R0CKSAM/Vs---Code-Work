param(
    [double]$SleepMinSeconds = 4.0,
    [double]$SleepMaxSeconds = 5.0,
    [int]$InitialDelayMinutes = 0,
    [int]$ApiLimit = -1
)

$ErrorActionPreference = "Stop"
$EtlRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $EtlRoot
$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"
$FullDecodeScript = Join-Path $EtlRoot "src\tools\decode_all_distinct_ua_api.py"
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

Write-Host "UA API decode: highest observed request volume first" -ForegroundColor Cyan
Write-Host "This run is resumable. Successful API rows are never requested twice."
Write-Host "Up to three authorized keys are rotated with one global request every $SleepMinSeconds-$SleepMaxSeconds seconds."

if ($InitialDelayMinutes -gt 0) {
    $ResumeAt = (Get-Date).AddMinutes($InitialDelayMinutes)
    Write-Host "API returned 429 earlier. Cooling down until $($ResumeAt.ToString('HH:mm:ss'))..." -ForegroundColor Yellow
    Start-Sleep -Seconds ($InitialDelayMinutes * 60)
}

& $Python $FullDecodeScript `
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
