param(
    [Parameter(Mandatory = $true)]
    [string]$Channel,
    [string[]]$Input = @(),
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
    $Input = @(Get-ChildItem (Join-Path $PSScriptRoot "data\raw") -Filter "ASRUN-*.txt" -File | ForEach-Object FullName)
}
if ($Input.Count -eq 0) {
    throw "Put ASRUN .txt files in $PSScriptRoot\data\raw or supply -Input."
}

$BuilderArgs = @($Builder, "--channel", $Channel, "--input") + $Input
if ($DetailedLogs) {
    $BuilderArgs += "--verbose"
}
& $Python @BuilderArgs
if ($LASTEXITCODE -ne 0) {
    throw "ASRUN dashboard generation failed with Python exit code $LASTEXITCODE."
}
