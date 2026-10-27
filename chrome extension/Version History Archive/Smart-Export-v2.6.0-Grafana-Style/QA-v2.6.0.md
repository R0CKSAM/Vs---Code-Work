# QA — v2.6.0

- **Existing reporting**: 16 core + 31 multi-report + 16 picker + 7 background + 26 duplicate-frame assertions passed (96 total).
- **CSV ZIP**: multiple UTF-8 CSVs, per-metric filenames, CRC/extraction passed with Python `zipfile`; duplicate filenames rejected.
- **Excel**: one valid worksheet per selected parameter plus Definitions; sheet names unique and length-constrained; generated XLSX ZIP and workbook XML parsed successfully.
- **Visual**: 1650×920, 1366×768, 768×930 and 390×844 rendered via Chromium `page.set_content`, no horizontal overflow or page errors. Main workspace uses full width, all six sections and 21 certified field choices render.
- **UI interaction**: metric search, section expansion, checkbox selection, 30-day date preset, CSV format selector, Results/Settings navigation passed under a mocked existing bridge. Footer does not cover all content; views hide correctly.
- **Data safety**: `Get data` is disabled until dates/selection/connection valid. Date or selection changes invalidate export readiness; exported master rows are sliced to requested date range.
- **Limitation**: The test environment blocked loading a local extension page via navigation (`ERR_BLOCKED_BY_ADMINISTRATOR`); browser rendering was tested with direct HTML/CSS injection and mocked Chrome/Grafana integration. Real signed-in Grafana query and persisted extension-ID behavior require a user-side smoke test.
