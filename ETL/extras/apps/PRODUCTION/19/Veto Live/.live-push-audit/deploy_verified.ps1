$ErrorActionPreference = 'Stop'
$destination = 'D:\Veto OTT'
$expected = @{
    'scoreboard_app.py' = 'A45C9940653C9CFBAA2EE90D62906634CE52FF750A641905320F989FC2C2DB1B'
    'scoreboard_web.py' = 'E27AB03875404752D46ACF532B49518270FE46A1A77D8327D1633DDE00A240DD'
    'scoreboard_media.py' = '9C3097EF8C946922EEA00319AADD33C7060E33E6F163ED7756F49F320EBD3BA3'
    'scoreboard_web.html' = 'B6B2D484CB80D68C7890CEABACF7DA72C7A7D04A49D22A890CFE9057068B5064'
}
foreach ($name in $expected.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $destination $name)).Hash -ne $expected[$name]) {
        throw "Production file changed during testing: $name. Deployment cancelled."
    }
}
$status = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/live/status' -TimeoutSec 5
if ($status.active) { throw 'SDI is active. Deployment cancelled without stopping output.' }
$backup = Join-Path $destination ('backups\live-push-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($name in $expected.Keys) {
    Copy-Item -LiteralPath (Join-Path $destination $name) -Destination (Join-Path $backup $name)
}
$status = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/live/status' -TimeoutSec 5
if ($status.active) { throw 'SDI became active. Deployment cancelled without stopping output.' }
& (Join-Path $destination 'stop_scoreboard.ps1')
try {
    foreach ($name in $expected.Keys) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $destination $name) -Force
        if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash -ne
                (Get-FileHash -LiteralPath (Join-Path $destination $name)).Hash) {
            throw "Deployment verification failed: $name"
        }
    }
    & (Join-Path $destination 'start_scoreboard.ps1')
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/live/status' -TimeoutSec 5
    if (-not $status.PSObject.Properties['program_dynamic']) {
        throw 'Server did not load the updated output status API.'
    }
    Write-Output "Backup: $backup"
    Write-Output ($status | ConvertTo-Json -Compress)
} catch {
    $failure = $_
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/live/status' -TimeoutSec 5
    } catch {
        throw "Deployment verification failed and output status is unknown. No automatic stop or rollback attempted. Backup: $backup"
    }
    if ($status.active) {
        throw "Deployment verification failed but SDI is active. No automatic stop or rollback attempted. Backup: $backup"
    }
    & (Join-Path $destination 'stop_scoreboard.ps1')
    foreach ($name in $expected.Keys) {
        Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $destination $name) -Force
    }
    & (Join-Path $destination 'start_scoreboard.ps1')
    throw $failure
}
