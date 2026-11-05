param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$Python = Join-Path $PSScriptRoot '..\..\venv\Scripts\python.exe'
if (-not (Test-Path (Join-Path $PSScriptRoot 'data\smartvod.sqlite'))) {
    throw 'Prepare data first: python prepare.py --date YYYY-MM-DD'
}
& $Python (Join-Path $PSScriptRoot 'server.py') --port $Port
