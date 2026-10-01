# RevenueLive production deployment via Git

## Repository boundary

Production receives reviewed source through Git, not a ZIP or compiled
executable. Prefer a dedicated private RevenueLive repository containing only
the application files. The current `Vs - Code Work` remote is a shared monorepo
and still tracks `ETL/RevenueLive/notneeded/` plus unrelated projects. Granting
access to that remote grants access to its other files and history. Do not give
the hosting team that access without explicit approval. Removing a file from
the current branch does not remove it from Git history.

The application currently uses SQLite (`revenuelive.db`). A Git checkout does
not make it compatible with Microsoft SQL Server, PostgreSQL, or MySQL. Confirm
the database engine before promising a server-database deployment.

Source code and browser JavaScript are visible to anyone who can read the Git
repository or host. Limit repository and server access accordingly.

## Host setup

1. Create a Windows service account without administrator rights. Give it
   access to an encrypted data directory outside the Git checkout, for example
   `D:\RevenueLiveData`, and a separate encrypted backup destination.
2. Check out the approved private repository and a reviewed release commit.
   From the application directory, run
   `powershell -ExecutionPolicy Bypass -File .\setup.ps1` with supported
   64-bit Python 3.11 or newer installed. The ignored `.venv/` is local to
   the host; never commit it.
3. Put a valid HTTPS reverse proxy in front of `127.0.0.1:8820`. Expose only
   the proxy. Preserve the public Host header and overwrite untrusted
   `X-Forwarded-For` with the real client IP.
4. Start with
   `powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start
   -DataDir 'D:\RevenueLiveData' -PublicUrl 'https://revenue.example.com'`.
   Register the same command with an approved service manager for reboot and
   failure recovery. The script does not create a reverse proxy or firewall
   rule.
5. For a fresh installation, read `initial_admin.txt` inside the protected
   data directory, sign in and change its password, then securely remove that
   file. Fresh installs have no demo channels or revenue.

If the approved repository is the present monorepo, the application directory
is `<checkout>\ETL\RevenueLive`. In a dedicated repository it can be the
checkout root. In either case, keep data, uploads, mail secrets, backups,
logs, and the Python environment out of Git.

## Git update procedure

1. In staging, test the target commit against a **copy** of production data.
   Check sign-in, scoped report/export, preview and publish, overlapping-file
   unpublish, date Hide/Restore, audit export, and backup/restore.
2. On production, record the running commit with `git rev-parse HEAD` and
   confirm `git status --porcelain` is empty. Do not edit application files
   in the checkout.
3. Back up before switching code. Set `REVENUE_BACKUP_DIR` to the protected
   backup destination, then run
   `powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Backup
   -DataDir 'D:\RevenueLiveData'`. Accept only a backup folder containing
   `BACKUP_COMPLETE`; keep an off-host copy.
4. During a maintenance window, stop the app with `manage.ps1 -Action Stop`
   and the same `-DataDir`. Fetch the reviewed commit with `git fetch origin`,
   then check out that exact commit with `git switch --detach <tested-commit>`.
   Run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` if
   dependencies changed. Restart with the Start command above.
5. Check `/health`, sign-in, report totals, export, upload controls, audit
   status, and server logs before reopening traffic. Roll back code to the
   recorded commit only after assessing schema changes; restore the matching
   database backup if the new version changed storage format.

## Mail and audit

Mail is optional. Create `<DataDir>\mail.json` from `mail.example.json` with
the exact HTTPS public origin. Supply `REVENUE_SMTP_PASSWORD` through the
service manager's protected environment, never Git, JSON, or a command line.
Test mail delivery in staging. This app does not include MFA.

The local audit hash chain is tamper-evident, not immutable to a host
administrator. Export its full log and head hash regularly to an independently
controlled append-only off-host store. Restrict and monitor access to the
database and backup destination.
