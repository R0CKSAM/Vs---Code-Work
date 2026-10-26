# Smart Report 3.7.1 — Regression report

Test date: 19 October 2026. Automated checks run in local headless Google Chrome.

## Scope

The suite in `tests/regression.js` loads the actual packaged JavaScript files. Panel-readiness checks use real browser DOM/canvas behavior. Capture control-flow checks mock CDP screenshot output and bitmap composition. Background-worker checks mock Chrome APIs, authentication and Microsoft Graph; they make no external requests and send no emails.

37 checks passed, zero failed:

- All six packaged JavaScript files parse.
- Capture completes at a single-viewport boundary, multi-tile boundary and nested-scroll boundary without phantom bottom padding; a final one-pixel strip is retained.
- Blank-chart and startup failures restore capture state and detach the debugger in the mocked engine.
- Real DOM values `42`, `UP`, `OK`, `Healthy` and `No data` pass readiness checks.
- Empty, loading-only, hidden-value and transparent-canvas panels fail readiness checks.
- Stale, identity-less and settings-mismatched preview approvals are rejected. The current preview can be approved.
- Pausing during token renewal cancels both manual and scheduled mail before POST without inflating failure counters.
- Changing recipients during token renewal blocks stale submission.
- An approved successful response increments acceptance exactly once; unapproved mail never submits.
- Preview capture opens a review tab without relying on a popup and does not alter mail counters.
- Network uncertainty pauses manual tests too; an outstanding submission marker prevents automatic resumption after restart.
- Upgrade pauses old schedules and invalidates old approval.
- Actual URL matching rejects changed variable filters.
- Pausing after POST preserves an accepted outcome while leaving monitoring paused.
- Failed capture releases the busy lock, allowing a subsequent successful attempt.
- Pausing during capture prevents submission; Resume cannot revive a cancelled in-flight report.

## Reproduce

Serve this extension folder locally, bound to loopback:

```powershell
& 'D:\Vs - Code Work\venv\Scripts\python.exe' -m http.server 18737 --bind 127.0.0.1
```

Open `http://127.0.0.1:18737/tests/runner.html` in Chrome. The page reports each result and the failure total. Stop the server afterward with Ctrl+C. Node and external test dependencies are not required.

## Live acceptance still required

These checks do not establish that an installed Chrome extension can render every Grafana plugin or send through your tenant. The previous 3.7.0 test report's CDP image-stitching results are historical and are not claimed as new 3.7.1 installed-extension verification.

1. Reload the existing unpacked extension and confirm version 3.7.1. Confirm the old schedule paused and your Outlook/configuration settings remain.
2. Use the intended Grafana tab. Check screenshot in both row modes. Compare first totals, UP/OK status panels, intermediate graphs and the last row against Grafana; inspect tile boundaries and text readability.
3. Close the popup during capture and confirm the preview still opens. Generate a second preview; approval from the older preview must be rejected.
4. Approve the latest preview, send one test to intended recipients, and check Sent Items and the actual received attachment. HTTP 202 alone is not delivery confirmation.
5. Start reports, observe two intervals, then Pause/Stop before submission. Confirm no later scheduled emails. If submission was already underway, reconcile it in Sent Items.
6. Confirm expected behavior after Chrome restart and with a closed/discarded Grafana tab. For any unconfirmed submission, check Sent Items before retrying/resuming.

No live corporate account, recipient mailbox, installed-extension end-to-end flow, or unattended soak test was exercised by this automated suite. Production acceptance remains conditional on these checks.
