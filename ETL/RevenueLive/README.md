# RevenueLive

Independent INR revenue reporting. Python 3.11+ on Windows. No ETL services are restarted.

## Setup and operation

From this folder, run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`,
copy `.env.example` to the ignored `.env`, configure MySQL Community or MariaDB,
then run `.\.venv\Scripts\python.exe deploy.py upgrade` and
`powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start`.
The default port is **8820** and Start binds only `127.0.0.1`.
Actions: `Start`, `Stop`, `Restart`, `Status`, `Backup`.

For a fresh server database, run `.\.venv\Scripts\python.exe deploy.py
init-admin`; its password prompts are hidden. SQLite local compatibility mode
still creates `data/initial_admin.txt`. Each newly created user's temporary
password must be changed at first login.

To recover or transfer Super Admin ownership on a deployed MySQL/MariaDB system,
stop the application and run `.\.venv\Scripts\python.exe deploy.py super-admin
--username <login>`. Enter and confirm the new password at the hidden prompts,
then restart the application. The command creates or promotes the account,
assigns Super Admin ownership, revokes its existing sessions, forces a password
change at sign-in, and records the recovery in the audit chain. It does not
silently disable the previous owner; review that account afterward in Users &
access. Never edit the `users` or `super_admin` tables manually.

A fresh install starts with no channels or revenue. Add channel names in Users &
access, then upload the actual reporting file to preview and publish it.

## Access

Admins manage all channels and users. Uploaders may publish only assigned
channels; viewers may read only assigned channels. Reports and CSV exports are
filtered on the server. Unknown/unassigned channels reject the entire upload.
No assignments means no revenue access. Admin assignments are unrestricted.
Channel and role changes are checked on every API request. Open online clients check for changes every two seconds and on focus, clear stale data, and refresh their permitted scope. Background browsers may throttle this check. Disabling an account or resetting its password revokes its sessions.

Create accounts on the instance where users will sign in. New users sign in with their temporary password, then set and confirm their own password before accessing reports. Account assignment controls support Select all, Select shown (matching search), and Clear (including hidden choices).

Development-only browser checks are archived under `notneeded/` and are not part of the source handoff.

## Email invitations (optional)

In Add user, choose Invite by email and enter the exact recipient email, role, and channels. Only explicitly created accounts can receive setup/reset links. Recipients can use Gmail or company email. Links expire after 30 minutes, are single-use, and are stored only as hashes. Completing a reset revokes all account sessions. Existing local accounts continue to work; they are not silently converted to email accounts.

Host configuration uses `APP_URL` and the `SMTP_*` environment variables shown
in `.env.example`. The protected legacy `mail.json` format remains supported.
Configure a provider-approved STARTTLS SMTP sender. Restrict configuration file
access to the host account. No public tunnel or mail account is created automatically.

Without mail configuration invitations are rejected before creating an account. If SMTP fails after account creation, the saved account remains pending; after fixing delivery request a new link using Forgot password. Reset requests return the same response for unknown and known emails; delivery failures are logged without email/token contents. Reset requests are limited to one per minute per source IP. Reverse proxies need a separately reviewed trusted-proxy configuration.

This invitation implementation is not MFA. Authenticator enrollment/recovery and account expiry remain a separate rollout; do not advertise mandatory MFA until those are enabled and tested.

For production source deployment, configure `DATA_DIR`, `UPLOAD_DIR`, `APP_URL`,
and database credentials in `.env`, then run `manage.ps1 -Action Start`. Put an approved
HTTPS reverse proxy in front of the loopback backend. No automatic Internet
exposure is configured. Sessions expire
after eight hours; passwords are hashed and writes require CSRF tokens.

## Uploads and persistence

XLS/XLSX first sheet or UTF-8 CSV; exact columns:
`Date, Channel Name, Views, Ad Impressions, Ad Revenue, Sponsorship/Others, Total Revenue`.
Use Excel dates or ISO `YYYY-MM-DD`; INR has at most two decimal places. Maximum
10 MB / 20,000 rows. Formula cells must have saved cached values. Zero is valid;
blank metrics are rejected. Negative adjustments are not supported in this version.

Revenue is stored as integer paise. Date/channel is unique. Preview is required;
replacement requires confirmation. A change after preview aborts publication.
Identical pending data (even in a different file format) and uploads that make no
change to live data are rejected. Unchanged rows in a mixed file are not republished.
Uploaders can publish their own validated files; admins can manage every file.
Archive removes a file's owned data from dashboard queries while retaining its
source, revisions, and audit history. Unarchive makes safe retained data visible
again; a conflicting newer publication must be reviewed instead of overwritten.
Delete removes the retained source and that file's live ownership, restoring the
last valid predecessor where applicable. Metadata and audit events remain.
Admins can hide or restore an entire reporting date across channels without
deleting its source records.
Hidden dates are excluded from reports, charts, exports, and available-date
filters. Archived files are clearly separated in the upload library.
Original files remain under the configured `UPLOAD_DIR`; MySQL/MariaDB row locks
and transactions provide all-or-nothing publication.

State-changing actions and successful sign-ins/outs are recorded with actor,
timestamp and a SHA-256 hash chain. The app checks the chain on startup, blocks
normal SQL UPDATE/DELETE on audit rows, and exposes an admin download of the
full chain. This is **tamper-evident, not immutable**: a host/database administrator
can rewrite the database and recompute hashes. Export the head hash and audit
file regularly to an independently controlled, append-only off-host store if
you need evidence against host-level tampering. Legacy audit rows are chained
at first upgrade using the usernames then present in the database.

Backups include a consistent SQL dump and retained source uploads; run regularly.
Set `MYSQLDUMP_PATH` if the tool is not on `PATH`. Restore the matching SQL dump
and uploads together after preserving the current state. Accept only backups
containing `BACKUP_COMPLETE`.

Production source is delivered by a reviewed Git commit, not a ZIP. Follow
`PRODUCTION-HANDOFF.md` for repository boundaries, protected data, backups,
and safe updates. The current shared monorepo includes unrelated projects and
tracked archived material; prefer a dedicated private RevenueLive repository.
Transfer existing production data separately through an approved encrypted
channel. The same source supports `mysql+pymysql` for MySQL Community and
`mariadb+pymysql` for MariaDB. Microsoft SQL Server and PostgreSQL are not
supported by this release.

## Analytics

Filters support one/multiple/all assigned channels, explicit empty selection,
single dates and custom ranges. Latest 7/30 days and Latest month are anchored to
the latest available data date, not to the wall clock. Apply commits the selection;
CSV export always matches the applied report, even if controls have unsaved changes.
The table is paginated, but totals/charts/export include all filtered records.

Charts include line trends (daily/weekly/monthly), channel ranking, pie/doughnut
share, stacked ad/sponsorship revenue and views-vs-revenue scatter. Share groups
channels after the top six as Other; Top 10 ranking can switch to All selected.
Weekly buckets begin Monday and include only records inside the applied date range.
The local Chart.js 4.4.1 bundle is MIT licensed; its license is in `static`.
