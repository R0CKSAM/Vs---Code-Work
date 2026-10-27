# Smart Export v2.1.1 — UI Reliability Update

This is a drop-in UI and interaction patch for Smart Export v2.1 Smart Data Picker. It does **not** change the Grafana/Hydrolix data-query logic, local master dataset, CSV/XLSX engines, or scheduler.

## Install

- **Recommended upgrade:** Pause daily syncing. Make a backup. Unzip and copy all contents into your **existing unpacked Smart Export extension directory**, then Reload the extension from `chrome://extensions/`.
- **New installation:** In `chrome://extensions/`, enable Developer mode, select **Load unpacked**, and choose the directory containing `manifest.json`.
- Keep Grafana signed in; select two or three completed IST dates for the first end-to-end test.

## What's fixed

- Native select dropdown arrows are correctly centered and no longer sit over the option text.
- Saved views are selected in a full-width dropdown, with clearly separated Load/Delete buttons.
- Metric accordion selection no longer unexpectedly resets its scroll position or keyboard focus.
- Data-preview counters update when your metric selection changes.
- Download buttons no longer offer stale data when you edit the Grafana dashboard address.
- Switching categories clears obsolete optional filters.
- Source, metric, and date settings lock during a fetch and unlock afterward.
- Long errors, names, URLs, and expanded settings stay inside the popup boundaries.

For exact checks see **UI-AUDIT.md**. All previous v2.1 capabilities remain available.

## Test commands

From the extension directory, with Node 22 and Python Playwright installed:

```bash
node tests/test-core.mjs
node tests/test-v2.mjs
node tests/test-picker.mjs
node tests/test-picker-background.mjs
python tests/test-ui-audit.py
```

The Playwright test uses local mock data and does not connect to private Grafana. Browser installation and authenticated queries need a separate live acceptance test.

**Need help? Please contact Smarth for support.**
