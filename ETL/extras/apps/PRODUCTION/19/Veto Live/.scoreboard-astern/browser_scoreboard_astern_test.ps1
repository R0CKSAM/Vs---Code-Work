$ErrorActionPreference = 'Stop'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$profile = 'D:\Veto Live\.scoreboard-astern\chrome-cdp-test'
$port = 9342
$arguments = @(
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-allow-origins=*', "--remote-debugging-port=$port",
    "--user-data-dir=`"$profile`"", '--window-size=1920,1080',
    'http://127.0.0.1:8092/scoreboard?astern-test=1'
)
$process = Start-Process -FilePath $chrome -ArgumentList $arguments -PassThru -WindowStyle Hidden
$socket = $null
try {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { $pages = Invoke-RestMethod "http://127.0.0.1:$port/json/list" -TimeoutSec 2; if ($pages) { break } } catch {}
    }
    $page = $pages | Where-Object { $_.type -eq 'page' -and $_.url -like 'http://127.0.0.1:8092/*' } | Select-Object -First 1
    if (-not $page) { throw 'Chrome did not open the dashboard.' }
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $socket.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    $nextId = 0
    function Invoke-Cdp([string]$Method, [hashtable]$Parameters) {
        $script:nextId++
        $payload = @{ id=$script:nextId; method=$Method; params=$Parameters } | ConvertTo-Json -Depth 12 -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
        $socket.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
        while ($true) {
            $builder = [Text.StringBuilder]::new()
            do {
                $buffer = New-Object byte[] 65536
                $result = $socket.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
                [void]$builder.Append([Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
            } until ($result.EndOfMessage)
            $message = $builder.ToString() | ConvertFrom-Json
            if ($message.id -eq $script:nextId) {
                if ($message.error) { throw ($message.error | ConvertTo-Json -Compress) }
                return $message.result
            }
        }
    }
    function Evaluate([string]$Expression, [bool]$Await=$false) {
        $result = Invoke-Cdp 'Runtime.evaluate' @{expression=$Expression; awaitPromise=$Await; returnByValue=$true}
        if ($result.exceptionDetails) { throw ($result.exceptionDetails | ConvertTo-Json -Depth 8 -Compress) }
        return $result.result.value
    }
    Invoke-Cdp 'Runtime.enable' @{} | Out-Null
    Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(typeof boot!=='undefined'&&boot&&previewReady){clearInterval(t);resolve(true)}else if(++n>120){clearInterval(t);reject(Error(document.getElementById('error')?.textContent||'Dashboard timeout'))}},100)})" $true | Out-Null
    Evaluate "template='t18';document.getElementById('template').value=template;configs.t18=clone(boot.defaults.t18);getConfig()._web_text_role='player_a';selectedLayer.t18='band';buildEditor();scheduleRender(false);true" | Out-Null
    $editScript = @'
document.querySelector('[data-country-pick="country_b"][data-country-value="Japan"]').click();
document.getElementById('asternSetCount').value='4';
document.getElementById('asternSetCount').dispatchEvent(new Event('change'));
const score=document.querySelector('[data-score-side="b"][data-score-index="3"]');
score.value='7';score.dispatchEvent(new Event('input'));score.dispatchEvent(new Event('change'));
const color=document.querySelector('[data-color="bottom_row_color"]');
color.value='#0055aa';color.dispatchEvent(new Event('input'));
true
'@
    Evaluate $editScript | Out-Null
    Evaluate "new Promise((resolve,reject)=>{let n=0,t=setInterval(()=>{if(previewReady){clearInterval(t);resolve(true)}else if(++n>120){clearInterval(t);reject(Error(document.getElementById('error')?.textContent||'Preview timeout'))}},100)})" $true | Out-Null
    $result = Evaluate "JSON.stringify({template:boot.template_names.t18,country:getConfig().country_b,setCount:getConfig().set_count,scores:getConfig().scores_b,color:getConfig().bottom_row_color,pickers:document.querySelectorAll('.flag-picker').length,options:document.querySelectorAll('[data-country-pick]').length,roles:boot.text_targets.t18.map(x=>x.key),preview:[document.getElementById('preview').naturalWidth,document.getElementById('preview').naturalHeight],error:document.getElementById('error').textContent})"
    $shot = Invoke-Cdp 'Page.captureScreenshot' @{format='png'; captureBeyondViewport=$false}
    [IO.File]::WriteAllBytes('D:\Veto Live\.scoreboard-astern\browser-scoreboard-astern.png', [Convert]::FromBase64String($shot.data))
    Write-Output "RESULT=$result"
} finally {
    if ($socket) { $socket.Dispose() }
    Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID',$process.Id,'/T','/F') -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
}
