# Smart Report 3.8.2 — Dual Account UI Audit Release

Built on the uploaded Smart Report 3.8.1 with Microsoft Graph/Grafana capture and scheduling preserved.

## Fixed

- The dashboard's provider strip shows BOTH Outlook and Gmail states and provides Connect/Reconnect actions even after entering with Google only.
- Gmail one-shot test appears WITH the normal Outlook test in the final overview. Google test is disabled until a screenshot is approved and recipients are valid; automatic Gmail scheduling is not represented as available.
- Google session health is checked on popup initialization with a silent OAuth/profile check. Expired or switched accounts trigger Reconnect instead of false confidence.
- Disconnecting Gmail no longer pauses an Outlook schedule.
- Gmail test sends are serialized; a network error after submission starts leaves a persistent blocker and requires checking Gmail Sent Items before retrying.
- Wider responsive popup, bounded textareas, long-address overflow protection, no duplicated Gmail login controls at top of screen, clearer state labels.
- Existing Preview/Approve flow, CC/BCC, Outlook email scheduler, screenshot capture, Microsoft token handling and tenant allowlist are kept unchanged except Gmail/Outlook send concurrency guard.

## Install

1. Keep a backup of the previously working extension. Disable that version; never run duplicate schedulers.
2. Extract ZIP, Chrome Extensions → Developer mode → Load unpacked → select Smart-Report-v3.8.2-Audited.
3. Check the extension ID and OAuth registrations (Microsoft redirect URI and Google OAuth Chrome client). The manifest `key` and Google client ID are preserved to keep identity stable for the SAME unpacked key.
4. Refresh Grafana, open Smart Report, connect Outlook or Google, choose dashboard, **capture and approve** a screenshot, then set recipients.
5. Send a single provider-specific test; verify its Sent Items and recipient inbox before scheduling Outlook reporting.

## Explicit restrictions

- **Gmail remains TEST-ONLY (one approved screenshot at a time).** Automatic schedule is Outlook-only.
- Recipient allowlist remains controlled by `company-config.js` (`vetostreaming.com`, `indiatvnews.com`) in this build. It is NOT changed silently, and other domains are rejected. Ask the administrator before widening it.
- Outlook Graph acceptance (HTTP 202) and Gmail API acceptance do not prove recipient delivery.
- Microsoft account and Google account credentials are not shared; the Chrome extension stores some metadata/tokens locally. Distribute only trusted builds.
- Chrome debugger-based Grafana capture can be restricted by policies; keep Grafana tab open. Native screenshots are unaffected by this UI update.
- In-memory `gmailBusy` stops double clicks while the worker is alive; the persisted `gmailSubmissionPending` prevents silent retries after timeouts/restarts. The app cannot reliably prove remote delivery.
- HTML UI tests use Chromium with mocked extension APIs and mocked server replies. **Live OAuth and Grafana flows are not verified by these tests.**

For troubleshooting, open **Activity & help → Export logs**. Please contact Smarth for support.
