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

Copy `.env.example` to an ignored `.env` on each host and change configuration
there. Never commit `.env`, database credentials, SMTP credentials, runtime
data, uploads, backups, logs, `.venv/`, `.tools/`, or archived development
material. Prefer a dedicated private RevenueLive repository over sharing the
existing monorepo and its unrelated history.
