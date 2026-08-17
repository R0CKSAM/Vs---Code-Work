[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)][datetime[]]$Dates,
    [string]$StreamRemoteRoot = "veto:veto-stream-logs/veto-stream-logs",
    [string]$FastRemoteRoot = "veto:veto-stream-logs/veto-fast-logs",
    [string]$RawRoot = "",
    [string]$StreamLocalName = "Veto Stream Backup",
    [string]$FastLocalName = "Veto fast Backup",
    [string]$RcloneExe = "",
    [string]$RcloneConfig = "",
    [string]$DownloadLogRoot = "",
    [string]$DownloadResultRoot = "",
    [ValidateRange(1, 6)][int]$MaxParallelDownloads = 6,
    [ValidateRange(1, 128)][int]$Transfers = 16,
    [ValidateRange(1, 256)][int]$Checkers = 32,
    [ValidateRange(0, 16)][int]$MultiThreadStreams = 4,
    [string]$BufferSize = "16M",
    [ValidateRange(1, 20)][int]$VerifyRetries = 3,
    [ValidateRange(0, 120)][int]$VerifyWaitMinutes = 0,
    [switch]$WaitForRemoteStable,
    [ValidateRange(1, 20)][int]$StableChecks = 2,
    [ValidateRange(1, 120)][int]$StableWaitMinutes = 10,
    [switch]$SkipVerifyAfterSync
)

$ErrorActionPreference = "Stop"
$workspaceRoot = $PSScriptRoot
$workerScript = Join-Path $workspaceRoot "sync_daily_source.ps1"
$defaultDataRoot = Join-Path $workspaceRoot "data"
$resolvedRawRoot = if ($RawRoot) { $RawRoot } else { Join-Path $defaultDataRoot "raw\Veto Logs Backup" }
$resolvedRclone = if ($RcloneExe) { $RcloneExe } else { Join-Path $workspaceRoot "tools\rclone\rclone.exe" }
$portableConfig = Join-Path $workspaceRoot "config\rclone.conf"
$resolvedConfig = if ($RcloneConfig) { $RcloneConfig } elseif (Test-Path -LiteralPath $portableConfig) { $portableConfig } else { "" }
$logRoot = if ($DownloadLogRoot) { $DownloadLogRoot } else { Join-Path $workspaceRoot "output\logs\downloads" }
$resultRoot = if ($DownloadResultRoot) { $DownloadResultRoot } else { Join-Path $workspaceRoot "output\state\downloads" }

if (-not (Test-Path -LiteralPath $workerScript)) { throw "Download worker is missing: $workerScript" }
if (-not (Test-Path -LiteralPath $resolvedRclone)) {
    $rcloneCommand = Get-Command -Name $resolvedRclone -CommandType Application -ErrorAction SilentlyContinue
    if (-not $rcloneCommand) { throw "rclone executable is missing: $resolvedRclone" }
    $resolvedRclone = $rcloneCommand.Source
}
if (-not $Dates.Count) { throw "At least one download date is required." }
New-Item -ItemType Directory -Path $resolvedRawRoot, $logRoot, $resultRoot -Force | Out-Null

$tasks = New-Object System.Collections.Generic.List[object]
foreach ($dateValue in @($Dates | Sort-Object -Unique)) {
    if ($dateValue.Date -ge (Get-Date).Date) { throw "Download date must be before today: $($dateValue.ToString('yyyy-MM-dd'))" }
    $month = $dateValue.ToString("MM")
    $day = $dateValue.ToString("dd")
    $iso = $dateValue.ToString("yyyy-MM-dd")
    foreach ($sourceConfig in @(
        [pscustomobject]@{ Source = "stream"; RemoteRoot = $StreamRemoteRoot; LocalName = $StreamLocalName },
        [pscustomobject]@{ Source = "fast"; RemoteRoot = $FastRemoteRoot; LocalName = $FastLocalName }
    )) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
        $tasks.Add([pscustomobject]@{
            Name = "$($sourceConfig.Source)_$($dateValue.ToString('yyyyMMdd'))"
            Arguments = @{
                Source = $sourceConfig.Source
                Date = $dateValue.Date
                RemotePath = "$($sourceConfig.RemoteRoot.TrimEnd('/'))/$month/$day"
                LocalPath = Join-Path (Join-Path $resolvedRawRoot $sourceConfig.LocalName) (Join-Path $month $day)
                RcloneExe = $resolvedRclone
                RcloneConfig = $resolvedConfig
                LogPath = Join-Path $logRoot ("download_{0}_{1}_{2}.log" -f $iso, $sourceConfig.Source, $stamp)
                ResultPath = Join-Path $resultRoot ("{0}_{1}.json" -f $iso, $sourceConfig.Source)
                Transfers = $Transfers
                Checkers = $Checkers
                MultiThreadStreams = $MultiThreadStreams
                BufferSize = $BufferSize
                VerifyRetries = $VerifyRetries
                VerifyWaitMinutes = $VerifyWaitMinutes
                WaitForRemoteStable = $WaitForRemoteStable.IsPresent
                StableChecks = $StableChecks
                StableWaitMinutes = $StableWaitMinutes
                SkipVerifyAfterSync = $SkipVerifyAfterSync.IsPresent
            }
        })
    }
}

Write-Host "[$(Get-Date -Format o)] Prefetch queue: $($tasks.Count) source/date downloads; max parallel=$MaxParallelDownloads; each transfers=$Transfers, checkers=$Checkers."
$failures = New-Object System.Collections.Generic.List[string]
for ($offset = 0; $offset -lt $tasks.Count; $offset += $MaxParallelDownloads) {
    $last = [Math]::Min($tasks.Count - 1, $offset + $MaxParallelDownloads - 1)
    $batch = @($tasks[$offset..$last])
    $jobs = @()
    foreach ($task in $batch) {
        Write-Host "[$(Get-Date -Format o)] Starting download job $($task.Name)."
        $jobs += Start-Job -Name $task.Name -ArgumentList $workerScript, $task.Arguments -ScriptBlock {
            param($ScriptPath, $WorkerArguments)
            & $ScriptPath @WorkerArguments
        }
    }

    Wait-Job -Job $jobs | Out-Null
    foreach ($job in $jobs) {
        $jobOutput = Receive-Job -Job $job -ErrorAction SilentlyContinue 2>&1
        if ($jobOutput) { $jobOutput | ForEach-Object { Write-Host $_ } }
        $task = $batch | Where-Object { $_.Name -eq $job.Name } | Select-Object -First 1
        $result = $null
        if ($task -and (Test-Path -LiteralPath $task.Arguments.ResultPath)) {
            try { $result = Get-Content -Raw -LiteralPath $task.Arguments.ResultPath | ConvertFrom-Json } catch {}
        }
        if ($job.State -ne "Completed" -or -not $result -or $result.status -ne "complete" -or (-not $SkipVerifyAfterSync -and $result.verified -ne $true)) {
            $reason = if ($result -and $result.error) { $result.error } else { "job state=$($job.State)" }
            $failures.Add("$($job.Name): $reason")
        }
        Remove-Job -Job $job -Force
    }
    if ($failures.Count) { break }
}

if ($failures.Count) {
    throw "Parallel prefetch failed: $($failures -join '; ')"
}
Write-Host "[$(Get-Date -Format o)] Parallel prefetch completed for all $($tasks.Count) source/date downloads."
