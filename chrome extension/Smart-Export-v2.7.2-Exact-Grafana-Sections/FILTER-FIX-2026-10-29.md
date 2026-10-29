# Grafana filtered exports — v2.7.3

The URL parser explicitly rejected every nonempty `var-filter` parameter. Both the connection picker and report source validation used that parser, so applying a normal Grafana filter made the dashboard appear unavailable. Fixed queries also omitted the native ad hoc filter macro and payload.

## Resulting behavior

- Parse repeated `var-filter=key|operator|value` parameters, Grafana escaped delimiters/display labels, comparison/wildcard operators, empty values, and multi-value operators. Unsupported syntax and other template-variable overrides fail with a specific message.
- Pass structured filters to the native Hydrolix query `filters` property. Add `$__adHocFilter()` to every base-table scan, including all KPI CTE scans. Values are not concatenated into SQL. Unfiltered SQL stays unchanged.
- Derive dataset identity from canonical filter contents, independent of date range, query-error metadata or parameter order. Existing `filters=none` records retain their keys.
- Get data refreshes the source from the actual open Grafana tab. Connection status displays active filter count. Recheck organization and filter URL parameters immediately before submitting a query; a changed tab scope rejects the request before saving data.
- Source/filter changes pause the prior schedule and clear V2 completion markers. Scheduled work still requires a tab matching its saved selection.
- Preserve the folder name and upgrade manifest/UI to 2.7.3. Reload the extension and reopen the workspace to refresh both the worker and UI modules.

## Verification

- Full audit runner: 10 suites, zero failures, including 23 dedicated filter checks and 30 production background checks exercising actual injected functions with synthetic requests.
- Real Chrome UI: 78 checks at each of two viewport sizes. Changing the live filter without reopening the workspace reaches the next Get data request. Cached export/download does not refetch.
- Real IndexedDB: 13 existing transaction/storage checks pass.
- Live acceptance in the separate `SmartExportLiveAudit` Chrome profile: organization 743, date 2026-10-26, `country = AU`, GEO report. Actual extension connection/save/fetch produced four rows, all country AU, under the filtered dataset key.
- Independently executed the original Grafana panel 20 SQL with the same dates and native filter. All four country/state/city/playtime records exactly matched the extension output.
- Restored the test profile configuration and closed its headless browser. The normal Chrome profile was not used for this acceptance run.

Live acceptance covers the equality filter and GEO end to end. Other filter operators and report templates have request/parser/SQL coverage; they were not individually queried against the live lake.

## Protocol references

- [Grafana dashboard URL variables](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard-url-variables/)
- [Grafana URL filter serialization](https://github.com/grafana/scenes/blob/main/packages/scenes/src/variables/adhoc/AdHocFiltersVariableUrlSyncHandler.ts)
- [Hydrolix structured filters and template handling](https://github.com/hydrolix/grafana-datasource-plugin/blob/main/src/datasource.ts)
- [Hydrolix native ad hoc filter macro](https://github.com/hydrolix/grafana-datasource-plugin/blob/main/pkg/plugin/macros_adhoc.go)
