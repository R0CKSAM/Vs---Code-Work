param(
    [Parameter(Mandatory = $true)]
    [string]$Channel,
    [string[]]$Input = @(),
    [string]$RawRoot = "",
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
if ($DetailedLogs) {
    $BuilderArgs += "--verbose"
}
& $Python @BuilderArgs
if ($LASTEXITCODE -ne 0) {
    throw "ASRUN dashboard generation failed with Python exit code $LASTEXITCODE."
}
