# VETO Multi-Channel Recorder

Background control from the ETL folder (no administrator needed for a recorder
started under your own account):

```powershell
.\manage_recorder.ps1 -Action Start
.\manage_recorder.ps1 -Action Status
.\manage_recorder.ps1 -Action Stop
.\manage_recorder.ps1 -Action Restart
```

If script execution is disabled, use:
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage_recorder.ps1 -Action Start`

Stop and Restart close active recordings before exiting. Restart brings back
the dashboard; select channels and start recording again afterward. Logs are
under `recorder/logs`. Start runs hidden and returns the PowerShell prompt.
An older recorder without management support must first be stopped with Ctrl+C
in its original terminal. The manager will not kill an unidentified service.

Run from the ETL folder:

```powershell
.\recorder\run_recorder.ps1
```

Open `http://127.0.0.1:8810/recorder`.

LAN access through the dedicated nginx recorder listener:
`http://192.168.50.126:8070/` (replace the IP if the host changes).
This uses the existing dashboard login and subnet allowlist in
`tools/nginx/conf/live_dashboard.conf`. Run `allow_recorder_firewall.ps1` once
in administrator PowerShell to allow TCP 8070 on Domain/Private profiles for
subnets 50, 55, and 56. This does not change the dashboard firewall rule.
Nginx routes only the recorder root page and `/api/` on port 8070 to port 8810.
The war-room API and scoreboard routes remain separate. The recorder backend
stays bound to loopback. Recordings stay on the host PC; signed-in users share
recording controls. Both nginx and the recorder must be running for LAN access.

Channel names and approved HLS playback URLs live in `channels.json`. A channel
is selectable only when `enabled` is true and `hls_url` is populated.

Recording requires FFmpeg. Set `FFMPEG_PATH` or pass `-FfmpegPath`:

```powershell
.\recorder\run_recorder.ps1 -FfmpegPath "C:\path\to\ffmpeg.exe"
```

Recordings are remuxed without re-encoding and split into timestamped MKV files.
Job state and interrupted-run recovery are stored in `recorder_state.sqlite`.

The Recordings library lists nonempty MKV segments from completed, failed, or
interrupted sessions in the recorder database. Filter by session start date or
channel, download an original MKV, or click Play for browser playback. Active
sessions appear in history but their files are withheld until the session ends.
Interrupted/failed captures may be damaged; playback conversion can fail.

Play creates a separate H.264/AAC MP4 under `recordings/.browser-previews`.
Only one conversion runs at a time, with two video encoder threads. The first
play can take time and consumes additional host disk space/CPU; subsequent plays
reuse the cached MP4. Originals are never overwritten or deleted. Closing the
dialog does not cancel conversion. Stopping the recorder terminates conversion;
an unfinished preview can be retried. Preview cache files are not automatically
expired. All LAN users with the shared login can browse and download these files.

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
