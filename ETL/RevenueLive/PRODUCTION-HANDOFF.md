# RevenueLive production handoff

## What is in the release

`RevenueLive.exe` and its companion DLLs contain the Python server, compiled with
Nuitka standalone mode. `static/` contains only the browser assets used by the
dashboard. The Lucide and flatpickr notices at the release root and the Chart.js
notice in `static/` accompany the browser libraries. `start_release.ps1` controls
the local backend. No database, uploads,
passwords, mail configuration, demo dataset, test scripts, Python source, or
build intermediates belong in the release folder. Compare its files against
`SHA256SUMS.txt` before deployment, and send the manifest hash to the hosting
team over a separate trusted channel. Prefer code signing for the executable.
`BUILD-DEPENDENCIES.txt` records the builder
packages so the owner can review versions and vulnerability advisories.

This is source reduction, not cryptographic secrecy. Browser JavaScript must
be delivered to browsers and remains readable. Administrators of the host can
inspect process memory, files, and traffic. Keep proprietary server logic on
infrastructure you control if host operators must not be able to inspect it.

## Host preparation

1. Use a supported Windows x64 host, a dedicated non-admin service identity,
   and an access-restricted data directory outside the release folder. Put the
   data directory **and backup destination** on encrypted storage (BitLocker or
   an approved encrypted cloud volume). Back up the recovery key separately.
2. Provide a valid HTTPS certificate and a reverse proxy on the same host. The
   proxy must be the only public entry point; forward to `127.0.0.1:8820`.
   Preserve the public `Host` and **overwrite**, do not append an untrusted
   client-supplied `X-Forwarded-For`, with the real client IP. Do not expose the
   backend HTTP port or trust proxy headers from the internet.
3. Run `powershell -ExecutionPolicy Bypass -File .\start_release.ps1 -Action Start
   -DataDir 'D:\RevenueLiveData' -PublicUrl 'https://revenue.example.com'`.
   Configure the same parameters in the approved Windows service/scheduler
   mechanism for automatic restart after reboot. The command starts only the
   loopback backend; it does **not** create a reverse proxy or open a firewall.
4. The first run creates `initial_admin.txt` in the data directory. Sign in,
   change the temporary password, then securely remove that file. Restrict
   access to the data directory to the service identity and authorized admins.
   A fresh compiled install starts without sample channels or revenue; add
   channels through the admin UI or restore a protected backup.
5. Check `-Action Status` and perform a real sign-in, upload preview, publish,
   scoped viewer access, CSV export, and backup/restore drill on a staging copy
   before accepting production traffic. Check that the compiled backend serves
   `/`, `/static/app.js`, and `/api/me` with expected auth behavior. Run a
   dependency vulnerability scan and review logs for errors before approval.

`-Action Stop` and `-Action Restart` use the same `-DataDir`; Restart also needs
`-PublicUrl`. Back up with `-Action Backup -DataDir 'D:\RevenueLiveData'
-BackupDir 'E:\RevenueLiveBackups'`. Only folders containing `BACKUP_COMPLETE`
are finished backups. Protect that backup volume and schedule off-host copies.

## Mail invitations

Mail is optional. Create `<DataDir>\mail.json` from the source repository's
`mail.example.json`, with the correct verified HTTPS public URL, SMTP host,
sender and optional username. In production, do not put the SMTP password in
JSON. Supply `REVENUE_SMTP_PASSWORD` through the service manager's protected
secret/environment facility. The setting must be present in the process that
starts `RevenueLive.exe`. Do not put it in command-line arguments, release
files, or logs. Test delivery in staging. The separate `MFA/` experiment is
not included and does not protect this dashboard.

## Security limits

- HTTPS and disk encryption are host responsibilities. The app sets secure
  session cookies and HSTS when configured with an HTTPS public origin.
- The backend validates CSRF tokens, origin, roles, and channel assignments;
  it is not a substitute for firewall rules, monitoring, patching, backups,
  or an independent security review.
- Compiling is not encryption. Do not distribute the original repository or
  `.tools/` build directory to the hosting team if server-source visibility is
  the concern. A host administrator can still reverse engineer a binary.
- Any production data copied from an existing machine must be transferred
  separately over an approved encrypted channel. Never copy a live SQLite file
  alone; use the application's backup command and protect the resulting files.

## Builder (owner machine only)

From the source folder, run `powershell -ExecutionPolicy Bypass -File
.\build_handoff.ps1`. It uses a standard CPython 3.14 installation (not the
Microsoft Store build), installs Nuitka and runtime dependencies in an ignored
`.tools/handoff-venv`, runs tests, compiles standalone with Visual Studio Build
Tools, and emits a timestamped
`.tools/handoff-release-*` folder. Do not ship `.tools/handoff-build-*`.
