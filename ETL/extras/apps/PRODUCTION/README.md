# Veto Broadcast Project Archive

This repository mirrors the project folders on the broadcast PC's `D:\` drive.
The active application remains **`D:\Veto OTT`**. Git's root is **`D:\`**; no
application folders have been moved.

## Folders

| Folder | Contents |
| --- | --- |
| `Veto OTT` | Active application, graphics assets and current saved data |
| `Veto Live` | Older application source and its uploaded assets |
| `old` | Earlier source snapshot |
| `older` | Earlier source snapshot |
| `Veto` | Note identifying the local diagnostics folder; crash reports excluded |

Current template JSON, competition libraries and uploaded media are included.
Browser-local recovery drafts and queues are not files in this repository.
Protected legacy projects are exported to `Veto OTT/project_exports` without
their password records; their original local files are left untouched.
Two saved presets containing credentials in their metadata are also excluded;
their exact local paths are listed in `.gitignore`.

## Deliberate Exclusions

- Credentials, password records, environment secrets and private keys.
- Windows system folders, Git metadata and browser profiles.
- Installed Python dependencies, offline wheels, FFmpeg binaries and caches.
- Logs, crash dumps, historical backups and temporary development/test folders.
- Local shortcuts, process IDs and machine-specific Python paths.

Do not use `git add -f` to bypass these protections. This is a project/data
archive, not an exact drive image. Review new uploads and saved data for private
content before each push, particularly when using a public GitHub repository.

## Setup and Restore

Install 64-bit Python 3.14 with pip and Tcl/Tk. Install FFmpeg separately for video
playback/export, in PATH or at `Veto OTT/tools/ffmpeg/bin/ffmpeg.exe`. SDI requires
compatible DeckLink hardware and the Blackmagic Desktop Video driver.

On a new machine, restore sanitized legacy collections before first startup by
placing `Veto OTT/project_exports/*.json` in `Veto OTT/data/projects`. Never
overwrite existing projects or credential files on an operational installation.
Then run from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Veto OTT\setup_scoreboard.ps1" -NoStart
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Veto OTT\start_scoreboard.ps1"
```

Setup installs Python dependencies from pip when offline wheels are absent.
The dashboard is http://127.0.0.1:8080/scoreboard.

New installations of **Veto OTT** generate unique passwords, recorded locally in
`Veto OTT/data/first_run_credentials.json`. Store them privately, then remove that
plaintext recovery file. It is excluded from Git. Existing logins do not change.
The historical versions are retained as source archives, not recommended hosts.

## Future Updates

Refresh the sanitized legacy exports after editing their original collections:

```powershell
python ".\Veto OTT\export_projects.py"
```

Review and push changes from `D:\`:

```powershell
Set-Location D:\
$git = 'C:\Program Files\Git\cmd\git.exe'
& $git status --short
& $git add -- .
& $git diff --cached --stat
& $git diff --cached
& $git commit -m 'Describe the update'
& $git push
```

Do not restart or replace running application code while SDI output is active.

[GitHub push guide](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).
