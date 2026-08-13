[CmdletBinding()]
param(
    [string]$TaskName = "Veto YouTube YT4 Collector"
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Scheduled task is not installed."
    exit 1
}
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    Task = $TaskName
    State = $task.State
    LastRun = $info.LastRunTime
    LastResult = $info.LastTaskResult
    NextRun = $info.NextRunTime
} | Format-List

$latest = Get-ChildItem (Join-Path $root "data\source=Youtube") `
    -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".parquet", ".journal" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 5 FullName, Length, LastWriteTime
if ($latest) {
    $latest | Format-Table -AutoSize
} else {
    Write-Host "No data files have been written yet."
}

$log = Join-Path $root "logs\yt4.log"
if (Test-Path -LiteralPath $log) {
    Write-Host "`nLatest log lines:"
    Get-Content -LiteralPath $log -Tail 12
}
