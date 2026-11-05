param(
    [Parameter(Mandatory = $true)]
    [string]$Channel,
    [string[]]$Input = @(),
    [string]$RawRoot = "",
    [string]$IdentityMinute = "",
    [switch]$DetailedLogs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "..\venv\Scripts\python.exe"
$Builder = Join-Path $PSScriptRoot "src\build_asrun_demo.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python virtual environment not found: $Python"
}
if ($Input.Count -eq 0) {
    if (-not $RawRoot) {
        $RawRoot = if ($env:VG_ASRUN_RAW_DIR) {
            $env:VG_ASRUN_RAW_DIR
        } else {
            "Z:\Veto Logs Backup\DO NOT DELETE\source=AsRUN"
        }
    }
    if (-not (Test-Path -LiteralPath $RawRoot)) {
        throw "ASRUN source folder not found: $RawRoot"
    }
    $Input = @(
        Get-ChildItem -LiteralPath $RawRoot -Filter "ASRUN-*.txt" -File |
            Sort-Object Name |
            ForEach-Object FullName
    )
}
if ($Input.Count -eq 0) {
    throw "No ASRUN-DDMMYY.txt files found in $RawRoot. Add source files there or supply -Input."
}

$BuilderArgs = @($Builder, "--channel", $Channel, "--input") + $Input
# The scheduled audience mart can lag the repaired ASRUN snapshot. Reuse only
# a completed refresh, including its explicitly recorded unavailable days.
$RefreshState = Join-Path $Root "output\state\asrun_available_refresh.json"
if (-not $IdentityMinute -and (Test-Path -LiteralPath $RefreshState)) {
    $Refresh = Get-Content -LiteralPath $RefreshState -Raw | ConvertFrom-Json
    if ($Refresh.status -eq "complete") {
        $Snapshot = Join-Path $Refresh.work "audience\identity_minute.parquet"
        if (-not (Test-Path -LiteralPath $Snapshot -PathType Leaf)) {
            throw "Completed ASRUN audience snapshot is missing: $Snapshot"
        }
        $IdentityMinute = $Snapshot
        foreach ($Day in $Refresh.unavailable_viewer_days) {
            $BuilderArgs += @("--unavailable-viewer-day", ("{0}:{1}" -f $Day[0], $Day[1]))
        }
    }
}
if ($IdentityMinute) {
    if (-not (Test-Path -LiteralPath $IdentityMinute -PathType Leaf)) {
        throw "Identity-minute file not found: $IdentityMinute"
    }
    Write-Host "Using ASRUN audience: $IdentityMinute"
    $BuilderArgs += @("--identity-minute", $IdentityMinute)
}
if ($DetailedLogs) {
    $BuilderArgs += "--verbose"
}
& $Python @BuilderArgs
if ($LASTEXITCODE -ne 0) {
    throw "ASRUN dashboard generation failed with Python exit code $LASTEXITCODE."
}
