# Smart Report v3.8.2 — Audited dual-mail dashboard

**Use this version for testing; not yet a production rollout.** Based on the last provided `Smart-Report-v3.8.0-dual-mail-beta(1).zip` plus its 3.8.1 patch. The original Grafana capture modules, preview/approval flow and Outlook reporting scheduler are retained.

## What works

- Sign in with Microsoft **or** Google; either opens the same dashboard workflow.
- Gmail-only users can configure a Grafana capture, review/approve an image, enter To/CC/BCC recipients, and send **one Gmail test**. Gmail auto-scheduling is **not implemented**.
- Outlook users can test one email and schedule recurring screenshots. Microsoft Graph is still required for Outlook sending.
- Users with both providers see both sender options in the final overview. Connect/reconnect is always available at the top; disconnect options are in the Account menu.
- Google session validation, ambiguous-send duplicate protection, and recovery after reviewing Gmail Sent Items.
- Existing screenshot capture, row-expansion settings, preview approval, pause/resume, recipient validation, progress, history and log export.

## Install

1. Disable other Smart Report builds to avoid duplicate scheduled reports. Keep your working prior ZIP as a rollback backup.
2. Extract and visit `chrome://extensions/` → Developer mode → Load unpacked; select the `Smart-Report-v3.8.2-Audited` folder.
3. Check that the **extension ID is unchanged**. If the ID differs, update the Microsoft Entra redirect URI and Google OAuth Chrome Extension client registration to match it. The previously configured manifest public key is retained, but verify the installed ID.
4. Reload any open Grafana tab. Open Smart Report. Connect your mail provider.
5. Link Grafana → Check screenshot → Review/Approve → Set To/CC/BCC → Test provider delivery.
6. Only after a successful OUTLOOK test should you start the recurring schedule. Gmail is one-time test mode in this release.

## Privacy / permissions

- Neither Client IDs nor the public manifest `key` are passwords. Do not place a Microsoft client secret, Gmail password, or service account key in the extension.
- Configured recipient policy remains limited to `@vetostreaming.com` and `@indiatvnews.com` (see `company-config.js`). Other recipients require intentional policy review before rollout.
- The `gmail.send` OAuth permission requires Google consent/verification as appropriate. Other organizations may require their own admin approval for Outlook Mail.Send.
- Browser-installed Chrome extensions are not trustworthy enforcement points for central company-wide allowlists; use a backend if policy needs tamper-resistant enforcement.
- Network timeouts after a Gmail send begins are potentially ambiguous; the app will block another Gmail test until the user confirms they checked Sent Items.
- Corporate Grafana account and Chrome window must remain available to capture dashboards.

## QA

Read `AUDIT-REPORT.md`. Tests use mocked identity and HTTP responses, not live corporate accounts. Please verify one screenshot and one Outlook and Gmail email in your Chrome profile before further distribution.

Need assistance? **Please contact Smarth for support.**
