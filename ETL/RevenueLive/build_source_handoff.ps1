$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$release=Join-Path $root ".tools\source-handoff-$stamp"
if (Test-Path -LiteralPath $release) { throw 'A handoff with this timestamp already exists.' }
New-Item -ItemType Directory -Path $release -Force | Out-Null
$source=@('app.py','account_email.py','insight_presets.py','backup.py',
    'provision_super_admin.py','requirements.txt','setup.ps1','manage.ps1',
    'mail.example.json','README.md','SOURCE-HANDOFF.md',
    'Lucide.LICENSE.txt','flatpickr.LICENSE.txt')
foreach ($name in $source) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination $release
}
$static=Join-Path $release 'static'
New-Item -ItemType Directory -Path $static -Force | Out-Null
$assets=@('index.html','style.css','analytics.css','app.js','analytics.js',
    'quick-insights.js','chart.umd.min.js','channel-comparison.js',
    'revenue-share.js','diy-graphs.js','dark.css','light.css','uploads.css',
    'flatpickr.min.css','flatpickr.min.js','lucide.min.js',
    'insight-growth-arrow.svg','Chart.js.LICENSE.md')
foreach ($name in $assets) {
    Copy-Item -LiteralPath (Join-Path $root "static\$name") -Destination $static
}
$logos=Join-Path $static 'channel-logos'
New-Item -ItemType Directory -Path $logos -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'static\channel-logos') -File |
    Where-Object { $_.Extension -in @('.png','.jpg','.jpeg','.webp','.svg') -or $_.Name -eq 'manifest.json' } |
    Copy-Item -Destination $logos
$forbidden=@(Get-ChildItem -LiteralPath $release -Recurse -File | Where-Object {
    $_.Extension -in @('.db','.sqlite','.sqlite3','.xls','.xlsx','.pyc','.pyo') -or
    $_.Name -in @('mail.json','initial_admin.txt','super_admin_initial.txt','DEMO_DATA.json','test_app.py')
})
if ($forbidden.Count) { throw "Handoff contains data or test files: $($forbidden.Name -join ', ')" }
$hashes=Get-ChildItem -LiteralPath $release -Recurse -File | ForEach-Object {
    $relative=$_.FullName.Substring($release.Length+1)
    '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash,$relative
}
$hashes | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding Ascii
Write-Host "Source handoff ready: $release"
