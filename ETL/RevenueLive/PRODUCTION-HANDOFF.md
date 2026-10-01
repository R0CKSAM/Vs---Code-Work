# RevenueLive production deployment via Git

## Repository boundary

Production receives reviewed source through Git, not a ZIP or compiled
executable. Prefer a dedicated private RevenueLive repository containing only
the application files. The current `Vs - Code Work` remote is a shared monorepo
and still tracks `ETL/RevenueLive/notneeded/` plus unrelated projects. Granting
access to that remote grants access to its other files and history. Do not give
the hosting team that access without explicit approval. Removing a file from
the current branch does not remove it from Git history.

The production database is MySQL Community Server or MariaDB. SQLite remains a
local compatibility and migration source only. The application uses SQLAlchemy,
PyMySQL, and versioned Alembic migrations. It does not support Microsoft SQL
Server or PostgreSQL without a separate adapter and migration project.

Source code and browser JavaScript are visible to anyone who can read the Git
repository or host. Limit repository and server access accordingly.

## Host setup

1. Install MySQL Community Server 8.4 LTS or a supported MariaDB release. Create
   an empty database with `utf8mb4`, plus a dedicated application account. Give
   schema migration permissions (`CREATE`, `ALTER`, `INDEX`, `REFERENCES`, and
   `TRIGGER`) only during deployment; the running application needs normal
   `SELECT`, `INSERT`, `UPDATE`, and `DELETE` access.
2. Create a Windows service account without administrator rights. Give it
   access to an encrypted data directory outside the Git checkout, for example
   `D:\RevenueLiveData`, a private upload directory, and a separate encrypted
   backup destination.
3. Check out the approved private repository and a reviewed release commit.
   From the application directory, run
   `powershell -ExecutionPolicy Bypass -File .\setup.ps1` with supported
   64-bit Python 3.11 or newer installed. The ignored `.venv/` is local to
   the host; never commit it.
4. Copy `.env.example` to `.env` and configure `APP_URL`, `DB_DRIVER`, database
   credentials, storage, cookie, proxy, and optional SMTP settings. `.env` is
   ignored by Git. For XAMPP/MariaDB use `DB_DRIVER=mariadb+pymysql`; for MySQL
   Community use `DB_DRIVER=mysql+pymysql`.
5. Run `.\.venv\Scripts\python.exe deploy.py upgrade`. On a fresh installation,
   run `.\.venv\Scripts\python.exe deploy.py init-admin` and enter the password
   at its hidden prompt. To migrate an existing SQLite installation, back it up,
   leave the target database empty except for the migration schema, then run:
   `.\.venv\Scripts\python.exe deploy.py import-sqlite --source <db-file>
   --source-uploads <uploads-directory>`.
6. Put a valid HTTPS reverse proxy in front of `127.0.0.1:8820`. Expose only
   the proxy. Preserve the public Host header and overwrite untrusted
   `X-Forwarded-For` with the real client IP.
7. Start with `powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start`.
   `manage.ps1` reads the deployment configuration from `.env`.
   Register the same command with an approved service manager for reboot and
   failure recovery. The script does not create a reverse proxy or firewall
   rule.
8. Open `/login`, sign in with the initialized admin, and verify `/admin` and
   `/user` permissions. Fresh installs have no demo channels or revenue.

For Super Admin recovery, stop RevenueLive and run `.\.venv\Scripts\python.exe
deploy.py super-admin --username <login>`. The operator enters the new password
twice at hidden prompts. Restart, sign in, and change the password when asked.
This action is audited, revokes the recovered account's sessions, and leaves the
previous owner as a normal admin for explicit review. Do not repair ownership
with ad-hoc SQL.

The recommended layout is one domain: `/login`, `/admin`, and `/user`. To move
later to `admin.example.com` and `app.example.com`, set `PORTAL_MODE=split`, the
two URL variables, and both exact hosts in `ALLOWED_HOSTS`, then route both hosts
to the same backend. No source change is needed. Cookies remain host-only, so a
user signs in separately on each host; add an external OIDC identity provider
later if seamless cross-subdomain SSO is required.

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
3. Back up before switching code. Set `REVENUE_BACKUP_DIR` and, when needed,
   `MYSQLDUMP_PATH`, then run `powershell -ExecutionPolicy Bypass -File
   .\manage.ps1 -Action Backup`. Accept only a backup folder containing
   `BACKUP_COMPLETE`; keep an off-host copy.
4. During a maintenance window, stop the app with `manage.ps1 -Action Stop`
   and the same `-DataDir`. Fetch the reviewed commit with `git fetch origin`,
   then check out that exact commit with `git switch --detach <tested-commit>`.
   Run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`, then
   `deploy.py upgrade`. Restart with the Start command above. Database migrations
   are forward-only; restoring an older release requires its matching database
   dump and upload directory.
5. Check `/health`, sign-in, report totals, export, upload controls, audit
   status, and server logs before reopening traffic. Roll back code to the
   recorded commit only after assessing schema changes; restore the matching
   database backup if the new version changed storage format.

## Mail and audit

Mail is optional. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
`SMTP_USERNAME`, and `SMTP_PASSWORD` through the service environment. The
legacy protected `mail.json` format remains supported. Never commit credentials.
Test mail delivery in staging. This app does not include MFA.

The local audit hash chain is tamper-evident, not immutable to a host
administrator. Export its full log and head hash regularly to an independently
controlled append-only off-host store. Restrict and monitor access to the
database and backup destination.
