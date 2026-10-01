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

function Test-ScoreboardProcess([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if (-not $process) { return $false }
    $appPath = Join-Path $PSScriptRoot "scoreboard_app.py"
    return ($process.CommandLine -and
        $process.CommandLine.IndexOf($appPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $process.CommandLine.IndexOf("--web", [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
}

if ($scoreboardPid -and -not (Test-ScoreboardProcess $scoreboardPid)) {
    Write-Warning "Ignoring stale PID $scoreboardPid; it does not belong to this scoreboard."
    $scoreboardPid = $null
}

if (-not $scoreboardPid) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ScoreboardPort/healthz" -TimeoutSec 2
        if ($health.service -eq "scoreboard-web" -and $health.app_dir -and
            [System.IO.Path]::GetFullPath($health.app_dir).TrimEnd('\') -ieq $PSScriptRoot.TrimEnd('\')) {
            $listener = Get-NetTCPConnection -LocalPort $ScoreboardPort -State Listen |
                Select-Object -First 1
            if ($listener -and (Test-ScoreboardProcess $listener.OwningProcess)) {
                $scoreboardPid = $listener.OwningProcess
            }
        }
    } catch {}
}

if (-not $scoreboardPid) {
    $health = $null
    try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ScoreboardPort/healthz" -TimeoutSec 2 } catch {}
    if ($health -and $health.service -eq "scoreboard-web" -and $health.app_dir -and
        [System.IO.Path]::GetFullPath($health.app_dir).TrimEnd('\') -ieq $PSScriptRoot.TrimEnd('\')) {
        throw "Scoreboard is running, but its process could not be verified. Refusing to claim it stopped."
    }
}

if ($scoreboardPid) {
    & taskkill.exe /PID $scoreboardPid /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop scoreboard process $scoreboardPid."
    }
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Scoreboard stopped."
