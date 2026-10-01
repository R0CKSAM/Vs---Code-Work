param([string]$PythonExe='')
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$buildTemp=Join-Path $root '.tools\handoff-temp'
$pipCache=Join-Path $root '.tools\handoff-pip-cache'
New-Item -ItemType Directory -Path $buildTemp,$pipCache -Force | Out-Null
$env:TEMP=$buildTemp
$env:TMP=$buildTemp
$env:PIP_CACHE_DIR=$pipCache
if (-not $PythonExe) {
    $PythonExe=(& py -3.14 -c 'import sys; print(sys.executable)').Trim()
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw 'Supply -PythonExe with a standard CPython 3.14 executable.'
}
$version=& $PythonExe -c 'import sys; print(sys.version_info.major, sys.version_info.minor)'
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne '3 14') { throw 'This release build requires standard CPython 3.14.' }
if ($PythonExe -like '*WindowsApps*') { throw 'Use standard CPython instead of a Microsoft Store installation.' }
$builderDir=Join-Path $root '.tools\handoff-venv'
$builder=Join-Path $builderDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $builder)) {
    & $PythonExe -m venv $builderDir
    if ($LASTEXITCODE -ne 0) {
        if (-not (Test-Path -LiteralPath $builder)) { throw 'Could not create the release build environment.' }
        & $builder -c 'import sys,pip; assert sys.prefix != sys.base_prefix'
        if ($LASTEXITCODE -ne 0) { throw 'Release build environment is incomplete.' }
        Write-Warning 'Activation batch file could not be copied; the isolated builder Python works.'
    }
}
& $builder -m pip install -r (Join-Path $root 'requirements.txt') 'Nuitka>=4.2,<5'
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies could not be installed.' }
Push-Location $root
try {
    & $builder -m unittest -q notneeded.test_app
    if ($LASTEXITCODE -ne 0) { throw 'RevenueLive tests failed; refusing to package.' }
    $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
    $buildRoot=Join-Path $root ".tools\handoff-build-$stamp"
    $release=Join-Path $root ".tools\handoff-release-$stamp"
    & $builder -m nuitka --mode=standalone --msvc=latest --assume-yes-for-downloads --include-module=account_email --include-module=insight_presets --include-module=openpyxl --include-module=xlrd --output-dir="$buildRoot" --output-filename=RevenueLive.exe (Join-Path $root 'app.py')
    if ($LASTEXITCODE -ne 0) { throw 'Nuitka compilation failed; no handoff was created.' }
    $dist=@(Get-ChildItem -LiteralPath $buildRoot -Directory -Filter '*.dist')
    if ($dist.Count -ne 1) { throw 'Expected exactly one Nuitka standalone distribution.' }
    New-Item -ItemType Directory -Path $release -Force | Out-Null
    Get-ChildItem -LiteralPath $dist[0].FullName -Force | Copy-Item -Destination $release -Recurse -Force
    $assetDir=Join-Path $release 'static'
    New-Item -ItemType Directory -Path $assetDir -Force | Out-Null
    $assets=@('index.html','style.css','analytics.css','app.js','analytics.js','quick-insights.js',
        'chart.umd.min.js','channel-comparison.js','revenue-share.js','diy-graphs.js',
        'dark.css','light.css','uploads.css','flatpickr.min.css','flatpickr.min.js','lucide.min.js',
        'insight-growth-arrow.svg','Chart.js.LICENSE.md')
    foreach ($name in $assets) {
        Copy-Item -LiteralPath (Join-Path $root "static\$name") -Destination $assetDir
    }
    $logos=Join-Path $assetDir 'channel-logos'
    New-Item -ItemType Directory -Path $logos -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $root 'static\channel-logos') -File |
        Where-Object { $_.Extension -in @('.png','.jpg','.jpeg','.webp','.svg') -or $_.Name -eq 'manifest.json' } |
        Copy-Item -Destination $logos
    Copy-Item -LiteralPath (Join-Path $root 'start_release.ps1') -Destination $release
    Copy-Item -LiteralPath (Join-Path $root 'PRODUCTION-HANDOFF.md') -Destination $release
    Copy-Item -LiteralPath (Join-Path $root 'Lucide.LICENSE.txt') -Destination $release
    Copy-Item -LiteralPath (Join-Path $root 'flatpickr.LICENSE.txt') -Destination $release
    & $builder -m pip freeze | Set-Content -LiteralPath (Join-Path $release 'BUILD-DEPENDENCIES.txt') -Encoding Ascii
    if ($LASTEXITCODE -ne 0) { throw 'Could not record build dependencies.' }
    $forbidden=@(Get-ChildItem -LiteralPath $release -Recurse -File | Where-Object {
        $_.Extension -in @('.py','.pyc','.pyo','.db','.sqlite','.xls','.xlsx') -or
        $_.Name -in @('mail.json','initial_admin.txt','super_admin_initial.txt')
    })
    if ($forbidden.Count) { throw "Release contains source or data files: $($forbidden.Name -join ', ')" }
    $hashes=Get-ChildItem -LiteralPath $release -Recurse -File | ForEach-Object {
        $relative=$_.FullName.Substring($release.Length+1)
        '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash,$relative
    }
    $hashes | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding Ascii
    Write-Host "Source-free release ready: $release"
} finally {
    Pop-Location
}
