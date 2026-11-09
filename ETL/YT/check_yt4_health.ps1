[CmdletBinding()]
param(
    [string]$TaskName = 'Veto YouTube YT4 Collector',
    [string]$OutDir = 'Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube',
    [int]$StaleMinutes = 20,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $root 'state\yt4_health.json'
$mutex = New-Object System.Threading.Mutex($false, 'Local\VetoYT4HealthCheck')
if (-not $mutex.WaitOne(0)) { $mutex.Dispose(); exit 0 }
function Get-RecentOutput {
    $now = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromMinutes(330))
    $files = foreach ($offset in @(0, -1)) {
        $day = $now.AddDays($offset)
        $dir = Join-Path $OutDir ('year={0:yyyy}\month={0:MM}\day={0:dd}' -f $day)
        if (Test-Path -LiteralPath $dir) {
            Get-ChildItem -LiteralPath $dir -File | Where-Object { $_.Length -gt 0 -and $_.Extension -in '.journal','.parquet' }
        }
    }
    $files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
}
try {
    $result = [ordered]@{ checked_at_ist=[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromMinutes(330)).ToString('o'); status='checking'; action='none' }
    # A disconnected archive is not proof that the collector is stuck.
    if (-not (Test-Path -LiteralPath $OutDir)) { throw 'YouTube output drive unavailable; collector left untouched.' }
    $task = Get-ScheduledTask -TaskName $TaskName
    $latest = Get-RecentOutput
    $fresh = $latest -and $latest.LastWriteTimeUtc -ge [DateTime]::UtcNow.AddMinutes(-$StaleMinutes)
    $result.latest_output = if ($latest) { $latest.FullName } else { $null }
    $result.latest_write_utc = if ($latest) { $latest.LastWriteTimeUtc.ToString('o') } else { $null }
    $result.task_state = [string]$task.State
    if ($fresh) { $result.status = 'healthy' }
    elseif ($CheckOnly) { $result.status = 'stale' }
    else {
        # Stop only this scheduled collector; its journal is recovered on startup.
        if ($task.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $TaskName
            for ($i=0; $i -lt 15; $i++) {
                if ((Get-ScheduledTask -TaskName $TaskName).State -ne 'Running') { break }
                Start-Sleep -Seconds 1
            }
            if ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Running') { throw 'Collector did not stop; refusing a duplicate start.' }
        }
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        $started = [DateTime]::UtcNow
        Start-ScheduledTask -TaskName $TaskName
        $result.action = 'restart'
        $result.status = 'restart_unverified'
        for ($i=0; $i -lt 12; $i++) {
            Start-Sleep -Seconds 10
            $after = Get-RecentOutput
            if ($after -and $after.LastWriteTimeUtc -gt $started) {
                $result.status = 'recovered'
                $result.latest_output = $after.FullName
                $result.latest_write_utc = $after.LastWriteTimeUtc.ToString('o')
                break
            }
        }
    }
} catch {
    $result.status = 'error'
    $result.error = $_.Exception.Message
} finally {
    New-Item -ItemType Directory -Path (Join-Path $root 'state') -Force | Out-Null
    $json = $result | ConvertTo-Json
    $json | Set-Content -LiteralPath ($statePath + '.tmp') -Encoding UTF8
    Move-Item -LiteralPath ($statePath + '.tmp') -Destination $statePath -Force
    Add-Content -LiteralPath (Join-Path $root 'logs\yt4-health.log') -Value ($result | ConvertTo-Json -Compress)
    Write-Output $json
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
if ($result.status -in 'error','restart_unverified','stale') { exit 1 }
