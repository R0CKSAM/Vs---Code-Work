# FanCode Monitor — Scheduler & Continuous Monitoring Engine (Phase 10)

## 1. Overview & Architecture

The **Scheduler & Continuous Monitoring Engine (Phase 10)** serves as the top-level orchestrator for the entire FanCode monitoring pipeline. It connects all individual scraper components, change detection, and notification delivery into a reliable, single-command or continuous daemon execution.

```
                  ┌────────────────────────────────────────┐
                  │   MonitorRunner / CLI (run_monitor)    │
                  └──────────────────┬─────────────────────┘
                                     │ (Exclusive File Lock)
                                     ▼
                  ┌────────────────────────────────────────┐
                  │            MonitorPipeline             │
                  └──────────────────┬─────────────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
1. ScheduleScraper            2. SportsToursScraper         3. MatchDetailScraper
       │                             │                             │
       └─────────────────────────────┼─────────────────────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
4. LiveNowScraper             5. VideosScraper              6. ChangeDetector
       │                             │                             │
       └─────────────────────────────┼─────────────────────────────┘
                                     │
                                     ▼
                            7. NotificationService
                                     │
                                     ▼
                              Email / Console
```

---

## 2. Pipeline Stages & Order

The pipeline executes stages in deterministic sequence with dependency awareness:

| # | Stage Name | Responsibility | Fatal? | Scraped Data Produced |
|---|---|---|---|---|
| **1** | `schedule` | Upcoming fixtures across days | No | Matches |
| **2** | `sports` | Sports categories & tournaments | No | Sports, Tours |
| **3** | `match_detail` | Detailed venue & team enrichment | No | Enriched Matches |
| **4** | `live_now` | Active in-progress matches | No | Live Matches |
| **5** | `videos` | Match highlights & clips | No | Videos |
| **6** | `change_detection` | State diffing against database | No | `change_events` |
| **7** | `notifications` | Batching, rendering, and delivery | No | Email Digests |
| *Opt* | `discovery` | Broad full-site URL crawl | No | Discovered Pages |

*Note: Discovery is skipped by default in regular monitor runs for speed and operational efficiency, but can be included with `--include-discovery`.*

---

## 3. Locking & Concurrency Control

To prevent concurrent monitor runs from overlapping or racing on database transactions, `MonitorLock`:
1. **Exclusive Lock File (`data/monitor.lock`)**: Created atomically using OS-level exclusive file creation.
2. **Lock Metadata**: Stores process ID (`pid`), UTC creation timestamp (`created_at`), host name (`hostname`), and `run_id`.
3. **Stale Lock Recovery**:
   - Checks if the process holding the lock is still alive on Windows (`OpenProcess`) or Unix (`os.kill(pid, 0)`).
   - Checks if the lock age exceeds `MONITOR_LOCK_TIMEOUT_SECONDS` (default: 1800s / 30m).
   - If stale, logs a warning and safely reclaims the lock.
4. **Collision Handling**: If an active lock is held, subsequent monitor processes immediately exit with status `SKIPPED` (Exit code: 3) without executing scrapers or sending alerts.

---

## 4. Failure Isolation & Bounded Retries

- **Failure Isolation**: If a single scraper stage encounters a network timeout or parsing issue, it is marked as `FAILED`, and the pipeline continues executing remaining independent stages.
- **Bounded Retries**: Failing stages are retried up to `MONITOR_MAX_RETRIES` (default: 1) with `MONITOR_RETRY_DELAY_SECONDS` backoff before moving forward.
- **Notification Safety on Failure**: If scrapers or change detection fail, the notification stage only processes legitimately generated change events and never invents notifications. If notifications fail, change events remain unnotified in the database and are safely retried during the next cycle.

---

## 5. Execution Modes

### A. One-Shot Mode (`--once`)
Executes exactly one complete pipeline cycle, commits audit records, releases the lock, and exits with a standard process exit code:
```bash
python run_monitor.py --once
```

### B. Scheduled Recurring Mode (`--interval`)
Runs continuously, executing the pipeline at the configured interval (default: 300s):
```bash
# Poll every 5 minutes (default)
python run_monitor.py

# Poll every 2 minutes (120 seconds)
python run_monitor.py --interval 120
```

### C. Dry-Run Mode (`--dry-run`)
Simulates the entire pipeline without mutating database entities or dispatching real emails:
```bash
python run_monitor.py --once --dry-run
```

---

## 6. Health & Status Check

Query current system health, lock status, and the most recent pipeline execution without starting a new scrape run:
```bash
python run_monitor.py --status
```

JSON output format for machine integration:
```bash
python run_monitor.py --status --json
```

---

## 7. Configuration Settings

| Setting | Default | Description |
|---|---|---|
| `MONITOR_ENABLED` | `true` | Enables or disables monitoring subsystem |
| `MONITOR_INTERVAL_SECONDS` | `300` | Polling interval between cycles in continuous mode |
| `MONITOR_RUN_TIMEOUT_SECONDS` | `900` | Maximum allowable duration for a single pipeline run |
| `MONITOR_STAGE_TIMEOUT_SECONDS` | `300` | Per-stage timeout limit |
| `MONITOR_MAX_RETRIES` | `1` | Maximum retries for a failed stage |
| `MONITOR_RETRY_DELAY_SECONDS` | `2.0` | Delay between retry attempts |
| `MONITOR_LOCK_ENABLED` | `true` | Enables exclusive file lock |
| `MONITOR_LOCK_FILE` | `data/monitor.lock` | Filepath for exclusive lock |
| `MONITOR_LOCK_TIMEOUT_SECONDS` | `1800` | Maximum age before considering a lock stale |
| `MONITOR_NOTIFICATION_ENABLED` | `true` | Enables or disables notification stage |

---

## 8. CLI Options Reference

```
usage: run_monitor.py [-h] [--once] [--interval INTERVAL] [--dry-run]
                      [--status] [--stage STAGE] [--skip-discovery]
                      [--include-discovery] [--skip-notifications]
                      [--max-retries MAX_RETRIES] [--headed] [--json]

options:
  --once                Execute exactly one pipeline cycle and exit immediately
  --interval INTERVAL   Polling interval in seconds for continuous scheduled execution
  --dry-run             Simulate pipeline execution without committing database mutations
  --status, --health    Display current system health, lock state, and recent run summary
  --stage STAGE         Execute only a specific pipeline stage
  --skip-discovery      Skip broad link discovery crawler (default: True)
  --include-discovery   Include discovery crawler in the cycle
  --skip-notifications  Skip notification dispatching stage
  --max-retries N       Maximum retry attempts per failed stage
  --headed              Run browser in visible mode
  --json                Print output as machine-readable JSON
```

---

## 9. Exit Codes

- `0` = `SUCCESS` — Pipeline executed with all stages passing.
- `1` = `PARTIAL` — Pipeline completed with one or more non-fatal stage failures.
- `2` = `CONFIG_ERROR` — Invalid configuration or missing dependencies.
- `3` = `LOCKED` — Execution skipped because another monitor process holds the lock.
- `4` = `FATAL` — Fatal unrecoverable pipeline failure.
