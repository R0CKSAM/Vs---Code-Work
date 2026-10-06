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
Channel matching ignores case, repeated whitespace and Unicode presentation
variants (NFKC); punctuation and accents are not guessed. New channel creation
uses the same normalization to prevent case/spacing duplicates. Existing
normalization collisions block upload for admin review instead of picking a
channel automatically. Upload errors list the file's affected channel names and
Excel rows, distinguishing unregistered, unassigned, archived and conflicting
names. During upload, admins and uploaders can explicitly create genuinely new
channels or map file names to active channels available to them. New channels
created by an uploader are assigned only to that uploader. This permission does
not allow taking access to existing unassigned or archived channels. The UI
offers an editable new-channel name and a dropdown of permitted channels,
followed by confirmation and revalidation. Creation, assignment and mapping are
audited and committed together with the successful preview; failed previews
roll back all changes. Cancelling a successful preview leaves explicitly created
channels registered. Mapping applies to this upload only, not a permanent alias.
New channels selected in the current review immediately appear as destinations
for other file names. They are created once, even when several names map to them;
references are resolved independently of spreadsheet order. Removing a pending
creation clears its dependent dropdown choices. Search is available for file
channel names, destination channels, and preview channel/date/Excel-row values.
Searching does not discard hidden selections or skip unresolved rows.
The preview lists applied mappings and flags repeated date/channel rows caused
by mapping for automatic daily totals. All channels must resolve before a preview is saved, and assignments
are checked again when publishing.
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

For production source deployment, configure `DATA_DIR`, `APP_URL`,
and database credentials in `.env`, then run `manage.ps1 -Action Start`. Put an approved
HTTPS reverse proxy in front of the loopback backend. No automatic Internet
exposure is configured. Sessions expire
after eight hours; passwords are hashed and writes require CSRF tokens.

## Uploads and persistence

XLS/XLSX first sheet or UTF-8 CSV; columns in this order:
`Date, Channel Name, Views, Ad Impressions, Ad Revenue, Sponsorship/Others, Total Revenue`.
The complete legacy header set is also accepted:
`Date, Channel Name, Views, Compaign/Ad Impression, Revenue, Sponsorship/Others, Total Ad Revenue`.
In that format, Revenue means ad revenue and Total Ad Revenue must equal
Revenue plus Sponsorship/Others. Header case and whitespace are normalized;
mixed or reordered schemas are rejected. Exports use the standard headers.
Use Excel dates or ISO `YYYY-MM-DD`. Revenue imports round each amount to the
nearest tenth of a rupee (half up: 4.55 becomes 4.6); counts must already be integers.
The supplied total must agree with either the rounded source sum or the sum of
rounded components. Stored totals are calculated from rounded ad revenue plus
rounded sponsorship so component totals remain additive. The preview shows
these normalized one-decimal values. Previously stored data is not re-rounded.
Previously discarded fractions require re-uploading the original file.
Inconsistent source totals appear as
highlighted warnings with Excel row numbers, supplied totals and calculated
totals. Users must explicitly accept calculated totals before publishing such
an upload; acceptance is checked on the server and recorded in the audit chain.
The file total is retained in the SQL upload snapshot; published totals use the
rounded ad revenue plus rounded sponsorship. Other validation errors still block
upload. The server automatically keeps one copy of exact duplicate rows
and sums different entries sharing a channel/date into daily totals. A summary
shows skipped copies and combined daily records, without extra combine/skip
checkboxes, buttons, or a separate browser request. New uploads, old saved previews
and publication all use the same daily-total preparation. Different views or impressions are not duplicates even
when revenue is zero. Different original
channel names mapped to the same destination are kept as separate activities,
even if their numbers match. Original rows, skipped row numbers and combined
totals remain in the SQL preview snapshot and the action is audited. Publication
still requires any total-mismatch and existing-record replacement confirmations.
Combining does not refresh stale database snapshots or bypass channel permissions.
Preview pagination and
the Issues only filter cover all rows, and
pending/rejected files can reopen their warnings from the upload library.
Maximum
10 MB / 20,000 rows. Formula cells must have saved cached values. Zero is valid;
blank metrics are rejected. Negative adjustments are not supported in this version.

Revenue uses the existing integer-paise database/API scale for compatibility;
new imports are multiples of 100 paise. Historical records are not rewritten.
CSV exports omit decimal places for whole rupees and preserve historical fractions.
Date/channel is unique. Preview is required;
replacement requires confirmation. A change after preview aborts publication.
Identical pending data (even in a different file format) and uploads that make no
change to live data are rejected. Unchanged rows in a mixed file are not republished.
Uploaders can publish their own validated files; admins can manage every file.
Archive removes a file's owned data from dashboard queries while retaining its
database snapshot, revisions, and audit history. Unarchive makes safe retained data visible
again; a conflicting newer publication must be reviewed instead of overwritten.
Delete removes that file's live ownership and download access, restoring the
last valid predecessor where applicable. Database snapshots, metadata and audit events remain
for revision history; Delete does not erase history or reclaim all database space.
Admins can hide or restore an entire reporting date across channels without
deleting its source records.
Hidden dates are excluded from reports, charts, exports, and available-date
filters. Archived files are clearly separated in the upload library.
Original CSV/Excel files are not retained. Filenames, hashes, validated rows,
preview snapshots and history live in SQL. Downloads regenerate CSV from the
upload's database snapshot, preserving values but not original Excel formatting.
`UPLOAD_DIR` is a legacy compatibility setting and is no longer used to store files.
MySQL/MariaDB row locks and transactions provide all-or-nothing publication.

State-changing actions and successful sign-ins/outs are recorded with actor,
timestamp and a SHA-256 hash chain. The app checks the chain on startup, blocks
normal SQL UPDATE/DELETE on audit rows, and exposes an admin download of the
full chain. This is **tamper-evident, not immutable**: a host/database administrator
can rewrite the database and recompute hashes. Export the head hash and audit
file regularly to an independently controlled, append-only off-host store if
you need evidence against host-level tampering. Legacy audit rows are chained
at first upgrade using the usernames then present in the database.

Backups include a consistent SQL dump containing upload rows; run regularly.
Set `MYSQLDUMP_PATH` if the tool is not on `PATH`. Restore the SQL dump
after preserving the current state. Accept only backups
containing `BACKUP_COMPLETE`.

Technical logs remain on disk under `LOG_DIR` (default `DATA_DIR/logs`). Each
process uses one rotating `revenuelive.log`, with five retained copies of 5 MiB
by default (approximately 30 MiB total). Configure `LOG_MAX_BYTES` and
`LOG_BACKUP_COUNT` as needed. Use one application process per log directory.
Old timestamped logs, original uploads and existing backups are not automatically
deleted. Explicit backups require separate retention and off-host storage.
The MySQL server also requires disk capacity; this change removes duplicate
upload files, not the database's storage requirement. HTTP server/proxy buffers
may use temporary disk files during requests; they are not an upload archive.

Production source is delivered by a reviewed Git commit, not a ZIP. Follow
`PRODUCTION-HANDOFF.md` for repository boundaries, protected data, backups,
and safe updates. The current shared monorepo includes unrelated projects and
tracked archived material; prefer a dedicated private RevenueLive repository.
Transfer existing production data separately through an approved encrypted
channel. The same source supports `mysql+pymysql` for MySQL Community and
`mariadb+pymysql` for MariaDB. Microsoft SQL Server and PostgreSQL are not
supported by this release.

## Activity History

Admins can filter Uploads > Activity history by login/logout, passwords, uploads,
live/unlive, archive/restore, deletion, users, channels, or other events. Counts
cover the complete history; each page shows up to 50 events, newest first.
Download history still exports the entire audit chain, irrespective of the filter.
Categories do not modify historical audit records. Older admin password resets
remain under Users (marked Password reset); new resets also emit a dedicated
password activity event. No password values are recorded. Role permissions are
unchanged by these filters.

## Analytics

The overview timeline has Auto, Daily, Weekly and Monthly intervals. Auto uses
daily totals for up to 31 days, calendar-week totals for 32-120 days, and calendar-
month totals for longer selections. Weeks start on Monday. Revenue uses stacked
bars for grouped periods; views and impressions use lines. Partial edge periods
are marked, and periods without records remain missing rather than zero.
Click a grouped period or choose it from Open period to view its daily breakdown;
Full range restores the overview. This drill-down changes only the timeline,
not the selected filters, KPI totals or doughnut. Controls also work in the
expanded view. Tooltip amounts remain exact; axes use K/L/Cr abbreviations.
Run `node tests/test_timeline.cjs` to verify aggregation and boundary cases.

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

### User Accounts and Recovery Email

New users require a username and a unique recovery email. Login still uses the
username; the email is used for invitations and Forgot password. Admins can add
or update recovery email in Edit user, subject to existing role protections.
Existing username-only accounts keep working and show Recovery email missing.
Users, including Super Admin, can register/update their own recovery email when
changing their password, with their current password required. First-login
password setup also collects this email. Email changes invalidate old reset
links and are recorded in password activity history. Addresses are marked
verified only after a successful emailed-token password setup/reset.

Temporary-password creation works without email delivery; first login requires
a password change. Invitations require SMTP and an HTTPS APP_URL, and the UI
disables invitations when that configuration is missing. Configuration presence
does not prove SMTP connectivity: an invitation delivery failure leaves the
account saved and reports delivery failure explicitly. Configure SMTP_HOST,
SMTP_PORT (STARTTLS, usually 587), SMTP_FROM, SMTP_USERNAME and SMTP_PASSWORD,
then restart. No real email was sent by automated tests.
