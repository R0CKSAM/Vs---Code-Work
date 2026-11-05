$ErrorActionPreference = 'Stop'
$Python = Join-Path $PSScriptRoot '..\..\venv\Scripts\python.exe'
& $Python (Join-Path $PSScriptRoot 'refresh.py')
if ($LASTEXITCODE -ne 0) { throw 'SmartVOD refresh failed; previous published snapshot retained.' }
