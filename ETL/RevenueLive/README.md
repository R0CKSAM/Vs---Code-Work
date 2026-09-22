# RevenueLive

Independent INR revenue reporting. Python 3.11+ on Windows. No ETL services are restarted.

## Setup and operation

From this folder, run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`, then
`powershell -ExecutionPolicy Bypass -File .\manage.ps1 -Action Start`.
The default port is **8820**. Start binds all network interfaces. Use
`-ListenAddress 127.0.0.1` for local-only operation.
Actions: `Start`, `Stop`, `Restart`, `Status`, `Backup`.

First launch creates an **admin** account with a random password in
`data/initial_admin.txt`. Change it on first login, then delete that credential
file. It is not served over HTTP. Each newly created user's temporary password
must also be changed at first login.

The provided sample registers 28 channel names on first launch, but does not
silently publish revenue. Sign in and upload `Upload File.xls` to preview and publish it.

## Access

Admins manage all channels and users. Uploaders may publish only assigned
channels; viewers may read only assigned channels. Reports and CSV exports are
filtered on the server. Unknown/unassigned channels reject the entire upload.
No assignments means no revenue access. Admin assignments are unrestricted.
Channel and role changes are checked on every API request. Open online clients check for changes every two seconds and on focus, clear stale data, and refresh their permitted scope. Background browsers may throttle this check. Disabling an account or resetting its password revokes its sessions.

Create accounts on the same instance where users will sign in (real: 8820; demo: 8822). New users sign in with their temporary password, then set and confirm their own password before accessing reports. Account assignment controls support Select all, Select shown (matching search), and Clear (including hidden choices).

Run `check_accounts.py` with the workspace Python for isolated two-browser account lifecycle checks; it never changes production users.

## Email invitations (optional)

In Add user, choose Invite by email and enter the exact recipient email, role, and channels. Only explicitly created accounts can receive setup/reset links. Recipients can use Gmail or company email. Links expire after 30 minutes, are single-use, and are stored only as hashes. Completing a reset revokes all account sessions. Existing local accounts continue to work; they are not silently converted to email accounts.

Host configuration: create `data/mail.json` (or `demo_data/mail.json` for demo) using `mail.example.json` as the schema. These data directories are ignored by Git. Configure a verified HTTPS public URL and a provider-approved STARTTLS SMTP sender. Restrict file access to the host account. Microsoft tenants may require an IT-approved relay rather than SMTP password authentication. No public tunnel or mail account is created automatically. Do not use the insecure standalone MFA demo as an authentication gateway.

Without mail configuration invitations are rejected before creating an account. If SMTP fails after account creation, the saved account remains pending; after fixing delivery request a new link using Forgot password. Reset requests return the same response for unknown and known emails; delivery failures are logged without email/token contents. Reset requests are limited to one per minute per source IP. Reverse proxies need a separately reviewed trusted-proxy configuration.

This invitation implementation is not MFA. Authenticator enrollment/recovery and account expiry remain a separate rollout; do not advertise mandatory MFA until those are enabled and tested.

Phone access: `http://<host-LAN-IP>:8820`. Company routing and a narrow Windows
firewall rule for approved subnets are required; this app does not modify them.
An IT administrator can run `allow_lan.ps1` once to allow port 8820 from
`192.168.50.0/24` on Domain/Private networks. Other approved subnets can be supplied
with `-Subnets`; do not open the port to all addresses.
HTTP is for trusted-network testing only. Before operational use, put this service
behind your approved HTTPS reverse proxy, set `REVENUE_HTTPS=1`, and restrict direct
backend access. No automatic Internet exposure is configured. Sessions expire
after eight hours; passwords are hashed and writes require CSRF tokens.

## Uploads and persistence

XLS/XLSX first sheet or UTF-8 CSV; exact columns:
`Date, Channel Name, Views, Ad Impressions, Ad Revenue, Sponsorship/Others, Total Revenue`.
Use Excel dates or ISO `YYYY-MM-DD`; INR has at most two decimal places. Maximum
10 MB / 20,000 rows. Formula cells must have saved cached values. Zero is valid;
blank metrics are rejected. Negative adjustments are not supported in this version.

Revenue is stored as integer paise. Date/channel is unique. Preview is required;
replacement requires confirmation. A change after preview aborts publication.
Original files are retained under `data/uploads`; SQLite WAL transactions provide
all-or-nothing publication. Admins can roll back an upload if no newer upload has
changed its rows. Backups include the database and source uploads; run regularly.
To restore a backup, stop RevenueLive and replace its database and uploads directory
from a backup, preserving a copy of the current data first. Never copy only a live
SQLite database file; use the Backup action.

Copy this folder to another PC, including `data`, but exclude `.venv`, `.tools`,
logs and Python caches. Run setup on the new PC. Keep credentials and backups private.
Do not run two hosts against the same SQLite file on a network share.

## Analytics and demo workspace

`manage.ps1 -Action Start -Demo` starts a separate service on **8822** with a
separate `demo_data` database. Its randomly generated admin password is in
`demo_data/initial_admin.txt`. It seeds 31 synthetic days (August 2026) for the
sample's 28 channels. The banner and exported filename explicitly mark demo data.
No synthetic data is inserted into the real database on port 8820.
Use `-Demo` with Status, Stop or Restart to manage only this instance.

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
