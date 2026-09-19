$ErrorActionPreference = 'Stop'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$profile = Join-Path $PSScriptRoot 'chrome-push-audit'
$port = 9348
$arguments = @('--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-allow-origins=*', "--remote-debugging-port=$port", "--user-data-dir=`"$profile`"", 'about:blank')
$process = Start-Process -FilePath $chrome -ArgumentList $arguments -PassThru -WindowStyle Hidden
$socket = $null
try {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { $pages = Invoke-RestMethod "http://127.0.0.1:$port/json/list" -TimeoutSec 2; if ($pages) { break } } catch {}
    }
    $page = $pages | Where-Object { $_.type -eq 'page' -and $_.url -eq 'about:blank' } | Select-Object -First 1
    if (-not $page) { throw 'Chrome did not open test page.' }
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $socket.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    $source = Get-Content (Join-Path $PSScriptRoot 'scoreboard_web.html') -Raw -Encoding UTF8
    $scriptSource = [regex]::Match($source, '(?s)<script>(.*?)</script>').Groups[1].Value
    $testSource = Get-Content (Join-Path $PSScriptRoot 'test_browser_push.js') -Raw -Encoding UTF8
    $expression = $testSource + "`nrunBrowserPushTests(" + (ConvertTo-Json -InputObject $scriptSource -Compress) + ')'
    $payload = @{id=1;method='Runtime.evaluate';params=@{expression=$expression;awaitPromise=$true;returnByValue=$true}} | ConvertTo-Json -Depth 8 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    $socket.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
    do {
        $builder = [Text.StringBuilder]::new()
        do {
            $buffer = New-Object byte[] 65536
            $result = $socket.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            [void]$builder.Append([Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
        } until ($result.EndOfMessage)
        $message = $builder.ToString() | ConvertFrom-Json
    } until ($message.id -eq 1)
    if ($message.error) { throw ($message.error | ConvertTo-Json -Depth 8 -Compress) }
    if ($message.result.exceptionDetails) { throw ($message.result.exceptionDetails | ConvertTo-Json -Depth 8 -Compress) }
    $message.result.result.value | ForEach-Object { Write-Output "PASS $_" }
} finally {
    if ($socket) { $socket.Dispose() }
    Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID',$process.Id,'/T','/F') -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
}
