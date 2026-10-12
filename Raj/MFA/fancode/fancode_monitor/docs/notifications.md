# FanCode Monitor — Alerting & Notification Engine (Phase 9)

## 1. Overview & Architecture

The **Alerting & Notification Engine (Phase 9)** provides automated, production-quality email notification digests for meaningful changes detected across the FanCode website.

The engine consumes persisted `change_events` produced by the Phase 8 Change Detection Engine, applying centralized policies, deterministic batching, event deduplication, HTML rendering, and transactional audit logging.

```
SCRAPERS (Schedule, Live Now, Detail, Videos, Sports/Tours)
    ↓
NORMALIZED DATABASE STATE (matches, tours, sports, videos)
    ↓
CHANGE DETECTION (Phase 8 ChangeDetector)
    ↓
change_events (Audit table)
    ↓
ALERTING / NOTIFICATION ENGINE (Phase 9 NotificationService)
    ↓
FILTER (NotificationPolicy)
    ↓
GROUP & DEDUPLICATE (EventGrouper + NotificationDeduplicator)
    ↓
RENDER DIGEST (HTML + Plain-Text with HTML escaping)
    ↓
EMAIL DELIVERY (Console, Test, or SMTP Backend)
    ↓
NOTIFICATION AUDIT (notification_batches, notification_deliveries, notification_event_links)
```

---

## 2. Notification Policy

Notification eligibility is governed centrally by `app.notifications.policy.NotificationPolicy`:

| Entity Type | Change Type | Conditions & Severity | Notifiable? |
|---|---|---|---|
| **MATCH** | `CREATED` | New fixture scheduled (`IMPORTANT`) | ✅ Yes |
| **MATCH** | `STATUS_CHANGED` | UPCOMING &rarr; `LIVE` (`CRITICAL`) | ✅ Yes |
| **MATCH** | `STATUS_CHANGED` | LIVE &rarr; `COMPLETED` (`IMPORTANT`) | ✅ Yes |
| **MATCH** | `STATUS_CHANGED` | UPCOMING &rarr; `CANCELLED` / `ABANDONED` (`CRITICAL`) | ✅ Yes |
| **MATCH** | `STATUS_CHANGED` | UPCOMING &rarr; `POSTPONED` / `DELAYED` (`IMPORTANT`) | ✅ Yes |
| **MATCH** | `UPDATED` | Venue, date, start time, team names (`IMPORTANT`) | ✅ Yes |
| **MATCH** | Volatile Score | Score summary, overs, wickets, points (`LOW` / noisy) | ❌ No (Ignored) |
| **VIDEO** | `CREATED` | New highlight or match replay (`INFO`) | ✅ Yes |
| **VIDEO** | `UPDATED` | Meaningful metadata update (`INFO`) | ✅ Yes |
| **TOUR** | `CREATED` | New tournament or series (`INFO`) | ✅ Yes |
| **TOUR** | `UPDATED` | Name, dates, sport (`INFO`) | ✅ Yes |
| **SPORT** | `CREATED` | New category discovered (`INFO`) | ✅ Yes |
| **ALL** | `REMOVED` | Complete snapshot omission (`IMPORTANT`) | ✅ Yes |

---

## 3. Grouping Strategy

To avoid overwhelming recipients with individual emails per event, `EventGrouper`:
1. **Deterministic Batching**: Combines unnotified events into a single digest batch.
2. **Deterministic Batch Key**: Computes a SHA256 hash over sorted event attributes and `scrape_run_id`.
3. **Per-Entity Aggregation**: Multiple changes for the same match (e.g. venue update + start time update + status transition) are grouped into a single visual card within the digest.

---

## 4. Deduplication & Idempotency

- **Event-Level Deduplication**: Events with `notified_at IS NOT NULL` are skipped.
- **Batch-Level Deduplication**: Batches whose `batch_key` has already been recorded as `SENT` in `notification_batches` are skipped.
- **Repeated Runs**: Re-running the notification service over already-notified events produces `0` emails dispatched.

---

## 5. Retry & Failure Behavior

If SMTP or delivery transport fails:
1. The `NotificationBatch` status is set to `FAILED` with the recorded `error_message`.
2. Individual `NotificationDelivery` attempts are recorded as `FAILED`.
3. The underlying `change_events` **remain unnotified** (`notified_at IS NULL`).
4. On the next execution, the failed batch is retried safely. Once successful, `status` becomes `SENT` and `ChangeEvent.notified_at` is updated.

---

## 6. HTML Email & Plain-Text Fallback

- **Email Client Compatibility**: Uses clean, table-based layouts with inlined CSS.
- **Zero JavaScript**: No external dependencies or executable scripts.
- **HTML Sanitization**: All scraped strings (titles, venues, team names, field values) are escaped via `html.escape()`.
- **Plain-Text Alternative**: A structured, complete plain-text fallback is generated for every digest.
- **Normalized Source Links**: Clickable links use normalized FanCode URLs with tracking parameters stripped.

---

## 7. Email Backends

1. **Console Backend (`EMAIL_BACKEND=console`)**:
   - Prints formatted email headers and plain-text digests to stdout.
   - Optionally saves rendered `.html` and `.txt` files to `NOTIFICATION_OUTPUT_DIR`.
   - Default for local development and testing.

2. **Test Backend (`EMAIL_BACKEND=test`)**:
   - Stores dispatched messages in an in-memory list for unit and integration testing.
   - Supports simulated delivery failures.

3. **SMTP Backend (`EMAIL_BACKEND=smtp` or `SMTP_ENABLED=true`)**:
   - Production delivery via `smtplib`.
   - Supports TLS encryption (`SMTP_USE_TLS=true`), authentication, and configurable timeouts.

---

## 8. Configuration

Configure settings via `.env` or environment variables:

```ini
NOTIFICATION_ENABLED=true
EMAIL_BACKEND=console
SMTP_ENABLED=false
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@example.com
SMTP_PASSWORD=secret
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=15
ALERT_EMAIL_FROM=alerts@fancode-monitor.local
ALERT_EMAIL_TO=admin@fancode-monitor.local
ALERT_EMAIL_CC=
ALERT_EMAIL_BCC=
NOTIFICATION_MAX_EVENTS_PER_BATCH=100
NOTIFICATION_OUTPUT_DIR=data/notifications
```

---

## 9. CLI Usage

Run manual notification checks or inspect rendered digests:

```bash
# Dry run: view what would be sent without dispatching or updating DB status
python run_notifications.py --dry-run

# Normal run using default backend (Console or configured SMTP)
python run_notifications.py

# Filter by entity type or severity
python run_notifications.py --entity-type MATCH --severity CRITICAL

# Output rendered HTML/text files to a directory
python run_notifications.py --output-dir data/notifications --backend console

# JSON output mode for programmatic consumption
python run_notifications.py --json
```

---

## 10. Security Considerations

- **Credential Safety**: SMTP passwords and usernames are never logged or embedded into email bodies.
- **XSS & Injection Protection**: All dynamic data from web pages is strictly sanitized before inserting into HTML templates.
- **Environment Isolation**: `.env` is ignored in Git and `.env.example` contains only safe placeholder values.
