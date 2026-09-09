[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RuleName = "Veto Live Dashboard LAN"
$Nginx = Join-Path $PSScriptRoot "tools\nginx\nginx.exe"
$AllowedNetworks = @("192.168.50.0/24", "192.168.55.0/24","192.168.56.0/24" )

if (-not (Test-Path -LiteralPath $Nginx)) {
    throw "Nginx was not found at $Nginx"
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Action Allow `
        -Direction Inbound -Profile Domain,Private -RemoteAddress $AllowedNetworks `
        -ErrorAction Stop
    Write-Host "Firewall rule updated: $RuleName"
} else {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 8090 -Profile Domain,Private -RemoteAddress $AllowedNetworks `
        -Program $Nginx -ErrorAction Stop | Out-Null
    Write-Host "Firewall rule created: $RuleName"
}
