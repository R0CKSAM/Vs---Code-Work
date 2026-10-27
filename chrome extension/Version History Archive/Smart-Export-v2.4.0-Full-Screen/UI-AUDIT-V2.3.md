# Smart Export v2.3 — UI and workflow audit

## Supported layouts
- 1440×900: two-column report builder; wide results preview; no horizontal overflow.
- 900×900: single-column builder, responsive navigation; no horizontal overflow.
- 600×850: compact controls; no horizontal overflow.
- 390×780: narrow mobile-style tab; no horizontal overflow.
- 356px launcher: stable width, no clipped controls.

## Verified interactions (mock Grafana/Chrome)
- Default selection and preset switching.
- Metric search and clear, cross-group searching.
- Fetch selected data, show preview, download actual valid XLSX.
- Saved views and panel explorer.
- Workspace tabs and no duplicate navigation IDs.
- Large input URLs, expanded settings, 21 selections and extreme feedback messages.
- Launcher tab management: reuse workspace, locate Grafana and open saved URL as fallback.

## Existing engine preserved
- `background.mjs` Grafana/Hydrolix query and daily scheduling unchanged except `CURRENT_GRAFANA_TAB` discovery, which now works when the workspace is the active tab.
- `database.mjs`, `report-db.mjs`, `reports.mjs`, `metric-catalog.mjs`, `xlsx.mjs`, `multi-xlsx.mjs` unchanged.
- Existing data stored in Chrome IndexedDB, same keys.

## Known limits
- Live authenticated Chrome extension query and browser service worker not exercised in this environment.
- A full-page extension tab, not a hosted remote web application. Chrome must remain open for daily schedules.
- Queries limited to the dashboard's verified datasets. Excel distinct-user metrics are not summed across days and called monthly unique users.
