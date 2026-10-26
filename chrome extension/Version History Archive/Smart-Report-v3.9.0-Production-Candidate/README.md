# Smart Report 3.9.0 — Company Release Candidate

Smart Report captures the configured Grafana dashboard, waits for Grafana panels, stitches a screenshot, and emails it through the signed-in employee's **Microsoft Outlook or Gmail** account. The default schedule is every **15 minutes**, and To/CC/BCC are supported. The reporting tab may be in the background, subject to Chrome debugger and workplace browser policies.

**This build is production-hardened, but is not certified for unattended company-wide rollout until the acceptance checklist below is completed on real employee machines.** Tests use mocked OAuth and mail APIs; they do not prove actual mailbox delivery. Production use also depends on Google OAuth app publication/verification and the relevant Microsoft tenant policies.

## Update safely (preserves the existing extension identity)

1. **Download a backup** of your currently working Smart Report ZIP and optionally export error logs.
2. Stop or pause scheduled reports. In `chrome://extensions/`, keep only one Smart Report extension enabled.
3. Extract this release. **For an in-place update**, replace the files in the extension folder Chrome already loads, then click **Reload**. Do not change the manifest's public `key`, Google OAuth client ID or configured Microsoft IDs.
4. Open Smart Report. **The upgrade deliberately pauses any running schedule and clears old screenshot approval.** Your recipient fields and account sessions remain saved if the extension identity and storage are preserved.
5. Open the intended Grafana tab; confirm filters, time range, refresh setting and desired expanded rows. Click **Use the current Grafana tab**, **Check screenshot**, and **Approve** in the preview.
6. Open Delivery. Enter To/CC/BCC, customize subject if desired, choose **Microsoft Outlook** or **Google Gmail**, and set interval (15 minutes by default).
7. For Outlook, connect Microsoft and send a test; check Sent Items and the recipient mailbox. For Gmail, connect Google and **send a successful Gmail test with the same recipients**; only then will Gmail automatic scheduling be enabled.
8. Click Start monitoring. Switch to another browser tab and verify **two scheduled emails**, correct screenshot layout and timestamps. Test Pause/Resume and restart Chrome once before wider rollout.

No passwords or OAuth secrets should be placed in `company-config.js`. Application and tenant IDs are public identifiers, and the extension includes only the existing public extension key.

## Employee operation

- Use the Chrome extension icon to open Smart Report.
- Connect your own Microsoft or Google sending account.
- Link your signed-in Grafana tab (one designated dashboard); review one screenshot and approve it.
- Set recipient addresses and schedule, send a test, then Start. Pause / Resume / Stop as needed.
- Keep Chrome running, your computer awake and Grafana authenticated. If you change dashboard/recipients/sender, Smart Report pauses to protect against unreviewed delivery.
- Check the **Activity & help** panel to export logs. **Contact Smarth for support.**

## Security and delivery limitations

- This extension can send from the **employee's own authorized mailbox**, not a shared central account. A centrally managed sender requires a separate secure backend and approval.
- External recipient addresses are **enabled in `company-config.js` because the owner requested that capability**. Treat Grafana reports as confidential; only send to explicitly authorized recipients. Restrict `allowExternalRecipients` to `false` for company-only mail, and maintain the recipient domain list.
- Microsoft delegated `Mail.Send` requires user consent or company administrator approval according to each tenant's policy. No Chrome code can override those policies.
- Google Gmail API uses `gmail.send`. For wider distribution, publish and, if required, verify the Google OAuth app; Testing status is unsuitable for continuous production use due to limited test users and time-limited grants.
- Existing Microsoft tenant allowlist contains only explicitly configured tenants. Add additional approved tenants in `company-config.js` where required. Browser-side settings are **not a tamper-proof enterprise access-control system**.
- Chrome's Debugger permission is used for background-tab screenshot capture and can be restricted by enterprise IT policies. Smart Report does not guarantee capture when Chrome is closed, the computer is asleep, or Grafana has logged out.
- Sending APIs confirm **acceptance**, not delivery to the recipient. Check the sender's Sent folder and recipient inbox during rollout. Uncertain sends pause and require a manual Sent Items check before clearing the blocker.

## Release acceptance checklist (must be completed by a real user)

- [ ] Popup opens at full width in Chrome; Google-only, Outlook-only and both-account dashboards are visible.
- [ ] Microsoft sign-in and Outlook test email work on a user in your company.
- [ ] Google sign-in and Gmail test email work on an approved Google account.
- [ ] Gmail 15-minute schedule delivers two consecutive emails in Gmail Sent Items, with the correct PNG.
- [ ] Outlook 15-minute schedule delivers two consecutive emails, with the correct PNG.
- [ ] Switching tabs does not disrupt the report; full-page stitching includes the intended panels.
- [ ] Dashboard navigation or recipient change pauses a running schedule.
- [ ] Closing/reopening Chrome restores a valid schedule only when authorization/approval remain valid.
- [ ] Recover from expired Google/Microsoft authorization; no emails duplicated after timeout.
- [ ] Test one additional employee from a second approved tenant or Google account before company-wide distribution.
- [ ] Review external-recipient policy with the owner / IT.

## Automated tests run in this build

- Browser regression runner (mocked Microsoft/Google service responses): **62/62 passed**.
- Popup layout/interaction checks, including initial 1px intrinsic sizing: **69/69 passed**.
- Gmail MIME and error-handling tests: passed.
- Manifest, JavaScript syntax and ZIP integrity: checked.

These automated results do NOT replace real email and permission tests. See `AUDIT-REPORT.md` for what was checked and remaining release gates.
