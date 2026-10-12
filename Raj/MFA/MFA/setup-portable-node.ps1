# setup-portable-node.ps1
# Downloads and sets up official portable Node.js + npm with ZERO admin privileges.

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Downloading Portable Node.js (No Admin Rights Needed)...   " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$zipUrl = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-win-x64.zip"
$zipFile = "D:\MFA\node-portable.zip"
$extractDest = "D:\MFA\node-portable"

if (-not (Test-Path $extractDest)) {
    New-Item -ItemType Directory -Path $extractDest -Force | Out-Null
}

Write-Host "1. Fetching Node.js v20.18.0 (approx 30 MB)..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile

Write-Host "2. Extracting..." -ForegroundColor Yellow
Expand-Archive -Path $zipFile -DestinationPath $extractDest -Force
Remove-Item $zipFile -Force

$nodeDir = "D:\MFA\node-portable\node-v20.18.0-win-x64"

Write-Host "3. Configuring PATH..." -ForegroundColor Yellow
$env:Path = "$nodeDir;" + $env:Path

# Add permanently to User environment variables (no admin needed)
$currentUserPath = [System.Environment]::GetEnvironmentVariable("Path", [System.EnvironmentVariableTarget]::User)
if ($currentUserPath -notlike "*$nodeDir*") {
    [System.Environment]::SetEnvironmentVariable("Path", "$nodeDir;$currentUserPath", [System.EnvironmentVariableTarget]::User)
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Portable Node.js & npm successfully installed!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

& "$nodeDir\node.exe" -v
& "$nodeDir\npm.cmd" -v

Write-Host "`nYou can now run: npm install" -ForegroundColor Cyan
