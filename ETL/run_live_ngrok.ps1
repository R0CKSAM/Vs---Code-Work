param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$EtlRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ngrok = Join-Path $EtlRoot "tools\ngrok.exe"
$EnvFile = Join-Path $EtlRoot ".env"
$HealthUrl = "http://127.0.0.1:$Port/healthz"
$DashboardUrl = "http://127.0.0.1:$Port/war-room"

if (-not (Test-Path -LiteralPath $Ngrok)) {
    throw "ngrok.exe was not found at $Ngrok"
}

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

$null = & $Ngrok config check 2>&1
$NgrokConfigReady = $LASTEXITCODE -eq 0
if (-not $env:NGROK_AUTHTOKEN -and -not $NgrokConfigReady) {
    throw "ngrok authentication is missing. Run ngrok config add-authtoken or add NGROK_AUTHTOKEN to ETL\.env."
}

try {
    $Health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    if ($Health.StatusCode -ne 200) {
        throw "Health endpoint returned HTTP $($Health.StatusCode)."
    }
}
catch {
    throw "The nginx live-dashboard proxy is not healthy at $HealthUrl. Start the live LAN proxy first. $($_.Exception.Message)"
}

$AuthStatus = 0
try {
    $Response = Invoke-WebRequest `
        -Uri $DashboardUrl `
        -UseBasicParsing `
        -MaximumRedirection 0 `
        -TimeoutSec 5
    $AuthStatus = [int]$Response.StatusCode
}
catch {
    if ($_.Exception.Response) {
        $AuthStatus = [int]$_.Exception.Response.StatusCode
    }
}
if ($AuthStatus -ne 401) {
    throw "Refusing to publish: $DashboardUrl returned HTTP $AuthStatus instead of requiring authentication (401)."
}

$Existing = Get-Process -Name "ngrok" -ErrorAction SilentlyContinue
if ($Existing) {
    throw "An ngrok process is already running (PID $($Existing.Id -join ', ')). Stop it before starting another tunnel."
}

Write-Host "Local dashboard authentication verified." -ForegroundColor Green
Write-Host "Starting an HTTPS ngrok endpoint for http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "Open the HTTPS forwarding URL shown below and append /war-room#audience" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop public access."

& $Ngrok http "http://127.0.0.1:$Port" --log stdout --log-format term
if ($LASTEXITCODE -ne 0) {
    throw "ngrok exited with code $LASTEXITCODE"
}
