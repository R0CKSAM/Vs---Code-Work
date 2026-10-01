# RevenueLive source handoff

Give the hosting team only the timestamped folder produced by
`build_source_handoff.ps1`. Do not send the working RevenueLive folder,
`notneeded/`, `data/`, `backups/`, `logs/`, `.tools/`, `.venv/`, or any
credentials. The handoff contains Python source and browser JavaScript; it
does not conceal the implementation from the hosting team.

## Host setup

1. Install supported 64-bit Python 3.11 or newer on Windows. From the handoff
   folder, run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`. If needed,
   pass `-Python 'C:\Path\To\python.exe'`.
2. Create an access-restricted data directory outside the source folder on
   encrypted storage. Use a dedicated non-admin service identity. Transfer any
   existing data only through an approved encrypted channel using a complete
   application backup, not a copy of a live SQLite file.
3. Put an HTTPS reverse proxy and valid certificate in front of
   `127.0.0.1:8820`. Keep the backend port private. Preserve the public Host
   header and overwrite incoming X-Forwarded-For with the real client IP.
4. Start the backend with
   `powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start
   -DataDir 'D:\RevenueLiveData' -PublicUrl 'https://revenue.example.com'`.
   Register the same command with an approved service manager for reboot and
   failure recovery; the script does not install a Windows service or proxy.
5. On a fresh database, read `initial_admin.txt` from the protected data
   directory, change the password on first sign-in, then securely remove the
   file. Add channels before uploading actual revenue data. A fresh install
   contains no demo channels or records.

Use `-Action Status`, `-Action Stop`, or `-Action Restart` with the same
`-DataDir`; Restart also needs `-PublicUrl`. For backups, set
`REVENUE_BACKUP_DIR` to a separate encrypted, restricted directory before
running `-Action Backup`. Restore only complete backups during a maintenance
window and test restore in staging.

## Mail and acceptance

Mail is optional. Create `<DataDir>\mail.json` from `mail.example.json` with
the exact HTTPS public origin. Pass `REVENUE_SMTP_PASSWORD` through the service
identity's protected environment or secret manager, never in JSON or source.

Before public use, test HTTPS sign-in, password change, channel scoping,
upload preview and publish, CSV export, mail reset if configured, backup and
restore, and restart after reboot. Review dependency advisories and server
logs. This dashboard does not include MFA. Disk encryption, TLS, firewall,
monitoring, and patching remain host responsibilities.
