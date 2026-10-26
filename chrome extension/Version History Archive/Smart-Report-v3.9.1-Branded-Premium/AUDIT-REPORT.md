# Smart Report 3.9.0 — Audit report

## Changes from the tested 3.8.3 popup baseline

1. Preserved the exact 540px intrinsic-width Chrome popup fix that solved the scrollbar-only failure.
2. Added an explicit sender selector (Outlook / Gmail) and optional email subject.
3. Added **scheduled Gmail** via Chrome-managed Google OAuth tokens. Gmail is only eligible after a user-approved screenshot and a successful one-time Gmail test with identical sender and recipients; validity is rechecked before a scheduled send.
4. Kept the original Microsoft OAuth + Grafana screenshot engine, dashboard URL/filter checks, preview approval, interval scheduler, and To/CC/BCC behavior.
5. Stopped monitoring when recipients, sender or dashboard settings change; enforced before-POST revalidation during slow account verification.
6. Added uncertain-send recovery for Outlook and retained the Gmail pending-state guard. Network timeouts are treated as **unconfirmed**, not as proof that nothing was sent; no automatic duplicate retry occurs.
7. Added safer upgrade migration: pauses active schedules and invalidates old screenshot approval, while preserving saved settings and existing account state when updating the same installed extension.
8. Added explicit external-recipient policy (`allowExternalRecipients: true`) because it was requested. The UI warns about sharing company analytics externally.
9. Added simulation tests for Gmail scheduling, sender switching, recipient changes, blocked sends, and external policy, plus popup layout stress tests.

## Automated validation

- 62 browser-based regression checks passed (Microsoft/Google API calls mocked).
- 69 browser-based popup checks passed: signed-out, Google-only, Microsoft-only, both accounts, pending states, long content; 555px, 400px host and 1px initial viewport root width.
- Google MIME/To/CC/BCC mock suite passed.
- Syntax checks on all JS files and ZIP integrity checks passed.

## What is NOT verified automatically

- Live capture of the real TrafficPeak Grafana instance using current employee permissions.
- Actual Microsoft 365 or Google consent and email delivery with the new Gmail schedule path.
- Google Cloud OAuth **In production** publication/verification status.
- Chrome Enterprise debugger policy or automatic user provisioning.
- Browser extension installation via signed CRX / private Chrome Web Store.
- True server-enforced cross-company access/recipient allowlisting. A Chrome extension alone cannot provide tamper-proof enterprise authorization.

## Security acceptance gates

- User must approve the screenshot layout and manually confirm addresses (including external ones) before starting unattended delivery.
- User must test both selected providers; the Gmail automatic option remains gated until a successful Gmail test.
- Verify two scheduled reports from each provider and pause/resume after closing the popup and switching Chrome tabs.
- Confirm unexpected error conditions pause instead of sending again. Download logs and contact Smarth for support.

**Status:** release candidate suitable for supervised company pilot; wider production rollout requires the real-world acceptance checklist in README.md and applicable IT / Google OAuth approvals.
