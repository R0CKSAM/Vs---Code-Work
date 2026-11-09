$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$user = '{0}\{1}' -f $env:USERDOMAIN,$env:USERNAME
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $root 'check_yt4_health.ps1')) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 6)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Veto YouTube Health Check' -Action $action -Trigger @($trigger,$logon) -Settings $settings -Principal $principal -Description 'Every six hours: verify recent YouTube output and restart a stale collector safely.' -Force | Out-Null
Start-ScheduledTask -TaskName 'Veto YouTube Health Check'
Get-ScheduledTaskInfo -TaskName 'Veto YouTube Health Check' | Select-Object LastRunTime,NextRunTime,LastTaskResult
