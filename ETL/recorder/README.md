# VETO Multi-Channel Recorder

Run from the ETL folder:

```powershell
.\recorder\run_recorder.ps1
```

Open `http://127.0.0.1:8810/recorder`.

Channel names and approved HLS playback URLs live in `channels.json`. A channel
is selectable only when `enabled` is true and `hls_url` is populated.

Recording requires FFmpeg. Set `FFMPEG_PATH` or pass `-FfmpegPath`:

```powershell
.\recorder\run_recorder.ps1 -FfmpegPath "C:\path\to\ffmpeg.exe"
```

Recordings are remuxed without re-encoding and split into timestamped MKV files.
Job state and interrupted-run recovery are stored in `recorder_state.sqlite`.

Discover verified playlist URLs from recent successful CDN lake requests:

```powershell
..\venv\Scripts\python.exe .\recorder\discover_channel_urls.py --write
```

Or discover immediately before starting the service:

```powershell
.\recorder\run_recorder.ps1 -DiscoverChannels
```

The discovery process uses the canonical ETL channel resolver, never persists
query-string credentials, and enables only URLs that return a valid HLS manifest.
