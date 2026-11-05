param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('start','stop','restart')][string]$Action,
    [int]$Port=8766
)
$ErrorActionPreference='Stop'
$RepoRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Python=Join-Path $RepoRoot 'venv\Scripts\python.exe'
$Server=Join-Path $PSScriptRoot 'server.py'
$TaskName='SmartVOD Daily Refresh'
function Get-SmartVODProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -like ('*'+$RepoRoot+'*') -and
        $_.CommandLine -match '(?i)SmartVOD[\\/]server\.py(?:"|\s|$)'
    })
}
if ($Action -in @('stop','restart')) {
    $Workers=Get-SmartVODProcesses
    foreach ($Worker in ($Workers | Sort-Object ParentProcessId -Descending)) {
        Stop-Process -Id $Worker.ProcessId -ErrorAction SilentlyContinue
    }
    if ($Workers.Count) {
        Wait-Process -Id $Workers.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
    }
    $Task=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Disable-ScheduledTask -TaskName $TaskName | Out-Null
    }
    Write-Output 'SmartVOD stopped. Its daily refresh is paused; main ETL tasks are unchanged.'
}
if ($Action -in @('start','restart')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'data\manifest.json'))) {
        throw 'SmartVOD data manifest is missing. Prepare data before starting.'
    }
    if (-not (Get-SmartVODProcesses).Count) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
            throw "Port $Port is in use. No process was stopped; choose another -Port."
        }
        Start-Process -FilePath $Python -WindowStyle Hidden -WorkingDirectory $RepoRoot `
            -ArgumentList @('-u',('"'+$Server+'"'),'--port',"$Port") `
            -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.out.log') `
            -RedirectStandardError (Join-Path $PSScriptRoot 'server.err.log') | Out-Null
        $Ready=$false
        for ($Attempt=0;$Attempt -lt 20;$Attempt++) {
            try {
                $null=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/meta" -TimeoutSec 1
                $Ready=$true;break
            } catch { Start-Sleep -Milliseconds 250 }
        }
        if (-not $Ready) { throw 'SmartVOD did not become ready. Check server.err.log.' }
    }
    $Task=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Task) { Enable-ScheduledTask -TaskName $TaskName | Out-Null }
    Write-Output "SmartVOD running: http://127.0.0.1:$Port (daily refresh enabled)."
}
