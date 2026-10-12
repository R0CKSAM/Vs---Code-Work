# Notification Pipeline Audit

## Audited flow

```text
ChangeEvent rows
    │
    ▼
Policy filter ── noisy/non-actionable ──► retained as unnotified history
    │ eligible
    ▼
Restart-safe deduplicator (event links + SENT batch keys)
    │ new
    ▼
Stable identity grouping ─► deterministic sorting ─► chunks of at most 50
    │
    ▼
Renderer: subject + plain text + inline-styled HTML
    │
    ├─ dry run ─► no DB write, no transport call
    │
    ▼
SMTP / console transport
    │
    ├─ failure ─► FAILED batch/delivery; events remain unnotified for retry
    │
    └─ success ─► SENT batch + per-recipient delivery + event links + notified_at
                   committed together
```

## State changes and exception behavior

| Situation | Expected state | Verified behavior |
|---|---|---|
| Empty input | No batch and no send | PASS |
| Policy rejects every event | No batch; events remain unnotified | PASS |
| Exact event repeats after restart | Existing SENT link/key suppresses resend | PASS |
| Transport throws | Batch/delivery FAILED; `notified_at` remains null | PASS |
| SMTP refuses one recipient | Treated as delivery failure | PASS |
| Transport succeeds | Batch/deliveries/links and event timestamps commit | PASS |
| Dry run | Render only; zero DB writes and zero email | PASS, copied DB SHA-256 unchanged |
| 51 events | Two ordered batches (50 + 1) | PASS |

## Rendering and security

- Batch keys are SHA-256, deterministic and independent of input order.
- Card numbers are sequential (`UPDATE 01`, `UPDATE 02`, …) in HTML and plain text.
- Badge, executive summary and card counts agree.
- UNKNOWN status is worded as a verification warning and never as an unsupported “stopped” claim.
- Only FanCode HTTP(S) source links are clickable; missing/unsafe links render “Source link unavailable”.
- Titles, teams, tours, venues and URLs are escaped by output context. Tests include ampersands, angle brackets, quotes, Unicode and emoji.
- Subjects are capped at 78 characters. Dates are stored in UTC and displayed in Asia/Kolkata where relevant.
- Email CSS is inline and layouts were visually checked at 360 px and 800 px (`tmp/render/`).
- SMTP logs omit usernames, passwords and address values. MIME includes Date and Message-ID.

## Evidence

- Full suite: 564 passed, 0 failed, 0 skipped.
- Real SMTP: server accepted one test message; latest matching audit is batch `SENT`, delivery `SENT`, provider `smtp`, event count 3.
- Exact mutation on copied production data: one `STATUS_CHANGED` event (`UPCOMING → LIVE`), one SENT batch, one SENT delivery, no placeholder regression events.
- Render artifacts: `tmp/render/*.html`, `tmp/render/*.txt`, `tmp/render/*_360.png`, and `tmp/render/*_800.png`.

The SMTP acceptance/audit evidence proves successful handoff to the configured provider. Final inbox placement is outside the monitor's observable boundary.
