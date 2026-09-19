[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RuleName = "Veto Recorder TV"
$Nginx = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "tools\nginx\nginx.exe")).Path
$settings = @{
    Enabled = "True"
    Direction = "Inbound"
    Action = "Allow"
    Protocol = "TCP"
    LocalPort = 8070
    RemoteAddress = "192.168.3.34"
    Profile = @("Domain", "Private")
    Program = $Nginx
}
if (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -DisplayName $RuleName @settings
} else {
    New-NetFirewallRule -DisplayName $RuleName @settings | Out-Null
}
Write-Host "Recorder firewall enabled for TV 192.168.3.34 on TCP 8070."
