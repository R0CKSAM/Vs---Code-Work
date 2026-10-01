# RevenueLive

Independent INR revenue reporting. Python 3.11+ on Windows. No ETL services are restarted.

## Setup and operation

From this folder, run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`, then
`powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start`.
The default port is **8820** and Start binds only `127.0.0.1`.
Actions: `Start`, `Stop`, `Restart`, `Status`, `Backup`.

First launch creates a **Super Admin** account with a random password in
`data/initial_admin.txt`. Change it on first login, then delete that credential
file. It is not served over HTTP. Each newly created user's temporary password
must also be changed at first login.

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

Host configuration: create `<DataDir>/mail.json` using `mail.example.json` as the schema. Configure a verified HTTPS public URL and a provider-approved STARTTLS SMTP sender. Set `REVENUE_SMTP_PASSWORD` in the service environment when SMTP authentication is needed; in HTTPS production mode, a password in mail.json is rejected. Restrict file access to the host account. Microsoft tenants may require an IT-approved relay rather than SMTP password authentication. No public tunnel or mail account is created automatically.

Without mail configuration invitations are rejected before creating an account. If SMTP fails after account creation, the saved account remains pending; after fixing delivery request a new link using Forgot password. Reset requests return the same response for unknown and known emails; delivery failures are logged without email/token contents. Reset requests are limited to one per minute per source IP. Reverse proxies need a separately reviewed trusted-proxy configuration.

This invitation implementation is not MFA. Authenticator enrollment/recovery and account expiry remain a separate rollout; do not advertise mandatory MFA until those are enabled and tested.

For production source deployment, create an access-restricted data directory
outside this code folder and run `manage.ps1 -Action Start -DataDir
'D:\RevenueLiveData' -PublicUrl 'https://your-domain.example'`. Put an approved
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
Uploaders can publish their own validated files; admins can accept any pending
file. Rejecting a pending file keeps its data off the dashboard. Admins can
unpublish an accepted file at any time. If a newer accepted file replaced its
rows, the newer values remain; when that newer file is unpublished, the last
still-accepted values are restored. Rejected and unpublished files cannot be
accepted again; re-upload the corrected file. Admins can hide or restore an
entire reporting date across channels without deleting its source records.
Hidden dates are excluded from reports, charts, exports, and available-date
filters. Archiving a legacy history entry only hides it from the default list.
Admins can delete the physical source of a rejected or unpublished file, but
the upload metadata, row snapshots, backups, and activity history remain.
Original files otherwise remain under `data/uploads`; SQLite WAL transactions
provide all-or-nothing publication.

State-changing actions and successful sign-ins/outs are recorded with actor,
timestamp and a SHA-256 hash chain. The app checks the chain on startup, blocks
normal SQL UPDATE/DELETE on audit rows, and exposes an admin download of the
full chain. This is **tamper-evident, not immutable**: a host/database administrator
can rewrite the database and recompute hashes. Export the head hash and audit
file regularly to an independently controlled, append-only off-host store if
you need evidence against host-level tampering. Legacy audit rows are chained
at first upgrade using the usernames then present in the database.

Backups include the database and retained source uploads; run regularly.
To restore a backup, stop RevenueLive and replace its database and uploads directory
from a backup, preserving a copy of the current data first. Never copy only a live
SQLite database file; use the Backup action.

Production source is delivered by a reviewed Git commit, not a ZIP. Follow
`PRODUCTION-HANDOFF.md` for repository boundaries, protected data, backups,
and safe updates. The current shared monorepo includes unrelated projects and
tracked archived material; prefer a dedicated private RevenueLive repository.
Transfer existing production data separately through an approved encrypted
channel. Do not run two hosts against the same SQLite file on a network share.
If the hosting team requires Microsoft SQL Server, PostgreSQL, or MySQL,
confirm that engine first: this version still uses SQLite and needs a database
adapter and migration before connecting to a server database.

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
