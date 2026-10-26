# Smart Export v1 — local audit

**Passed**
- JavaScript syntax: `node --check` for all `.mjs` modules.
- Core assertions (15): domain/UID validation, unsupported filters blocked, IST midnight boundaries, recent-date presets, aggregation SQL shape, Grafana dataframe parser, range errors, duplicate groups, CSV formula injection prevention, XLSX construction.
- Spreadsheet structure: generated XLSX ZIP passed integrity and XML parse of all worksheet/relationship parts. XLSX includes GEO Daily, formula-driven Daily Summary, freeze header, filters, numeric formatting.
- UI: 540px actual HTML/CSS rendering in Chromium via `set_content`, both collapsed and expanded settings; every button inside horizontal bounds.
- No Chrome-extension network permission outside TrafficPeak Grafana.

**Not yet verified in a signed-in Chrome extension:**
- Grafana Hydrolix plugin acceptance of the new date-aware SQL through `/api/ds/query`.
- Background alarm after browser restart, and 8am IST job timing.
- Real Excel opening in Microsoft Excel or Google Sheets (structure checked with XML parser only).

**Important limitation:** Chrome's extension loading was blocked by browser policy in the test container; the page-rendering checks are not an end-to-end installed-extension test.
