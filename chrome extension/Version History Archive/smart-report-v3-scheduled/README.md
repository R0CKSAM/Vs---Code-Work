# Smart Report v3 — scheduled Outlook email

This is a **pilot build**, not a production-grade unattended monitoring service. It preserves the public Chrome extension key and OAuth redirect identity used by Smart Report v2.

## Install
1. Disable the earlier Smart Report extension. Unzip and load the `smart-report-v3-scheduled` directory at `chrome://extensions/` via **Load unpacked**.
2. Make sure the OAuth redirect shown in the extension is registered as a **SPA** redirect in your Microsoft Entra app.
3. Under **Advanced settings**, enter the company Entra application ID and tenant ID once. Both are public identifiers, **not secrets**. For employee rollout these can be preconfigured in a company-specific signed build.
4. Open Grafana and configure the time range / filters you want. Press **Use current Grafana tab**, or paste the dashboard URL. Note that not all UI filters are necessarily encoded in the URL; check that a refresh preserves the view.
5. Set To/CC/BCC and interval (default 15 minutes). Click **Connect Outlook** and complete sign-in. Choose **Capture preview**, then **Send test email**. After verifying the recipient inbox, click **Start monitoring**.
6. Chrome must remain running and the Grafana login must stay valid. First scheduled run occurs after the selected interval. Popup may be closed. The schedule uses `chrome.alarms`.

## What this pilot does
- Opens/finds a Grafana tab and leaves it in the background; reloads it at each capture to refresh queries.
- Waits for page loading plus a configurable settling delay and for known Grafana loading indicators to clear.
- Uses the **Chrome Debugger protocol** to capture a PNG of the tab viewport without activating it. Chrome may display a **debugging notification/banner**; the browser or company policy may restrict this capability. Only the Grafana host is allowed.
- Sends a PNG through Microsoft Graph `/me/sendMail` using the signed-in employee's delegated Mail.Send permission.
- Supports To, CC, BCC, scheduled repeats, manual test, Pause/Resume/Stop, log download, and attempts silent renewal with OAuth refresh tokens.

## Important limitations and security
- This requests the powerful **debugger** permission. Review and approve internally before distributing to staff. Do not use the extension on non-Grafana tabs.
- Token material, including refresh tokens when available, is persisted in Chrome extension local storage to enable unattended reports across service-worker restarts. **Do not install on shared or unmanaged workstations.** This is not equivalent to an enterprise server-side credential vault. Refresh tokens may expire or be revoked; interactive sign-in will then be required.
- Do not embed the client secret or password; neither is used by this extension.
- Emails to external recipients can expose internal analytics. Consider company allowlists and retention policy before employee rollout.
- `sendMail` HTTP 202 only proves Microsoft Graph accepted the message for delivery, not recipient receipt.
- Background capture is *best effort*. Debugger conflicts with DevTools and may be disabled by policy. Some dynamic Grafana dashboards can show old or missing data due to background throttling. Inspect the first scheduled captures.
- Only the **viewport** is captured, not the full scrollable dashboard. It captures the active content of the Grafana tab as sized, regardless of whether the tab is foreground.
- A Chrome extension cannot work after the browser is fully closed or the computer is powered off. If this becomes operationally critical, prefer an admin-approved central service.
- A refreshed URL may not preserve settings stored only in Grafana's UI. Save/bookmark the correct URL and verify refresh behavior.
- `Send test email` requires explicit confirmation. Scheduled emails occur only after Start is clicked.
- `Stop` disables future alarms but does not cancel an email already in flight.
- Do not log message bodies or secrets; logs contain statuses and error text, including Microsoft error responses where present.

## Testing
Static JS syntax tests are run for the distributed files. Live Microsoft/Grafana behavior is **not** verified in this environment. Test with one report to your own mailbox, then run a 1–2 minute pilot before selecting 15 minutes.
