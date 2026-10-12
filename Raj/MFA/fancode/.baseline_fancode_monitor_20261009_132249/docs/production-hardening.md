# Phase 11 — Production Hardening, Observability & Data Maintenance

This document details the hardening, observability, operational diagnostics, and maintenance architecture introduced in **Phase 11** for the **FanCode Monitor** platform.

---

## 1. Architecture Overview

Phase 11 hardens the continuous monitoring loop without altering scraper logic or notification semantics:

```text
               ┌────────────────────────────────────────────────────────┐
               │           Operational Observability Layer              │
               │   Structured Logging • Secret Redaction • Correlation  │
               └──────────────────────────┬─────────────────────────────┘
                                          │
    Scheduler / CLI ───► Configuration Validation ───► Stale Run Reclaim
           │                                                │
           ▼                                                ▼
     MonitorLock ────────────────────────────────────► Heartbeat Touch
           │                                                │
           ▼                                                ▼
     Pipeline Stages ───► Database Audit ───► Change Detection ──► Alerts
           │                                                │
           ▼                                                ▼
     Failure Isolation ◄─── Error Classification ◄── Operational Metrics
                                                            │
                                                            ▼
                                                   Data Retention Cleanup
```

---

## 2. Structured Logging & Secret Redaction

### Correlation Context
Every monitor execution generates a correlated context attached to all logs:
- `run_id`: Unique identifier of the pipeline run.
- `stage`: Current stage being executed (e.g., `schedule`, `live_now`, `change_detection`).
- `scrape_run_id`: Associated database audit run ID.

### Secret Redaction Filter
The `SecretRedactionFilter` inspects log records and automatically masks:
- Passwords (`password=...`, `smtp_password=...`)
- Bearer tokens (`Authorization: Bearer ...`)
- API keys (`api_key=...`, `token=...`)
- Session cookies (`Cookie: session_id=...`)

Example formatted log:
```text
2026-10-07T09:30:12Z INFO  app.monitor.pipeline [run_id=42, stage=schedule, scrape_run_id=42]: Stage [schedule] finished with status SUCCESS in 4.21s
```

---

## 3. Operational Metrics

In-process metrics tracked by `MetricsRegistry`:
- **Cycles**: `monitor_cycles_total`, `monitor_cycles_success`, `monitor_cycles_failed`
- **Stages**: `stage_runs_total`, `stage_runs_success`, `stage_runs_failed`, `stage_retries_total`
- **Data**: `records_processed`, `records_created`, `records_updated`
- **Alerts**: `change_events_created`, `notifications_created`, `notifications_sent`, `notifications_failed`
- **Errors**: `database_errors`, `lock_failures`
- **Gauges**: `last_cycle_duration_seconds`

Metrics are queryable via CLI using:
```bash
python run_monitor.py --diagnostics --json
```

---

## 4. Health & System Status

System health evaluates database connectivity, lock state, heartbeat liveness, and run history across 4 distinct states:
- **`HEALTHY`**: Database connection and tables intact, no active unrecovered errors, recent runs successful.
- **`DEGRADED`**: System operational, but recent run failed or recoverable issues observed.
- **`UNHEALTHY`**: Database connection failed, required tables missing, or critical fatal dependency unavailable.
- **`UNKNOWN`**: Insufficient state information available.

Command:
```bash
python run_monitor.py --health
```

---

## 5. Heartbeat Tracking

The `HeartbeatManager` writes liveness metadata to `data/monitor.heartbeat`:
- Current process PID
- Last heartbeat UTC timestamp
- Current active stage (or `idle`)
- Cycle count
- Process uptime in seconds

Health diagnostics verify heartbeat freshness to distinguish between an idle process and a hung scraper stage.

---

## 6. Stale Run Reclamation

If a monitor process terminates abruptly (e.g., system power off, OOM), runs can be left in the `running` state in `scrape_runs`.

The stale run recovery engine (`reclaim_stale_runs`):
- Runs automatically before each pipeline execution cycle.
- Inspects runs in `running` status older than `STALE_RUN_TIMEOUT_SECONDS` (default: 1800s / 30m).
- Verifies process ownership; if the PID is still alive, the run is **not** touched.
- Safely marks abandoned runs as `stale_reclaimed`, records recovery metadata, and frees system audit state.

---

## 7. Data Retention & Safe Cleanup

Historical operational tables grow continuously during 24/7 monitoring. The `DataRetentionCleaner` provides safe purge operations:

### Protected Core Tables (Strictly NEVER Deleted)
- `sports`
- `tours`
- `matches`
- `videos`
- `pages`

### Operational Tables Cleaned
- `scrape_runs` (default: 30 days retention)
- `change_events` (default: 90 days retention)
- `notification_batches`, `notification_deliveries`, `notification_event_links` (default: 90 days retention)

### Commands
```bash
# Dry run simulation (reports purge counts without deleting)
python run_monitor.py --cleanup --dry-run

# Live cleanup (requires explicit --yes confirmation)
python run_monitor.py --cleanup --yes
```

---

## 8. Configuration Validation

All application settings are validated on startup (`validate_settings()`):
- Valid HTTP/HTTPS schemes for target endpoints
- Positive values for intervals, timeouts, and retention days
- Non-negative values for retries and backoff delays
- SMTP host and port validation when email alerts are enabled
- Sensitive secrets are omitted from all configuration error messages

---

## 9. Error Classification & Action Strategy

Exceptions are classified by `classify_error()` into explicit operational categories:

| Category | Typical Cause | Recommended Action |
|---|---|---|
| `NETWORK_ERROR` | Connection reset, DNS failure | `RETRY` |
| `TIMEOUT_ERROR` | Navigation or stage timeout | `RETRY` |
| `SCRAPER_ERROR` | DOM layout change, element missing | `CONTINUE` |
| `NOTIFICATION_ERROR` | SMTP delivery error, provider downtime | `CONTINUE` / `DEGRADE` |
| `LOCK_ERROR` | Concurrent instance active | `ABORT` |
| `DATABASE_ERROR` | SQLite lock, disk full, corrupted schema | `ABORT` |
| `CONFIGURATION_ERROR` | Invalid settings, negative timeout | `ABORT` |
| `INTERRUPTION` | User pressed Ctrl+C | `ABORT` (exit cleanly) |

---

## 10. CLI Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success / normal completion |
| `1` | Partial run or operational failure |
| `2` | Configuration validation error |
| `3` | Lock held by another process |
| `4` | Fatal database or dependency error |
| `130` | Process interrupted by user (Ctrl+C) |
