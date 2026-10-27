# Smart Export v2.4.0 — Technical & UI audit

## Scope

Baseline: Smart Export v2.3.0 Full Workspace. Modified:

- `reports.mjs`: exact-duplicate consolidation and conflicting-metric rejection for all six datasets.
- `core.mjs`: same safe duplicate handling for the legacy GEO parser.
- `background.mjs`: warning logs for identical repeats and existing atomic database semantics retained.
- `workspace.html`, `workspace.css`: purpose-built responsive full-viewport UI, no dependency on popup sizing, preserved control IDs.
- `popup.html`, `launcher.css`: launcher branding refresh, unchanged launcher actions.
- `popup.mjs`: error assistance, diagnostic shortcut, active-view scroll reset.
- `manifest.json`: version bump to 2.4.0. Permissions and Chrome extension identity not intentionally changed.

Unchanged generation/data modules: `database.mjs`, `report-db.mjs`, `metric-catalog.mjs`, `multi-xlsx.mjs`, `picked-export.mjs`, `xlsx.mjs`, `tab-nav.mjs` and `workspace-nav.mjs`.

## Verification checklist

- `test-core.mjs`: 16 assertions, including GEO exact/conflicting duplicates.
- `test-v2.mjs`: 31 assertions, including multi-frame duplicate safety.
- `test-picker.mjs`: 16 assertions.
- `test-picker-background.mjs`: 7 assertions.
- `test-v23-tab-nav.mjs`: launcher/tab navigation.
- `test-v24-duplicate-recovery.mjs`: 26 specific duplicate/frame safety checks.
- `test-v24-viewport.py`: Chromium-rendered at 1920×1080, 1440×900, 1366×768, 1024×768, 768×900, 390×844. Verified document width and height, no horizontal control overflow, navigation, saved-view selection, dropdown arrow in its field, fetching and Excel download using simulated Grafana results.
- `test-v24-stress.py`: 21 selected metrics, 850-char URL, huge message, expanded Settings and no horizontal overflow at 1920, 1366, 1024, 768, 390 widths.
- `test-v24-error-ui.py`: conflicting response → actionable error → troubleshooting → logs; dismissal.
- Node `--check` for all JS modules and ZIP CRC check.

## Release gate still requiring live verification

A complete signed-in Grafana run with 2–3 real IST dates and exact reconciliation against Grafana. These browser tests use **synthetic data**: they demonstrate UI and parser behavior, not actual network permission or datasource compatibility.

## Design principle

Never convert a duplicate distinct-user or distinct-IP count into a falsely aggregated total. Deduplicate only identical groups, preserve source data and stop on conflicts. Store updates only when the complete requested set succeeds.
