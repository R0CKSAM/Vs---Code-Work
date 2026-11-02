$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'output\state\lake_parallel_prefetch.json'
$state = @{status='running'; pid=$PID; dates=@('2026-10-31','2026-11-01')}
function Save-State {
    $state | ConvertTo-Json | Set-Content -LiteralPath "$statePath.tmp" -Encoding UTF8
    Move-Item -LiteralPath "$statePath.tmp" -Destination $statePath -Force
}
Save-State
try {
    $global:LASTEXITCODE = 0
    & (Join-Path $PSScriptRoot 'prefetch_daily_sources.ps1') -Dates @([datetime]'2026-10-31',[datetime]'2026-11-01') -MaxParallelDownloads 4 -Transfers 16 -Checkers 32
    if ($LASTEXITCODE -ne 0) { throw "Prefetch failed: $LASTEXITCODE" }
    $state['status']='complete'
} catch {
    $state['status']='failed'
    $state['error']=$_.Exception.Message
    throw
} finally { Save-State }
