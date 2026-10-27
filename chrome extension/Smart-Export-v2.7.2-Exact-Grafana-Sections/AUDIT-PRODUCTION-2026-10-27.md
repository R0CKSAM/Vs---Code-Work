# Smart Export 2.7.2 production audit — 27 October 2026

Status: automated and bounded live acceptance checks pass for the cases described below. A real Chrome alarm refresh was verified in an isolated profile. These results do not guarantee the absence of all future bugs or establish that every selectable metric was queried live.

## Changes verified

| Area | Result |
| --- | --- |
| Grafana requests | Live source definitions are validated before submitting SQL. Dashboard inspection has a 15-second timeout, queries a 90-second timeout. Large multi-panel requests stop starting further queries after three minutes. Organization headers are supplied to dashboard inspection and queries, and matching tabs are selected by organization and dashboard. |
| Failed requests | Login errors, non-JSON responses, timeouts and changed source definitions stop the update. Existing saved reports are retained. A multi-section fetch commits only after all requested sections succeed. |
| Storage and concurrency | Failed initial activity writes release the fetch lock. Config writes are serialized; changing the source or enabling a schedule during a fetch is blocked. Clearing reports and fetching cannot run together. Failed IndexedDB insertions roll back the full replacement transaction. |
| Saved reports | Missing dates, duplicate identities and empty replacement batches are rejected. Report values cannot overwrite stored dashboard identities. Other dates, sections and dashboards remain isolated. |
| Missing values | Null measurements stay null; downloads render blank cells. Empty city/state values are allowed. Real zero values remain numeric zero. Duplicate conflicting Grafana groups are rejected. |
| Preview and download | Preview, counts and export use the selected dates. Cached reports can be downloaded without another fetch. Duplicate download clicks are ignored. Individual CSV mode consistently produces a ZIP, including a single metric. |
| Excel | Bold black headers on a light fill, wrapping, a standard Normal style, and preserved formulas. Missing KPI measurements do not calculate a misleading day-over-day change. |
| Settings | Saved selections update visible panels. Empty selections do not prevent pausing an existing schedule. Panel mapping can be inspected without selecting a report. Saving/replacing selections is transactional and actions are locked while saving. |
| Notifications | Visible progress, readable dark-theme colors, accessible error announcements, error help, dismiss buttons, and persistent warnings/errors. Success notices dismiss after seven seconds unless hovered or focused. Reduced-motion preferences are respected. |
| Navigation | Builder-only footer; one output-format selector on Preview. Selection counters exclude hidden legacy metrics. Keyboard navigation, launcher click guards, dynamic version display and startup preference-error reporting are included. |
| Background status | An activity/badge/log failure after a committed update does not falsely claim the data was lost. Activity events do not repeatedly reload the complete stored dataset. Stale overlapping state refreshes cannot replace newer UI state. |

## Verification completed

- Nine Node regression suites pass, including original core/query/picker/source-panel/navigation/duplicate-frame tests and 21 new background checks.
- Browser UI: 74 checks at each of two viewport sizes (148 checks), plus a separate real-time browser run for visual inspection.
- Real IndexedDB: 13 checks cover date replacement, dashboard/section isolation, invalid input rejection, transaction rollback after a DataCloneError, identity protection and clearing one dashboard.
- Export regressions: 17 browser checks and inspection of three actual XLSX files with an independent Excel reader. Headers, retained rows, blanks, numeric zeros and formulas pass.
- JavaScript syntax and Git whitespace checks pass.

The tests use isolated browser profiles, synthetic records and mocked Chrome/Grafana APIs. The IndexedDB tests use actual browser storage. No employee sessions or production data were cleared, and no live daily schedule was enabled by the tests.

Run the regression suites with Node 22 or newer:

```powershell
node .\tests\run-audit.mjs
```

Run the UI and real browser-storage checks with Python 3, Chrome and Node installed:

```powershell
python .\tests\test-settings-browser.py --chrome "C:\Program Files\Google\Chrome\Application\chrome.exe" --node "PATH_TO_NODE_EXE"
```

The local verified portable runtime used for this audit is `D:\Vs - Code Work\.tmp\node-runtime\node.exe`; it is not a runtime dependency of the extension. The regression runner redirects generated workbook fixtures into a temporary directory.

## Live acceptance completed — 27 October 2026

Tests ran in a separate visible Chrome profile at `C:\Users\Intern\AppData\Local\SmartExportLiveAudit\ChromeProfile`, with the actual unpacked extension, actual Grafana session access, actual IndexedDB, real browser downloads and actual Chrome alarms. The employee's normal Chrome profile was not automated or signed out.

The live test discovered and fixed a real SQL formatting defect: `%M` produced a month name (`2026-10-26 00:October`) instead of minute digits. The SQL now uses `%i` for all one-minute, five-minute and viewership-minute time labels. The regression suite checks this format explicitly. Strict timestamp validation remains enabled.

| Live check for 26 October 2026 IST | Result |
| --- | --- |
| Live Grafana panel mapping | All 34 panels found and mapped. |
| Three-category fetch | 1,544 rows stored: 103 GEO groups, 1,440 device-ID minute buckets, one viewership summary. |
| Independent source-panel comparison | Re-ran original Grafana panel SQL with the same one-day time bounds and resolved macros. All 103 GEO groups/values, all 1,440 minute timestamps/values and the viewership-hours value matched. Source panels 20, 4 and 13 were compared. |
| GEO total | 1,013,816.7 minutes, equal between original source SQL and export. |
| Viewership summary | 16,973.98 hours, equal between original source SQL and export. |
| Additional series | Five-minute device series returned 288 valid buckets. Viewership-minute series returned 1,440 valid buckets. |
| Actual Excel download | Browser confirmed file completion. Independent reader verified all 1,544 selected rows, blank dimensions, numeric values, dates and bold black headers on a light fill. |
| Actual Individual CSV ZIP download | Browser confirmed file completion. Three CSV members, intact ZIP CRCs, all 1,544 rows matched stored records. |
| Expired-session error handling | A controlled HTTP 401 response was injected only for the isolated Grafana tab's query endpoint. The extension showed the 401, preserved 103 existing GEO rows and successfully fetched again after interception was removed. This was a simulated expired-session response, not a real account logout. |
| Actual Chrome alarm | Temporarily configured the isolated profile for one completed day and an already-due schedule, then let `chrome.alarms` fire. It fetched and saved 103 GEO rows and recorded the completion date. |
| Repeat alarm | A second actual alarm retained the same success timestamp and did not repeat the completed day's refresh. |
| Schedule cleanup | Test-profile daily updates were paused afterward; standard 8 AM IST / three-day defaults and the hourly alarm were restored. The employee profile's schedule was unchanged. |

Live artifacts and independent verification results are saved under `D:\Vs - Code Work\Smart-Export-Live-Audit-20261027`.

The first automated download attempt used a forward-slash Windows download path and was canceled by Chrome. Retrying with a native Windows path completed both actual downloads. This was a test-harness path issue. These download failures are retained in the diagnostic attempt history; the completed file checks above use the subsequent successful downloads.

### Remaining rollout observation

The scheduled refresh was exercised through a real alarm with a temporary due time, not by waiting overnight for the normal 8 AM window. Browser restart, sleep/resume, organizational session expiry and source changes should still be observed in normal use. A real sign-out was not performed because account logout can affect other organizational applications; controlled 401 recovery was tested instead.

For a release owner repeating acceptance in their regular profile:

1. Reload the same unpacked extension folder in Chrome and close/reopen its workspace tab. Keep the authenticated Grafana dashboard open in the correct organization.
2. Fetch a known completed IST day for a GEO panel, a time-series panel and a viewership panel. Compare values, timestamps and grouping with Grafana.
3. Download Excel and Individual CSV files. Confirm blank locations, dates, numeric values, header readability and worksheet/file names.
4. Test an expired Grafana login and then reconnect. Confirm the failed fetch preserves saved data and that a cached download remains available for dates already stored.
5. Enable daily updates for an approved selection. Verify one real refresh after the configured IST hour with Chrome running, then confirm the next hourly alarm does not repeat that completed day's job.

Daily updates refresh local saved data; they do not automatically download reports or send emails. Chrome must be running, and the signed-in Grafana tab must remain available. Server-side outages, source-dashboard changes and Chrome service-worker suspension remain external runtime conditions; visible errors and bounded requests handle them without certifying successful delivery.
