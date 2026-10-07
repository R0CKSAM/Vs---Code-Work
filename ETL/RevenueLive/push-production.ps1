param(
    [string]$Message = 'Update RevenueLive production application',
    [string]$Checkout = (Join-Path $PSScriptRoot '..\output\temp\vetorptdashboard-production-publish-20261005'),
    [switch]$Preview
)

$ErrorActionPreference = 'Stop'
$remote = 'https://github.com/veto-stream/vetorptdashboard.git'
$source = $PSScriptRoot

function Invoke-Git {
    param([string[]]$GitArgs)
    & git -C $Checkout @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "Git failed: $($GitArgs -join ' ')" }
}

# Explicit runtime allowlist: never copy the workspace, credentials or user data.
$files = @(
    '.env.example', '.gitignore', 'account_email.py', 'app.py', 'backup.py',
    'channel_images.py', 'config.py', 'database.py', 'db_schema.py', 'deploy.py',
    'insight_presets.py', 'runtime_logging.py', 'sqlite_legacy.py',
    'requirements.txt', 'manage.ps1', 'setup.ps1',
    'flatpickr.LICENSE.txt', 'Lucide.LICENSE.txt'
)
$extensions = @('.py', '.js', '.css', '.html', '.json', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.md', '.txt')
foreach ($folder in @('static', 'migrations')) {
    Get-ChildItem -LiteralPath (Join-Path $source $folder) -File -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($source.Length + 1).Replace('\', '/')
        if ($relative -notmatch '(^|/)(\.[^/]+|__pycache__|node_modules|tests?|backups?|logs?|data)(/|$)' -and $extensions -contains $_.Extension.ToLowerInvariant()) {
            $files += $relative
        }
    }
}
foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $file) -PathType Leaf)) {
        throw "Required production file missing: $file"
    }
}
if ($Preview) {
    $files | Sort-Object
    Write-Host "Preview only: $($files.Count) runtime files. No copy, commit or push performed."
    return
}
if (-not (Test-Path -LiteralPath $Checkout)) {
    & git clone --branch main --single-branch $remote $Checkout
    if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
}
$Checkout = (Resolve-Path -LiteralPath $Checkout).Path
if (-not (Test-Path -LiteralPath (Join-Path $Checkout '.git'))) { throw 'Destination must be a dedicated Git checkout.' }
$actualRemote = Invoke-Git @('remote', 'get-url', 'origin')
if ($actualRemote.TrimEnd('/') -notin @($remote, $remote.Replace('.git', ''))) { throw 'Wrong origin remote; stopped.' }
$branch = Invoke-Git @('branch', '--show-current')
if ($branch -ne 'main') { throw 'Destination must be on main.' }
$status = Invoke-Git @('status', '--porcelain')
if ($status) { throw 'Publication checkout has pending changes. Review/commit them before rerunning; nothing overwritten.' }
Invoke-Git @('pull', '--ff-only', 'origin', 'main')

foreach ($file in $files) {
    $destination = Join-Path $Checkout $file
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination)
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination $destination
}
# Keep the publication-specific handoff documents intact. Never delete files automatically.
Invoke-Git @('diff', '--check')
Invoke-Git (@('add', '--') + $files)
$changes = Invoke-Git @('diff', '--cached', '--name-only')
if ($changes) {
    Invoke-Git @('diff', '--cached', '--stat')
    Invoke-Git @('commit', '-m', $Message)
} else {
    Write-Host 'No new runtime changes to commit.'
}
Invoke-Git @('push', 'origin', 'main')
Write-Host 'GitHub updated. Hosting still needs its normal pull/deploy process.'
