[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$destination = '\\192.168.50.11\analysis team\Veto Logs Backup\Dashboards'
$output = Join-Path $PSScriptRoot 'output'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$audit = Join-Path $output "validation\shared_dashboard_publish_$stamp"
$archive = Join-Path $destination "_archive\$stamp"
$staging = Join-Path $destination "_publish_staging_$stamp"
$mappings = @(
    @{source='overview\overview_dashboard.html';name='overview_dashboard.html';kind='core'},
    @{source='watch_hours\concurrency\veto_concurrency.html';name='veto_concurrency.html';kind='core'},
    @{source='latency\veto_latency.html';name='veto_latency.html';kind='core'},
    @{source='audience_ops\veto_audience_operations.html';name='veto_audience_operations.html';kind='core'},
    @{source='master\veto_master_dashboard.html';name='veto_master_dashboard.html';kind='core'},
    @{source='watch_hours\veto_watch_hours.html';name='veto_watch_hours.html';kind='core'},
    @{source='device_decode\ua_decode_dashboard_preview.html';name='ua_decode_dashboard_preview.html';kind='latest_available_snapshot'},
    @{source='watch_hours\stream_showcase\stream_watch_hours_showcase.xlsx';name='stream_watch_hours_showcase.xlsx';kind='latest_available_snapshot'},
    @{source='watch_hours\stream_showcase\stream_watch_hours_showcase.html';name='stream_watch_hours_showcase.html';kind='latest_available_snapshot'}
)
$pipeline = Get-Content -LiteralPath (Join-Path $output 'state\pipeline_last_run.json') -Raw | ConvertFrom-Json
if ($pipeline.status -ne 'complete' -or $pipeline.target_date -ne '2026-10-14') { throw 'Expected completed October 14 pipeline' }
$daily = Get-Content -LiteralPath (Join-Path $output 'state\daily_runs\2026-10-14.json') -Raw | ConvertFrom-Json
if ($daily.status -ne 'complete' -or $daily.validation_status -ne 'PASS') { throw 'Daily validation has not passed' }

function Assert-Scoped([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside scope: $full" }
    $cursor = $full
    while ($cursor -and $cursor.Length -ge $base.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $cursor" }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}
function Hash([string]$Path) {
    $stream = [IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read,8MB,[IO.FileOptions]::SequentialScan)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}
function Assert-NoCoreWriter {
    $writers = Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.Name -match '^python' -and
        $_.CommandLine -match 'run_pipeline\.py|overViewGenerator\.py|generate_(audience_ops|master_dashboard|watch_hours|concurrency|ua_decode)|build_latency_profile|build_stream_watch_hours_showcase'
    }
    if ($writers) { throw 'A mapped dashboard producer is running; retry after it finishes.' }
}
Assert-NoCoreWriter
foreach ($mapping in $mappings) {
    $source = Assert-Scoped (Join-Path $output $mapping.source) $output
    $file = Get-Item -LiteralPath $source
    if ($file.Length -lt 1000) { throw "Unexpectedly small source: $source" }
    if ($mapping.kind -eq 'core' -and $file.LastWriteTime.Date -ne [datetime]'2026-10-15') { throw "Core output not generated today: $source" }
    $mapping.source_path=$source
    $mapping.bytes=$file.Length
    $mapping.source_ticks=$file.LastWriteTimeUtc.Ticks
    Write-Output "PUBLISH $($mapping.name): $($file.Length) bytes, generated $($file.LastWriteTime)"
}
if (-not $Apply) { Write-Output 'DRY RUN: 9 files; preserve historical content; skip active ASRUN.'; exit 0 }
New-Item -ItemType Directory -Path $audit,$archive,$staging -Force | Out-Null
$report = @{status='staging';started_at=(Get-Date).ToString('o');destination=$destination;core_target_date=$pipeline.target_date;files=$mappings;moved=@();deleted_duplicates=@();notes=@('ASRUN excluded because a build is active.','Showcase and UA are latest available snapshots, not guaranteed to match the core ETL target date.')}
$reportPath = Join-Path $audit 'publication.json'
function Save-Report { $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8 }
function Archive-Item([string]$Name, [string]$Category) {
    $source=Assert-Scoped (Join-Path $destination $Name) $destination
    if (-not (Test-Path -LiteralPath $source)) { return }
    $target=Assert-Scoped (Join-Path $archive "$Category\$Name") $destination
    if (Test-Path -LiteralPath $target) { throw "Archive collision: $target" }
    $item=Get-Item -LiteralPath $source -Force
    if ($item.PSIsContainer) {
        foreach($child in Get-ChildItem -LiteralPath $source -Recurse -Force) { [void](Assert-Scoped $child.FullName $source) }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Move-Item -LiteralPath $source -Destination $target
    $report.moved += @{source=$source;destination=$target}
    Save-Report
}
try {
    Save-Report
    foreach ($mapping in $mappings) {
        Write-Output "Copy and verify: $($mapping.name)"
        $mapping.sha256=Hash $mapping.source_path
        $stage=Assert-Scoped (Join-Path $staging $mapping.name) $destination
        Copy-Item -LiteralPath $mapping.source_path -Destination $stage
        if ((Hash $stage) -ne $mapping.sha256) { throw 'Staging checksum mismatch' }
        $current=Get-Item -LiteralPath $mapping.source_path
        if ($current.Length -ne $mapping.bytes -or $current.LastWriteTimeUtc.Ticks -ne $mapping.source_ticks) { throw 'Source changed during copy' }
        Save-Report
    }
    Assert-NoCoreWriter
    $report.status='publishing'
    Save-Report
    foreach ($mapping in $mappings) {
        $current=Get-Item -LiteralPath $mapping.source_path
        if ($current.Length -ne $mapping.bytes -or $current.LastWriteTimeUtc.Ticks -ne $mapping.source_ticks) { throw 'Source changed before publishing' }
        $stage=Assert-Scoped (Join-Path $staging $mapping.name) $destination
        $target=Assert-Scoped (Join-Path $destination $mapping.name) $destination
        $backup=Assert-Scoped (Join-Path $archive "previous-published\$($mapping.name)") $destination
        New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
        if (Test-Path -LiteralPath $target) {
            $mapping.previous_sha256=Hash $target
            [IO.File]::Replace($stage,$target,$backup)
            if ((Hash $backup) -ne $mapping.previous_sha256) { throw 'Previous-version backup mismatch' }
        } else { Move-Item -LiteralPath $stage -Destination $target }
        if ((Hash $target) -ne $mapping.sha256) { throw 'Published checksum mismatch' }
        $mapping.published=$true
        Save-Report
        Write-Output "Published: $($mapping.name)"
    }
    $duplicate=Assert-Scoped (Join-Path $destination 'channel_average_graph_style_options (2).html') $destination
    $original=Assert-Scoped (Join-Path $destination 'channel_average_graph_style_options.html') $destination
    if ((Test-Path -LiteralPath $duplicate) -and (Test-Path -LiteralPath $original)) {
        $hash=Hash $duplicate
        if ($hash -eq (Hash $original)) {
            $report.deleted_duplicates += @{path=$duplicate;retained=$original;sha256=$hash;bytes=(Get-Item -LiteralPath $duplicate).Length}
            Save-Report
            Remove-Item -LiteralPath $duplicate
        }
    }
    foreach($name in @('overview_dashboard (2).html','veto_audience_operations (2).html','veto_concurrency (2).html','veto_latency (2).html','veto_watch_hours (2).html')) { Archive-Item $name 'historical-snapshots' }
    foreach($name in @('-','old','del')) { Archive-Item $name 'historical-folders' }
    $stagePath=Assert-Scoped $staging $destination
    if (@(Get-ChildItem -LiteralPath $stagePath -Force).Count -eq 0) { Remove-Item -LiteralPath $stagePath }
    $report.status='complete'
    $report.finished_at=(Get-Date).ToString('o')
    Save-Report
    Copy-Item -LiteralPath $reportPath -Destination (Join-Path $archive 'publication.json')
    Write-Output "COMPLETE. Audit: $reportPath; historical files: $archive"
} catch {
    $report.status='failed';$report.error=$_.Exception.Message;Save-Report;throw
}
