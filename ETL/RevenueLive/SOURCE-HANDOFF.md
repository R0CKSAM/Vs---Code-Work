# RevenueLive source delivery

RevenueLive is delivered through a reviewed Git commit. The same source supports
MySQL Community Server and MariaDB through deployment configuration. Use
`PRODUCTION-HANDOFF.md` for database provisioning, environment variables,
migrations, domains, backups, and update steps.

The recommended first deployment uses one HTTPS origin:
`https://example.com/login`, `/admin`, and `/user`. Authentication and every API
permission are enforced by the server. A later deployment can set
`PORTAL_MODE=split`, `ADMIN_URL`, `USER_URL`, and `ALLOWED_HOSTS` to serve the
same application and database through two subdomains without changing source.
Host-only cookies intentionally require a separate login on each subdomain.

Reporting data, uploaded filenames, validated rows and activity history are
stored in SQL. Original spreadsheets are not retained; upload downloads produce
CSV from the stored rows. Backups are explicit SQL dumps. Technical logs use
bounded rotation; see `.env.example`. Existing legacy files require a separate
cleanup and are not removed by installing this version.

## Company profiles

Run `python deploy.py upgrade` before restarting this version. Migration
`0003_user_profiles` adds SQL-backed company names without modifying revenue data.
In Users & access, Add/Edit user includes Company Name, Username and Email.
Company Name appears above Username in the header; Email appears in the menu.
An empty Company Name preserves the existing username-only header.
Super Admin can edit their own profile but cannot change their protected role,
disable themselves or reset their password through this form. Use Change password.
Existing passwords are never displayed. Admins can edit ordinary users, disable
their accounts, or set temporary passwords that require a change at next login.
Only Super Admin can manage other admin accounts. Profile and password changes
are recorded in the activity history.

For host-level recovery without SMTP, run
`python deploy.py super-admin --username <existing-username> --email <email>`.
Enter the new password at the hidden prompt. This assigns Super Admin ownership
to that username and revokes its sessions; use the intended owner account.

## Channel names and logos

Admins can edit names and add/replace logos from Users & access > Channel
directory. Renames keep channel IDs, assignments and revenue records unchanged;
previous names remain aliases for future uploads. Original upload snapshots and
audit history retain their original text. Logos accept still PNG/JPG/WebP images
up to 2 MB and 4 megapixels, are resized to at most 512 x 512, and stored as
normalized PNG data in SQL. Restore default logo returns to the bundled logo
or initials. Renaming preserves the original bundled-logo association.

For this release, install `requirements.txt` (including Pillow), run
`python deploy.py upgrade`, then restart the service. Migration
`0002_channel_branding` adds two tables; it does not rewrite revenue records.

Copy `.env.example` to an ignored `.env` on each host and change configuration
there. Never commit `.env`, database credentials, SMTP credentials, runtime
data, uploads, backups, logs, `.venv/`, `.tools/`, or archived development
material. Prefer a dedicated private RevenueLive repository over sharing the
existing monorepo and its unrelated history.

## Files to keep in the production source repository

- Root Python modules: application, configuration, authentication/email,
  database/schema, migrations CLI, backups, logging and insight presets.
  `sqlite_legacy.py` is still required for local tests and SQLite migration support.
- `static/` with channel logos, JavaScript, styles and bundled library licenses.
- `migrations/`, `requirements.txt`, `setup.ps1`, `manage.ps1`.
- `.env.example`, `.gitignore`, README and both handoff guides, library licenses.
- `tests/` for release verification; these do not run as part of the web server.

Keep `.env` and `.venv/` on each host, outside version control. Do not move a
running host's data, logs or backups simply to make its checkout look smaller.
Use configured external data/log/backup directories on a new production host.
Do not include `notneeded/`, local runtime folders or old backups in the client
handoff. `.gitignore` does not remove already tracked files from Git history.

The source cleanup archived the obsolete mail configuration example, generated
Python cache and the old SQLite-only preset installer under
`notneeded/source-cleanup-20261001/`. SMTP environment settings remain in
`.env.example`. Python may regenerate `__pycache__` during normal operation.
