# Smart Export 2.2.0 — UI, interaction and integration audit

## Original failure mode

The previous v2.1.1 popup put all report templates, nested metric accordions, Grafana source, date selection, previews, exports, and settings in one vertically scrolling container. Dropdowns competed for space with adjacent actions and selection rerenders could affect focus. Past CSS changes accumulated as overrides rather than a single coherent design system.

## Corrections in v2.2.0

1. Replaced the single page with separate **Choose data / Preview & export / Settings** views. Retained persistent fetch and Excel buttons and a global live status strip.
2. Removed nested metric `details` accordions. Category buttons select one metric group; search works across all groups and displays results without expanding nested dropdowns.
3. Checkbox selection updates in-place: remains checked, retains focus and scroll; selected counts and badges update immediately.
4. Kept the existing native `select` controls only where appropriate, with explicit right padding and a noninteractive, vertically aligned caret.
5. Saved views use a full-width dropdown and separate row of action buttons. Long names truncate in the native select rather than pushing buttons out of the popup.
6. Each view scrolls independently within a fixed 520×600 popup. The header, step navigation, status and footer remain visible; no global horizontal scroll or scrollbar-only collapse.
7. All cards, buttons, inputs, tooltips, error messages, preview tables, and long URLs have explicit width, min-width, wrapping or bounded internal scroll rules.
8. Start/fetch uses a teal-blue gradient; Excel is green; CSV is blue; delete is muted red; loading and warning states have distinct colors. Reduced-motion preferences and keyboard-focus outlines are supported.
9. Screens are keyboard accessible: tab buttons respond to arrows/Home/End, native labels target inputs, status changes use an ARIA live region, and inactive screens are actually hidden.
10. Preserved the **same MV3 permissions**, config/storage keys and core modules. New `smartExportActiveView_v22` stores only current UI screen.

## Static/code checks

- Popup JS parses with Node and imports known local ES modules; no external scripts or remote CDN dependencies.
- Manifest uses MV3 service worker and the original Grafana host permission; no added permissions.
- All DOM IDs used by the popup controller exist exactly once.
- Existing background/query/database/XLSX/CSV modules were left unmodified.

## Test results

- Core GEO test suite: 15 assertions passed.
- Six-report suite: 30 assertions passed.
- Metric-picker suite: 16 assertions passed.
- Background command suite: 7 assertions passed.
- New Chromium UI test: 38 checks passed (root dimensions, tabs, accessibility, search, checkbox focus and scroll, all metrics, dropdown alignment, fetch-lock, preview, actual XLSX download, saved views, log export, long text, keyboard navigation, console errors).
- XLSX generated from the browser was imported and inspected using `artifact_tool`; the expected GEO values and Definitions sheet were present.
- Native Chrome extension launch/service worker could **not** be validated in this test environment; Chrome never exposed the extension worker. Live authenticated Grafana extraction remains unverified in this release.

## Known constraints before a company-wide roll-out

- Perform two-day/three-day real-data comparisons with the original Grafana panel and verify row counts; data extraction changes are outside this UI release.
- Some users may need to sign in again to Grafana when the browser session expires.
- Daily updates operate only when Chrome is running and authorized access remains available.
- Do not claim month-level unique audience by summing daily unique counts.
- For multi-report CSV, choose a single group or use Excel to preserve separate sheet grains.
