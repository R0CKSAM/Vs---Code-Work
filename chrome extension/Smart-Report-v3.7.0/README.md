# Smart Report 3.7.0 — Capture review build

## Install and test (do not leave 3.6 reporting while testing)

1. Pause the old extension. Back up its unpacked folder.
2. Replace ALL extension files in that same folder with this package. Keep your existing company Microsoft IDs and approved recipient domains if IT changed them. The manifest key is unchanged, preserving extension identity.
3. Reload in chrome://extensions and confirm version 3.7.0. Old schedules pause on upgrade. Existing settings, counters and OAuth storage are not intentionally erased.
4. Open the required Grafana dashboard, wait for its normal graphs, and click Use tab.
5. Choose Open all sections (default), or As currently open for your manually selected rows.
6. Click Check screenshot. It opens a full-size local review tab. Verify the first totals, plotted graphs and the last row. Do NOT approve a blank/incomplete capture.
7. Click Approve this layout, return to the popup and Send test. Check the actual email attachment. Only then Start reports.

The new approval step is required once for the new version and again when the saved dashboard URL/filter/section mode changes. It is not required for every scheduled report. Approval means the user reviewed a sample layout, not that every future panel's business data can be independently validated.

## What is different from 3.6

- Fixed 1600 × 1000 capture viewport, independent of laptop window size. A viewport override failure is an error, not silently ignored.
- Discovers and scrolls the actual Grafana scroll container. Captures viewport-sized raster tiles, then stitches them locally. It no longer requests one oversized offscreen screenshot.
- Waits for visible chart canvases/visualizations to render, not only panel wrappers and absent loading spinners.
- Checks screenshot pixel variation within chart regions to reject empty compositor captures. This checks painting; it does not verify query correctness or guarantee that every plugin visualization can be recognized.
- Measures panel/row edges instead of using the document's whole scroll height, avoiding a large empty tail.
- Recognizes common legacy and newer Grafana row controls. Open all sections expands recognized rows; it does not cycle different dashboard pages, filter dropdown values or tab-based layouts.
- Keeps the linked tab; never silently creates a replacement report tab. Time/filter mismatch asks you to Use tab again. One specifically configured diagnostic URL parameter is ignored for matching; other var-* filters are checked in both directions.
- Restores scroll position, viewport and focus emulation after capture, including failures. Rows opened by Open all sections stay open locally and are not saved to the server dashboard.
- Preparing screenshot is separate from Submitting email; the last completed email stays visible while a new capture is running. Progress shows part number and elapsed time.
- Wider, compact burgundy popup. Check screenshot is visible, not buried in Tools.
- A preview does not increment email counters. A test/scheduled email increments accepted only after HTTP 202 from Microsoft Graph. Failed/unconfirmed requests are separate.

## Time and refresh

Defaults for URLs missing the corresponding settings are Today so far (`from=now/d&to=now`) and native Grafana refresh `1m`. Existing explicit time/refresh values are preserved. Today is based on the dashboard's timezone (or browser timezone if configured that way).

Use tab may navigate that same tab ONCE to apply missing URL defaults. There is no recurring tab reload, browser F5, or forced Refresh click before each report. Grafana's own refresh runs independently of the email interval. Opening previously collapsed rows may itself initiate their queries.

Capturing multiple tiles takes time; native refresh can update data during that period. This is a rendered dashboard report, not a transactionally consistent data snapshot.

## Email and limits

- One full-width image attachment per report. PNG first, then JPEG if needed. Image width is not reduced to fit email.
- Local limits: 24,000-pixel output height, 45 captured parts, 4-minute capture timeout, 35-second wait per part, and 2.5 MiB attachment target. These are extension limits, not an assertion of all Microsoft mailbox limits.
- Over-limit or persistently blank captures fail with a visible error rather than sending a silently shrunken/blank image.
- Explicit Grafana No data is retained as No data; no values or plots are invented. Query errors block capture.
- Graph HTTP 202 confirms acceptance for processing, not recipient delivery. Check Sent Items, recipient inbox or your mail administrator for delivery.
- A send timeout/network failure has uncertain acceptance; check Sent Items before retrying. Scheduled reporting pauses on that error to avoid repeated uncertain submissions.
- Pause/Stop prevents further scheduled sends, but cannot recall a request Microsoft has already accepted.
- Chrome and the logged-in Grafana tab must remain open. Sleeping/locked/discarded tabs, browser policy, plugin behavior or slow data sources can still interrupt rendering.

## Security and configuration

No new external service, mailbox permission, client secret or third-party screenshot endpoint was added. Existing Microsoft identifiers and recipient allowlist remain in company-config.js. Never add passwords, tokens or Microsoft client secrets there.

A single screenshot preview is stored in extension-local storage for review (replaced on the next preview). It can contain sensitive company metrics. It is not sent to Microsoft until you explicitly send a test or start scheduled reports. Logs contain panel titles/errors and capture metadata; treat exported logs as internal information.

## Test scope

See TEST-REPORT.md. Automated rendering tests use a synthetic Grafana-like page, real Chromium DOM/canvas/CDP rendering, and mocked Chrome-extension/Microsoft APIs. They do not authenticate to or send through the company Grafana/Outlook environment. Live installation and delivery must still be verified on your computer.
