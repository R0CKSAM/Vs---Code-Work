# YT4 collector

The collector uses the repository virtual environment and writes to the mapped
YouTube backup root on `Z:` by default:

```text
ETL\YT
|-- YT4.py
|-- channels.txt
|-- install_yt4_task.ps1
|-- status_yt4.ps1
|-- logs\yt4.log
`-- state\yt4.lock
```

## Install

1. Ensure the repository `venv` contains `yt-dlp` and `pyarrow`.
2. Edit `channels.txt` if the tracked channel list needs to change.
3. Run from `ETL\YT` while logged in as the user that can access `Z:`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_yt4_task.ps1
```

The installer registers an at-logon task under the current interactive user,
starts it through hidden `pythonw.exe`, and restarts it one minute after a
failure. This account choice is intentional: a `SYSTEM` task cannot normally
see the user's mapped `Z:` drive. Viewer measurement is public-first through
yt-dlp; an API key in `.env` is optional and is used only as a fallback.
The launchers use eight workers for the eight configured channels so a slow
channel does not routinely consume the next minute's collection slot. If a
cycle still exceeds 60 seconds, the log records an explicit `COLLECTION GAP`
warning; the collector never fabricates a missing concurrency value.

Check it without opening the collector console:

```powershell
.\status_yt4.ps1
```

Every poll is fsynced to a journal. Completed files are 15-minute Parquet
segments. After a reboot, YT4 publishes any surviving journal before polling
again, so only an interrupted line currently being written can be lost.
# Connection-loss recovery

The collector stays running through transient network and output-share errors.
Failed startup/storage operations retry after 5, 10, 20, 40 and then 60 seconds
indefinitely. When every source lookup fails, polling uses the same capped
backoff and resumes its normal interval after a successful poll. A failed channel
discovery is retried on the next poll rather than waiting for the normal
15-poll discovery interval. Discovery and measurement both have socket timeouts.

Lookup failures retain unknown viewer counts and preserve previously live
streams; they do not count as successful end-of-stream confirmations. Missed
historical concurrency cannot be reconstructed by retrying. `--once` still fails
immediately, and explicit HTTP configuration/authentication failures are not
retried by the startup recovery loop. The six-hour health task remains a separate
fallback for a stalled process.
