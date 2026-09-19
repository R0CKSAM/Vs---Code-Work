$ErrorActionPreference = 'Stop'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$profile = 'D:\Veto Live\.variable-preview-queue\chrome-cdp-test'
$port = 9338
$arguments = @(
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-allow-origins=*', "--remote-debugging-port=$port",
    "--user-data-dir=`"$profile`"", '--window-size=1920,1080',
    'http://127.0.0.1:8080/scoreboard?queue-cdp-test=1'
)
$process = Start-Process -FilePath $chrome -ArgumentList $arguments -PassThru -WindowStyle Hidden
$socket = $null
try {
    $pages = $null
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        Start-Sleep -Milliseconds 200
        try {
            $pages = Invoke-RestMethod "http://127.0.0.1:$port/json/list" -TimeoutSec 2
            if ($pages) { break }
        } catch {}
    }
    $page = $pages | Where-Object { $_.type -eq 'page' -and $_.url -like 'http://127.0.0.1:8080/*' } | Select-Object -First 1
    if (-not $page) { throw 'Chrome did not open the dashboard page.' }

    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $socket.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    $nextId = 0
    function Invoke-Cdp([string]$Method, [hashtable]$Parameters) {
        $script:nextId++
        $payload = @{ id = $script:nextId; method = $Method; params = $Parameters } | ConvertTo-Json -Depth 12 -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
        $socket.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
        while ($true) {
            $builder = [Text.StringBuilder]::new()
            do {
                $buffer = New-Object byte[] 65536
                $segment = [ArraySegment[byte]]::new($buffer)
                $result = $socket.ReceiveAsync($segment, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
                [void]$builder.Append([Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
            } until ($result.EndOfMessage)
            $text = $builder.ToString()
            $message = $text | ConvertFrom-Json
            if ($message.id -eq $script:nextId) {
                if ($message.error) { throw ($message.error | ConvertTo-Json -Compress) }
                return $message.result
            }
        }
    }
    function Evaluate([string]$Expression, [bool]$Await = $false) {
        $result = Invoke-Cdp 'Runtime.evaluate' @{ expression = $Expression; awaitPromise = $Await; returnByValue = $true }
        if ($result.exceptionDetails) { throw ($result.exceptionDetails | ConvertTo-Json -Depth 8 -Compress) }
        return $result.result.value
    }

    Invoke-Cdp 'Runtime.enable' @{} | Out-Null
    Invoke-Cdp 'Page.enable' @{} | Out-Null
    Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(typeof boot!=='undefined'&&boot&&previewReady){clearInterval(t);resolve(true)}else if(++n>100){clearInterval(t);reject(Error(document.getElementById('error')?.textContent||'Dashboard did not become ready'))}},100)})" $true | Out-Null
    $initial = Evaluate "JSON.stringify({slots:document.querySelectorAll('.queue-slot').length,empty:document.querySelectorAll('.queue-empty').length,status:document.getElementById('queueStatus').textContent,error:document.getElementById('error').textContent})"
    Evaluate "changeQueueCount(1); true" | Out-Null
    $increased = Evaluate "JSON.stringify({slots:queueItems.length,cards:document.querySelectorAll('.queue-slot').length,status:document.getElementById('queueStatus').textContent})"
    Evaluate "changeQueueCount(-1); true" | Out-Null
    $decreased = Evaluate "JSON.stringify({slots:queueItems.length,cards:document.querySelectorAll('.queue-slot').length,status:document.getElementById('queueStatus').textContent})"
    Evaluate "addQueueItem(0); true" | Out-Null
    Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(queueUrls[0]){clearInterval(t);resolve(true)}else if(++n>100){clearInterval(t);reject(Error('Queue thumbnail did not render'))}},100)})" $true | Out-Null
    $added = Evaluate "JSON.stringify({queued:!!queueItems[0],selected:selectedQueue,selectedCards:document.querySelectorAll('.queue-slot.selected').length,images:document.querySelectorAll('.queue-thumb img:not([hidden])').length,name:queueItems[0]?.name})"
    Evaluate "selectQueueItem(0); true" | Out-Null
    Evaluate "new Promise(resolve=>{let n=0,t=setInterval(()=>{if(previewReady||++n>100){clearInterval(t);resolve(true)}},100)})" $true | Out-Null
    $selected = Evaluate "JSON.stringify({selected:selectedQueue,templateMatches:template===queueItems[0].template,configMatches:currentSnapshotKey()===queueSnapshotKey(queueItems[0])})"
    $shot = Invoke-Cdp 'Page.captureScreenshot' @{ format = 'png'; captureBeyondViewport = $false }
    [IO.File]::WriteAllBytes('D:\Veto Live\.variable-preview-queue\queue-desktop.png', [Convert]::FromBase64String($shot.data))
    Evaluate "removeQueueItem(0); true" | Out-Null
    $removed = Evaluate "JSON.stringify({queued:!!queueItems[0],empty:document.querySelectorAll('.queue-empty').length,status:document.getElementById('queueStatus').textContent})"
    Write-Output "INITIAL=$initial"
    Write-Output "INCREASED=$increased"
    Write-Output "DECREASED=$decreased"
    Write-Output "ADDED=$added"
    Write-Output "SELECTED=$selected"
    Write-Output "REMOVED=$removed"
} finally {
    if ($socket) { $socket.Dispose() }
    taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
}
