# Smart Export v2.6.0 — Grafana-Style Parameter Exporter

A **standalone Chrome extension**. This replaces the v2.5.x Parameter Studio UI with a simpler, Grafana-ordered workspace. It does NOT modify the separate Smart Report screenshot/email extension.

## In this release

- Grafana-inspired dark header and breadcrumbs. **Date range lives in the header**, with Yesterday, Last 7 Days and Last 30 Days, always using **completed Asia/Kolkata days**. The existing query limit is 31 days per multi-report fetch. Custom dates are entered directly.
- Supported metrics appear in roughly the dashboard's section order: Session and Users Stats; Users/Sessions/Views Time Series; Viewership Trend; Popular Content; Playtime GEO; and Devices/OS.
- No fake charts, unsupported disabled checkboxes, arbitrary breakdown selector, or duplicate large selection panel. The selection count appears in the bottom bar.
- Two export modes: **Excel** (one worksheet per selected parameter, plus Definitions), or **CSV** (one CSV per selected parameter, bundled into one ZIP when several are selected).
- The existing Grafana background query, authenticated tab binding, transactional IndexedDB master, duplicate-frame safeguards, date/query limits, saved views, daily updates, CSV formula injection protection, and data tables are retained.
- The output is **date-bounded**: exports use the dates currently selected in the header and require a new successful fetch after selection or date changes.
- Selected metrics and custom valid dates are stored locally. No credentials are saved in UI source code.

## Install or upgrade

1. Stop any daily updater and back up the existing Smart Export extension directory and downloaded master Excel files.
2. Extract this ZIP. Copy its files into **the same unpacked extension directory** currently installed (to preserve the unpacked extension ID and stored data). Do not install a second copy on top of the old copy.
3. Open `chrome://extensions/` and click **Reload** on Smart Export.
4. Open your authenticated TrafficPeak Grafana dashboard. The extension icon opens a small launcher; click **Open Smart Export Workspace**.
5. Choose dates in the top bar; choose the metric cards you need; choose Excel or CSV files; click **Get data**; inspect the actual results and click **Download**.
6. Validate one 2-day export against Grafana before enabling automated daily updates.

## Important functional boundaries

- Supports only the six previously verified dataset families and 21 metric choices. More dashboard panels exist, but unmapped queries (e.g., first-time users, returning-user history, specific per-minute cumulative series) are deliberately **not displayed** as working exports.
- The source is restricted to the configured TrafficPeak Grafana dashboard UID. A nonempty Grafana ad-hoc filter cannot be reproduced safely; it is blocked with an explanation.
- Date grouping comes from the validated dataset itself: daily for most reports and hourly for traffic. Arbitrary cross-category joins are **not** created. Unique daily audience figures are not summed into range-wide unique users.
- CSVs are downloaded in a ZIP when there are multiple selected metrics; this avoids Chrome multi-download prompts and keeps the files together.
- Chrome and the signed-in Grafana browser session must remain available for scheduled daily updates.
- The saved master inside IndexedDB is left untouched by exports. The exported file is a date-bounded snapshot.

## Technical overview

- `workspace.html` + `grafana-simplified.css` + `grafana-simplified.mjs`: new full-page interface.
- `popup.mjs`: legacy certified export controller and bridge, extended for metric-by-metric output and date-bounded export.
- `multi-xlsx.mjs`: optional one-worksheet-per-metric mode without affecting legacy group-sheet callers.
- `csv-zip.mjs`: local, standards-compliant ZIP32 archive writer with duplicate-name and size safeguards.
- `background.mjs`, `reports.mjs`, `core.mjs`, `report-db.mjs`: original query/storage modules (not replaced).

## Verification status

Static syntax checks, existing analytics tests, mock-browser UI tests at desktop/tablet/mobile widths, ZIP extraction with CRC, and Excel workbook XML checks passed. **Live authenticated Grafana data fetching has not been verified from this environment.** Validate on your actual dashboard before broad deployment.
