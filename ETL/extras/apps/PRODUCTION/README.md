# Veto Scoreboard Production

`Veto OTT` is the active Davis Cup and Billie Jean King Cup application.
`notrequired` holds old snapshots, source artwork, package caches and backups.
It is a local archive excluded from Git, not a deployable app.

## Folders

| Folder | Contents |
| --- | --- |
| `Veto OTT` | Active application, graphics assets and current saved data |
| `notrequired` | Historical snapshots and unused local bundles |

Keep the complete `Veto OTT/data` folder when moving the app to another PC;
saved templates and uploads both live there. Setup rewrites the machine-specific
Python path. Stop verifies a stored PID before terminating any process.

## Deliberate Exclusions

- Credentials, password records, environment secrets and private keys.
- Windows system folders, Git metadata and browser profiles.
- Installed Python dependencies, offline wheels, FFmpeg binaries and caches.
- Logs, crash dumps, historical backups and temporary development/test folders.
- Local shortcuts, process IDs and machine-specific Python paths.

Do not use `git add -f` to bypass these protections. Review new uploads and
saved data for private content before any push.

## Setup and Restore

Install 64-bit Python 3.14 with pip and Tcl/Tk. Install FFmpeg separately for video
playback/export, in PATH or at `Veto OTT/tools/ffmpeg/bin/ffmpeg.exe`. SDI requires
compatible DeckLink hardware and the Blackmagic Desktop Video driver.

On each Windows host, run from this folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Veto OTT\setup_scoreboard.ps1" -NoStart
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Veto OTT\start_scoreboard.ps1"
```

Setup uses `python -m pip install --user --upgrade -r requirements.txt` and
verifies a headless render. No offline wheels or vendored packages are needed.
Manual equivalent: `py -3.14 -m pip install --user -r ".\Veto OTT\requirements.txt"`.
The dashboard is http://127.0.0.1:8080/scoreboard.

New installations of **Veto OTT** generate unique passwords, recorded locally in
`Veto OTT/data/first_run_credentials.json`. Store them privately, then remove that
plaintext recovery file. It is excluded from Git. Existing logins do not change.
Historical versions remain under `notrequired` on this PC only.

## Future Updates

Run `../leaderBoardGen/build_scoreboard_code_update.ps1` to package the active
code and all required competition artwork. The code ZIP assumes a host already
has the current setup/start/stop/updater scripts. For an older host, use the
full portable package and preserve its existing data and settings.
Do not restart or replace running code while SDI output is active.

The app uses HTTP and operator sessions, not internet-grade account security.
Keep it on a trusted LAN or behind an authenticated HTTPS gateway/VPN. Do not
expose port 8080 directly to the public internet.
