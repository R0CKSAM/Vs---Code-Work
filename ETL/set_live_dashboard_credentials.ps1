[CmdletBinding(PositionalBinding = $false)]
param(
    [PSCredential]$Credential
)

if ($args.Count -gt 0) {
    throw "Unexpected positional arguments. Run the script without arguments to enter credentials securely."
}

$ErrorActionPreference = "Stop"
$NginxRoot = Join-Path $PSScriptRoot "tools\nginx"
$AuthFile = Join-Path $NginxRoot "conf\live_dashboard.htpasswd"
$ProxyLauncher = Join-Path $PSScriptRoot "run_live_lan_proxy.ps1"

if (-not $Credential) {
    $Credential = Get-Credential -Message "Choose the username and password for the Veto live dashboard"
}
if (-not $Credential) {
    throw "Credential setup was cancelled."
}

$username = $Credential.UserName.Trim()
if (-not $username -or $username.Contains(":")) {
    throw "Username cannot be empty or contain a colon."
}
if ($username -match '[\r\n]') {
    throw "Username cannot contain a line break."
}

$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
    $Credential.Password
)
$plainPassword = $null
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if ([string]::IsNullOrEmpty($plainPassword)) {
        throw "Password cannot be empty."
    }
    if ($plainPassword -match '[\r\n]') {
        throw "Password cannot contain a line break."
    }

    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        $passwordBytes = [Text.Encoding]::UTF8.GetBytes($plainPassword)
        $passwordHash = [Convert]::ToBase64String($sha1.ComputeHash($passwordBytes))
        [Array]::Clear($passwordBytes, 0, $passwordBytes.Length)
    } finally {
        $sha1.Dispose()
    }

    $temporary = "$AuthFile.tmp"
    $line = "${username}:{SHA}$passwordHash`n"
    [IO.File]::WriteAllText($temporary, $line, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $AuthFile -Force
} finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $plainPassword = $null
}

& $ProxyLauncher
Write-Host "Dashboard login updated for user '$username'."
Write-Host "Open: http://192.168.50.126:8080/war-room"
