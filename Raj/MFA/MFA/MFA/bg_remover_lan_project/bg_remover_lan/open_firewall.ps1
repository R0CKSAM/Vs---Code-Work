# Run this PowerShell script as Administrator to allow LAN inbound traffic on port 6805
try {
    New-NetFirewallRule -DisplayName "Office AI Background Remover (Port 6805)" `
                        -Direction Inbound `
                        -LocalPort 6805 `
                        -Protocol TCP `
                        -Action Allow
    Write-Host "Successfully opened firewall port 6805 for TCP inbound traffic." -ForegroundColor Green
} catch {
    Write-Host "Failed to open port. Please ensure this PowerShell session is run as Administrator." -ForegroundColor Red
    Write-Host $_.Exception.Message
}
