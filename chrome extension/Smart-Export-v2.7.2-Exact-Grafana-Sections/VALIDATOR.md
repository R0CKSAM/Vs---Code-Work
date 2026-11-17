# Parquet × Grafana validator (v2.7.4)

Open **Validate Parquet** at the top of the workspace. This uses the existing extension and its signed-in Grafana tab; no new extension permissions, credentials or server are required.

1. Select the sports property (or whole portfolio) from the prepared local reference.
2. Choose **Read saved reports** for an immediate historical comparison, or connect to the open Grafana tab and fetch one live report. Start with one date; live queries are limited to seven completed IST dates.
3. Review the selected date, dashboard URL/filters, required hosts and metric definitions. Click **Compare numbers**.
4. Inspect values, signed differences, percentage differences, ratios and explanations. Export the CSV and audit JSON.

Live capture reuses the validated fixed Grafana queries and the original filter checks. It never merges into or clears the existing report master, changes the dashboard filters, enables a schedule or accepts arbitrary SQL. Saved snapshots retain their original row update times. An import must be a validator snapshot/audit JSON; arbitrary Excel workbooks and raw Parquet uploads are not supported by this screen.

## What a result means

- **Within / outside tolerance:** numerical classification after the operator confirms scope and original build rules. These confirmations are recorded, not treated as automated evidence.
- **Scope / rules unverified:** both numbers exist, but the matching conditions have not been confirmed.
- **Definition mismatch:** known differences such as positive-TS users versus all-traffic IPs, six-second versus 0.6-second hours, or approximate/blank device ID handling. Confirmation does not override these flags.
- **No Parquet data / No Grafana value:** a date/group/value is absent. It is never silently treated as zero.

The percentage is `(Grafana - Parquet) / Parquet * 100`. A nonzero Grafana value against a zero Parquet baseline has no percentage; absolute difference is still shown. Daily and location distinct counts are never summed into period unique users. Only additive GEO playtime is rolled up across city rows to a country/state group. URL-escaped region names are normalized and their additive values combined.

## Metric definitions

The sponsor deck defines users as distinct client IPs on positive `raw_ts_requests` rows. Its estimated hours use `SUM(raw_ts_requests) * 0.6 / 3600`. Grafana's current fixed templates use six seconds, HTTP 200/206 and TS path/filename conditions. The validator shows the known tenfold formula gap and separately compares both sources using six seconds; its segment-count comparison also recalculates Grafana counts at 0.6 seconds.

The Parquet lacks HTTP status, request path, city, session IDs, bytes and player timestamps. It cannot prove equivalent server-side selection rules, manifest views, concurrent viewers, player watch time or ad impressions. Grafana's device/OS classification and approximate device counts are not automatically equivalent to the supplied labels. Host names are reused across properties; a host match alone is not an event mapping.

## Rebuild the private aggregate reference

From the workspace PowerShell terminal:

```powershell
& 'D:\Vs - Code Work\venv\Scripts\python.exe' `
  'D:\Vs - Code Work\SPORTS-PDF\build_grafana_reference.py' `
  --source 'Y:\Veto Logs Backup\Chinmoy\sports_all_dates_12_columns.parquet' `
  --output 'D:\Vs - Code Work\chrome extension\Smart-Export-v2.7.2-Exact-Grafana-Sections\validation-reference.json'
```

Reload the validator tab after rebuilding. `validation-reference.json` contains private aggregate business data and is ignored by Git. No raw IPs or device IDs are exported. The screen also accepts a reference JSON from another local path via its file picker.

## Validation performed

20 pure comparison checks, 36 production background checks, 23 filter checks, and 13 real Chrome UI checks at each of desktop and narrow widths. Covered formula differences, nulls/zero baselines, duplicates, stale inputs, CSV protection, encoded region rollups, filter checks, bounded live capture and no report-master writes. A fresh signed-in query for 25 October 2026 succeeded. Reports are saved in `Reports/Grafana_Parquet_Validation_20261117`.
