# Smart Export v1.0 — independent Grafana GEO data extension

Smart Export is **a separate Chrome MV3 extension**. It does not modify or share data with Smart Report or Smart Flow.

## Purpose

Export day-wise `Playtime by GEO` data for the **Sessions & Users Monitoring with Playtime Analytics** dashboard on TrafficPeak Grafana. Data is combined into one locally maintained master and exported as CSV or Excel.

Source dashboard verified from the Grafana JSON file provided by the project owner:
- Dashboard UID: `db7ce6f6-d689-4976-89e5-ddf0b5401f97`, org 743.
- Panel 20: `Playtime by GEO`.
- Datasource: Hydrolix, discoverable from the live dashboard (fallback UID from exported JSON).
- Underlying metric: `count() * 6 / 60.0` — **estimated playtime in minutes based on six-second segment requests**, not independently measured actual viewing minutes.
- Base filters: TS segment requests, status codes 200/206, valid segment path, nonempty state.

## Install

1. Extract the ZIP.
2. Open `chrome://extensions/`, turn on Developer mode.
3. Click **Load unpacked**, select the folder `smart-export-v1`.
4. Leave **Smart Report installed**; Smart Export is a separate app and needs no Microsoft or Google login.
5. Open and sign in to your existing Grafana dashboard in another Chrome tab.
6. Open the Smart Export toolbar icon and press **Use open Grafana tab**.
7. Choose a historic **IST** date range (ended yesterday or earlier), then press **Fetch & merge data**.
8. When rows appear, choose **Export Excel** (two sheets: GEO Daily + Daily Summary) or **Export CSV** (one daily master table).

## Automatic daily updates

Switch **Automatic daily update** ON. Chrome checks approximately hourly, and once it is past 08:00 IST it fetches the **last 3 completed IST days**, refreshing recent values without duplicates.

- Chrome must remain running, and the Grafana dashboard must stay open and logged in in a tab. The tab may be in the background.
- The extension cannot run when Chrome is closed or the computer is off.
- After long downtime, run a manual historical backfill.
- If data can't be retrieved (expired Grafana login, API denial, changed SQL), it **does not overwrite existing rows**, logs an error and retries at the next check.
- Only the local extension master is updated automatically. Chrome extensions do not have permission to silently modify an already downloaded Excel file. Export a new workbook whenever you need the latest combined file.

## Data format

| Date (IST) | Country | State | City | Playtime (minutes) |
| --- | --- | --- | --- | --- |
| 2026-10-01 | IN | Delhi | NEWDELHI | ... |
| 2026-10-01 | IN | Maharashtra | MUMBAI | ... |
| 2026-10-02 | IN | Delhi | NEWDELHI | ... |

For the same dashboard, Date + Country + State + City uniquely identifies a row; rerunning a date range replaces records in that range. The Excel **Daily Summary** tab includes formula-driven total minutes and day-over-day differences.

## Security / scope

- Permissions: `storage`, `alarms`, `tabs`, `scripting`, and host access **only** to `https://grafana-apj.trafficpeak.live/*`.
- All Grafana network queries happen inside the user's logged-in Grafana tab using that session. No Grafana password, cookies, or access token are copied to the extension or embedded in source code.
- Aggregated output is kept locally in IndexedDB. No third-party telemetry, analytics, or uploads.
- A saved or active Grafana URL containing nonempty `var-` filters is blocked. v1 does **not** silently ignore filters and export misleading data.
- Source SQL is pinned to the provided `Playtime by GEO` panel. If the panel's metric is changed, the extension pauses instead of silently continuing with old assumptions.
- Diagnostics are local; review before sharing.

## Troubleshooting

- **Open Grafana tab**: The extension can only query a tab displaying the configured dashboard.
- **401 / 403 / HTML response**: Sign in to Grafana again or ask your Grafana owner whether `/api/ds/query` and dashboard API requests are permitted to your role.
- **Panel SQL has changed**: Reverify metric definitions before exporting; do not assume the old calculation is still correct.
- **Ad-hoc filters**: Clear them in Grafana or request a filter-aware version of Smart Export.
- **Missing column / no data**: Download logs in Advanced & Support; contact Smarth.

## Test status

- JS syntax checked; core logic tests for dates, aggregation, CSV protections, and XLSX generation passed.
- Generated XLSX was validated structurally (ZIP and worksheet XML).
- Actual popup layout was rendered and checked at 540 px, including expanded advanced settings and button boundaries.
- **NOT VERIFIED:** Live Grafana `/api/ds/query` response using the organization's credentials, and the Chrome alarm's real scheduled execution. The environment used to build Smart Export cannot access your private Grafana session, and automated loading of an unpacked extension was blocked. Please run a first manual sync in your browser before enabling daily mode.

## Sources for APIs

- Grafana data query API: https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/
- Hydrolix plugin documentation: https://grafana.com/grafana/plugins/hydrolix-hydrolix-datasource/
- Chrome Extension alarms and storage: https://developer.chrome.com/docs/extensions/reference/api/alarms
