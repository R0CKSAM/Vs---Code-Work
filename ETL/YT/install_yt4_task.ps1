[CmdletBinding()]
param(
    [string]$TaskName = "Veto YouTube YT4 Collector",
    [string]$OutDir = "Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube",
    [int]$IntervalSeconds = 60,
    [int]$RollMinutes = 15
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $root "..\..")
$script = Join-Path $root "YT4.py"
$channels = Join-Path $root "channels.txt"
$pythonw = Join-Path $repoRoot "venv\Scripts\pythonw.exe"
$taskUser = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME

if (-not (Test-Path -LiteralPath $script)) {
    throw "Missing $script"
}
if (-not (Test-Path -LiteralPath $channels)) {
    throw "Missing $channels"
}
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Missing repository Python runner: $pythonw"
}
if ($IntervalSeconds -lt 1) {
    throw "IntervalSeconds must be at least 1."
}
if ($RollMinutes -lt 1) {
    throw "RollMinutes must be at least 1."
}
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$arguments = '"{0}" --interval-seconds {1} --out-dir "{2}" --url-file "{3}" --measurement-mode auto --roll-minutes {4}' -f $script, $IntervalSeconds, $OutDir, $channels, $RollMinutes
$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument $arguments `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId $taskUser `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $taskPrincipal `
    -Description "Quota-independent crash-safe YouTube live audience collector"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Write-Host "Configured data root: $OutDir"
Write-Host "Log:  $(Join-Path $root 'logs\yt4.log')"
