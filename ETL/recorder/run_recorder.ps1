param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8810,
    [string]$FfmpegPath = "",
    [switch]$DiscoverChannels
)

$ErrorActionPreference = "Stop"
$EtlRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path (Split-Path -Parent $EtlRoot) "venv\Scripts\python.exe"
$Server = Join-Path $PSScriptRoot "recorder_server.py"
$Discovery = Join-Path $PSScriptRoot "discover_channel_urls.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}

if ($DiscoverChannels) {
    Write-Host "Discovering verified live playlists from recent lake data..." -ForegroundColor Cyan
    & $Python $Discovery --write
    if ($LASTEXITCODE -ne 0) {
        throw "Channel discovery failed with exit code $LASTEXITCODE"
    }
}

$arguments = @($Server, "--host", $HostAddress, "--port", "$Port")
if ($FfmpegPath) {
    $arguments += @("--ffmpeg", $FfmpegPath)
}

Write-Host "VETO recorder: http://${HostAddress}:$Port/recorder" -ForegroundColor Cyan
& $Python @arguments
