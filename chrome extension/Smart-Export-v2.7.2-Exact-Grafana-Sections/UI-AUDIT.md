# Smart Export v2.1.1 — UI and Interaction Audit

**Scope:** Chrome popup and direct UI state updates. Started from the previously supplied Smart Export v2.1 Smart Data Picker ZIP. The Grafana query templates, background scheduler, IndexedDB schema, CSV/XLSX writers, metric catalog, and host permissions were not changed.

## Confirmed interface issues repaired

1. **Metric accordion resets:** Toggling a checkbox rebuilt all `<details>` elements, causing scroll jumps and loss of keyboard focus. Metric checkbox changes now update in place; accordion open/closed choices persist through search.
2. **Saved-view dropdown collision:** The dropdown, Load, and Delete buttons shared one narrow row. The dropdown now has its own full-width row and the action buttons sit in a separate two-column row.
3. **Unreliable caret positioning:** Replaced font glyphs with CSS-drawn, vertically centered carets on the metric accordions, saved-view picker, export filter, and expandable settings panels.
4. **Filter leaks across reports:** Switching report categories previously preserved an unrelated filter value. Switching from Channel to GEO now clears the previous category's filter.
5. **Stale data counters:** Metric changes did not refresh the stored row/date/dataset statistics until the next background refresh. Counts and status now update immediately.
6. **Source mismatch:** Download controls could still appear enabled if a different Grafana URL was typed. They are disabled until that source is fetched/saved.
7. **Fetch-time changes:** UI controls could be edited mid-fetch, causing displayed categories/dates to differ from the request. Selection, dates, URL, and filter inputs now lock during the fetch and unlock afterward.
8. **Focus regression on Quick Picks:** Quick Pick buttons are no longer destroyed/recreated after every selection, preserving keyboard focus.
9. **Stale empty-preview message:** The empty-state message now resets when switching to a report without stored rows.
10. **Long-content layout:** Bounded scroll containers, wrapping, ellipsis, and minimum-size safeguards for URLs, dropdown text, selected chips, settings values, and error messages.
11. **Date preset clarity:** Last 7/30 buttons indicate the active preset; manual date entry clears that state.
12. **Portable tests:** Original core tests saved fixtures to hard-coded paths from earlier versions, causing false failures. Fixture output now uses paths relative to each test file.

## Verification performed

- Browser-driven 520 × 590 popup checks: **28 passed** in a local Chromium page containing the actual popup HTML/CSS/JS and mocked Chrome/Grafana services.
- Original Node checks: GEO core **15**, multi-report **30**, smart-picker **16**, background command **7**; **68 passed**.
- CSS dropdown arrow vertical difference under 5px; no measured horizontal overflow or button collision under the tested scenarios.
- Tested search, category expand/collapse, checkbox selection and focus, Quick Picks, report switching, export filters, saved-view save/load/delete, panel explorer, in-flight lock/unlock, preview, real browser-generated XLSX download, stale Grafana URL protection, long URLs/errors, and full 21-metric selection.
- JavaScript syntax checks, manifest JSON, and ZIP integrity checked.

**Total:** 96 automated checks passed. These are offline/browser-mock tests, **not an authenticated live Grafana test**. The first production acceptance test should use a signed-in Grafana tab and compare a two- or three-day export against Grafana Inspect → Data.

## Upgrade guidance

1. Back up the installed unpacked Smart Export folder, leaving the existing master data untouched.
2. Copy the new extension files into the **same installed extension folder** and select **Reload** at `chrome://extensions/`.
3. Use **Top channels → Choose your numbers → Filter dropdown**, then **Daily updates & saved views** to verify the new control layout.
4. Fetch one short completed IST date range and check the Excel/CSV output before re-enabling daily automation.

No database migrations or additional browser permissions were introduced.
