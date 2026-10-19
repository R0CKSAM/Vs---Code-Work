[CmdletBinding()]
param([Parameter(Mandatory=$true)][datetime]$Date)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$day = $Date.ToString('yyyy-MM-dd')
$python = Join-Path (Split-Path $root -Parent) 'venv\Scripts\python.exe'
$helper = Join-Path $root 'src\tools\resume_failed_lake.py'
$auditRoot = Join-Path $root "output\temp\lake_resume_$($Date.ToString('yyyyMMdd'))"
$retainedRoot = '\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\retained_intermediates'
$source = [IO.Path]::GetFullPath((Join-Path $root ("data\stage\parquet\source=stream\year={0}\month={1}\day={2}" -f $Date.ToString('yyyy'),$Date.ToString('MM'),$Date.ToString('dd'))))
$destination = [IO.Path]::GetFullPath((Join-Path $retainedRoot "lake_resume_$day\stream_parquet"))
if (-not $source.StartsWith($root+'\data\stage\parquet\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe source path.' }
if (-not $destination.StartsWith($retainedRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe retention path.' }
$mutex = [Threading.Mutex]::new($false, 'Local\VetoETLRecoveryBacklog')
$owned = $false
$state = @{date=$day;status='preflight';files=@();relocated_bytes=0L;started_at=(Get-Date).ToString('o')}
New-Item -ItemType Directory -Path $auditRoot -Force | Out-Null
if (Test-Path -LiteralPath (Join-Path $auditRoot 'state.json')) {
    $previous = Get-Content -LiteralPath (Join-Path $auditRoot 'state.json') -Raw | ConvertFrom-Json
    $state.files = @($previous.files)
    $state.relocated_bytes = [long]$previous.relocated_bytes
}
function Save-State {
    $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $auditRoot 'state.json.tmp') -Encoding UTF8
    Move-Item -LiteralPath (Join-Path $auditRoot 'state.json.tmp') -Destination (Join-Path $auditRoot 'state.json') -Force
}
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'Another recovery runner is active.' }
    & (Join-Path $root 'manage_live_monitor.ps1') -Action Disable
    & $python $helper --date $day --base (Join-Path $root 'data') --check-only
    if ($LASTEXITCODE -ne 0) { throw 'Final-clean preflight failed.' }
    $pipelineLock = Join-Path $root 'output\state\pipeline.lock'
    if (Test-Path -LiteralPath $pipelineLock) {
        $lock = Get-Content -LiteralPath $pipelineLock -Raw | ConvertFrom-Json
        if (Get-Process -Id $lock.pid -ErrorAction SilentlyContinue) { throw 'An ETL pipeline is still running.' }
    }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a reparse-point source.' }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $state.status = 'retaining_stage'
    Save-State
    foreach ($file in Get-ChildItem -LiteralPath $source -File -Filter '*.parquet') {
        $absolute = [IO.Path]::GetFullPath($file.FullName)
        $target = [IO.Path]::GetFullPath((Join-Path $destination $file.Name))
        if (-not $absolute.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase) -or
            -not $target.StartsWith($destination+'\',[StringComparison]::OrdinalIgnoreCase) -or
            ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe stage file path.' }
        $state.current_file = $file.Name
        Save-State
        $hash = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash
        if (-not (Test-Path -LiteralPath $target)) {
            $partial = "$target.copying"
            Copy-Item -LiteralPath $absolute -Destination $partial -Force
            if ((Get-Item -LiteralPath $partial).Length -ne $file.Length -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $hash) { throw "Copy verification failed: $absolute" }
            Move-Item -LiteralPath $partial -Destination $target
        } elseif ((Get-Item -LiteralPath $target).Length -ne $file.Length -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $hash) {
            throw "Existing retained copy differs: $target"
        }
        $current = Get-Item -LiteralPath $absolute
        if ($current.Length -ne $file.Length -or $current.LastWriteTimeUtc -ne $file.LastWriteTimeUtc) { throw 'Source changed during retention.' }
        # Both absolute paths are bounded above and the retained copy is hash-verified.
        Remove-Item -LiteralPath $absolute
        $state.files += @{source=$absolute;destination=$target;sha256=$hash;bytes=$file.Length}
        $state.relocated_bytes += $file.Length
        Save-State
        Write-Output "Retained $($file.Name); freed $([math]::Round($state.relocated_bytes/1GB,2)) GiB."
    }
    $free = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'").FreeSpace
    if ($free -lt 30GB) { throw 'Less than 30 GiB free; refusing another disk-full partition attempt.' }
    $state.status = 'partitioning'
    Save-State
    & $python -u $helper --date $day --base (Join-Path $root 'data') --temp-dir (Join-Path $retainedRoot "lake_resume_$day\duckdb")
    if ($LASTEXITCODE -ne 0) { throw 'Partition resume failed; retained inputs were preserved.' }
    $state.status = 'normal_recovery'
    Save-State
    $mutex.ReleaseMutex()
    $owned = $false
    & (Join-Path $root 'run_recovery_pipeline.ps1') -StartDate $Date -ThroughDate $Date
    if ($LASTEXITCODE -ne 0) { throw 'Normal recovery failed; inspect recovery logs.' }
    $state.status = 'complete'
    $state.finished_at = (Get-Date).ToString('o')
    Save-State
} catch {
    if ($owned -or $state.status -eq 'normal_recovery') {
        $state.status = 'failed'
        $state.error = $_.Exception.Message
        Save-State
    }
    throw
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
