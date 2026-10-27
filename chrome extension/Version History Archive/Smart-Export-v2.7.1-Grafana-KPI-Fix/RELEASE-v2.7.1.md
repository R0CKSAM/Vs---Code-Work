# Smart Export v2.7.1 — Grafana KPI Layout & Export Fix

## What is fixed

`Session and Users Stats` now contains the **exact nine KPI panel slots**, ordered by the supplied Grafana dashboard export, followed by `Total Unique IPs & Session` spanning all three columns. The cards retain the production checkbox selection logic and use the source Grafana titles.

| Row / columns | Grafana panel IDs | Layout |
|---|---|---|
| 1 / 3 cards | 2, 1, 8 | Device-based users; session-ID sessions; unique IPs |
| 2 / 3 cards | 6, 7, 12 | New users; returning users; IP + UA sessions |
| 3 / 3 cards | 5, 41, 49 | Manifest views; session duration; average watch time |
| 4 / full width | 11 | Total Unique IPs & Session (`unique_cliIP` and `unique_session`) |

## Working data bindings

Four additional **daily** KPI fields are now produced from the source Grafana SQL definitions:

- `new_users`: count of device IDs with exactly one unique session ID during that IST day (source panel 6).
- `returning_users`: count of device IDs with more than one unique session ID during that IST day (source panel 7).
- `session_hours`: six-second TS segment estimate divided by 3600 (source panel 41).
- `avg_watch_minutes_per_user`: matching TS segment estimate divided by distinct IPs, restricted to valid `channel_name` values (source panel 49).

Existing fields, API calls, saved master database and export logic remain intact. Added source SQL guards stop if any of the newly mapped panels no longer have the expected definitions. The source panel 11 is a *two-column table*, not a new additive audience metric. Its checkbox selects `unique_ips` and `ip_ua_sessions` together; those remain separate selectable/exportable numeric measures and produce separate Excel/CSV outputs. Mixed/partial checkbox state is visible when only one field is selected.

**Important:** a multi-day Grafana stat recalculated over an entire window may differ from any sum of daily unique counts. Smart Export still produces daily groups and never labels their sum as unique users for the entire multi-day period. New/returning values represent *within-day session frequency*, not registration cohorts.

## Upgrade and testing

1. Back up and download your existing workbook from v2.7.0.
2. Extract this ZIP; copy files into the **same unpacked Smart Export extension folder**. Don't uninstall: that could affect locally saved data.
3. Open `chrome://extensions/`, then Reload Smart Export.
4. Open signed-in Grafana, choose one completed IST date, select the KPI section and click **Get data**.
5. Validate each exported KPI against Grafana's panel for the same single-day range. If the source query has changed, the extension stops with an error instead of silently substituting values.

Historical v2.7 KPI records lack the four new fields. Select **Get data** again to refresh the chosen date range before exporting the new metrics. The Excel/CSV writers will refuse missing fields rather than export blank values.

**Remaining limitation:** the Time Series section still exports validated *hourly* metrics; Grafana's separate per-minute and five-minute chart queries are not implemented in the current six-dataset engine. They are intentionally labeled hourly so that no false panel equivalence is claimed. Live production Grafana extraction was not available in the test environment.
