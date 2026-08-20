$ErrorActionPreference = "Stop"

$EtlRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $EtlRoot

$Chunks = @(
    @("2026-06-17", "2026-06-23"),
    @("2026-06-24", "2026-06-30"),
    @("2026-07-01", "2026-07-07"),
    @("2026-07-08", "2026-07-15"),
    @("2026-07-23", "2026-07-23"),
    @("2026-07-27", "2026-07-27")
)

try {
    Set-Location -LiteralPath $RepoRoot
    Write-Host "Starting backfill for missing stream concurrency dates..."

    foreach ($Chunk in $Chunks) {
        $Start = $Chunk[0]
        $End = $Chunk[1]

        Write-Host ""
        Write-Host "========================================="
        Write-Host "[run] STREAM concurrency $Start to $End"
        Write-Host "========================================="
        
        & ".\venv\Scripts\python.exe" "ETL\src\tools\build_concurrency.py" `
            --source stream `
            --start $Start `
            --end $End `
            --threads 6 `
            --memory-limit 16GB
            
        if ($LASTEXITCODE -ne 0) {
            throw "STREAM concurrency backfill failed for $Start to $End with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "✅ All missing STREAM concurrency dates backfilled successfully!"
    Write-Host "You can now re-run extras\one_off_helpers\stream_concurrency_and_watch_hours\export_stream_concurrency.py to generate the updated CSVs."
}
catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}
