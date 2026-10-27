# v2.7.1 Audit — Grafana Panel Parity

## Source of truth

The user's exported Grafana v2 Dashboard JSON supplied with the conversation. A minimal position/title fixture is included under `tests/source-kpi-layout.json` so the checks are reproducible without the private full dashboard export.

## Completed checks

- 10 source panels mapped to exact Grafana panel IDs, titles and x/y positions: 9 × 8-column cards, then Panel 11 at 24-column width.
- Four newly mapped KPI definitions reviewed against original source SQL and converted to daily IST grouping.
- All six original report categories and the existing report store retained.
- Existing data tests: Core (16), v2 analytics (33), Picker (16), background (7), duplicate-frame (26) and tab-navigation checks passed.
- New source-parity test passed: source map, KPI query, selected CSV, per-metric Excel, stale-data rejection.
- Browser-rendered UI with simulated (not live) Grafana state passed at 1919px, 1650px, 1366px, 768px and 390px.
- Search, individual checkbox selection, complete/partial composite checkbox and selection persistence passed.
- No horizontal overflow in tested viewports. Full-width table spans the three-column KPI grid.
- JavaScript syntax, generated XLSX package, and DoD formula column references verified.

## Still to verify in the user's signed-in Chrome

1. The live Grafana Hydrolix datasource accepts the extended KPI SQL (particularly the device/session subquery).
2. KPI values for a *single completed calendar day* match original Grafana panels.
3. New values remain available after restarting Chrome and exporting a fresh workbook.

Only a passed local automated suite is claimed. The live authenticated Grafana response was not captured in this development environment.
