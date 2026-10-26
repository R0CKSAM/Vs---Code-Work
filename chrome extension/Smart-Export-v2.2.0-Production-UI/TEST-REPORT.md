# v2.1.1 UI Maintenance QA

- 28 browser interaction/layout assertions passed (mocked Chrome services).
- 68 Node core/report/picker/background assertions passed.
- 96 checks total. See UI-AUDIT.md for scope and limitations.

# Smart Export v2.1 — test report

## Verified automatically

- Original v1 core unit assertions: 15 passed.
- Existing v2 SQL/report/Excel assertions: 30 passed.
- New Smart Picker metric selection and workbook assertions: 16 passed.
- Chrome message handler tests for save, daily schedule safety, invalid selections, missing Grafana tab: 7 passed.
- Runtime popup UI with mocked backend rendered in headless Chromium at the fixed 520×590 viewport; search, quick picks, selected field count, filter dropdown alignment, expanded Advanced and Daily Update sections tested without JavaScript errors.
- Screenshot geometry: no horizontal overflow, buttons within popup bounds, 21 selected metric options remain within the bounded selection panel.
- Selected Excel workbook parsed successfully with artifact_tool. It produced separate `Daily KPIs`, `Popular Content`, and `Definitions` sheets in the fixture.
- ZIP is checked for integrity and all JS modules checked with Node syntax parser.

## Not verified automatically

- Real authenticated Grafana/Hydrolix API queries.
- Chrome service worker wakeup and persistent scheduled runs in the user's own machine.
- Source panel inventory against the live Grafana dashboard when no session is present.

## First live test

- Pick GEO playtime for a single completed day.
- Compare with original Grafana panel output for that day.
- Pick Daily overview plus Channels, fetch 2 completed days, export workbook and validate both tabs.
- Try a channel dimension filter on Excel export and confirm stored master is unchanged.
- Use the daily toggle only after confirming the data.
