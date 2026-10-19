# Smart Report v3.4.0 — Simple Company Edition

This version repairs failures shown by exported v3.3 logs and removes complicated popup settings.

## Essential setup
1. Extract this ZIP into your **existing extension folder** and replace all files, including `background.js` and `popup.js`. On `chrome://extensions`, click **Reload** on **one** installed Smart Report extension. Remove/disable older duplicate installs.
2. Open your Grafana dashboard in Chrome and sign in there.
3. In Smart Report, click **Connect** for company Outlook. Confirm the Microsoft popup completes.
4. Enter or select the Grafana URL, paste emails into **Send to**, choose interval (default 15 minutes).
5. Click **Send test**. Only after you receive the screenshot email, click **Start reports**.
6. Watch **Report status**, progress, next attempt, last accepted email, and recent activity. Export logs if something fails.

## Changes
- Normalizes invalid legacy panel delays to an internal 12-second default; old `0` or missing values cannot block reports.
- Only explicitly visible **Send to** recipients receive emails. Old CC/BCC saved values are ignored and are cleared on the next save. No hidden extra recipient delivery.
- Multi-email paste appends and deduplicates; email chips show exactly who is listed.
- Simplified burgundy UI: one screen for Outlook, Grafana URL, recipients, interval, Send test / Start / Pause / Stop.
- Clearer error panel, progress stages, verification, recent events and logs; technical tools inside an optional section.
- Microsoft Outlook connection is verified via Graph `/me` after login and on popup open; Graph send acceptance is reported as accepted, not delivered.

## Important limitations
- Chrome must be open for alarm execution. Hidden/discarded Grafana tabs and corporate Chrome policies can affect screenshot capture.
- Company Microsoft Entra App registration must allow the existing chromiumapp.org redirect URI and Graph `Mail.Send`, `User.Read` delegated permissions.
- `Send test` and `Check screenshot` require actual Grafana and Microsoft access. Automated local checks cannot prove corporate Outlook delivery or Grafana panel readiness.
- By default, recipients must belong to the signed-in Outlook account's domain unless IT explicitly sets `allowedRecipientDomains` in `company-config.js`.

## Troubleshooting
- If old `Assignment to constant variable` or `Panel settling delay must be 2–120 seconds` errors continue, you are probably running an older installed copy. Inspect the version in `chrome://extensions`; it must be **3.4.0** and only one copy should be enabled.
- If a report fails, click **Export logs** and inspect the newest error, not old failures that are still listed.
- The extension does not hide Graph authentication failures or pretend that email was received.
