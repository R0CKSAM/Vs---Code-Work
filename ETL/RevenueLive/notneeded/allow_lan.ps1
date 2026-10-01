param([ValidateRange(1024,65535)][int]$Port=8820, [string[]]$Subnets=@('192.168.50.0/24'))
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'An IT administrator must run this once to permit inbound RevenueLive access. No firewall changes were made.'
}
$name="VETO RevenueLive LAN $Port"
$rule=Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
if ($rule) {
    $rule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Domain,Private -RemoteAddress $Subnets -Protocol TCP -LocalPort $Port | Out-Null
} else {
    New-NetFirewallRule -DisplayName $name -Enabled True -Direction Inbound -Action Allow -Profile Domain,Private -RemoteAddress $Subnets -Protocol TCP -LocalPort $Port | Out-Null
}
Write-Host "RevenueLive port $Port permitted for: $($Subnets -join ', ') on Domain/Private networks."
