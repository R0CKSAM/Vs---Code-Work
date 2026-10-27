# Smart Export v2.7.0 UI / Code Audit

## Scope

Compared the actual Smart Export v2.6 package against the reference Grafana exported dashboard configuration, then changed only selector UI, panel presentation, navigation labels, and package version. Core authenticated Grafana queries, data merges, Excel/CSV generators, and stored data keys were retained.

## Verified automated tests

- `tests/test-core.mjs`: 16 assertions passed.
- `tests/test-v2.mjs`: 31 assertions passed.
- `tests/test-picker.mjs`: 16 assertions passed.
- `tests/test-picker-background.mjs`: 7 assertions passed.
- `tests/test-v23-tab-nav.mjs`: passed.
- `tests/test-v24-duplicate-recovery.mjs`: 26 assertions passed.
- `qa_smart_export_270.py`: rendered UI at 1919, 1650, 1440, 1366, 1024, 768, and 390 px; no document horizontal overflow and zero JavaScript page errors in mocked-browser runs. Validated 21 mapped panels, search, select-visible, metric removal, date presets, background fetch handoff, export format, and navigation.

## Explicit boundaries

- The UI uses true names where they correspond to certified data fields. The current engine cannot export all 34+ raw Grafana panels verbatim. Minute and five-minute time series, independently grouped platform-only versus OS-only exports, GEO unique IPs, and authentic new/returning-user measures are not offered as separate buttons.
- Browser tests used mocked Grafana responses, not a live authenticated request.
- A signed-in user should compare the exported results for two complete dates to the relevant Grafana data before production deployment.
