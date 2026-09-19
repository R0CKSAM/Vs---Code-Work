param([switch]$NoStart)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "Veto Scoreboard Maker setup" -ForegroundColor Cyan
function Test-Python314([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable)) { return $false }
    if ($Executable -match "\\WindowsApps\\") { return $false }
    & $Executable -c "import sys, tkinter, venv; raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

function Find-Python314 {
    $candidates = @()
    if ($env:SCOREBOARD_PYTHON) { $candidates += $env:SCOREBOARD_PYTHON }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        "C:\Python314\python.exe"
    )
    try {
        $resolved = (& py -3.14 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($resolved) { $candidates += $resolved.Trim() }
    } catch {}
    try { $candidates += (Get-Command python.exe -ErrorAction Stop).Source } catch {}
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Python314 $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return $null
}

$python = Find-Python314
if (-not $python) {
    throw "Install 64-bit Python 3.14 with pip and Tk, then run setup again. The Microsoft Store alias alone is not sufficient."
}

$packageTarget = Join-Path $PSScriptRoot "python_packages"
New-Item -ItemType Directory -Path $packageTarget -Force | Out-Null

$wheelFolder = Join-Path $PSScriptRoot "wheels"
$offlineWheels = Get-ChildItem -LiteralPath $wheelFolder -Filter "*.whl" -ErrorAction SilentlyContinue
Write-Host "Installing scoreboard dependencies. This can take several minutes..."
if ($offlineWheels) {
    & $python -m pip install --disable-pip-version-check --no-index --find-links $wheelFolder --target $packageTarget --upgrade -r (Join-Path $PSScriptRoot "requirements.txt")
} else {
    & $python -m pip install --disable-pip-version-check --target $packageTarget --upgrade -r (Join-Path $PSScriptRoot "requirements.txt")
}
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot "data\uploads") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot "logs") -Force | Out-Null
Set-Content -LiteralPath (Join-Path $PSScriptRoot "data\python_path.txt") -Value $python -Encoding ASCII
$env:PYTHONPATH = $packageTarget
$env:SCOREBOARD_WEB_UPLOAD_DIR = Join-Path $PSScriptRoot "data\uploads"
$testImage = Join-Path $PSScriptRoot "data\setup-test.png"
& $python (Join-Path $PSScriptRoot "scoreboard_app.py") --headless $testImage
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $testImage)) {
    throw "The scoreboard self-test failed."
}
Remove-Item -LiteralPath $testImage -Force -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "tools\ffmpeg\bin\ffmpeg.exe"))) {
    Write-Warning "FFmpeg is not bundled. PNG and live output work, but MP4 export needs FFmpeg in PATH or tools\ffmpeg\bin\ffmpeg.exe."
}
$desktopVideoPaths = @(
    "C:\Program Files\Blackmagic Design\Desktop Video",
    "C:\Program Files\Blackmagic Design\Blackmagic Desktop Video"
)
if (-not ($desktopVideoPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)) {
    Write-Warning "DeckLink output needs Blackmagic Desktop Video installed on this PC."
}

Set-Content -LiteralPath (Join-Path $PSScriptRoot ".setup-complete") -Value (Get-Date -Format o) -Encoding ASCII
Write-Host "Setup completed successfully." -ForegroundColor Green
if (-not $NoStart) {
    & (Join-Path $PSScriptRoot "start_scoreboard.ps1")
}
