# Smart Export v2.0 — Release test report

## Automated tests performed

- JavaScript syntax: checked all module files using `node --check`.
- Original v1 GEO helper assertions: 15 passed.
- V2 report/query and data parser assertions: 30 passed.
- Verified every source-panel assertion against the supplied Grafana dashboard JSON definition.
- Generated Executive XLSX: ZIP integrity and XML well-formed; all 7 sheets successfully imported with `artifact_tool`.
- Chromium DOM/CSS rendering tests using a simulated popup: 450px, 360px, expanded Advanced, 600-character URLs, 800-character unbroken error messages; no horizontal overflow. Select-chevron centered.
- Full installed-extension test with mocked Grafana endpoint **blocked by the Chromium environment** before extension service worker boot. Not counted as passed.
- Actual authenticated Grafana/Hydrolix query and automatic daily scheduler: **not executed**. Requires a live employee login and test against known dashboard values.

## Manual acceptance checklist
1. Update in the same unpacked extension folder; make a backup first.
2. Open correct signed-in Grafana dashboard with no ad-hoc filters.
3. GEO export for 3 completed IST days; cross-check against Grafana Inspect.
4. Executive export for same 3 days; verify all six tabs and explanations.
5. Re-export same dates; verify no duplicate rows.
6. Check long source URL and dropdown remain aligned.
7. Test daily schedule once with Chrome running and the dashboard tab open.
8. Export diagnostic JSON; check it does not include personal data before sharing.

Do not distribute as fully production verified until live Grafana query and scheduled reconciliation checks pass.
