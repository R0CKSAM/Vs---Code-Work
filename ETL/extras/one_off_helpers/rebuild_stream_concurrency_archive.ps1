param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Python = Join-Path $Root '..\venv\Scripts\python.exe'
$Builder = Join-Path $Root 'src\tools\build_concurrency.py'
$Generator = Join-Path $Root 'src\dashboards\concurrencyDashboard\generate_concurrency.py'
$ArchiveLake = 'Z:\Veto Logs Backup\DO NOT DELETE'
$CurrentLake = Join-Path $Root 'data\lake'
$OutDir = Join-Path $Root 'output\watch_hours\concurrency'
$TempDir = Join-Path $Root 'output\cache\duckdb_temp\deep_profile'
$Windows = @(
    @('2026-04-01', '2026-04-30'),
    @('2026-05-01', '2026-05-31'),
    @('2026-06-01', '2026-06-30'),
    @('2026-07-01', '2026-07-15')
)

foreach ($Window in $Windows) {
    $Start, $End = $Window
    Write-Output "[$(Get-Date -Format o)] Restoring STREAM $Start to $End from archive."
    & $Python $Builder --lake $ArchiveLake --out-dir $OutDir --source stream --threads 2 --memory-limit 8GB --temp-dir $TempDir --start $Start --end $End
    if ($LASTEXITCODE -ne 0) {
        throw "Archive Concurrency rebuild failed for $Start to $End with exit code $LASTEXITCODE."
    }
}

Write-Output "[$(Get-Date -Format o)] Re-applying current STREAM 16-17 July from D: lake."
& $Python $Builder --lake $CurrentLake --out-dir $OutDir --source stream --threads 2 --memory-limit 8GB --temp-dir $TempDir --start 2026-07-16 --end 2026-07-17
if ($LASTEXITCODE -ne 0) {
    throw "Current-lake Concurrency rebuild failed with exit code $LASTEXITCODE."
}

Write-Output "[$(Get-Date -Format o)] Regenerating Concurrency dashboard."
& $Python $Generator --data-dir $OutDir --out (Join-Path $OutDir 'veto_concurrency.html') --title 'Veto Concurrency'
if ($LASTEXITCODE -ne 0) {
    throw "Concurrency HTML generation failed with exit code $LASTEXITCODE."
}
Write-Output "[$(Get-Date -Format o)] Archive-aware Concurrency recovery completed."
