$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdministrator) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -WindowStyle Hidden -Wait
    exit
}

. (Join-Path $PSScriptRoot "scoreboard_settings.ps1")
$ruleName = "Veto Scoreboard Maker TCP $ScoreboardPort"
Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ScoreboardPort -RemoteAddress $AllowedRemoteAddresses -Profile Domain,Private | Out-Null
Write-Host "Firewall access enabled on TCP $ScoreboardPort for: $($AllowedRemoteAddresses -join ', ')" -ForegroundColor Green
