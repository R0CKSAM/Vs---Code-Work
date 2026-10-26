# Smart Export v2.3.0 — Full Workspace

A standalone Chrome extension that opens a **normal, full-size Chrome tab** for building and exporting Grafana analytics reports. This is **not an externally hosted website**: it is a private page bundled into the extension and reuses the existing authentication/session and IndexedDB report master.

## How to use

1. Open the authenticated Grafana dashboard in Chrome.
2. Click the Smart Export extension icon. A minimal launcher will appear.
3. Click **Open Smart Export Workspace**. An existing workspace tab is reused rather than duplicating it.
4. In **Choose data**, select a suggested template or choose your metrics. Choose a date range. Use **Use open tab** to select the signed-in Grafana dashboard; the extension finds it even when this workspace is active.
5. Click **Fetch & preview**. The extension queries Grafana using your existing browser session, saves the results to its local master, and moves to **Preview & export**.
6. Review sample rows and choose **Export Excel** or **Export CSV**. Multi-category selections use separate Excel worksheets; CSV requires a single category.
7. Click **Back to Grafana** in the workspace header whenever you need to inspect or change the source dashboard. The original Grafana tab is reused where possible.
8. Under **Settings**, manage optional daily updates, named views, panel discovery, error logs, and legacy UI.

## Install / upgrade safely

- Open `chrome://extensions` and enable Developer mode.
- To preserve the existing Smart Export extension ID and local IndexedDB data, **pause daily updates and replace the files in the same unpacked folder** that v2.2.0 used, then click **Reload**. Do not uninstall the old extension first. Back up your master Excel download before upgrading.
- For a first-time install, unzip and use **Load unpacked**, selecting this folder.
- Grafana must remain signed in in another tab for fetching and daily updates. Switching to the workspace doesn't end your Grafana session.
- The extension doesn't move personal data to a hosted Smart Export server. It queries the trusted Grafana origin through the authenticated tab and stores report rows in Chrome's local IndexedDB.

## What changed in v2.3.0

- A **tiny launcher** (`popup.html`) replaces the tall popup.
- A spacious, responsive **workspace tab** (`workspace.html`) replaces cramped data selection. The selection, preview, and settings screens work at desktop and narrow widths.
- **Back to Grafana** returns to the existing Grafana tab; opens saved dashboard if the tab was closed.
- **Use open tab** works from a separate extension tab (previously assumed Grafana was active).
- Reuses the same metric picker, export engine, date validation, saved views, IndexedDB, daily automation, and error log functions from v2.2.0.
- Keeps the old compact interface under Settings → Advanced → Open classic interface for fallback.

## Testing / restrictions

- JS syntax, 68 original data/picker/background checks, launcher-tab tests, and simulated-browser UI/export checks passed.
- Layout tested at 1440px, 900px, 600px and 390px wide, with long URLs, 21 metrics and expanded settings.
- The authenticated Grafana query and Chrome's real extension-service-worker lifecycle need a live test on your company browser. Exported values remain dependent on the original Hydrolix queries and permissions.
- Your saved data is scoped to the extension ID. Reinstalling at a different path may create a new ID and a separate local dataset.
- The extension intentionally refuses unknown/unmapped Grafana data sources and ad-hoc filters rather than silently exporting misleading data.

## Support

Please contact Smarth for support. Download the error logs from Settings → Advanced, and check them before sharing.
