# Smart Report v3.9.2 — Aurora UI & Full Navigation

## What this release fixes

The supplied four-screen reference showed a **dark purple/blue application with separate Dashboard, Schedule, Reports, and Settings screens**. v3.9.1 retained the old pale wizard and navy/mint branding, so it did not resemble that reference. This release implements an actual four-tab popup interface using the same reporting engine.

- Dark purple/blue gradients, matching S-logo icons, illuminated yet restrained borders
- Fixed bottom navigation: Dashboard, Schedule, Reports, Settings
- Working Microsoft/Google account connections and Account dropdown
- Sender tabs (Outlook/Gmail), with actual provider selection connected to the existing scheduler
- Explicit colored actions: purple/blue for capture/configuration, teal for Start, amber for Pause, blue for Resume, red for Stop
- Reports tab showing the **actual locally recorded events**, most recent mail acceptance, errors, and log export. This is not a fabricated server-side email history
- Settings screen with connection controls, privacy/safety text, support and log tools
- Fixed dashboard URL order, account dropdown propagation bug, scrolling history reset, misplaced footer
- Stable 540px-wide popup with 596px-high bounded, internally scrolling content; bottom navigation stays reachable
- Full-width inputs, bounded textareas, wrapping for unusually long recipients/errors, and aligned CSS chevrons
- Screenshot approval tab recolored to match the app

## Critical integrity commitments

`background.js`, `capture-engine.js`, `capture-page.js`, `google-mail.js`, and `company-config.js` are byte-identical to v3.9.1. The Microsoft/Google credentials, OAuth scopes, extension manifest `key`, Chrome identity, Grafana screenshot logic, mail submissions, and scheduler are unchanged. Changes are to popup HTML, popup JS navigation, styles, preview CSS, and icon assets.

The sample graph inside the Dashboard tab is **illustrative UI artwork**, not a live Grafana screenshot. To review your actual screenshot, select **Capture current view → Preview image** and approve it in the separate review tab.

## Safe upgrade

1. **Pause Smart Report** and copy your entire existing extension directory somewhere safe.
2. Extract this ZIP and copy its contents **into the same installed unpacked extension directory**. Do not delete storage or change the manifest's `key`.
3. Visit `chrome://extensions/` and click **Reload** on Smart Report.
4. Reopen the popup. Check Microsoft and Gmail connection states, dashboard address, approved screenshot, sender and recipients.
5. Send **one test email** to a known recipient. Check the attachment and Sent Items.
6. Resume the schedule only after confirming setup. Chrome and the Grafana tab must remain running and authorized.

## Validation

- 62 reporting regression checks passed against the underlying engine.
- 65 browser UI assertions passed across welcome, dashboard, delivery, ready/running schedules, Reports, Settings, long recipient emails, errors, account dropdowns, and 1-pixel initial viewport sizing.
- JavaScript syntax checked, manifest validated, no missing or duplicate element IDs, ZIP integrity confirmed.
- These are **offline tests with simulated account data**. A live Chrome extension installation is still required to verify OAuth and email delivery after the UI upgrade.

## Support

The extension retains **Contact Smarth for support**, an on-demand error-log download, and the existing company policies for permitted recipients.
