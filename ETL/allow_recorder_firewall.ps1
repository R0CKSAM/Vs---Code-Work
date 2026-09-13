[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RuleName = 'Veto Recorder LAN'
$Nginx = Join-Path $PSScriptRoot 'tools\nginx\nginx.exe'
$Networks = @('192.168.50.0/24', '192.168.55.0/24', '192.168.56.0/24')
if (!(Test-Path -LiteralPath $Nginx)) { throw "Nginx not found: $Nginx" }
if (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Direction Inbound `
        -Action Allow -Profile Domain,Private -Protocol TCP -LocalPort 8070 `
        -RemoteAddress $Networks -Program $Nginx | Out-Null
} else {
    New-NetFirewallRule -DisplayName $RuleName -Enabled True -Direction Inbound `
        -Action Allow -Profile Domain,Private -Protocol TCP -LocalPort 8070 `
        -RemoteAddress $Networks -Program $Nginx | Out-Null
}
Write-Host 'Recorder firewall rule ready: TCP 8070 for subnets 50, 55, 56.'
