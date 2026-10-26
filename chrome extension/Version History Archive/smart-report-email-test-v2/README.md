# Smart Report — Outlook Screenshot Email Test v2

Independent Chrome extension for one manual test of the complete screenshot/email pipeline.

## Setup
1. Disable the v1 authentication-only extension. Extract this ZIP and load the `smart-report-email-test-v2` folder as an unpacked Chrome extension. The `manifest.key` is the same as v1, so the extension ID / registered chromiumapp.org redirect should stay the same. Verify the redirect displayed in the popup.
2. Open your Grafana dashboard in Chrome (https://grafana-apj.trafficpeak.live/), set filters, date range and expanded panels, and ensure data has loaded. Keep this Grafana tab active.
3. Click the Smart Report icon, and enter the Entra App **client ID** and **tenant ID** from the registered `Smart Report - Grafana Automation` application. These two non-secret IDs are stored locally for convenience.
4. Click **Capture current Grafana tab**. Preview the image. It captures only the visible tab, not a complete long dashboard or hidden sections.
5. Enter the recipient address. Click **Send test email with PNG** and complete Microsoft sign-in. This requests delegated Graph Mail.Send consent. Only one mail is attempted per click.
6. Verify the received image and Sent Items. Microsoft HTTP 202 means accepted for processing, not guaranteed recipient delivery.

## Security and limits
- No client secret or password is used. PKCE login is applied. Tokens stay only in popup memory and disappear when the popup closes.
- No automatic sending, refresh, scheduling, email replay, or background delivery in v2.
- The dashboard screenshot is visible only in the popup until you send/download it; it is not saved in chrome.storage.
- Avoid other Chrome extensions that modify dashboard data. Don't include private dashboards in unexpected recipients.
- The Chrome pop-up may close if you switch focus or tabs; capture from an already active Grafana tab and keep the popup open during sign-in.
- Microsoft Graph sendMail uses a JSON fileAttachment which has practical request size limits. If a high-resolution screenshot fails due to size, report the error.
- To protect the company's mailbox, keep the recipient to yourself for the first test.

If sign-in reports AADSTS50011, verify that the redirect URL in the popup matches the URI registered in Microsoft Entra. Never grant tenant-wide admin consent just to test a personal delegated mail flow.
