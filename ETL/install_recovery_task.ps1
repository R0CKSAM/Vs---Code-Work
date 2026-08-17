[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$TaskName = "Veto ETL Daily 7AM IST",
    [datetime]$DailyAt = "07:00",
    [string]$UserId = "$env:USERDOMAIN\$env:USERNAME",
    [ValidateRange(1, 100)]
    [int]$RestartCount = 20,
    [ValidateRange(1, 120)]
    [int]$RestartMinutes = 15
)

if ($args.Count -gt 0) {
    throw "Unexpected positional arguments. Use named parameters such as -TaskName or -DailyAt. Received: $($args -join ' ')"
}

$ErrorActionPreference = "Stop"
$WorkspaceRoot = $PSScriptRoot
$RecoveryScript = Join-Path $WorkspaceRoot "run_recovery_pipeline.ps1"
if (-not (Test-Path -LiteralPath $RecoveryScript)) {
    throw "Recovery runner is missing: $RecoveryScript"
}

$actionArguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $RecoveryScript
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $actionArguments `
    -WorkingDirectory $WorkspaceRoot
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount $RestartCount `
    -RestartInterval (New-TimeSpan -Minutes $RestartMinutes) `
    -Priority 5

$task = New-ScheduledTask `
    -Action $action `
    -Trigger @($dailyTrigger, $logonTrigger) `
    -Principal $principal `
    -Settings $settings `
    -Description "Crash-safe Veto ETL backlog recovery. Runs daily and at Intern logon, oldest missing date first."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
$installed = Get-ScheduledTask -TaskName $TaskName
$info = $installed | Get-ScheduledTaskInfo
[pscustomobject]@{
    TaskName = $installed.TaskName
    State = $installed.State
    UserId = $installed.Principal.UserId
    Triggers = $installed.Triggers.Count
    NextRunTime = $info.NextRunTime
    Action = "$($installed.Actions.Execute) $($installed.Actions.Arguments)"
} | Format-List
