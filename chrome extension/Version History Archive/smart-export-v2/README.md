# Smart Export v2.0 — Grafana Analytics Suite

Standalone Chrome Manifest V3 extension. **Not integrated into Smart Report or Smart Flow.**

## New in v2

Select a report and export a growing local Excel master:

| Choice | Excel sheet | Source Grafana panels |
|---|---|---|
| Executive Workbook | Six sheets below + Definitions | Combined |
| Daily KPIs | Daily KPIs | 2, 1, 8, 12, 5, 41, 15 |
| Channel Performance | Channel Performance | 34, 68 |
| GEO Performance | GEO Performance | 20 |
| Device & OS | Device and OS | 58, 55 |
| Popular Content | Popular Content | 27 |
| Traffic Trends | Traffic Trends | 9, 38, 3, 15 |

The Executive workbook exports **seven sheets**: Daily KPIs, Channel Performance, GEO Performance, Device and OS, Popular Content, Traffic Trends, Definitions. Daily KPIs includes formula-based day-on-day percentage changes when two recorded dates are consecutive.

### Data meaning
- Playtime is a **six-second segment-request estimate**, not verified player watch time.
- Views use the dashboard's master manifest URL request pattern; not unique starts.
- Unique device IDs, IPs and session IDs are distinct *within each date/group*. Do **not** add daily counts to claim monthly uniques.
- Channel unique IPs use traffic for each channel, while channel playtime is based on valid TS segments.
- Device categories are derived from User Agent CASE rules in source panels 58 and 55.
- Geography uses decoded country/state/city dimensions. Content titles are extracted from manifest query strings.
- Time zone is Asia/Kolkata for date/hour grouping.
- Ad-hoc Grafana filters are **not supported**. The extension rejects a saved/live filtered URL instead of exporting misleading unfiltered results.

## Install
1. Extract ZIP and load `smart-export-v2` from **Chrome → chrome://extensions → Developer mode → Load unpacked**.
2. Keep the Grafana dashboard at `grafana-apj.trafficpeak.live` open and signed in.
3. Open Smart Export → choose **GEO Performance** for the first smoke test, select 2–3 completed IST dates, click **Fetch & merge data**.
4. Compare a day against Grafana Inspect data, then export Excel or CSV.
5. If that works, select **Executive Workbook**, select 2–3 completed days, and fetch. It makes six Grafana requests sequentially and merges only if all six succeed.
6. Enable Daily updates only after verifying your numbers. Default: around 8 AM IST (Chrome + the signed-in Grafana tab must remain open). The latest three completed dates are re-queried to capture late data.

### Existing v1 data
The original v1 GEO IndexedDB remains **untouched** and is imported into the new v2 master once when the v2 popup first opens. Fetching GEO in v2 also updates the legacy GEO master as a best-effort compatibility mirror. Existing v1 nightly GEO jobs remain unchanged until you enable the new v2 daily schedule.

### Export limits
- Completed IST dates only. Max 366 days for single reports; **31 days per Executive fetch**.
- 80,000 rows maximum per individual report query and 120,000 records per atomic merge or workbook.
- Full Executive CSV is deliberately disabled; choose one report for a tabular CSV.
- The master is saved to **local Chrome IndexedDB**. Downloading Excel creates a snapshot. The extension does not overwrite downloaded files automatically or upload data to a server.
- When any requested report fails or returns no rows, that fetch **does not merge any of its results**. Existing history remains intact.
- The daily scheduler may miss runs if Chrome/Grafana is closed. Use the historical date range to backfill.

## Permissions & privacy
Only permissions: `storage`, `alarms`, `tabs`, `scripting`, and host access to the specific Grafana domain. SQL is built from fixed report templates, and the query runs inside the authenticated Grafana tab. No passwords or Grafana tokens are stored, and no external analytics service is contacted.

## Troubleshooting
Open **Advanced & support → Export error logs**. Verify source panel IDs still match the approved dashboard. The source may have changed after this build. When errors occur, contact **Smarth** for support.

## Test boundaries
Passed: pure query/parser tests; workbook ZIP/XML and Excel import; Chromium-rendered popup overflow/dropdown checks. **Live authenticated Hydrolix query and installed-extension service worker cycle were not verified in this environment** due to browser policy restrictions. Complete the 3-day GEO accuracy smoke test before production.
