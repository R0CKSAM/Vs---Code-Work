$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "Restarting Veto Scoreboard Maker..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "stop_scoreboard.ps1")
Start-Sleep -Milliseconds 500
& (Join-Path $PSScriptRoot "start_scoreboard.ps1")
