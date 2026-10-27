# Smart Export v2.5.1 — Parameter Studio viewport repair

This maintenance release fixes the screenshot issue where the new Parameter Studio renders inside a narrow (~600px) portion of a full Chrome tab.

## What was wrong

The v2.5.0 page retained the legacy `#view-build` two-column CSS Grid. The new Parameter Studio was inserted as its first child, so the entire studio occupied only the first grid column, leaving most of the browser window blank. The old CSS also had `display` rules that could defeat the HTML `hidden` attribute when switching tabs.

## What changed

- A dedicated `parameter-fix.css` placed last in the stylesheet order removes the old grid and allows the studio to occupy the full workspace width.
- The header is shared by Choose Data, Preview & Export, and Settings, with working navigation.
- Date controls, metric cards, selection summary, dropdowns and actions now use the full browser width, with 3 columns on desktop, 2 on tablets, and 1 on phones.
- The main card and selection summary scroll locally only when content cannot fit. The bottom Get Data bar remains unobstructed.
- A high-specificity `[hidden]` selector prevents inactive screens from appearing underneath the active one.
- `SmartExportBridge` exposes the **existing** validated selection and fetch functions to the new UI. This replaces unreliable clicks on hidden legacy inputs.
- `Get data` waits for actual fetch completion instead of guessing after 1.5 seconds. Busy state disables repeat submissions.
- Metric selection is updated in one operation for Select Visible and Clear. Search and category navigation preserve selections.
- When the current selection is changed in Settings (saved views), the build screen refreshes from the real engine.
- Date validation enforces completed IST dates and the 31-day per-request limit of the selected report flow.
- CSV is rejected for a multi-category selection rather than offering an invalid combined export.
- The popup launcher and version labels now read 2.5.1.

## Installation / keep your existing master data

1. Stop any existing daily export and make a backup of your current extension directory.
2. Extract the v2.5.1 ZIP.
3. Replace the files in the **same unpacked extension directory**, not a different installation.
4. Visit `chrome://extensions/` and click **Reload** on Smart Export.
5. Click the extension icon → **Open Smart Export Workspace**.
6. Open your signed-in Grafana dashboard in another tab and click **Use open Grafana tab** if necessary.
7. Choose one or two metrics, a completed date range, click **Get data**, and confirm the Excel numbers match Grafana.

This release does not replace your saved IndexedDB or stored selections. Avoid uninstalling the old extension before backing up your data.

## Tested

- Node data/excel/report suites: 96+ assertions across existing suites.
- Simulated Chromium UI at 1919×1079, 1650×930, 1440×900, 1366×768, 1024×800, 768×930, and 390×844. No horizontal document overflow.
- Search, category switch, selection, Select Visible, full 21-metric selection, CSV multi-report restriction, modal preview, tab switching, and fetch-hand-off with a simulated engine.
- JavaScript syntax and ZIP integrity checks.

**Limitations:** Browser UI checks use local mock responses, not your authenticated Grafana server. Successful live Grafana extraction has not been independently established by this release. Only the previously mapped metric categories can be fetched. “Grafana tab ready” verifies that the configured tab is available; the server validates actual sign-in when fetching.

For issues, export diagnostics from Settings → Advanced tools and contact Smarth for support.
