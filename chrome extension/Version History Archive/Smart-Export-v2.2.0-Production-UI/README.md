# Smart Export 2.2.0 — Production UI Release Candidate

An independent Chrome Manifest V3 extension for exporting **day-wise Grafana/Hydrolix analytics** as Excel or CSV. This release **redesigns the popup** while retaining the tested v2.1.1 data engine, report catalog, storage, Chrome host permissions, SQL templates, and scheduler.

## Installation / upgrade — preserve your data

1. Pause any automated daily updates and make a backup of your existing extension folder.
2. Unzip `Smart-Export-v2.2.0-Production-UI.zip`.
3. **Recommended upgrade:** Copy its contents into the **same folder already loaded as Smart Export** (overwrite the old files). Don't uninstall the existing extension.
4. At `chrome://extensions/`, press **Reload** on Smart Export and reopen its popup. The Chrome extension ID and IndexedDB dataset should remain the same when updating files in place.
5. If installing fresh instead, enable Developer mode → **Load unpacked** → choose the extracted `Smart-Export-v2.2.0-Production-UI` directory. Fresh installs use separate extension storage unless the ID stays the same.

## What's different for employees

- **Choose data:** Begin with six ready-made report templates, or select a category and individual metrics. Search across all categories. No nesting/closing accordion controls.
- **Preview & export:** Check counts, use an optional one-category filter, preview sample rows, and download Excel/CSV.
- **Settings:** Daily update toggle, saved metric combinations, panel discovery, advanced tools, and downloadable diagnostics.
- **Persistent actions:** Fetch and Excel buttons remain visible at the bottom. The current screen is remembered.
- **Safe datasets:** Fields with incompatible dimensions are exported on different Excel tabs. IPs, device IDs, and sessions are not presented as interchangeable or additive across dates.

## Supported data

This build uses the same six supported report datasets as v2.1.1: Daily KPIs, Channel, GEO, Devices, Popular Content, and Traffic. Excel output uses the original validated workbook writer; data is stored in local Chrome IndexedDB. Existing automatic daily reconciliation remains opt-in.

**Limitations:** The extension is configured for your Grafana host and known Hydrolix data source. Unmapped panels are visible for discovery but cannot be queried without a validated mapping. Grafana ad-hoc filters are not silently applied. Chrome must remain open and authenticated for scheduled updates. The extension does not overwrite previously downloaded Excel files.

## Acceptance test on your actual dashboard

1. Open and sign in to `grafana-apj.trafficpeak.live`.
2. Open Smart Export, press **Use open tab**, choose **Audience locations**, set two completed IST dates, then **Fetch data**.
3. On **Preview & export**, compare sample GEO playtime with **Grafana → Inspect → Data**, then export Excel.
4. Open the XLSX and confirm Country, State, City, Date, and Playtime columns.
5. Try **Top channels**, add a second report category, and confirm Excel creates separate tabs. CSV only works for a single report category.
6. On **Settings**, save a view and load it; expand Advanced to test the panel explorer and downloadable error logs.
7. Reenable daily updates only after numbers agree with Grafana.

For errors: **Settings → Advanced tools → Download error logs**. Review the JSON before sharing it. **Please contact Smarth for support.**

## Local regression commands

```bash
node tests/test-core.mjs
node tests/test-v2.mjs
node tests/test-picker.mjs
node tests/test-picker-background.mjs
python tests/test-v22-popup.py
```

The browser UI suite uses a mocked Chrome/Grafana bridge; it does **not** authenticate against your real Grafana deployment. The production candidate requires the live acceptance test above.
