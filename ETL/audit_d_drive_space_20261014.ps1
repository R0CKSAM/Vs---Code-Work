$ErrorActionPreference = 'Stop'
$audit = Join-Path $PSScriptRoot ('output/validation/d_drive_space_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$env:TEMP = $audit
$env:TMP = $audit

# Metadata only: skip reparse points and Windows-managed system directories.
$scan = @{Groups=@{};Largest=@();Skipped=[Collections.Generic.List[string]]::new();Files=0L;Bytes=0L}
$pending = [Collections.Generic.Stack[string]]::new()
$pending.Push('D:\')
$timer = [Diagnostics.Stopwatch]::StartNew()
$threshold = 0L
while ($pending.Count) {
    $directory = $pending.Pop()
    try {
        foreach ($item in ([IO.DirectoryInfo]$directory).EnumerateFileSystemInfos()) {
            try {
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    $scan.Skipped.Add('LINK: ' + $item.FullName); continue
                }
                if ($item.Attributes -band [IO.FileAttributes]::Directory) {
                    if ($item.FullName -in @('D:\System Volume Information','D:\Config.Msi')) {
                        $scan.Skipped.Add('SYSTEM: ' + $item.FullName); continue
                    }
                    $pending.Push($item.FullName); continue
                }
                $length = $item.Length
                $scan.Files++; $scan.Bytes += $length
                $parts = $item.FullName.Substring(3).Split('\')
                $key = 'D:'
                $levels = [math]::Max(1, [math]::Min($parts.Count-1, 6))
                for ($n=0; $n -lt $levels; $n++) {
                    $key += '\' + $parts[$n]
                    if (-not $scan.Groups.ContainsKey($key)) {
                        $scan.Groups[$key] = [pscustomobject]@{Path=$key;Bytes=0L;Files=0L}
                    }
                    $scan.Groups[$key].Bytes += $length
                    $scan.Groups[$key].Files++
                }
                if ($length -ge $threshold) {
                    $scan.Largest += [pscustomobject]@{Path=$item.FullName;Bytes=$length}
                    if ($scan.Largest.Count -gt 100) { $scan.Largest = @($scan.Largest | Sort-Object Bytes -Descending | Select-Object -First 100) }
                    if ($scan.Largest.Count -eq 100) { $threshold = $scan.Largest[99].Bytes }
                }
            } catch { $scan.Skipped.Add($item.FullName + ': ' + $_.Exception.Message) }
        }
    } catch { $scan.Skipped.Add($directory + ': ' + $_.Exception.Message) }
    if ($timer.Elapsed.TotalSeconds -gt 15) {
        Write-Output ('Scanned {0:N0} files, {1:F2} GiB logical; {2} directories queued' -f $scan.Files,($scan.Bytes/1GB),$pending.Count)
        $timer.Restart()
    }
}
$scan.Groups.Values | Sort-Object Bytes -Descending | Select-Object Path,Files,Bytes,@{N='GiB';E={[math]::Round($_.Bytes/1GB,3)}} |
    Export-Csv -LiteralPath (Join-Path $audit 'folder_sizes.csv') -NoTypeInformation -Encoding UTF8
$scan.Largest | Sort-Object Bytes -Descending | Select-Object Path,Bytes,@{N='GiB';E={[math]::Round($_.Bytes/1GB,3)}} |
    Export-Csv -LiteralPath (Join-Path $audit 'largest_files.csv') -NoTypeInformation -Encoding UTF8
$scan.Skipped | Set-Content -LiteralPath (Join-Path $audit 'skipped.txt') -Encoding UTF8
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'"
[pscustomobject]@{ScanCompletedAt=(Get-Date).ToString('o');Files=$scan.Files;LogicalBytes=$scan.Bytes;
    CapacityBytes=$disk.Size;FreeBytes=$disk.FreeSpace;SkippedCount=$scan.Skipped.Count;
    Note='Read-only metadata scan. Logical sizes count hard links more than once; live files may change during scan.'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'summary.json') -Encoding UTF8
Write-Output "REPORT: $audit"
$scan.Groups.Values | Where-Object {($_.Path.TrimEnd('\') -split '\\').Count -eq 2} |
    Sort-Object Bytes -Descending | Select-Object Path,Files,@{N='GiB';E={[math]::Round($_.Bytes/1GB,3)}} | Format-Table -AutoSize
