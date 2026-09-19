$ErrorActionPreference = 'Stop'
$python = (Get-Content 'D:\Veto Live\data\python_path.txt' -Raw).Trim()
$env:PYTHONPATH = 'D:\Veto Live\python_packages'
$server = Start-Process -FilePath $python -ArgumentList @('-u', 'test_integration_server.py') -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'integration-server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'integration-server-error.log')
$browser = $null
$socket = $null
try {
    for ($attempt=0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { Invoke-RestMethod 'http://127.0.0.1:8094/api/bootstrap' -TimeoutSec 2 | Out-Null; break } catch { if ($server.HasExited) { throw 'Memory server failed to start.' } }
    }
    $profile = Join-Path $PSScriptRoot 'chrome-integration-audit'
    $arguments = @('--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-allow-origins=*', '--remote-debugging-port=9349', "--user-data-dir=`"$profile`"", 'about:blank')
    $browser = Start-Process -FilePath 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList $arguments -PassThru -WindowStyle Hidden
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { $pages = Invoke-RestMethod 'http://127.0.0.1:9349/json/list' -TimeoutSec 2; if ($pages) { break } } catch {}
    }
    $page = $pages | Where-Object { $_.type -eq 'page' -and $_.url -eq 'about:blank' } | Select-Object -First 1
    if (-not $page) { throw 'Chrome did not open the integration test.' }
    $socket = [Net.WebSockets.ClientWebSocket]::new()
    $socket.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
    $script:nextId=0
    $script:browserErrors=@()
    function Invoke-Cdp([string]$Method,[hashtable]$Parameters) {
        $script:nextId++
        $payload = @{id=$script:nextId;method=$Method;params=$Parameters} | ConvertTo-Json -Depth 15 -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
        $socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
        while ($true) {
            $builder=[Text.StringBuilder]::new()
            do {
                $buffer=New-Object byte[] 65536
                $result=$socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),[Threading.CancellationToken]::None).GetAwaiter().GetResult()
                [void]$builder.Append([Text.Encoding]::UTF8.GetString($buffer,0,$result.Count))
            } until ($result.EndOfMessage)
            $message=$builder.ToString() | ConvertFrom-Json
            if ($message.method -eq 'Runtime.exceptionThrown') { $script:browserErrors += $message.params }
            if ($message.id -eq $script:nextId) {
                if ($message.error) { throw ($message.error | ConvertTo-Json -Depth 8 -Compress) }
                return $message.result
            }
        }
    }
    function Evaluate([string]$Expression,[bool]$Await=$false) {
        $result=Invoke-Cdp 'Runtime.evaluate' @{expression=$Expression;awaitPromise=$Await;returnByValue=$true}
        if ($result.exceptionDetails) { throw ($result.exceptionDetails | ConvertTo-Json -Depth 8 -Compress) }
        return $result.result.value
    }
    function Wait-Preview {
        Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(typeof boot!=='undefined'&&boot&&previewReady&&readyPreviewSnapshot===currentSnapshotKey()){clearInterval(t);resolve(true)}else if(++n>200){clearInterval(t);reject(Error('Preview timeout: '+document.getElementById('error')?.textContent))}},100)})" $true | Out-Null
    }
    Invoke-Cdp 'Runtime.enable' @{} | Out-Null
    Invoke-Cdp 'Page.enable' @{} | Out-Null
    Invoke-Cdp 'Page.addScriptToEvaluateOnNewDocument' @{source="window.browserTestErrors=[];window.addEventListener('error',e=>browserTestErrors.push(e.message));window.addEventListener('unhandledrejection',e=>browserTestErrors.push(String(e.reason)));window.confirm=()=>true;"} | Out-Null
    Invoke-Cdp 'Emulation.setDeviceMetricsOverride' @{width=1920;height=1080;deviceScaleFactor=1;mobile=$false} | Out-Null
    Invoke-Cdp 'Page.navigate' @{url='http://127.0.0.1:8094/scoreboard'} | Out-Null
    Wait-Preview
    Evaluate "template='t18';configs.t18=clone(boot.defaults.t18);queueItems=[null,null,null,null];queueUrls=['','','',''];selectedQueue=-1;getConfig().country_b='Korea';buildEditor();renderTemplateOptions();scheduleRender(false);true" | Out-Null
    Wait-Preview
    Evaluate "addQueueItem(0);document.getElementById('liveButton').onclick()" $true | Out-Null
    $firstPush=Evaluate "(async()=>{if(document.getElementById('takeLive').disabled)throw Error('Push disabled after memory start');const start=performance.now();await document.getElementById('takeLive').onclick();if(!latestLive.on_air||lastShown!==currentSnapshotKey())throw Error('First push failed');return{ms:Math.round(performance.now()-start),revision:latestLive.program_revision,layout:latestLive.program_layout}})()" $true
    Evaluate "template='t12';configs.t12=clone(boot.defaults.t12);buildEditor();renderTemplateOptions();scheduleRender(false);true" | Out-Null
    Wait-Preview
    Evaluate "addQueueItem(1);selectQueueItem(0);true" | Out-Null
    Wait-Preview
    Evaluate "selectQueueItem(1);true" | Out-Null
    Wait-Preview
    $secondPush=Evaluate "(async()=>{if(document.getElementById('takeLive').disabled)throw Error('Push disabled after queue selection');const start=performance.now();await document.getElementById('takeLive').onclick();if(!latestLive.on_air||lastShown!==queueSnapshotKey(queueItems[1]))throw Error('Queued push failed');return{ms:Math.round(performance.now()-start),revision:latestLive.program_revision,layout:latestLive.program_layout}})()" $true
    Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(programReady&&displayedProgramRevision===latestLive.program_revision){clearInterval(t);resolve(true)}else if(++n>100){clearInterval(t);reject(Error('Program monitor timeout'))}},100)})" $true | Out-Null
    $desktop=Evaluate "JSON.stringify({preview:[document.getElementById('preview').naturalWidth,document.getElementById('preview').naturalHeight],monitor:[document.getElementById('programImage').naturalWidth,document.getElementById('programImage').naturalHeight],selectedQueue,errors:browserTestErrors,error:document.getElementById('error').textContent,overflow:document.documentElement.scrollWidth>innerWidth})"
    $shot=Invoke-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
    [IO.File]::WriteAllBytes((Join-Path $PSScriptRoot 'browser-integration-desktop.png'),[Convert]::FromBase64String($shot.data))
    Invoke-Cdp 'Emulation.setDeviceMetricsOverride' @{width=390;height=844;deviceScaleFactor=1;mobile=$false} | Out-Null
    Start-Sleep -Milliseconds 300
    $mobile=Evaluate "JSON.stringify({viewport:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth,errors:browserTestErrors})"
    $shot=Invoke-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
    [IO.File]::WriteAllBytes((Join-Path $PSScriptRoot 'browser-integration-mobile.png'),[Convert]::FromBase64String($shot.data))
    Evaluate "liveCommand('/api/live/stop',{expected_revision:latestLive.program_revision})" $true | Out-Null
    if ($script:browserErrors.Count) { throw ($script:browserErrors | ConvertTo-Json -Depth 8 -Compress) }
    Write-Output ('FIRST_PUSH=' + ($firstPush | ConvertTo-Json -Compress))
    Write-Output ('QUEUED_PUSH=' + ($secondPush | ConvertTo-Json -Compress))
    Write-Output "DESKTOP=$desktop"
    Write-Output "MOBILE=$mobile"
} finally {
    if ($socket) { $socket.Dispose() }
    if ($browser) { Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID',$browser.Id,'/T','/F') -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null }
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}
