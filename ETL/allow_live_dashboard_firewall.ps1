[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RuleName = "Veto Live Dashboard LAN"
$Nginx = Join-Path $PSScriptRoot "tools\nginx\nginx.exe"

if (-not (Test-Path -LiteralPath $Nginx)) {
    throw "Nginx was not found at $Nginx"
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Action Allow `
        -Direction Inbound -Profile Domain,Private -RemoteAddress LocalSubnet `
        -ErrorAction Stop
    Write-Host "Firewall rule updated: $RuleName"
} else {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 8080 -Profile Domain,Private -RemoteAddress LocalSubnet `
        -Program $Nginx -ErrorAction Stop | Out-Null
    Write-Host "Firewall rule created: $RuleName"
}
