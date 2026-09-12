$ErrorActionPreference = "SilentlyContinue"
Set-Location -LiteralPath $PSScriptRoot
$pidFile = Join-Path $PSScriptRoot "data\scoreboard.pid"
if (Test-Path -LiteralPath $pidFile) {
    $scoreboardPid = [int](Get-Content -LiteralPath $pidFile -Raw)
    & taskkill.exe /PID $scoreboardPid /T /F | Out-Null
    Remove-Item -LiteralPath $pidFile -Force
}
Write-Host "Scoreboard stopped."
