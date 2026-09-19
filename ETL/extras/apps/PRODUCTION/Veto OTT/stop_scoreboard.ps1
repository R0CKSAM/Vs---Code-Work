$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot "scoreboard_settings.ps1")

$pidFile = Join-Path $PSScriptRoot "data\scoreboard.pid"
$scoreboardPid = $null
if (Test-Path -LiteralPath $pidFile) {
    $storedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($storedPid -match '^\d+$') {
        $scoreboardPid = [int]$storedPid
    }
}

if (-not $scoreboardPid) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ScoreboardPort/healthz" -TimeoutSec 2
        if ($health.service -eq "scoreboard-web") {
            $listener = Get-NetTCPConnection -LocalPort $ScoreboardPort -State Listen |
                Select-Object -First 1
            if ($listener) { $scoreboardPid = $listener.OwningProcess }
        }
    } catch {}
}

if ($scoreboardPid -and (Get-Process -Id $scoreboardPid -ErrorAction SilentlyContinue)) {
    & taskkill.exe /PID $scoreboardPid /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop scoreboard process $scoreboardPid."
    }
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Scoreboard stopped."
