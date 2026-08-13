# YT4 remote collector

Keep this bundle together in one root folder, for example `C:\Veto-IndiaTv`:

```text
C:\Veto-IndiaTv
|-- YT4.py
|-- channels.txt
|-- requirements-yt4.txt
|-- install_yt4_task.ps1
|-- status_yt4.ps1
|-- .env
|-- .venv\
|-- data\source=Youtube\year=YYYY\month=MM\day=DD\
|-- logs\yt4.log
`-- state\yt4.lock
```

## Install

1. Copy `.env.example` to `.env` and set `YOUTUBE_API_KEY`.
2. Edit `channels.txt` if the tracked channel list needs to change.
3. Open PowerShell as Administrator in this folder.
4. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_yt4_task.ps1
```

The installer creates the local `.venv`, installs dependencies, registers an
at-startup task under `SYSTEM`, starts it through hidden `pythonw.exe`, and
restarts it one minute after a failure.

Check it without opening the collector console:

```powershell
.\status_yt4.ps1
```

Every poll is fsynced to a journal. Completed files are 15-minute Parquet
segments. After a reboot, YT4 publishes any surviving journal before polling
again, so only an interrupted line currently being written can be lost.
