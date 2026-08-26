[CmdletBinding()]
param(
    [string]$TaskName = "Veto YouTube YT4 Collector",
    [string]$OutDir = "Z:\Veto Logs Backup\DO NOT DELETE\source=Youtube",
    [int]$IntervalSeconds = 60,
    [int]$RollMinutes = 15
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "YT4.py"
$requirements = Join-Path $root "requirements-yt4.txt"
$channels = Join-Path $root "channels.txt"
$envFile = Join-Path $root ".env"
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$pythonw = Join-Path $venv "Scripts\pythonw.exe"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator, then run this installer again."
}
if (-not (Test-Path -LiteralPath $script)) {
    throw "Missing $script"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Create $envFile from .env.example and set YOUTUBE_API_KEY first."
}
if (-not (Select-String -LiteralPath $envFile -Pattern '^\s*(YOUTUBE_API_KEY|YOUTUBE_DATA_API_KEY)\s*=\s*\S+' -Quiet)) {
    throw "$envFile does not contain a non-empty YouTube API key."
}
if (-not (Test-Path -LiteralPath $channels)) {
    throw "Missing $channels"
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

if (-not (Test-Path -LiteralPath $python)) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3 -m venv $venv
    } else {
        $systemPython = Get-Command python.exe -ErrorAction Stop
        & $systemPython.Source -m venv $venv
    }
}

& $python -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed with exit code $LASTEXITCODE."
}

$arguments = '"{0}" --interval-seconds {1} --out-dir "{2}" --url-file "{3}" --roll-minutes {4}' -f $script, $IntervalSeconds, $OutDir, $channels, $RollMinutes
$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument $arguments `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $taskPrincipal `
    -Description "Crash-safe 15-minute YouTube live audience collector"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Write-Host "Data: $(Join-Path $root 'data\source=Youtube')"
Write-Host "Configured data root: $OutDir"
Write-Host "Log:  $(Join-Path $root 'logs\yt4.log')"
