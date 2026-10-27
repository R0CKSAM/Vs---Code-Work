# Smart Export v2.4.0 — Horizon Workspace

A full-browser-tab analytics exporter for the TrafficPeak Grafana dashboard. This is a **separate Chrome extension** from Smart Report and Smart Flow.

## What's new

- Full-viewport desktop studio with a persistent left navigation rail and a fixed action bar. The whole document doesn't scroll on desktop; large metric lists/tables have their own scroll containers.
- Brighter icy-white/cyan/violet design, readable typography, responsive tablet widths, purposeful button colors, and consistent select/accordion chevrons.
- Metric builder, preview/export and automation settings remain fully functional. Quick Picks, 21 metric selections, saved views, date ranges, daily updates, download CSV/XLSX and Back to Grafana are all preserved.
- Robust handling for duplicate Grafana data frames: **exact duplicate groups are safely collapsed**, while **conflicting duplicate metrics are rejected**. Unreliable data is never silently added, averaged, overwritten or saved.
- If an error occurs, the notification has a **Troubleshoot** button taking the user directly to the existing downloadable diagnostics. Repeated identical groups are also counted in warning logs.

## Install or upgrade

1. Pause any existing Smart Export daily job. Export a backup workbook from your current Smart Export before updating.
2. Extract the ZIP archive.
3. To preserve existing local data and extension identity, **replace the contents of the existing installed Smart Export folder** with the contents of `Smart-Export-v2.4.0-Full-Screen`, then open `chrome://extensions/` and click **Reload**. Do not uninstall and reinstall unless you are willing to reconfigure local data.
4. Click the toolbar icon → **Open Smart Export Workspace**. It opens a full tab. Keep a signed-in Grafana dashboard tab open.
5. Choose a template, category, and dates; use **Use open tab**, then **Fetch data**, review the Preview screen, and **Download Excel**.
6. Compare the first two or three dates with Grafana before enabling daily refresh.

**Required source**: the configured TrafficPeak dashboard, authorized logged-in Chrome session. The queries do not support active ad hoc Grafana filters. The extension will block such filters rather than silently export a different result.

## What “Duplicate content group” means now

The previous parser threw an error whenever two Grafana frames included the same date/content grouping. Grafana can return multiple frames for a query. Smart Export v2.4.0 compares the metrics of duplicated groups:

- **Exact match:** retain a single row and add a warning log with the duplicate count.
- **Different metrics:** stop before the database transaction and show the conflicting group/columns and a troubleshooting link. This is intentional: summing unique IPs or distinct sessions would produce inaccurate numbers.
- **Distinct group:** preserve both groups. Never remove legitimate content titles, cities or hours just because they share a date.

No raw Grafana session credentials or access tokens are exported in log downloads.

## Known limitations

- Tested with simulated Grafana frame responses; querying your live authenticated Hydrolix dashboard still needs an in-browser test.
- For desktop screens, the browser window is fully used; metric and table sections scroll internally when necessary. At tablet/mobile widths the active content screen may scroll vertically to keep controls legible.
- Daily scheduling requires Chrome to be running, Grafana signed in, and the dashboard tab not discarded.
- If duplicate rows for the same group contain conflicting values, an accurate total cannot be inferred from those partial results. Review/repair the upstream query or send sanitized diagnostics to Smarth.

**Support:** Please contact Smarth for support. From Settings → Advanced tools, download error logs.
