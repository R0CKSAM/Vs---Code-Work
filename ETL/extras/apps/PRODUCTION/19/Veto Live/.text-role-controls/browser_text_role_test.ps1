$ErrorActionPreference = 'Stop'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$profile = 'D:\Veto Live\.text-role-controls\chrome-cdp-test'
$port = 9339
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
    Evaluate "template='t12';document.getElementById('template').value=template;configs[template]=clone(boot.defaults[template]);selectedSaved='';history=[];historyIndex=-1;commit();buildEditor();renderTemplateOptions();scheduleRender(false);true" | Out-Null
    Evaluate "new Promise(resolve=>{let n=0,t=setInterval(()=>{if(previewReady||++n>100){clearInterval(t);resolve(true)}},100)})" $true | Out-Null
    $initial = Evaluate "JSON.stringify({roles:boot.text_targets.t12.map(x=>x.key),moveOptions:[...document.getElementById('previewLayer').options].map(x=>x.value),error:document.getElementById('error').textContent})"
    Evaluate "selectedLayer.t12='text:title';getConfig()._web_text_role='title';buildEditor();document.getElementById('textVariant').value='italic';document.getElementById('textSize').value='130';document.getElementById('textX').value='10';document.getElementById('textY').value='5';document.getElementById('textColor').value='#ff00ff';document.getElementById('textColorEnabled').checked=true;document.getElementById('textX').dispatchEvent(new Event('change'));true" | Out-Null
    Evaluate "new Promise(resolve=>{let n=0,t=setInterval(()=>{if(previewReady||++n>100){clearInterval(t);resolve(true)}},100)})" $true | Out-Null
    $styled = Evaluate "JSON.stringify({selected:document.getElementById('previewLayer').value,style:getConfig().text_styles.title,editorRole:document.getElementById('textRole').value,error:document.getElementById('error').textContent})"
    Evaluate "nudgeSelected(1,0);true" | Out-Null
    Evaluate "new Promise(resolve=>{let n=0,t=setInterval(()=>{if(previewReady||++n>100){clearInterval(t);resolve(true)}},100)})" $true | Out-Null
    $nudged = Evaluate "JSON.stringify({x:getConfig().text_styles.title.x_pct,y:getConfig().text_styles.title.y_pct,fieldX:Number(document.getElementById('textX').value),selected:document.getElementById('previewLayer').value})"
    $shot = Invoke-Cdp 'Page.captureScreenshot' @{ format = 'png'; captureBeyondViewport = $false }
    [IO.File]::WriteAllBytes('D:\Veto Live\.text-role-controls\quarter-text-controls.png', [Convert]::FromBase64String($shot.data))
    Write-Output "INITIAL=$initial"
    Write-Output "STYLED=$styled"
    Write-Output "NUDGED=$nudged"
} finally {
    if ($socket) { $socket.Dispose() }
    Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', $process.Id, '/T', '/F') -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
}
