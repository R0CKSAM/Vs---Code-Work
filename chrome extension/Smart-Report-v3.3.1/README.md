# Smart Report v3.3.1 — Recipient counter fix

- Main recipient count shows **To** addresses only (no hidden CC/BCC included).
- Any saved CC or BCC addresses are explicitly shown in the main setup area, with their values, so you can spot leftover recipients.
- Test and Start confirmation messages list the actual To, CC and BCC recipients, not just a number.
- Duplicate addresses across To, CC and BCC are eliminated before email submission.
- This update **does not erase** saved recipients or settings; edit CC/BCC under More settings & tools to remove them.

# Smart Report v3.3 — Burgundy Company Edition

Chrome Manifest V3 extension: captures a saved Grafana dashboard in a background tab, and emails the screenshot through the signed-in company's Outlook/Microsoft 365 account (Microsoft Graph `Mail.Send`).

## What's new

- Burgundy, more compact interface: three readiness indicators, Running/Paused/Stopped state, next scheduled report, last accepted email, sent count, progress stages, recent activity, and visible errors.
- Multi-address **To / CC / BCC**: paste addresses separated by commas, spaces, semicolons, tabs or newlines, or Outlook-style `Person <person@company.com>` entries. Additional pastes preserve existing addresses and deduplicate them, case-insensitively.
- Drafts autosave while typing and never get overwritten by background status refreshes. Outlook sign-in no longer requires a saved dashboard or recipients.
- Schedule changes take effect without stopping/restarting monitoring; screenshot preview requires a dashboard URL but not email recipients or Outlook sign-in.
- Before capture, the extension checks the exact saved dashboard **and every configured URL query parameter** (including `from`, `to`, `timezone`, `orgId`, and `var-*` filters). Mismatched time ranges / filters fail closed.
- After applying the 1600×900 capture viewport, waits for panels to finish rendering again rather than relying on one fixed delay.
- When an administrator has not set allowed recipient domains, **only addresses matching the signed-in Outlook account's email domain** can be emailed. Other domains must be explicitly allowed by IT.

## Install / upgrade

1. Extract the ZIP to a permanent local directory; do **not** point Chrome at the ZIP itself.
2. Navigate to `chrome://extensions` in Chrome, enable Developer mode.
3. For first install, select **Load unpacked** and choose the extracted `Smart-Report-v3.3` directory (the one containing `manifest.json`).
4. For upgrade, retain the existing extension and directory if you want to keep settings: replace the existing version's files with the v3.3 files (keep the manifest key unchanged), then click **Reload** at `chrome://extensions`. Or install the new directory and migrate the saved fields manually if Chrome treats it as a new install.
5. Open Smart Report, **Connect** Outlook, fill the Grafana URL (or **Use tab**) and paste To addresses. Choose the interval (default 15 minutes), then **Send test email** before clicking **Start monitoring**.
6. **More settings & tools** reveals CC, BCC, email subject, extra panel load delay, capture preview, open dashboard, and Microsoft's OAuth redirect URL. Export logs appears under Recent activity.

## Admin security setup

- Microsoft public-client `clientId` and `tenantId` are in `company-config.js`. They are public identifiers, not secrets. Never place a client secret in this extension.
- Set `allowedRecipientDomains` to a list of authorized recipient domains (e.g. `['mycompany.com']`) to allow them. An empty list defaults to *same-domain-only* based on the connected Outlook account (Graph `User.Read`), not unrestricted sending.
- Cap To+CC+BCC via `maxRecipients` (default 50). For security, the extension refuses unapproved external recipients.
- Microsoft Entra: register the extension redirect shown under **More settings & tools** (`https://<extension-id>.chromiumapp.org/`) as a **Mobile and desktop applications** public-client redirect. Delegated permissions: `Mail.Send`, `User.Read`, `offline_access`, `openid`, `profile`. Configure enterprise-app assignment as required by IT.
- The manifest's existing public `key` is **unchanged** to preserve the extension ID / redirect URI across updates using the same extension identity.
- Chrome permission `debugger` is powerful and displays Chrome's debugging warning while capturing. IT should review before deploying. The extension must never be given a client secret.
- Access token resides in `chrome.storage.session`; refresh token in `chrome.storage.local`, so deployment requires protected work devices and Conditional Access. **Disconnect** removes both and pauses monitoring.

## Reliability and limitations

- Chrome must stay running and signed in to Grafana. Scheduled reporting is best-effort and depends on the Chrome MV3 service worker, browser tab lifecycle, and the signed-in Grafana session.
- Panel checks fail closed if Grafana is on a login page, no recognizable panel exists, panels show loading indicators, or saved URL query parameters have changed. The admin-only `requirePanels: false` override exists for Grafana builds with alternative panel markup.
- Each successful Graph `sendMail` response means Microsoft **accepted** the email for delivery, not confirmation that every recipient got it. Check the sender's Sent Items and recipient inbox.
- Capture is fixed at 1600×900 and tries PNG, then JPEG compression to remain under the single-request attachment limit.
- The extension attempts to keep its worker active through long panel loads with API activity; Chrome can still suspend/discard hidden tabs. For crucial reporting, consider Grafana server-side reporting/image rendering.

## Suggested functional tests (run in actual Chrome)

1. Sign in to Outlook **before** adding any recipients. Verify it works.
2. Paste two email addresses into To, then paste three more, including one duplicate. Verify existing addresses remain and the unique count updates; reopen the popup to verify persistence.
3. Use the exact dashboard URL including `from`, `to`, `timezone`, `orgId`, and `var-*` parameters. Capture preview. Then switch to a different filter and verify the extension does not email a mismatched dashboard.
4. Send a test email to an approved same-domain address. Confirm receipt and Sent Items entry. Attempt a disallowed external address: it must fail.
5. Start monitoring at 15 minutes. Confirm the next-attempt timestamp and monitor stage progression. Switch tabs; leave Grafana in background for 30–45 minutes.
6. Change 15 to 30 minutes while running and verify the displayed next-attempt time updates. Test Pause, Resume, Stop, Outlook Disconnect, and browser restart.
7. Export logs after both a good report and an intentionally failed run.

**Static validation is not a substitute for live Grafana, Microsoft sign-in, and email-delivery tests.**
