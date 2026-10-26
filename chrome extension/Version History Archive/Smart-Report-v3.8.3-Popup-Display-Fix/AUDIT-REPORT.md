# Smart Report v3.8.2 — Technical audit

## Scope

Baseline: the provided 3.8.0 dual-mail ZIP and 3.8.1 Google dashboard patch. Audited manifest, UI pages, popup controller, Google adapter, worker entry points, capture and scheduling interactions. The original Grafana capture engine and Outlook Graph send sequence were not rewritten.

## Issues found and addressed

1. **Google-only sign-in trapped users without Microsoft connect controls:** added persistent dual-provider account strip and Account menu actions.
2. **Gmail test was detached from reporting workflow:** moved into Overview beside Outlook test, exposed only when Google is connected; stepper/preview/approval remain shared.
3. **Persisted Gmail email could be mistaken for valid OAuth:** silent token/profile check on popup opening; stale tokens display Reconnect and disable send.
4. **No Gmail sign-out path:** added Disconnect Gmail; does not pause Outlook reporting.
5. **Gmail test double-submission and uncertain network response:** serialized Gmail and Outlook operations; persisted a pre-POST pending marker. Timed-out or invalid responses require checking Sent Items before manual reset.
6. **Wrong status for Google-only users:** hid irrelevant scheduled-report and Outlook-only counters/fields, and labeled Gmail as one-time test mode.
7. **UI overflow and disconnected controls:** built compact responsive provider cards, constrained text content, bounded textareas, wrap-safe recipient/history and error text.
8. **Outdated documentation/test fixture:** updated the primary README and Google setup guide; adjusted historical version fixture in regression suite.

## Verification

- 53 regression checks passed in Chromium harness (with mocked Microsoft APIs, synthetic Grafana DOM and Chrome APIs); zero failures.
- 62 additional popup assertions across 555px and 400px simulated Chrome widths, including Microsoft-only, Google-only, both connected, scheduled running, expired Google session, pending sends, large entries, no horizontal overflow and no JavaScript page errors.
- Google adapter unit mock: accepted send including To/CC/BCC MIME fields; definitive HTTP error clears pending; network timeout preserves pending to avoid duplicate retries.
- `node --check` for every packaged JS file; all valid.
- ZIP integrity and required asset checks.
- Original `capture-engine.js`, `capture-page.js`, `preview.js` and preview styling unchanged from the 3.8.1 baseline.

## What was NOT tested

No live authenticated Grafana server, Microsoft Graph SMTP delivery, Gmail API or OAuth sign-in was invoked by the tests; actual access and third-party policies cannot be simulated completely. Scheduled Gmail delivery is NOT implemented. No central mailbox or tamper-resistant user allowlisting is included. `Mail.Send` and Gmail consent may still require organization approval.

## Current recipient limits

The uploaded baseline `company-config.js` allows To/CC/BCC only to `vetostreaming.com` and `indiatvnews.com`. This audit does not silently enable unrestricted external delivery. If outside recipients are required, review company policy and deliberately update `allowedRecipientDomains`.

## Manual production smoke test

1. Connect Google without Outlook; confirm dashboard loads and Gmail test becomes available after approved screenshot/recipients.
2. Connect Outlook from the Google dashboard; confirm both sender options display.
3. Send one Gmail test; check sender's Sent Items and recipient inbox.
4. Send one Outlook test and confirm PNG attachment and sender.
5. Start an Outlook 2–3 minute test schedule, switch Chrome tabs, confirm expected report, pause, then resume. Revert interval to 15 minutes.
6. Export logs for any error and contact Smarth for support.
