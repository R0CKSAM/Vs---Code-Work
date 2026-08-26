param(
    [string]$RemoteRoot = "veto:veto-stream-logs/veto-stream-logs",
    [string]$StreamRemoteRoot = "veto:veto-stream-logs/veto-stream-logs",
    [string]$FastRemoteRoot = "veto:veto-stream-logs/veto-fast-logs",
    [string]$LocalRoot = "",
    [string]$RawRoot = "",
    [string]$OverviewLakeRoot = "",
    [string]$OverviewSources = "fast,stream",
    [string]$StreamLocalName = "Veto Stream Backup",
    [string]$FastLocalName = "Veto fast Backup",
    [string]$PrefsFile = "",
    [string]$VenvPython = "",
    [Nullable[datetime]]$Date = $null,
    [int]$LookbackDays = 1,
    [int]$StableChecks = 2,
    [int]$StableWaitMinutes = 10,
    [int]$VerifyRetries = 3,
    [int]$VerifyWaitMinutes = 0,
    [switch]$WaitForRemoteStable,
    [int]$PostVerifyDelaySeconds = 60,
    [switch]$SkipRemoteStableCheck,
    [switch]$SkipVerifyAfterSync,
    [switch]$SkipPostVerifyDelay,
    [switch]$SkipDownload,
    [ValidateRange(1, 6)]
    [int]$MaxParallelDownloads = 2,
    [ValidateRange(1, 128)]
    [int]$DownloadTransfers = 16,
    [ValidateRange(1, 256)]
    [int]$DownloadCheckers = 32,
    [switch]$SkipWatch,
    [switch]$SkipOverview,
    [switch]$SkipUaProfile,
    # Keep the daily path bounded; use -UaApiLimit -1 only for a deliberate backlog run.
    [int]$UaApiLimit = 25,
    [switch]$SkipUaMalformedApi,
    [switch]$RunDeviceDecode,
    [switch]$StrictPipeline,
    [switch]$SingleSourceMode,
    # Aggressive workstation defaults: tuned for the 6-core / 12-thread, 32 GB ETL host.
    # Every value remains overridable for a constrained or concurrent run.
    [int]$Etl1Workers = 12,
    [int]$StageThreads = 12,
    [string]$StageMemory = "24GB",
    [string]$StageMaxTempSize = "200GB",
    [int]$DeepProfileThreads = 12,
    [string]$DeepProfileMemory = "22GB",
    [string]$DeepProfileMaxTempSize = "200GB",
    [string]$DeepProfileTempDir = "",
    [int]$ConcurrencyThreads = 12,
    [string]$ConcurrencyMemory = "22GB",
    [int]$LatencyThreads = 12,
    [string]$LatencyMemory = "22GB",
    [int]$IdentityThreads = 12,
    [string]$IdentityMemory = "22GB",
    [int]$ContentThreads = 12,
    [string]$ContentMemory = "22GB",
    [switch]$KeepProcessedInputs,
    [string]$ArchiveLakeRoot = "Z:\Veto Logs Backup\DO NOT DELETE",
    # Keep the D+1 IST spillover partition hot so the next daily run can merge into it.
    [ValidateRange(1, 31)]
    [int]$HotLakeRetentionDays = 1,
    [switch]$SkipLakeArchive,
    [ValidateSet("zstd", "snappy", "lz4", "gzip", "brotli", "none")]
    [string]$Etl1Compression = "snappy",
    [ValidateSet("zstd", "snappy", "lz4", "none")]
    [string]$StageCompression = "snappy"
)

if ($args.Count -gt 0) {
    throw "Unexpected positional arguments. Use named parameters such as -Date YYYY-MM-DD. Received: $($args -join ' ')"
}

foreach ($remoteValue in @($RemoteRoot, $StreamRemoteRoot, $FastRemoteRoot)) {
    if (-not $remoteValue -or $remoteValue.StartsWith("-") -or $remoteValue -notmatch "^[^\\/:]+:.+") {
        throw "Invalid rclone remote root parameter: '$remoteValue'"
    }
}
foreach ($configuredPath in @($LocalRoot, $RawRoot, $OverviewLakeRoot, $PrefsFile, $VenvPython, $DeepProfileTempDir, $ArchiveLakeRoot)) {
    if ($configuredPath -and $configuredPath.StartsWith("-")) {
        throw "Invalid path parameter: '$configuredPath'"
    }
}

$ErrorActionPreference = "Stop"
$WorkspaceRoot = $PSScriptRoot
if ($LocalRoot) {
    $DefaultLocalRoot = $LocalRoot
} elseif (Test-Path (Join-Path $WorkspaceRoot "data\lake")) {
    $DefaultLocalRoot = Join-Path $WorkspaceRoot "data"
} elseif (Test-Path (Join-Path $WorkspaceRoot "lake")) {
    $DefaultLocalRoot = $WorkspaceRoot
} else {
    $DefaultLocalRoot = Join-Path $WorkspaceRoot "data"
}
$RawBaseRoot = if ($RawRoot) {
    $RawRoot
} else {
    Join-Path $DefaultLocalRoot "raw\Veto Logs Backup"
}
$DefaultVenvPython = if ($VenvPython) {
    $VenvPython
} elseif (Test-Path (Join-Path $WorkspaceRoot "venv\Scripts\python.exe")) {
    Join-Path $WorkspaceRoot "venv\Scripts\python.exe"
} elseif (Test-Path (Join-Path (Split-Path $WorkspaceRoot -Parent) "venv\Scripts\python.exe")) {
    Join-Path (Split-Path $WorkspaceRoot -Parent) "venv\Scripts\python.exe"
} else {
    "python"
}
$env:VG_ETL_BASE = $DefaultLocalRoot
$DefaultOverviewLakeRoot = if ($OverviewLakeRoot) {
    $OverviewLakeRoot
} elseif ($env:VG_OVERVIEW_LAKE_ROOT) {
    $env:VG_OVERVIEW_LAKE_ROOT
} else {
    Join-Path $DefaultLocalRoot "lake"
}
$env:VG_OVERVIEW_LAKE_ROOT = $DefaultOverviewLakeRoot
$env:VG_OVERVIEW_SOURCES = $OverviewSources
$PreferredSharedTempRoot = "Z:\Veto Logs Backup\DO NOT DELETE\Temp"
$PreferredSharedTempDir = Join-Path $PreferredSharedTempRoot "VetoETL\duckdb\deep_profile"
$DefaultTempCandidates = @()
if ($env:VG_DUCKDB_TEMP_DIR) {
    $DefaultTempCandidates += $env:VG_DUCKDB_TEMP_DIR
}
$DefaultTempCandidates += "\\192.168.50.11\analysis team\Veto Logs Backup\etl_temp\deep_profile"
$DefaultTempCandidates += "Z:\Veto Logs Backup\etl_temp\deep_profile"
$DefaultTempCandidates += (Join-Path $WorkspaceRoot "output\cache\duckdb_temp\deep_profile")
if ($env:LOCALAPPDATA) {
    $DefaultTempCandidates += (Join-Path $env:LOCALAPPDATA "VetoETL\duckdb_temp\deep_profile")
}

function Get-TempCandidateFreeBytes {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        $root = [System.IO.Path]::GetPathRoot($Path)
        if (-not $root) { return -1 }
        if ($root.StartsWith("\\")) {
            # UNC free-space reporting is unreliable and previously used MaxValue,
            # which forced every automatic run onto the network share. Keep a
            # reachable share as a last-resort candidate without outranking local disk.
            if (-not (Test-Path $root)) { return -1 }
            return 0
        }
        if (-not (Test-Path $root)) { return -1 }
        $drive = [System.IO.DriveInfo]::new($root)
        if ($drive.DriveType -eq [System.IO.DriveType]::Network) {
            return 0
        }
        return $drive.AvailableFreeSpace
    } catch {
        return -1
    }
}

function Resolve-DefaultDuckDbTempDir {
    param([string[]]$Candidates)

    $bestPath = $null
    $bestFree = -1
    foreach ($candidate in $Candidates) {
        if (-not $candidate) { continue }
        $free = Get-TempCandidateFreeBytes -Path $candidate
        if ($free -gt $bestFree) {
            $bestPath = $candidate
            $bestFree = $free
        }
    }
    if ($bestPath) { return $bestPath }
    return (Join-Path $WorkspaceRoot "output\cache\duckdb_temp\deep_profile")
}

$DefaultDeepProfileTempDir = if ($DeepProfileTempDir) {
    $DeepProfileTempDir
} elseif ($env:VG_DUCKDB_TEMP_DIR) {
    $env:VG_DUCKDB_TEMP_DIR
} elseif (Test-Path $PreferredSharedTempRoot) {
    # This shared path has capacity for large DuckDB spill files; keep scratch
    # isolated beneath VetoETL so archive/source data is never touched.
    $PreferredSharedTempDir
} else {
    Resolve-DefaultDuckDbTempDir -Candidates $DefaultTempCandidates
}
$env:VG_DUCKDB_TEMP_DIR = $DefaultDeepProfileTempDir
$env:VG_DEVICE_SNAPSHOT_THREADS = $DeepProfileThreads.ToString()
$env:VG_DEVICE_SNAPSHOT_MEMORY_GB = ($DeepProfileMemory -replace '[^0-9]', '')
try {
    New-Item -ItemType Directory -Path $DefaultDeepProfileTempDir -Force | Out-Null
    $TempProbe = Join-Path $DefaultDeepProfileTempDir ".etl_temp_probe.tmp"
    Set-Content -LiteralPath $TempProbe -Value "ok" -Encoding ASCII
    Remove-Item -LiteralPath $TempProbe -Force
} catch {
    throw "DuckDB temp folder is not writable: $DefaultDeepProfileTempDir. $($_.Exception.Message)"
}
if (($DefaultVenvPython -ne "python") -and (-not (Test-Path $DefaultVenvPython))) { $DefaultVenvPython = "python" }
$BundledRclone = Join-Path $WorkspaceRoot "tools\rclone\rclone.exe"
$RcloneExe = if (Test-Path $BundledRclone) { $BundledRclone } else { "rclone" }
$PortableRcloneConfig = Join-Path $WorkspaceRoot "config\rclone.conf"
if (Test-Path $PortableRcloneConfig) {
    $env:RCLONE_CONFIG = $PortableRcloneConfig
}

function Invoke-Rclone {
param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    Write-Host "[$(Get-Date -Format o)] rclone ${StepName}: $($Arguments -join ' ')"
    & $RcloneExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "rclone $StepName failed with exit code $LASTEXITCODE"
    }
}

function Get-RcloneSize {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    Write-Host "[$(Get-Date -Format o)] Checking $Label size/count: $Path"
    $jsonLines = & $RcloneExe size $Path --json
    if ($LASTEXITCODE -ne 0) {
        throw "rclone size failed for $Label with exit code $LASTEXITCODE"
    }

    $jsonText = ($jsonLines | Out-String).Trim()
    if (-not $jsonText) {
        throw "rclone size returned empty output for $Label"
    }

    $stats = $jsonText | ConvertFrom-Json
    return [pscustomobject]@{
        Count = [int64]$stats.count
        Bytes = [int64]$stats.bytes
    }
}

function Wait-RemoteStable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RemotePath,
        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    if ($SkipRemoteStableCheck) {
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: remote stability check skipped."
        return
    }

    $needed = [Math]::Max(1, $StableChecks)
    $sameSeen = 0
    $previous = $null

    while ($true) {
        $current = Get-RcloneSize -Path $RemotePath -Label "$SourceName remote"
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: remote count=$($current.Count), bytes=$($current.Bytes)"

        if ($previous -and $previous.Count -eq $current.Count -and $previous.Bytes -eq $current.Bytes) {
            $sameSeen += 1
        } else {
            $sameSeen = 1
            $previous = $current
        }

        if ($sameSeen -ge $needed) {
            Write-Host "[$(Get-Date -Format o)] ${SourceName}: remote stable after $sameSeen matching check(s)."
            return
        }

        $waitSeconds = [Math]::Max(1, $StableWaitMinutes) * 60
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: remote not stable yet. Waiting $StableWaitMinutes minute(s) before next check."
        Start-Sleep -Seconds $waitSeconds
    }
}

function Sync-RemoteDay {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RemotePath,
        [Parameter(Mandatory = $true)]
        [string]$LocalPath,
        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    Invoke-Rclone -StepName "sync" -Arguments @(
        "sync",
        $RemotePath,
        $LocalPath,
        "--size-only",
        "--transfers", "16",
        "--checkers", "32",
        "--multi-thread-streams", "4",
        "--buffer-size", "16M",
        "--retries", "5",
        "--low-level-retries", "10",
        "--stats", "30s",
        "-P"
    )
}

function Test-LocalMatchesExpectedSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [int64]$ExpectedCount,
        [Parameter(Mandatory = $true)]
        [int64]$ExpectedBytes,
        [Parameter(Mandatory = $true)]
        [string]$LocalPath,
        [Parameter(Mandatory = $true)]
        [string]$RemotePath,
        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    if ($SkipVerifyAfterSync) {
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: post-sync verification skipped."
        return
    }

    $maxRetries = [Math]::Max(1, $VerifyRetries)
    for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: remote/local snapshot verification attempt $attempt/$maxRetries"
        $remoteStats = Get-RcloneSize -Path $RemotePath -Label "$SourceName remote verification"
        $localStats = Get-RcloneSize -Path $LocalPath -Label "$SourceName local"

        Write-Host "[$(Get-Date -Format o)] ${SourceName}: start remote count=$ExpectedCount, bytes=$ExpectedBytes"
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: current remote count=$($remoteStats.Count), bytes=$($remoteStats.Bytes)"
        Write-Host "[$(Get-Date -Format o)] ${SourceName}: local count=$($localStats.Count), bytes=$($localStats.Bytes)"

        if ($localStats.Count -eq $remoteStats.Count -and $localStats.Bytes -eq $remoteStats.Bytes) {
            Write-Host "[$(Get-Date -Format o)] ${SourceName}: local folder verified by file count and total bytes."
            return
        }

        if ($attempt -eq $maxRetries) {
            throw "local verification failed after $maxRetries attempt(s): remote count/bytes $($remoteStats.Count)/$($remoteStats.Bytes), local count/bytes $($localStats.Count)/$($localStats.Bytes)"
        }

        Write-Host "[$(Get-Date -Format o)] ${SourceName}: snapshot mismatch. Re-running sync."
        Sync-RemoteDay -RemotePath $RemotePath -LocalPath $LocalPath -SourceName $SourceName
        if ($VerifyWaitMinutes -gt 0) {
            Write-Host "[$(Get-Date -Format o)] ${SourceName}: waiting $VerifyWaitMinutes minute(s) before next verification."
            Start-Sleep -Seconds ($VerifyWaitMinutes * 60)
        }
    }
}

# Set local date to fetch. Default = yesterday (-1), so if it runs today it copies yesterday.
if ($Date) {
    $TargetDate = $Date.Date
} else {
    $TargetDate = (Get-Date).AddDays(-1 * [Math]::Abs($LookbackDays))
}
if ($TargetDate -ge (Get-Date).Date) {
    throw "Target date must be a completed day before today: $($TargetDate.ToString('yyyy-MM-dd'))"
}
foreach ($pathValue in @($DefaultLocalRoot, $RawBaseRoot, $DefaultOverviewLakeRoot)) {
    if (-not $pathValue -or $pathValue.StartsWith("-")) {
        throw "Invalid ETL path parameter: '$pathValue'"
    }
}
$month = $TargetDate.ToString("MM")
$day = $TargetDate.ToString("dd")

$sources = @()
if ($SingleSourceMode) {
    $sources += [pscustomobject]@{
        Name = "single"
        RemoteRoot = $RemoteRoot
        LocalRoot = $DefaultLocalRoot
    }
} else {
    $sources += [pscustomobject]@{
        Name = "stream"
        RemoteRoot = $StreamRemoteRoot
        LocalRoot = Join-Path $RawBaseRoot $StreamLocalName
    }
    $sources += [pscustomobject]@{
        Name = "fast"
        RemoteRoot = $FastRemoteRoot
        LocalRoot = Join-Path $RawBaseRoot $FastLocalName
    }
}
foreach ($source in $sources) {
    if (-not $source.RemoteRoot -or $source.RemoteRoot.StartsWith("-") -or $source.RemoteRoot -notmatch "^[^\\/:]+:.+") {
        throw "Invalid rclone remote root for $($source.Name): '$($source.RemoteRoot)'"
    }
}

$logFolder = Join-Path $WorkspaceRoot "output\logs"
$logFile = Join-Path $logFolder ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
foreach ($source in $sources) {
    $sourceLocalPath = Join-Path $source.LocalRoot (Join-Path $month $day)
    New-Item -ItemType Directory -Path $sourceLocalPath -Force | Out-Null
}

Start-Transcript -Path $logFile -Append | Out-Null

try {
    Write-Host "[$(Get-Date -Format o)] Target date : $($TargetDate.ToString('yyyy-MM-dd'))"
    Write-Host "[$(Get-Date -Format o)] ETL base    : $DefaultLocalRoot"
    if (-not $SingleSourceMode) {
        Write-Host "[$(Get-Date -Format o)] Raw root    : $RawBaseRoot"
    }

    if ($SkipDownload) {
        if ($SingleSourceMode) { throw "-SkipDownload is not supported with -SingleSourceMode." }
        $downloadResultRoot = Join-Path $WorkspaceRoot "output\state\downloads"
        foreach ($source in @("stream", "fast")) {
            $resultPath = Join-Path $downloadResultRoot ("{0}_{1}.json" -f $TargetDate.ToString("yyyy-MM-dd"), $source)
            if (-not (Test-Path -LiteralPath $resultPath)) {
                throw "Validated prefetch result is missing for $source/$($TargetDate.ToString('yyyy-MM-dd')): $resultPath"
            }
            try { $downloadResult = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json } catch {
                throw "Validated prefetch result is unreadable: $resultPath"
            }
            if (
                $downloadResult.status -ne "complete" -or
                $downloadResult.verified -ne $true -or
                $downloadResult.source -ne $source -or
                $downloadResult.date -ne $TargetDate.ToString("yyyy-MM-dd") -or
                [int64]$downloadResult.remote_count -le 0 -or
                [int64]$downloadResult.remote_count -ne [int64]$downloadResult.local_count -or
                [int64]$downloadResult.remote_bytes -ne [int64]$downloadResult.local_bytes -or
                -not (Test-Path -LiteralPath $downloadResult.local_path)
            ) {
                throw "Validated prefetch result did not pass integrity checks: $resultPath"
            }
        }
        Write-Host "[$(Get-Date -Format o)] Download phase skipped after verified FAST and STREAM prefetch evidence."
    } elseif (-not $SingleSourceMode) {
        $prefetchScript = Join-Path $WorkspaceRoot "prefetch_daily_sources.ps1"
        if (-not (Test-Path -LiteralPath $prefetchScript)) { throw "Parallel prefetch launcher is missing: $prefetchScript" }
        $prefetchArguments = @{
            Dates = @($TargetDate)
            StreamRemoteRoot = $StreamRemoteRoot
            FastRemoteRoot = $FastRemoteRoot
            RawRoot = $RawBaseRoot
            StreamLocalName = $StreamLocalName
            FastLocalName = $FastLocalName
            RcloneExe = $RcloneExe
            MaxParallelDownloads = $MaxParallelDownloads
            Transfers = $DownloadTransfers
            Checkers = $DownloadCheckers
            VerifyRetries = $VerifyRetries
            VerifyWaitMinutes = $VerifyWaitMinutes
            WaitForRemoteStable = $WaitForRemoteStable.IsPresent
            StableChecks = $StableChecks
            StableWaitMinutes = $StableWaitMinutes
            SkipVerifyAfterSync = $SkipVerifyAfterSync.IsPresent
        }
        if (Test-Path -LiteralPath $PortableRcloneConfig) { $prefetchArguments["RcloneConfig"] = $PortableRcloneConfig }
        $global:LASTEXITCODE = 0
        & $prefetchScript @prefetchArguments
        if ($LASTEXITCODE -ne 0) { throw "Parallel prefetch failed with exit code $LASTEXITCODE" }
    } else {
        foreach ($source in $sources) {
            $sourceRemoteRoot = $source.RemoteRoot.TrimEnd("/")
            $remotePath = "$sourceRemoteRoot/$month/$day"
            $localPath = Join-Path $source.LocalRoot (Join-Path $month $day)

            Write-Host "[$(Get-Date -Format o)] [$($source.Name)] Target remote: $remotePath"
            Write-Host "[$(Get-Date -Format o)] [$($source.Name)] Target local : $localPath"
            $remoteStartStats = Get-RcloneSize -Path $remotePath -Label "$($source.Name) remote"
            if ($remoteStartStats.Count -le 0) { throw "remote file count is zero for $remotePath" }
            Sync-RemoteDay -RemotePath $remotePath -LocalPath $localPath -SourceName $source.Name
            Test-LocalMatchesExpectedSnapshot -ExpectedCount $remoteStartStats.Count -ExpectedBytes $remoteStartStats.Bytes -LocalPath $localPath -RemotePath $remotePath -SourceName $source.Name
        }
    }

    if (-not $SkipPostVerifyDelay) {
        Write-Host "[$(Get-Date -Format o)] All source folders verified. Waiting $PostVerifyDelaySeconds second(s) before ETL."
        Start-Sleep -Seconds ([Math]::Max(0, $PostVerifyDelaySeconds))
    } else {
        Write-Host "[$(Get-Date -Format o)] Post-verify delay skipped."
    }

    $env:VG_ETL_BASE = $DefaultLocalRoot
    $env:VG_OVERVIEW_LAKE_ROOT = $DefaultOverviewLakeRoot
    $env:VG_OVERVIEW_SOURCES = $OverviewSources
    $pipeline = Join-Path $PSScriptRoot "src\orchestrator\run_pipeline.py"
    $asrunPriorityPath = Join-Path $PSScriptRoot "output\state\asrun_priority.json"
    $asrunPriority = $null
    if (Test-Path -LiteralPath $asrunPriorityPath) {
        try {
            $asrunPriority = Get-Content -Raw -LiteralPath $asrunPriorityPath | ConvertFrom-Json
            Write-Host "[$(Get-Date -Format o)] ASRUN priority mode enabled: lake + validation first; heavy marts and dashboards deferred."
        } catch {
            throw "ASRUN priority request is unreadable: $asrunPriorityPath. $($_.Exception.Message)"
        }
    }
    $watchArgs = @()
    $isIntermediateRecovery = $SkipDownload -and $SkipWatch -and $SkipOverview -and $SkipLakeArchive
    if ($SkipWatch) { $watchArgs += "--skip-watch" }
    if ($SkipOverview) { $watchArgs += "--skip-overview" }
    if ($isIntermediateRecovery) {
        $watchArgs += @("--skip-audience", "--skip-master")
        Write-Host "[$(Get-Date -Format o)] Intermediate recovery date: daily marts remain enabled; top-level dashboard rendering is deferred."
    }
    if ($asrunPriority) {
        $watchArgs += @(
            "--skip-watch",
            "--skip-overview",
            "--skip-deep-profile",
            "--skip-device-snapshot",
            "--skip-device-decode-profile",
            "--skip-concurrency",
            "--skip-latency",
            "--skip-identity-mart",
            "--skip-content-mart",
            "--skip-audience",
            "--skip-master"
        )
    } elseif (-not $RunDeviceDecode) {
        $watchArgs += "--skip-device-decode-profile"
    }
    if (-not $StrictPipeline) { $watchArgs += "--continue-on-error" }
    if ($StrictPipeline) {
        Write-Host "[$(Get-Date -Format o)] Strict pipeline mode enabled: recoverable step failures will fail the scheduled task."
    } else {
        Write-Host "[$(Get-Date -Format o)] Smart pipeline mode enabled: recoverable dashboard/enrichment failures continue and are written to output\state."
    }

    $pipelineArgs = @(
        "--base", $DefaultLocalRoot,
        "--overview-lake-root", $DefaultOverviewLakeRoot,
        "--overview-sources", $OverviewSources,
        # Raw day D legitimately creates an early-IST D+1 spillover partition.
        # Retain it for the next run, but never publish it as a completed day.
        "--publish-through", $TargetDate.ToString("yyyy-MM-dd")
    )
    if (-not $SingleSourceMode) {
        $pipelineArgs += @(
            "--etl1-daily-date", $TargetDate.ToString("yyyy-MM-dd"),
            "--etl1-daily-raw-root", $RawBaseRoot,
            "--etl1-stream-name", $StreamLocalName,
            "--etl1-fast-name", $FastLocalName
        )
    }
    if ($PrefsFile) {
        $pipelineArgs += @("--etl1-prefs-file", $PrefsFile)
    }
    if ($Etl1Workers -gt 0) {
        $pipelineArgs += @("--etl1-workers", $Etl1Workers.ToString())
    }
    if ($Etl1Compression) {
        $pipelineArgs += @("--etl1-compression", $Etl1Compression)
    }
    if ($StageCompression) {
        $pipelineArgs += @("--stage-compression", $StageCompression)
    }
    if (-not $SingleSourceMode) {
        if ($asrunPriority) {
            Write-Host "[$(Get-Date -Format o)] ASRUN priority retention: keeping raw/stage until the normal post-priority cleanup run."
        } elseif ($KeepProcessedInputs) {
            Write-Host "[$(Get-Date -Format o)] Retention: keeping raw and stage intermediates by request."
        } else {
            $pipelineArgs += "--cleanup-daily-intermediates"
            Write-Host "[$(Get-Date -Format o)] Retention: validated daily raw/stage intermediates will be removed after pipeline success."
        }
    }
    $pipelineArgs += @(
        "--lake-repair-lookback-days", "0",
        "--deep-profile-mode", "incremental",
        "--deep-profile-window-days", "1",
        "--ua-profile-window-days", "1",
        "--device-decode-window-days", "1",
        "--concurrency-window-days", "1",
        "--latency-window-days", "1",
        "--stage-threads", $StageThreads.ToString(),
        "--stage-memory", $StageMemory,
        "--stage-max-temp-size", $StageMaxTempSize,
        "--deep-profile-threads", $DeepProfileThreads.ToString(),
        "--deep-profile-memory", $DeepProfileMemory,
        "--deep-profile-temp-dir", $DefaultDeepProfileTempDir,
        "--deep-profile-max-temp-size", $DeepProfileMaxTempSize,
        # These marts run after the profile but can otherwise each request
        # more RAM than this workstation has free. Their spill files use Z:.
        "--concurrency-threads", $ConcurrencyThreads.ToString(),
        "--concurrency-memory", $ConcurrencyMemory,
        "--latency-threads", $LatencyThreads.ToString(),
        "--latency-memory", $LatencyMemory,
        "--identity-threads", $IdentityThreads.ToString(),
        "--identity-memory", $IdentityMemory,
        "--content-threads", $ContentThreads.ToString(),
        "--content-memory", $ContentMemory
    )
    Write-Host "[$(Get-Date -Format o)] Performance: ETL1=$Etl1Workers workers; stages=$StageThreads threads/$StageMemory; profile=$DeepProfileThreads threads/$DeepProfileMemory; marts=$ConcurrencyThreads threads/$ConcurrencyMemory; spill=$DefaultDeepProfileTempDir (max $DeepProfileMaxTempSize)."
    if (-not $SkipUaProfile -and -not $asrunPriority) {
        $pipelineArgs += @(
            "--run-ua-profile",
            "--ua-api-limit", $UaApiLimit.ToString()
        )
        if (-not $SkipUaMalformedApi) {
            $pipelineArgs += "--ua-api-include-malformed"
        }
    }
    $pipelineArgs += $watchArgs

    $cmd = @($DefaultVenvPython, $pipeline) + $pipelineArgs
    Write-Host "[$(Get-Date -Format o)] Running: $cmd"
    & $DefaultVenvPython $pipeline @pipelineArgs
    if ($LASTEXITCODE -ne 0) { throw "run_pipeline.py failed with exit code $LASTEXITCODE" }

    Write-Host "[$(Get-Date -Format o)] Pipeline completed."

    $isFinalAsrunPriorityDate = $asrunPriority -and -not $SkipWatch -and -not $SkipOverview
    if ($isFinalAsrunPriorityDate) {
        $priorityStart = [string]$asrunPriority.start_date
        $priorityEnd = $TargetDate.ToString("yyyy-MM-dd")
        $priorityChannel = if ($asrunPriority.channel) {
            [string]$asrunPriority.channel
        } else {
            "Unassigned - stakeholder mapping required"
        }
        $identityBuilder = Join-Path $PSScriptRoot "src\tools\build_identity_minute.py"
        $identityOut = Join-Path $PSScriptRoot "output\watch_hours\concurrency"
        foreach ($identitySource in @("fast", "stream")) {
            $identityArgs = @(
                $identityBuilder,
                "--lake", (Join-Path $DefaultLocalRoot "lake"),
                "--out-dir", $identityOut,
                "--source", $identitySource,
                "--start", $priorityStart,
                "--end", $priorityEnd,
                "--threads", $ConcurrencyThreads.ToString(),
                "--memory-limit", $ConcurrencyMemory,
                "--temp-dir", $DefaultDeepProfileTempDir
            )
            Write-Host "[$(Get-Date -Format o)] ASRUN priority: building $identitySource identity-minute for $priorityStart through $priorityEnd."
            & $DefaultVenvPython @identityArgs
            if ($LASTEXITCODE -ne 0) {
                throw "ASRUN priority identity-minute build failed for $identitySource with exit code $LASTEXITCODE."
            }
        }

        $asrunRunner = Join-Path $PSScriptRoot "asrun_demo\run_demo.ps1"
        Write-Host "[$(Get-Date -Format o)] ASRUN priority: publishing dashboard."
        & $asrunRunner -Channel $priorityChannel
        if ($LASTEXITCODE -ne 0) {
            throw "ASRUN priority dashboard generation failed with exit code $LASTEXITCODE."
        }
        Write-Host "[$(Get-Date -Format o)] ASRUN priority completed; recovery will restore normal ETL behavior after committing the final checkpoint."
    }

    if (-not $SingleSourceMode -and -not $SkipLakeArchive) {
        $HotLakeRoot = Join-Path $DefaultLocalRoot "lake"
        $LakeArchiver = Join-Path $WorkspaceRoot "src\tools\archive_lake_partitions.py"
        $ArchiveThrough = $TargetDate.Date.AddDays(1 - $HotLakeRetentionDays)
        $ArchiveAuditDir = Join-Path $WorkspaceRoot "output\lake_archive"
        $ArchiveQuarantine = Join-Path $ArchiveLakeRoot "delete temp\lake_conflicts"
        $PipelineLock = Join-Path $WorkspaceRoot "output\state\pipeline.lock"

        if (-not (Test-Path -LiteralPath $ArchiveLakeRoot)) {
            Write-Warning "Lake archive skipped because the archive root is unavailable: $ArchiveLakeRoot"
        } elseif (-not (Test-Path -LiteralPath $LakeArchiver)) {
            Write-Warning "Lake archive skipped because the archiver is missing: $LakeArchiver"
        } else {
            $ArchiveArgs = @(
                $LakeArchiver,
                "--source-root", $HotLakeRoot,
                "--archive-root", $ArchiveLakeRoot,
                "--through", $ArchiveThrough.ToString("yyyy-MM-dd"),
                "--sources", "fast,stream",
                "--quarantine-root", $ArchiveQuarantine,
                "--audit-dir", $ArchiveAuditDir,
                "--pipeline-lock", $PipelineLock
            )
            Write-Host "[$(Get-Date -Format o)] Lake retention: keeping $HotLakeRetentionDays IST spillover partition date(s) hot; archiving completed partitions through $($ArchiveThrough.ToString('yyyy-MM-dd'))."
            & $DefaultVenvPython @ArchiveArgs
            if ($LASTEXITCODE -ne 0) {
                throw "Lake archive dry run failed with exit code $LASTEXITCODE"
            }
            & $DefaultVenvPython @ArchiveArgs --execute
            if ($LASTEXITCODE -ne 0) {
                throw "Lake archive transfer failed with exit code $LASTEXITCODE"
            }
            Write-Host "[$(Get-Date -Format o)] Lake retention completed."
        }
    } elseif ($SkipLakeArchive) {
        Write-Host "[$(Get-Date -Format o)] Lake retention skipped by request."
    }
} catch {
    Write-Error "[FAILED] $($_.Exception.Message)"
    throw
} finally {
    Stop-Transcript | Out-Null
}
