# Smart Report v3.6 — Company Edition

## What changed
- Default Grafana time range is **Today so far** (`from=now/d&to=now`) when the saved URL does not already include a time range.
- Default Grafana refresh is **1m** when the saved URL does not already include a refresh parameter.
- Scheduled captures **do not force a dashboard reload** by default; the extension keeps the current open tab state and relies on Grafana page refresh settings.
- Full-page dashboard screenshots are captured vertically, so the result is less dependent on screen size and can include expanded rows/sections visible on the open dashboard tab.
- Visible counters for **Accepted by Outlook** (Microsoft Graph accepted for processing) and **Failed emails**.
- Last email attempt result, kind (test/scheduled), time and exact error persist across popup openings.
- Screenshot previews do **not** count as sent email attempts.
- Send failures are counted whether caused by settings, Grafana capture, Microsoft authentication, domain restrictions or Graph API rejection.
- Recipient allowlist includes **vetostreaming.com** and **indiatvnews.com**; other recipient domains remain blocked unless IT approves them in company-config.js.
- Better recognition of Grafana panel markup across versions, still fails closed if no panels are present.
- Same burgundy minimal interface; advanced tools remain collapsed.
- No user-adjustable panel settling delay. Old invalid values are ignored.

## Meaning of status
- Accepted by Outlook: Microsoft Graph sendMail returned success, **not proof of recipient delivery**. Check Outlook Sent Items and receiving inbox for final delivery confirmation.
- Failed emails: a requested email could not be accepted; select the error message to diagnose. Counting starts in v3.6 (previous accepted total is preserved).
- Preview success: screenshot only; no email has been sent.
- After updating, old schedules are paused and must be restarted after a successful test.

## Upgrade
1. Backup current unpacked extension directory, then replace its files with ALL files from this package.
2. In Chrome visit chrome://extensions, click Reload for Smart Report and confirm v3.6.0.
3. Keep existing connection and settings if preserved; confirm recipient domains.
4. Click Send test and watch the LAST EMAIL ATTEMPT field change to Accepted or Not sent. Never use screenshot success as an email confirmation.
5. If accepted, verify the mail via Outlook Sent Items and recipient inbox, then Start reports.

## Data & security
Microsoft IDs in company-config.js are public app identifiers, not secrets. OAuth PKCE is used; never embed Microsoft client secrets in browser extensions. To add a recipient domain, edit COMPANY_POLICY.allowedRecipientDomains only after approval. Report screenshots can contain sensitive company metrics.
