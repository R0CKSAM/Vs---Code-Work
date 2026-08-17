[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)][ValidateSet("fast", "stream", "single")]
    [string]$Source,
    [Parameter(Mandatory = $true)][datetime]$Date,
    [Parameter(Mandatory = $true)][string]$RemotePath,
    [Parameter(Mandatory = $true)][string]$LocalPath,
    [Parameter(Mandatory = $true)][string]$RcloneExe,
    [string]$RcloneConfig = "",
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$ResultPath,
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
$targetIso = $Date.ToString("yyyy-MM-dd")
$startedAt = Get-Date
$transcriptStarted = $false

function Write-JsonAtomic {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][hashtable]$Payload)

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.tmp.$PID"
    $Payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Invoke-Rclone {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [Parameter(Mandatory = $true)][string]$Step)

    Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] rclone ${Step}: $($Arguments -join ' ')"
    # Native stderr is progress/error output, not a PowerShell exception boundary.
    # Always decide success from rclone's exit code so transient cleanup messages
    # can be handled by the retry loop below.
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $RcloneExe @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "rclone $Step failed for $Source/$targetIso with exit code $exitCode"
    }
}

function Get-RcloneSnapshot {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)

    Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] Reading $Label snapshot: $Path"
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $jsonLines = & $RcloneExe size $Path --json
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "rclone size failed for $Source/$targetIso $Label with exit code $exitCode"
    }
    $jsonText = ($jsonLines | Out-String).Trim()
    if (-not $jsonText) { throw "rclone size returned no data for $Source/$targetIso $Label" }
    $stats = $jsonText | ConvertFrom-Json
    return [pscustomobject]@{ Count = [int64]$stats.count; Bytes = [int64]$stats.bytes }
}

function Wait-ForStableRemote {
    $matches = 0
    $previous = $null
    while ($true) {
        $current = Get-RcloneSnapshot -Path $RemotePath -Label "remote stability"
        if ($previous -and $previous.Count -eq $current.Count -and $previous.Bytes -eq $current.Bytes) {
            $matches += 1
        } else {
            $matches = 1
        }
        $previous = $current
        if ($matches -ge $StableChecks) { return $current }
        Start-Sleep -Seconds ($StableWaitMinutes * 60)
    }
}

function Sync-Remote {
    $syncArguments = @(
            "sync", $RemotePath, $LocalPath,
            "--size-only",
            "--transfers", $Transfers.ToString(),
            "--checkers", $Checkers.ToString(),
            "--multi-thread-streams", $MultiThreadStreams.ToString(),
            "--buffer-size", $BufferSize,
            "--retries", "5",
            "--low-level-retries", "10",
            "--stats", "30s",
            "--stats-one-line"
        )
    $lastFailure = $null
    for ($syncAttempt = 1; $syncAttempt -le 3; $syncAttempt++) {
        try {
            Invoke-Rclone -Step "sync attempt $syncAttempt/3" -Arguments $syncArguments
            return
        } catch {
            $lastFailure = $_
            if ($syncAttempt -lt 3) {
                Write-Warning "[$Source/$targetIso] Sync attempt $syncAttempt failed; retrying in 10 seconds. $($_.Exception.Message)"
                Start-Sleep -Seconds 10
            }
        }
    }
    throw $lastFailure
}

try {
    if ($Date.Date -ge (Get-Date).Date) { throw "Date must be a completed day before today: $targetIso" }
    if ($RemotePath.StartsWith("-") -or $RemotePath -notmatch "^[^\\/:]+:.+") {
        throw "Invalid rclone remote path: '$RemotePath'"
    }
    foreach ($path in @($LocalPath, $RcloneExe, $LogPath, $ResultPath)) {
        if (-not $path -or $path.StartsWith("-")) { throw "Invalid worker path: '$path'" }
    }
    if (-not (Test-Path -LiteralPath $RcloneExe)) {
        $rcloneCommand = Get-Command -Name $RcloneExe -CommandType Application -ErrorAction SilentlyContinue
        if (-not $rcloneCommand) { throw "rclone executable is missing: $RcloneExe" }
        $RcloneExe = $rcloneCommand.Source
    }
    if ($RcloneConfig) { $env:RCLONE_CONFIG = $RcloneConfig }

    New-Item -ItemType Directory -Path $LocalPath, (Split-Path -Parent $LogPath), (Split-Path -Parent $ResultPath) -Force | Out-Null
    Start-Transcript -Path $LogPath -Append | Out-Null
    $transcriptStarted = $true
    Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] Download worker started with transfers=$Transfers, checkers=$Checkers."

    $startRemote = if ($WaitForRemoteStable) {
        Wait-ForStableRemote
    } else {
        Get-RcloneSnapshot -Path $RemotePath -Label "starting remote"
    }
    if ($startRemote.Count -le 0) { throw "Remote file count is zero: $RemotePath" }

    Sync-Remote

    $verifiedRemote = $startRemote
    $verifiedLocal = $null
    $verified = $false
    if ($SkipVerifyAfterSync) {
        Write-Warning "Post-sync verification was skipped for $Source/$targetIso."
    } else {
        for ($attempt = 1; $attempt -le $VerifyRetries; $attempt++) {
            Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] Verification attempt $attempt/$VerifyRetries."
            $verifiedRemote = Get-RcloneSnapshot -Path $RemotePath -Label "current remote"
            $verifiedLocal = Get-RcloneSnapshot -Path $LocalPath -Label "local"
            if ($verifiedRemote.Count -eq $verifiedLocal.Count -and $verifiedRemote.Bytes -eq $verifiedLocal.Bytes) {
                $verified = $true
                break
            }
            if ($attempt -lt $VerifyRetries) {
                Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] Snapshot mismatch; syncing again."
                Sync-Remote
                if ($VerifyWaitMinutes -gt 0) { Start-Sleep -Seconds ($VerifyWaitMinutes * 60) }
            }
        }
        if (-not $verified) {
            throw "Remote/local verification failed: remote=$($verifiedRemote.Count)/$($verifiedRemote.Bytes), local=$($verifiedLocal.Count)/$($verifiedLocal.Bytes)"
        }
    }

    $finishedAt = Get-Date
    Write-JsonAtomic -Path $ResultPath -Payload @{
        schema_version = 1
        status = "complete"
        source = $Source
        date = $targetIso
        remote_path = $RemotePath
        local_path = $LocalPath
        remote_count = $verifiedRemote.Count
        remote_bytes = $verifiedRemote.Bytes
        local_count = if ($verifiedLocal) { $verifiedLocal.Count } else { $null }
        local_bytes = if ($verifiedLocal) { $verifiedLocal.Bytes } else { $null }
        verified = $verified
        transfers = $Transfers
        checkers = $Checkers
        started_at_ist = $startedAt.ToString("o")
        finished_at_ist = $finishedAt.ToString("o")
        duration_seconds = [Math]::Round(($finishedAt - $startedAt).TotalSeconds, 2)
        log_path = $LogPath
        computer = $env:COMPUTERNAME
    }
    Write-Host "[$(Get-Date -Format o)] [$Source/$targetIso] Download and validation complete."
} catch {
    $failure = $_.Exception.Message
    try {
        Write-JsonAtomic -Path $ResultPath -Payload @{
            schema_version = 1
            status = "failed"
            source = $Source
            date = $targetIso
            error = $failure
            started_at_ist = $startedAt.ToString("o")
            failed_at_ist = (Get-Date).ToString("o")
            log_path = $LogPath
            computer = $env:COMPUTERNAME
        }
    } catch {}
    [Console]::Error.WriteLine("Download worker failed for $Source/${targetIso}: $failure")
    throw
} finally {
    if ($transcriptStarted) { try { Stop-Transcript | Out-Null } catch {} }
}
