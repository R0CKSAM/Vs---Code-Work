$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$work = Join-Path $root 'output\temp\backlog_repair_20261014'
$python = [IO.Path]::GetFullPath((Join-Path $root '..\venv\Scripts\python.exe'))
$script = Join-Path $root 'src\tools\repair_october_backlog_20261014.py'
$statePath = Join-Path $work 'state.json'
$env:VG_ETL_BASE = $root
$env:VG_ETL_NOTIFY_FAILURES = '1'
$env:TEMP = Join-Path $work 'process_temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$stdout = Join-Path $work 'supervised.out.log'
$stderr = Join-Path $work 'supervised.err.log'
$localLake = Join-Path $root 'output\temp\asrun_priority_20261012_1700\combined_lake'
try {
    $startedAt = Get-Date
    $process = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + $script + '"'),
        '--resume', '--threads', '4', '--local-fast-lake', ('"' + $localLake + '"')) -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $freshFailure = $state.phase -eq 'failed' -and (Get-Item -LiteralPath $statePath).LastWriteTime -ge $startedAt
    if ($process.ExitCode -ne 0 -and -not $freshFailure) {
        throw "Repair supervisor detected an unexpected worker exit: $($process.ExitCode). Last phase: $($state.phase)"
    }
    if ($process.ExitCode -eq 0 -and $state.phase -ne 'complete') {
        throw "Repair worker exited without completion. Last phase: $($state.phase)"
    }
    exit $process.ExitCode
} catch {
    $errorText = $_.Exception.Message
    & $python (Join-Path $root 'src\runtime\etl_notifications.py') --step 'Repair supervisor' --error $errorText --log-path $stderr --state-path $statePath
    exit 1
}
