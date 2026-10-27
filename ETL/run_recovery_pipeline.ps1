[CmdletBinding(PositionalBinding = $false)]
param(
    [Nullable[datetime]]$StartDate = $null,
    [Nullable[datetime]]$ThroughDate = $null,
    [ValidateRange(1, 366)]
    [int]$MaxCatchUpDays = 31,
    [ValidateRange(1, 366)]
    [int]$BootstrapLookbackDays = 60,
    [ValidateRange(1, 6)]
    [int]$MaxParallelDownloads = 2,
    [ValidateRange(1, 128)]
    [int]$DownloadTransfers = 16,
    [ValidateRange(1, 256)]
    [int]$DownloadCheckers = 32,
    [switch]$DryRun,
    [switch]$Force
)

if ($args.Count -gt 0) {
    throw "Unexpected positional arguments. Use named parameters such as -StartDate or -ThroughDate. Received: $($args -join ' ')"
}

$ErrorActionPreference = "Stop"
$WorkspaceRoot = $PSScriptRoot
$DailyScript = Join-Path $WorkspaceRoot "run_daily_pipeline.ps1"
$PrefetchScript = Join-Path $WorkspaceRoot "prefetch_daily_sources.ps1"
$LiveManager = Join-Path $WorkspaceRoot "manage_live_monitor.ps1"
$StateDir = Join-Path $WorkspaceRoot "output\state"
$DailyStateDir = Join-Path $StateDir "daily_runs"
$RecoveryStatePath = Join-Path $StateDir "recovery_backlog.json"
$PipelineLastRunPath = Join-Path $StateDir "pipeline_last_run.json"
$AsrunPriorityPath = Join-Path $StateDir "asrun_priority.json"
$ValidationRoot = Join-Path $WorkspaceRoot "output\validation"
$LogDir = Join-Path $WorkspaceRoot "output\logs"
$GuardPython = Join-Path (Split-Path $WorkspaceRoot -Parent) 'venv\Scripts\python.exe'
$CapacityGuard = Join-Path $WorkspaceRoot 'src\tools\recovery_capacity_guard.py'
$RecoveryDependency = Join-Path $StateDir 'recovery_dependency.json'
$TargetThroughDate = if ($ThroughDate) { $ThroughDate.Date } else { (Get-Date).Date.AddDays(-1) }
if ($TargetThroughDate -ge (Get-Date).Date) {
    throw "Through date must be a completed day before today: $($TargetThroughDate.ToString('yyyy-MM-dd'))"
}

function Write-JsonAtomic {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.tmp"
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Read-RecoveryState {
    $state = @{}
    if (-not (Test-Path -LiteralPath $RecoveryStatePath)) { return $state }
    try {
        $payload = Get-Content -Raw -LiteralPath $RecoveryStatePath | ConvertFrom-Json
        foreach ($property in $payload.PSObject.Properties) {
            $state[$property.Name] = $property.Value
        }
    } catch {
        throw "Recovery state is unreadable: $RecoveryStatePath. $($_.Exception.Message)"
    }
    return $state
}

function Read-PipelineLastRun {
    $state = @{}
    if (-not (Test-Path -LiteralPath $PipelineLastRunPath)) { return $state }
    try {
        $payload = Get-Content -Raw -LiteralPath $PipelineLastRunPath | ConvertFrom-Json
        foreach ($property in $payload.PSObject.Properties) {
            $state[$property.Name] = $property.Value
        }
    } catch {
        throw "Pipeline last-run state is unreadable: $PipelineLastRunPath. $($_.Exception.Message)"
    }
    return $state
}

function Get-ValidationEvidence {
    param(
        [Parameter(Mandatory = $true)][datetime]$Date,
        [Nullable[datetime]]$NotBefore = $null
    )

    if (-not (Test-Path -LiteralPath $ValidationRoot)) { return $null }
    $iso = $Date.ToString("yyyy-MM-dd")
    $asrunPriorityDate = $false
    if (Test-Path -LiteralPath $AsrunPriorityPath) {
        try {
            $priority = Get-Content -Raw -LiteralPath $AsrunPriorityPath | ConvertFrom-Json
            $priorityStart = [datetime]::ParseExact([string]$priority.start_date, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture).Date
            $asrunPriorityDate = $Date.Date -ge $priorityStart -and $Date.Date -le $TargetThroughDate
        } catch {
            throw "ASRUN priority request is unreadable: $AsrunPriorityPath. $($_.Exception.Message)"
        }
    }
    $underscored = $Date.ToString("yyyy_MM_dd")
    # PowerShell unwraps Nullable[datetime] parameters to DateTime values.
    # Calling .Value therefore returns null on a supplied timestamp.
    $notBeforeUtc = if ($null -ne $NotBefore) { ([datetime]$NotBefore).ToUniversalTime() } else { $null }
    $candidates = @(
        Get-ChildItem -LiteralPath $ValidationRoot -Recurse -File -Filter "*.json" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name.Contains($iso) -or $_.Name.Contains($underscored) } |
            Sort-Object LastWriteTime -Descending
    )

    foreach ($candidate in $candidates) {
        if ($notBeforeUtc -and $candidate.LastWriteTimeUtc -lt $notBeforeUtc) {
            continue
        }
        try {
            $report = Get-Content -Raw -LiteralPath $candidate.FullName | ConvertFrom-Json
        } catch {
            continue
        }
        $acceptedMode = $report.mode -eq "full" -or ($asrunPriorityDate -and $report.mode -eq "structural")
        if ($report.date -ne $iso -or -not $acceptedMode) { continue }
        if ([int]($report.hard_failure_count) -ne 0) { continue }
        if ($report.overall_status -notin @("PASS", "REVIEW")) { continue }

        $sourceResults = @($report.source_results)
        $reconciliations = @($report.profile_reconciliation)
        $valid = $true
        foreach ($source in @("fast", "stream")) {
            $sourceResult = $sourceResults | Where-Object { $_.source -eq $source } | Select-Object -First 1
            $reconciliation = $reconciliations | Where-Object { $_.source -eq $source } | Select-Object -First 1
            $sourceInvalid = -not $sourceResult -or $sourceResult.status -ne "PASS" -or $sourceResult.selected.full_day -ne $true
            $reconciliationInvalid = $report.mode -eq "full" -and (
                -not $reconciliation -or
                $reconciliation.status -ne "PASS" -or
                [int64]($reconciliation.delta_rows) -ne 0
            )
            if ($sourceInvalid -or $reconciliationInvalid) {
                $valid = $false
                break
            }
        }
        if ($valid) {
            return [pscustomobject]@{
                Complete = $true
                Kind = "validation"
                Path = $candidate.FullName
                OverallStatus = $report.overall_status
                LastWriteTimeUtc = $candidate.LastWriteTimeUtc.ToString("o")
            }
        }
    }
    return $null
}

function Get-DateCompletion {
    param([Parameter(Mandatory = $true)][datetime]$Date)

    $iso = $Date.ToString("yyyy-MM-dd")
    $marker = Join-Path $DailyStateDir "$iso.json"
    $incident = Join-Path $StateDir "cdn_incident_closeout\$iso.json"
    if (Test-Path -LiteralPath $incident) {
        & $GuardPython (Join-Path $WorkspaceRoot 'src\tools\verify_cdn_closeout.py') --etl-root $WorkspaceRoot --date $iso | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "CDN closeout evidence failed verification for $iso." }
        return [pscustomobject]@{ Complete = $false; Kind = 'accepted_source_gap'; Path = $incident; OverallStatus = 'PARTIAL' }
    }
    if (Test-Path -LiteralPath $marker) {
        Assert-ReportingCompletion -Date $Date
        try {
            $payload = Get-Content -Raw -LiteralPath $marker | ConvertFrom-Json
            if ($payload.status -eq "complete" -and $payload.date -eq $iso) {
                return [pscustomobject]@{
                    Complete = $true
                    Kind = "checkpoint"
                    Path = $marker
                    OverallStatus = $payload.validation_status
                }
            }
        } catch {
            Write-Warning "Ignoring unreadable daily checkpoint: $marker"
        }
    }
    $evidence = Get-ValidationEvidence -Date $Date
    if ($evidence) { Assert-ReportingCompletion -Date $Date }
    return $evidence
}

function Assert-ReportingCompletion {
    param([datetime]$Date)
    & $GuardPython (Join-Path $WorkspaceRoot 'src\tools\check_daily_run_completion.py') --etl-root $WorkspaceRoot --date $Date.ToString('yyyy-MM-dd')
    if ($LASTEXITCODE -ne 0) { throw "Reporting failures remain for $($Date.ToString('yyyy-MM-dd')); refusing a completion checkpoint." }
}

function Save-RecoveryState {
    param(
        [Parameter(Mandatory = $true)][hashtable]$State,
        [Parameter(Mandatory = $true)][string]$Status
    )

    $State["schema_version"] = 1
    $State["status"] = $Status
    $State["updated_at_ist"] = (Get-Date).ToString("o")
    $State["computer"] = $env:COMPUTERNAME
    Write-JsonAtomic -Path $RecoveryStatePath -Payload $State
}

function Resume-PendingCleanup {
    if ($DryRun) { return }
    Save-RecoveryState -State $state -Status 'cleanup_recovery'
    $python = Join-Path (Split-Path $WorkspaceRoot -Parent) 'venv\Scripts\python.exe'
    $helper = Join-Path $WorkspaceRoot 'src\tools\resume_pending_cleanups.py'
    $maintenanceArgs = @('-u', $helper, '--etl-root', $WorkspaceRoot, '--archive-lake', 'Z:\Veto Logs Backup\DO NOT DELETE', '--execute')
    if ($state['last_successful_date']) { $maintenanceArgs += @('--archive-through', $state['last_successful_date']) }
    & $python @maintenanceArgs
    if ($LASTEXITCODE -ne 0) { throw 'ETL processing is validated, but cleanup/archive maintenance failed. See audit logs; local data is retained until verified transfer.' }
    $state['cleanup_checked_at_ist'] = (Get-Date).ToString('o')
    $state['archive_checked_through'] = $state['last_successful_date']
    $state['current_attempt_id'] = $null
    Save-RecoveryState -State $state -Status 'maintenance_complete'
}

function Save-DailyCheckpoint {
    param(
        [Parameter(Mandatory = $true)][datetime]$Date,
        [Parameter(Mandatory = $true)]$Evidence,
        [string]$AttemptId = ""
    )

    Assert-ReportingCompletion -Date $Date
    $iso = $Date.ToString("yyyy-MM-dd")
    $marker = Join-Path $DailyStateDir "$iso.json"
    Write-JsonAtomic -Path $marker -Payload @{
        schema_version = 1
        date = $iso
        status = "complete"
        completed_at_ist = (Get-Date).ToString("o")
        validation_status = $Evidence.OverallStatus
        validation_report = $Evidence.Path
        recovery_attempt_id = $AttemptId
        computer = $env:COMPUTERNAME
    }
}

function Assert-DailyScriptContract {
    $requiredParameters = @(
        "Date",
        "SkipDownload",
        "SkipPostVerifyDelay",
        "SkipWatch",
        "SkipOverview",
        "SkipLakeArchive"
    )
    $command = Get-Command -Name $DailyScript -CommandType ExternalScript
    $missing = @($requiredParameters | Where-Object { -not $command.Parameters.ContainsKey($_) })
    if ($missing.Count) {
        throw "Daily pipeline parameter contract is incompatible. Missing: $($missing -join ', ')"
    }
}

if (-not (Test-Path -LiteralPath $DailyScript)) {
    throw "Daily pipeline launcher is missing: $DailyScript"
}
if (-not (Test-Path -LiteralPath $PrefetchScript)) {
    throw "Parallel prefetch launcher is missing: $PrefetchScript"
}
Assert-DailyScriptContract
New-Item -ItemType Directory -Path $StateDir, $DailyStateDir, $LogDir -Force | Out-Null

$mutex = [System.Threading.Mutex]::new($false, "Local\VetoETLRecoveryBacklog")
$ownsMutex = $false
$transcriptStarted = $false
$livePausedForDailyEtl = $false
$ensureLiveMonitorAtExit = $false
try {
    try {
        $ownsMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }
    if (-not $ownsMutex) {
        Write-Host "Another Veto ETL recovery runner is already active. Exiting cleanly."
        exit 0
    }
    $ensureLiveMonitorAtExit = -not $DryRun

    $logPath = Join-Path $LogDir ("recovery_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    Start-Transcript -Path $logPath -Append | Out-Null
    $transcriptStarted = $true
    Write-Host "[$(Get-Date -Format o)] Recovery runner started. Through date: $($TargetThroughDate.ToString('yyyy-MM-dd'))"

    $state = Read-RecoveryState
    if (-not $DryRun) {
        Save-RecoveryState -State $state -Status 'waiting_for_required_repair'
        & $GuardPython $CapacityGuard --dependency $RecoveryDependency
        if ($LASTEXITCODE -ne 0) { throw 'Required repair did not complete; no new dates will be downloaded.' }
        # A repair may finish after midnight; catch up through the new yesterday.
        if (-not $ThroughDate) { $TargetThroughDate = (Get-Date).Date.AddDays(-1) }
    }
    $pipelineLastRun = Read-PipelineLastRun
    $lastSuccessful = $null
    if ($state["last_successful_date"]) {
        $parsed = [datetime]::MinValue
        if ([datetime]::TryParseExact(
            [string]$state["last_successful_date"],
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None,
            [ref]$parsed
        )) {
            $lastSuccessful = $parsed.Date
        }
    }

    if ($pipelineLastRun["status"] -eq "complete" -and $pipelineLastRun["target_date"]) {
        try {
            $pipelineDate = [datetime]::ParseExact(
                [string]$pipelineLastRun["target_date"],
                "yyyy-MM-dd",
                [Globalization.CultureInfo]::InvariantCulture
            ).Date
            if (-not $lastSuccessful -or $pipelineDate -gt $lastSuccessful) {
                $lastSuccessful = $pipelineDate
                Write-Host "[$(Get-Date -Format o)] Bootstrapped from pipeline_last_run.json: $($pipelineDate.ToString('yyyy-MM-dd'))"
            }
        } catch {
            Write-Warning "Ignoring unreadable pipeline last-run target date: $PipelineLastRunPath"
        }
    }

    if (-not $lastSuccessful -and -not $StartDate) {
        for ($offset = 0; $offset -lt $BootstrapLookbackDays; $offset++) {
            $candidate = $TargetThroughDate.AddDays(-1 * $offset)
            $evidence = Get-DateCompletion -Date $candidate
            if ($evidence) {
                $lastSuccessful = $candidate
                Write-Host "[$(Get-Date -Format o)] Bootstrapped checkpoint from $($evidence.Kind): $($candidate.ToString('yyyy-MM-dd'))"
                break
            }
        }
    }

    if ($StartDate) {
        $cursor = $StartDate.Date
    } elseif ($lastSuccessful) {
        $cursor = $lastSuccessful.AddDays(1)
    } else {
        throw "No recovery checkpoint was found. Supply -StartDate YYYY-MM-DD for the first run."
    }

    if ($cursor -gt $TargetThroughDate) {
        Resume-PendingCleanup
        Write-Host "[$(Get-Date -Format o)] No ETL backlog. Latest completed date is already current."
        if (-not $DryRun) {
            $state["last_successful_date"] = if ($lastSuccessful) { $lastSuccessful.ToString("yyyy-MM-dd") } else { $null }
            $state["current_date"] = $null
            $state["last_error"] = $null
            Save-RecoveryState -State $state -Status "idle"
        }
        exit 0
    }

    $dates = New-Object System.Collections.Generic.List[datetime]
    $candidate = $cursor
    while ($candidate -le $TargetThroughDate -and $dates.Count -lt $MaxCatchUpDays) {
        $dates.Add($candidate)
        $candidate = $candidate.AddDays(1)
    }

    $completionByDate = @{}
    $pendingDates = New-Object System.Collections.Generic.List[datetime]
    foreach ($dateValue in $dates) {
        $iso = $dateValue.ToString("yyyy-MM-dd")
        $evidence = if ($Force) { $null } else { Get-DateCompletion -Date $dateValue }
        $completionByDate[$iso] = $evidence
        if (-not $evidence) { $pendingDates.Add($dateValue) }
    }

    $pendingText = if ($pendingDates.Count) {
        ($pendingDates | ForEach-Object { $_.ToString("yyyy-MM-dd") }) -join ", "
    } else {
        "none"
    }
    Write-Host "[$(Get-Date -Format o)] Pending ETL dates: $pendingText"
    if ($DryRun) {
        Write-Host "Dry-run plan: one date at a time; at most two source downloads, then ETL, validation and archival before the next date."
        Write-Host "Dry run complete; no ETL or checkpoint files were changed."
        exit 0
    }

    if ($pendingDates.Count) {
        if (-not (Test-Path -LiteralPath $LiveManager)) {
            throw "Live-monitor manager is missing: $LiveManager"
        }
        Write-Host "[$(Get-Date -Format o)] Pausing the live monitor while daily source downloads and ETL use workstation resources."
        $livePausedForDailyEtl = $true
        & $LiveManager -Action Stop
    }

    $finalPendingDate = if ($pendingDates.Count) { $pendingDates[$pendingDates.Count - 1] } else { $null }
    foreach ($dateValue in $dates) {
        $iso = $dateValue.ToString("yyyy-MM-dd")
        $existing = $completionByDate[$iso]
        if ($existing -and $existing.Kind -eq 'accepted_source_gap' -and -not $Force) {
            Write-Host "$iso accepted CDN source gap; skipping without creating a full-day checkpoint."
            $state['last_processed_exception_date'] = $iso
            Save-RecoveryState -State $state -Status 'catching_up'
            continue
        }
        if ($existing -and -not $Force) {
            Write-Host "[$(Get-Date -Format o)] $iso already complete via $($existing.Kind); advancing checkpoint."
            Save-DailyCheckpoint -Date $dateValue -Evidence $existing
            $state["last_successful_date"] = $iso
            $state["current_date"] = $null
            $state["last_error"] = $null
            Save-RecoveryState -State $state -Status "catching_up"
            continue
        }

        $preparedReady = $false
        $preparedReceipt = Join-Path $StateDir "prepared_lake\$iso.json"
        if (Test-Path -LiteralPath $preparedReceipt) {
            & $GuardPython (Join-Path $WorkspaceRoot 'src\tools\prepared_priority_lake.py') --verify $preparedReceipt --base (Join-Path $WorkspaceRoot 'data')
            if ($LASTEXITCODE -ne 0) { throw "Prepared lake receipt is invalid for $iso; inputs will not be silently rebuilt." }
            $preparedReady = $true
            Write-Host "Reusing verified lake for $iso; raw download and 001/02/03 are not repeated."
        }
        if (-not $preparedReady) {
        & $GuardPython $CapacityGuard --data (Join-Path $WorkspaceRoot 'data') --archive 'Z:\Veto Logs Backup\DO NOT DELETE'
        if ($LASTEXITCODE -ne 0) { throw "Insufficient verified storage reserve before $iso. No download started." }
        $sourceCheckDir = Join-Path $WorkspaceRoot "output\temp\source_check_$iso"
        & $GuardPython (Join-Path $WorkspaceRoot 'src\tools\wait_for_complete_source.py') --date $iso --work-dir $sourceCheckDir --check-only
        if ($LASTEXITCODE -ne 0) { throw "Source availability check failed for $iso." }
        $sourceCheck = Get-Content -Raw -LiteralPath (Join-Path $sourceCheckDir 'state.json') | ConvertFrom-Json
        if ($sourceCheck.status -ne 'ready_for_recovery') {
            throw "Raw source logs for $iso are incomplete. Keeping completed-day dashboards; later dates remain queued. See $sourceCheckDir."
        }
        $state["current_date"] = $null
        $state["download_dates"] = @($iso)
        $state["download_jobs"] = 2
        $state["max_parallel_downloads"] = [Math]::Min(2, $MaxParallelDownloads)
        $state["download_transfers_each"] = $DownloadTransfers
        $state["download_checkers_each"] = $DownloadCheckers
        $state["last_error"] = $null
        Save-RecoveryState -State $state -Status "downloading"

        Write-Host "[$(Get-Date -Format o)] Downloading only $iso before processing and cleanup."
        $prefetchArguments = @{
            Dates = [datetime[]]@($dateValue)
            MaxParallelDownloads = [Math]::Min(2, $MaxParallelDownloads)
            Transfers = $DownloadTransfers
            Checkers = $DownloadCheckers
            ForceRevalidate = $Force.IsPresent
        }
        $global:LASTEXITCODE = 0
        & $PrefetchScript @prefetchArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Parallel recovery prefetch returned exit code $LASTEXITCODE."
        }
        $state["download_dates"] = @()
        $state["download_jobs"] = 0
        Save-RecoveryState -State $state -Status "downloads_complete"
        & $GuardPython $CapacityGuard --data (Join-Path $WorkspaceRoot 'data') --archive 'Z:\Veto Logs Backup\DO NOT DELETE' --data-reserve-gib 20
        if ($LASTEXITCODE -ne 0) { throw "Storage reserve is too low after downloading $iso. Inputs retained; processing not started." }
        }

        $isFinalPendingDate = $finalPendingDate -and $dateValue.Date -eq $finalPendingDate.Date
        $attemptStartedAt = Get-Date
        $attemptId = "{0}_{1}" -f $iso.Replace("-", ""), $attemptStartedAt.ToString("yyyyMMdd_HHmmss_fff")
        $dailyArguments = @{
            Date = $dateValue
            SkipPostVerifyDelay = $true
            SkipDownload = $true
        }

        $state["current_date"] = $iso
        $state["current_attempt_id"] = $attemptId
        $state["last_started_at_ist"] = $attemptStartedAt.ToString("o")
        $state["last_error"] = $null
        Save-RecoveryState -State $state -Status "running"

        Write-Host "[$(Get-Date -Format o)] Running ETL for $iso. Attempt: $attemptId. Final backlog date: $isFinalPendingDate"
        $global:LASTEXITCODE = 0
        & $DailyScript @dailyArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Daily pipeline returned exit code $LASTEXITCODE for $iso."
        }

        $evidence = Get-ValidationEvidence -Date $dateValue -NotBefore $attemptStartedAt
        if (-not $evidence) {
            throw "ETL returned for $iso without fresh exact full-day validation evidence for attempt $attemptId."
        }
        Save-DailyCheckpoint -Date $dateValue -Evidence $evidence -AttemptId $attemptId
        $state["last_successful_date"] = $iso
        $state["current_date"] = $null
        $state["current_attempt_id"] = $null
        $state["last_finished_at_ist"] = (Get-Date).ToString("o")
        $state["last_error"] = $null
        Save-RecoveryState -State $state -Status "catching_up"
        Write-Host "[$(Get-Date -Format o)] ETL checkpoint committed for $iso."
        Resume-PendingCleanup
    }

    Resume-PendingCleanup
    $remaining = [Math]::Max(0, [int]($TargetThroughDate - $dates[$dates.Count - 1]).TotalDays)
    $state["current_date"] = $null
    $state["backlog_days_remaining"] = $remaining
    $state["last_error"] = $null
    Save-RecoveryState -State $state -Status $(if ($remaining -gt 0) { "backlog_remaining" } else { "idle" })
    if ($remaining -eq 0 -and (Test-Path -LiteralPath $AsrunPriorityPath)) {
        Remove-Item -LiteralPath $AsrunPriorityPath -Force
        Write-Host "[$(Get-Date -Format o)] ASRUN priority request cleared; normal ETL behavior restored."
    }
    Write-Host "[$(Get-Date -Format o)] Recovery runner completed. Remaining backlog days: $remaining"
} catch {
    $failure = $_.Exception.Message
    [Console]::Error.WriteLine("Recovery runner failed: $failure")
    if (-not $DryRun) {
        try {
            $failedState = Read-RecoveryState
            $failedState["last_error"] = $failure
            $failedState["last_failed_at_ist"] = (Get-Date).ToString("o")
            Save-RecoveryState -State $failedState -Status "failed"
        } catch {
            [Console]::Error.WriteLine("Could not persist recovery failure state: $($_.Exception.Message)")
        }
    }
    try {
        $notifyPython = Join-Path $WorkspaceRoot '..\venv\Scripts\python.exe'
        & $notifyPython (Join-Path $WorkspaceRoot 'src\runtime\etl_notifications.py') `
            --step 'Daily recovery' --error $failure --state-path $RecoveryStatePath
    } catch {
        [Console]::Error.WriteLine("Could not show recovery failure alert: $($_.Exception.Message)")
    }
    exit 1
} finally {
    $liveRestartFailure = $null
    if ($ensureLiveMonitorAtExit -and (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'output\live_monitor\disabled.request'))) {
        Write-Host "Live monitor remains disabled by operator request."
    } elseif ($ensureLiveMonitorAtExit) {
        try {
            $liveAction = if ($livePausedForDailyEtl) {
                "Daily ETL work ended; restarting"
            } else {
                "Ensuring"
            }
            Write-Host "[$(Get-Date -Format o)] $liveAction the live monitor."
            & $LiveManager -Action Start
        } catch {
            [Console]::Error.WriteLine("Live monitor restart failed: $($_.Exception.Message)")
            $liveRestartFailure = $_.Exception
        }
    }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
    if ($ownsMutex) {
        try { $mutex.ReleaseMutex() } catch {}
    }
    $mutex.Dispose()
    if ($liveRestartFailure) {
        throw "Live monitor was not restored after daily ETL: $($liveRestartFailure.Message)"
    }
}
