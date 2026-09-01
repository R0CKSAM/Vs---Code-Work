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

Check it without opening the collector console:

```powershell
.\status_yt4.ps1
```

Every poll is fsynced to a journal. Completed files are 15-minute Parquet
segments. After a reboot, YT4 publishes any surviving journal before polling
again, so only an interrupted line currently being written can be lost.
