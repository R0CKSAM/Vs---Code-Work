# RevenueLive source delivery

Source delivery is now through a reviewed Git commit. Use
`PRODUCTION-HANDOFF.md` for repository boundaries, Windows host setup, backup,
and update steps. ZIP and executable handoff scripts are retained only as
owner-side legacy tools; they are not part of the production Git workflow.

Do not commit or sync `data/`, `backups/`, `logs/`, `.venv/`, `.tools/`, local
mail configuration, credentials, or archived development material. The current
shared monorepo still tracks `notneeded/`, so a dedicated private production
repository is preferred over granting broad access to this remote.
