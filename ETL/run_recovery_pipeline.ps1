[CmdletBinding(PositionalBinding = $false)]
param(
    [Nullable[datetime]]$StartDate = $null,
    [Nullable[datetime]]$ThroughDate = $null,
    [ValidateRange(1, 366)]
    [int]$MaxCatchUpDays = 31,
    [ValidateRange(1, 366)]
    [int]$BootstrapLookbackDays = 60,
    [ValidateRange(1, 6)]
    [int]$MaxParallelDownloads = 6,
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
$StateDir = Join-Path $WorkspaceRoot "output\state"
$DailyStateDir = Join-Path $StateDir "daily_runs"
$RecoveryStatePath = Join-Path $StateDir "recovery_backlog.json"
$ValidationRoot = Join-Path $WorkspaceRoot "output\validation"
$LogDir = Join-Path $WorkspaceRoot "output\logs"
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

function Get-ValidationEvidence {
    param(
        [Parameter(Mandatory = $true)][datetime]$Date,
        [Nullable[datetime]]$NotBefore = $null
    )

    if (-not (Test-Path -LiteralPath $ValidationRoot)) { return $null }
    $iso = $Date.ToString("yyyy-MM-dd")
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
        if ($report.date -ne $iso -or $report.mode -ne "full") { continue }
        if ([int]($report.hard_failure_count) -ne 0) { continue }
        if ($report.overall_status -notin @("PASS", "REVIEW")) { continue }

        $sourceResults = @($report.source_results)
        $reconciliations = @($report.profile_reconciliation)
        $valid = $true
        foreach ($source in @("fast", "stream")) {
            $sourceResult = $sourceResults | Where-Object { $_.source -eq $source } | Select-Object -First 1
            $reconciliation = $reconciliations | Where-Object { $_.source -eq $source } | Select-Object -First 1
            if (
                -not $sourceResult -or
                $sourceResult.status -ne "PASS" -or
                $sourceResult.selected.full_day -ne $true -or
                -not $reconciliation -or
                $reconciliation.status -ne "PASS" -or
                [int64]($reconciliation.delta_rows) -ne 0
            ) {
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
    if (Test-Path -LiteralPath $marker) {
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
    return Get-ValidationEvidence -Date $Date
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

function Save-DailyCheckpoint {
    param(
        [Parameter(Mandatory = $true)][datetime]$Date,
        [Parameter(Mandatory = $true)]$Evidence,
        [string]$AttemptId = ""
    )

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

    $logPath = Join-Path $LogDir ("recovery_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    Start-Transcript -Path $logPath -Append | Out-Null
    $transcriptStarted = $true
    Write-Host "[$(Get-Date -Format o)] Recovery runner started. Through date: $($TargetThroughDate.ToString('yyyy-MM-dd'))"

    $state = Read-RecoveryState
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
        Write-Host "Dry-run prefetch plan: $($pendingDates.Count * 2) source/date jobs, max $MaxParallelDownloads parallel, each transfers=$DownloadTransfers/checkers=$DownloadCheckers."
        Write-Host "Dry run complete; no ETL or checkpoint files were changed."
        exit 0
    }

    if ($pendingDates.Count) {
        $state["current_date"] = $null
        $state["download_dates"] = @($pendingDates | ForEach-Object { $_.ToString("yyyy-MM-dd") })
        $state["download_jobs"] = $pendingDates.Count * 2
        $state["max_parallel_downloads"] = $MaxParallelDownloads
        $state["download_transfers_each"] = $DownloadTransfers
        $state["download_checkers_each"] = $DownloadCheckers
        $state["last_error"] = $null
        Save-RecoveryState -State $state -Status "downloading"

        Write-Host "[$(Get-Date -Format o)] Starting validated parallel prefetch for $($pendingDates.Count) date(s)."
        $prefetchArguments = @{
            Dates = [datetime[]]@($pendingDates)
            MaxParallelDownloads = $MaxParallelDownloads
            Transfers = $DownloadTransfers
            Checkers = $DownloadCheckers
        }
        $global:LASTEXITCODE = 0
        & $PrefetchScript @prefetchArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Parallel recovery prefetch returned exit code $LASTEXITCODE."
        }
        $state["download_dates"] = @()
        $state["download_jobs"] = 0
        Save-RecoveryState -State $state -Status "downloads_complete"
    }

    $finalPendingDate = if ($pendingDates.Count) { $pendingDates[$pendingDates.Count - 1] } else { $null }
    foreach ($dateValue in $dates) {
        $iso = $dateValue.ToString("yyyy-MM-dd")
        $existing = $completionByDate[$iso]
        if ($existing -and -not $Force) {
            Write-Host "[$(Get-Date -Format o)] $iso already complete via $($existing.Kind); advancing checkpoint."
            Save-DailyCheckpoint -Date $dateValue -Evidence $existing
            $state["last_successful_date"] = $iso
            $state["current_date"] = $null
            $state["last_error"] = $null
            Save-RecoveryState -State $state -Status "catching_up"
            continue
        }

        $isFinalPendingDate = $finalPendingDate -and $dateValue.Date -eq $finalPendingDate.Date
        $attemptStartedAt = Get-Date
        $attemptId = "{0}_{1}" -f $iso.Replace("-", ""), $attemptStartedAt.ToString("yyyyMMdd_HHmmss_fff")
        $dailyArguments = @{
            Date = $dateValue
            SkipPostVerifyDelay = $true
            SkipDownload = $true
        }
        if (-not $isFinalPendingDate) {
            $dailyArguments["SkipWatch"] = $true
            $dailyArguments["SkipOverview"] = $true
            $dailyArguments["SkipLakeArchive"] = $true
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
    }

    $remaining = [Math]::Max(0, [int]($TargetThroughDate - $dates[$dates.Count - 1]).TotalDays)
    $state["current_date"] = $null
    $state["backlog_days_remaining"] = $remaining
    $state["last_error"] = $null
    Save-RecoveryState -State $state -Status $(if ($remaining -gt 0) { "backlog_remaining" } else { "idle" })
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
    exit 1
} finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
    if ($ownsMutex) {
        try { $mutex.ReleaseMutex() } catch {}
    }
    $mutex.Dispose()
}
