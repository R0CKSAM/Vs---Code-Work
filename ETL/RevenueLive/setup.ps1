param([string]$Python='python')
$ErrorActionPreference = 'Stop'
$EnvPath = Join-Path $PSScriptRoot '.venv'
& $Python -m venv $EnvPath
if ($LASTEXITCODE -ne 0) {
    $LocalPython=Join-Path $EnvPath 'Scripts\python.exe'
    if (!(Test-Path $LocalPython)) { throw 'Python setup failed. Supply -Python with a working python.exe path.' }
    & $LocalPython -c "import sys, pip; assert sys.prefix != sys.base_prefix"
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment is incomplete.' }
    Write-Warning 'Activation scripts could not be installed. The isolated Python works; manage.ps1 uses it directly.'
}
& (Join-Path $EnvPath 'Scripts\python.exe') -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Setup complete. Run .\manage.ps1 -Action Start'
