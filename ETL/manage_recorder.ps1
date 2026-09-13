[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('Start', 'Stop', 'Restart', 'Status')]
    [string]$Action = 'Status',
    [ValidateRange(1, 65535)]
    [int]$Port = 8810,
    [System.Net.IPAddress]$HostAddress = '127.0.0.1',
    [string]$FfmpegPath = '',
    [ValidateRange(10, 1800)]
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$RecorderRoot = Join-Path $PSScriptRoot 'recorder'
$Python = Join-Path (Split-Path -Parent $PSScriptRoot) 'venv\Scripts\python.exe'
$App = Join-Path $RecorderRoot 'recorder_server.py'
$LogRoot = Join-Path $RecorderRoot 'logs'
$StopFile = Join-Path $LogRoot "recorder_$Port.stop"
$Url = "http://127.0.0.1:$Port"

function Get-RecorderStatus {
    try {
        $value = Invoke-RestMethod "$Url/api/status" -TimeoutSec 3
        if ($value.service -eq 'veto-recorder') { return $value }
    } catch { }
    return $null
}

function Get-ListenerIds {
    return @(netstat -ano -p tcp | ForEach-Object {
        if ($_ -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            [int]$Matches[1]
        }
    } | Sort-Object -Unique)
}

function Start-Recorder {
    $status = Get-RecorderStatus
    if ($status) {
        if ($status.stopping) { throw 'Recorder is still stopping; wait for it to finish.' }
        Write-Host "Recorder already running: $Url/recorder"
        return
    }
    if ((Get-ListenerIds).Count) {
        throw "Port $Port is occupied by another service or an older recorder. Stop that instance in its original terminal first."
    }
    if (!(Test-Path -LiteralPath $Python)) { throw "Python not found: $Python" }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $out = Join-Path $LogRoot "recorder_${Port}_$stamp.out.log"
    $err = Join-Path $LogRoot "recorder_${Port}_$stamp.err.log"
    $arguments = '"{0}" --host {1} --port {2}' -f $App, $HostAddress, $Port
    if ($FfmpegPath) {
        $resolvedFfmpeg = (Resolve-Path -LiteralPath $FfmpegPath).Path
        $arguments += ' --ffmpeg "{0}"' -f $resolvedFfmpeg
    }
    $process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $RecorderRoot -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Get-RecorderStatus) {
            Write-Host "Recorder running: $Url/recorder" -ForegroundColor Green
            Write-Host "Log: $err"
            return
        }
        if ($process.HasExited) { throw "Recorder exited. See $err" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Recorder startup not confirmed. See $err before trying again."
}

function Stop-Recorder {
    $status = Get-RecorderStatus
    if (!$status) {
        if ((Get-ListenerIds).Count) { throw "Port $Port is occupied; no process was stopped. An older recorder must be stopped in its original terminal." }
        Write-Host 'Recorder already stopped.'
        return
    }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding ASCII
    Write-Host "Closing $($status.active_recordings) active recording(s)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (!(Get-ListenerIds).Count) {
            Write-Host 'Recorder stopped. Recordings remain saved.'
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw 'Shutdown is taking longer than expected. Stop remains requested; no processes were forcibly killed. Check Status before restarting.'
}

# Serialize lifecycle commands from multiple terminals on this PC.
$mutex = [System.Threading.Mutex]::new($false, "Local\VetoRecorderManager_$Port")
$held = $false
try {
    try { $held = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $held = $true }
    if (!$held) { throw 'Another recorder management command is running.' }
    switch ($Action) {
        'Start' { Start-Recorder }
        'Stop' { Stop-Recorder }
        'Restart' { Stop-Recorder; Start-Recorder }
        'Status' {
            $status = Get-RecorderStatus
            if ($status) {
                Write-Host "Recorder running: $Url/recorder | PID $($status.pid) | Active recordings: $($status.active_recordings)"
                if (Test-Path -LiteralPath $StopFile) { Write-Host 'Shutdown requested.' }
            } elseif ((Get-ListenerIds).Count) {
                Write-Host "Port $Port is occupied; recorder identity could not be verified."
            } else { Write-Host 'Recorder stopped.' }
        }
    }
} finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
