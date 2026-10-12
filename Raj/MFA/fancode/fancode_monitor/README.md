# FanCode Monitor

## Production setup and operation

From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Edit `.env` locally; never commit it. At minimum, review `DATABASE_URL`, browser timeouts, notification backend, SMTP TLS/SSL mode, sender and recipients. Validate the complete deployment before starting it:

```powershell
python run_monitor.py --healthcheck --json
python run_monitor.py --once --dry-run
python run_monitor.py --once
python run_monitor.py --interval 300
```

`--dry-run` performs no database writes and sends no email. Only use `scripts/send_test_notification.py` when an intentional real SMTP test to the configured `.env` recipient is desired.

Operational files are under `data/` and rotating logs under `logs/`. SQLite runs in WAL mode with foreign keys enabled. Back up a live database through `app.database.backup.create_sqlite_backup`; copying only `fancode.db` can miss committed WAL pages.

Troubleshooting:

- Healthcheck failure: inspect the named check in its JSON output, then `logs/`.
- Browser launch failure: run `python -m playwright install chromium` in the active environment.
- Lock held: do not delete a live lock. The monitor automatically recovers dead-PID, corrupt and empty locks.
- SMTP failure: confirm port 465 uses implicit SSL, while port 587 normally uses STARTTLS. Credentials are intentionally redacted from logs.
- Windows emoji/encoding issues: run in a UTF-8 terminal (`chcp 65001`); application output also has a UTF-8 fallback.
- Database concern: run `python scripts/e2e_step6b_runner.py --snapshot-only --database data/fancode.db`.

The complete validated evidence, known risks and reproduction commands are in [docs/E2E_TEST_REPORT.md](docs/E2E_TEST_REPORT.md). The notification-specific flow and failure semantics are in [docs/NOTIFICATION_AUDIT.md](docs/NOTIFICATION_AUDIT.md).

> **Phase 0 – Project Foundation & Test Infrastructure**

A production-quality monitoring and data-collection system for publicly
accessible [FanCode](https://www.fancode.com/) content.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Prerequisites](#prerequisites)
3. [Python Setup & Virtual Environment](#python-setup--virtual-environment)
4. [Install Dependencies](#install-dependencies)
5. [Install Playwright Browser](#install-playwright-browser)
6. [Environment Variables (.env)](#environment-variables-env)
7. [Running Tests](#running-tests)
8. [Running Headed Playwright Tests](#running-headed-playwright-tests)
9. [Test Results & Artifacts](#test-results--artifacts)
10. [Phase Roadmap](#phase-roadmap)

---

## Project Structure

```
fancode_monitor/
│
├── app/
│   ├── __init__.py
│   └── config/
│       ├── __init__.py
│       └── settings.py          ← Pydantic-Settings configuration
│
├── tests/
│   ├── e2e/
│   │   ├── conftest.py          ← Shared Playwright fixtures
│   │   └── test_fancode_smoke.py
│   └── unit/
│       └── test_settings.py
│
├── data/                        ← Collected data (git-ignored)
├── logs/                        ← Log files (git-ignored)
├── screenshots/                 ← Failure screenshots (git-ignored)
├── docs/                        ← Documentation
│
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
└── run_tests.py                 ← Convenience test-runner CLI
```

---

## Prerequisites

| Requirement | Minimum Version |
|-------------|----------------|
| Python      | 3.11            |
| pip         | 23+             |
| Git         | 2.x             |

---

## Python Setup & Virtual Environment

### Windows (PowerShell)

```powershell
# Verify Python version
python --version          # should print Python 3.11.x or higher

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.venv\Scripts\Activate.ps1

# If you see an execution-policy error, run first:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### macOS / Linux

```bash
python3 --version         # should print Python 3.11.x or higher
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` in your prompt after activation.

---

## Install Dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Install Playwright Browser

After installing Python packages, download the Chromium browser binary:

```bash
playwright install chromium
```

> **Tip:** This downloads ~120 MB of browser binaries to a local cache.
> You only need to run this once per machine (or after upgrading `playwright`).

To install **all** supported browsers (Chromium, Firefox, WebKit):

```bash
playwright install
```

---

## Environment Variables (.env)

1. Copy the example file:

   ```bash
   # Windows
   copy .env.example .env

   # macOS / Linux
   cp .env.example .env
   ```

2. Open `.env` in any text editor and adjust as needed:

   | Variable | Default | Description |
   |----------|---------|-------------|
   | `BASE_URL` | `https://www.fancode.com` | Target website URL |
   | `BROWSER_HEADLESS` | `true` | Run browser headlessly |
   | `BROWSER_SLOW_MO` | `0` | Slow-motion delay (ms) |
   | `BROWSER_TIMEOUT` | `30000` | Navigation timeout (ms) |
   | `BROWSER_VIEWPORT_WIDTH` | `1280` | Viewport width |
   | `BROWSER_VIEWPORT_HEIGHT` | `720` | Viewport height |
   | `LOG_LEVEL` | `INFO` | Logging verbosity |
   | `SCREENSHOT_DIR` | `screenshots` | Failure screenshot path |

---

## Running Tests

### All tests (headless, default)

```bash
# From the fancode_monitor/ directory
pytest

# Or via the convenience runner
python run_tests.py
```

### E2E tests only

```bash
pytest tests/e2e -v

# Via runner
python run_tests.py --e2e
```

### Unit tests only

```bash
pytest tests/unit -v

# Via runner
python run_tests.py --unit
```

### Specific test file

```bash
pytest tests/e2e/test_fancode_smoke.py -v
```

### Specific test by name

```bash
pytest tests/e2e/test_fancode_smoke.py::TestFanCodeSmokeBasic::test_page_loads_successfully -v
```

---

## Running Headed Playwright Tests

To watch the browser during test execution:

```bash
# pytest flag
pytest tests/e2e -v --headed

# Via runner
python run_tests.py --e2e --headed
```

### Slow-motion mode (useful for debugging)

```bash
# Add 500ms delay between each Playwright action
pytest tests/e2e -v --headed --slow-mo 500
```

### Override the base URL

```bash
pytest tests/e2e -v --base-url https://staging.fancode.com

# Via runner
python run_tests.py --e2e --base-url https://staging.fancode.com
```

---

## Test Results & Artifacts

| Artifact | Location | Description |
|----------|----------|-------------|
| Failure screenshots | `screenshots/` | Auto-captured on test failure |
| Logs | `logs/` | Application logs (Phase 2+) |
| Data | `data/` | Scraped data files (Phase 1+) |

> **Note:** `screenshots/`, `logs/`, and `data/` are listed in `.gitignore`
> and will not be committed to version control.

---

---

## Phase 1 — FanCode Discovery Engine

Phase 1 investigates and documents the publicly accessible FanCode site structure, extracts internal links, classifies pages, monitors network requests, and outputs discovery artifacts.

### Running Discovery

Run discovery via the module entrypoint or convenience runner:

```bash
# Using module entrypoint
python -m app.scraper.discovery

# Or using the root runner script
python run_discovery.py

# With custom limits
python run_discovery.py --max-pages 10 --depth 1 --headed
```

### Discovery Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `DISCOVERY_MAX_DEPTH` | `2` | Crawl depth starting from seed URL |
| `DISCOVERY_MAX_PAGES` | `30` | Maximum pages to visit per discovery run |
| `DISCOVERY_MAX_LINKS_PER_PAGE` | `50` | Maximum internal links extracted per page |
| `DISCOVERY_TIMEOUT_SECONDS` | `120` | Total wall-clock timeout for the run |
| `REQUEST_DELAY_SECONDS` | `1.5` | Politeness delay between page visits |
| `DISCOVERY_OUTPUT_DIR` | `data/raw/discovery` | Output directory for discovery JSON artifacts |

### Discovery Output Artifacts
- **JSON Output**: `data/raw/discovery/discovery_<timestamp>.json` contains all discovered pages, metadata, and observed network events.
- **Discovery Report**: `docs/discovery.md` summarizes observed vs assumed behaviors, page types, and scraping recommendations.

### Running Phase 1 Tests

```bash
# Run all tests (unit + E2E)
pytest -v

# Run Discovery unit tests only
pytest tests/unit/test_discovery_unit.py -v

# Run Discovery E2E Playwright tests only
pytest tests/e2e/test_discovery.py -v
```

---

---

## Phase 2 — Database & Persistence Layer

Phase 2 establishes the persistent data layer using SQLAlchemy 2.x and SQLite, including ORM models for all core entities, repository methods with deterministic upsert logic, schema verification, and diagnostic health checks.

### Database Initialization

```bash
# Initialize development SQLite database
python -m app.database
```

### Database Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/fancode.db` | SQLAlchemy database connection string |
| `DATABASE_ECHO` | `false` | Enable SQL query debug logging |

### Diagnostic Health API
A minimal diagnostic endpoint is available for monitoring connectivity:
- `GET /health`: Basic service heartbeat
- `GET /health/db`: Database connectivity and table schema verification

### Running Phase 2 Tests

```bash
# Run all tests (Phase 0 + Phase 1 + Phase 2)
pytest -v

# Run database unit tests only
pytest tests/unit/test_database.py -v

# Run database health Playwright tests only
pytest tests/e2e/test_database.py -v
```

---

---

## Phase 3 — FanCode Schedule Scraper

Phase 3 extracts structured match schedules, upcoming fixtures, and event metadata from FanCode and persists normalized records into SQLite.

### Running Schedule Scraper

```bash
# Scrape schedule and persist to database
python run_schedule.py

# Run in headed mode
python run_schedule.py --headed --max-items 20

# Run without modifying the database
python run_schedule.py --no-db
```

### Schedule Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `SCHEDULE_URL` | `https://www.fancode.com/schedule` | Target schedule URL |
| `SCHEDULE_MAX_ITEMS` | `100` | Maximum items to process per run |
| `SCHEDULE_TIMEOUT_SECONDS` | `60` | Navigation timeout in seconds |
| `SCHEDULE_WAIT_AFTER_LOAD_MS` | `3000` | Extra settle delay for hydration |
| `SCHEDULE_SAVE_RAW` | `false` | Save raw network responses to disk |

### Running Phase 3 Tests

```bash
# Run all tests (Phase 0 + 1 + 2 + 3)
pytest -v

# Run schedule unit tests only
pytest tests/unit/test_schedule_parser.py tests/unit/test_schedule_normalizer.py tests/unit/test_schedule_repository.py -v

# Run schedule Playwright tests only
pytest tests/e2e/test_schedule.py -v
```

---

---

## Phase 4 — FanCode Sports & Tours Scrapers

Phase 4 extracts sporting categories and tournaments/series/tours, persisting them to the database and establishing relational links with matches.

### Running Sports & Tours Scrapers

```bash
# Scrape sports categories
python run_sports.py

# Scrape tournaments / series
python run_tours.py

# Run in headed mode
python run_sports.py --headed
python run_tours.py --headed
```

### Running Phase 4 Tests

```bash
# Run all tests (Phase 0 + 1 + 2 + 3 + 4)
pytest -v

# Run sports unit & E2E tests
pytest tests/unit/test_sports_*.py tests/e2e/test_sports.py -v

# Run tours unit & E2E tests
pytest tests/unit/test_tours_*.py tests/e2e/test_tours.py -v
```

---

## Phase 5 — FanCode Match Detail Scraper & Enrichment

Phase 5 enriches existing matches discovered in Phase 3/4 with deeper metadata (accurate venue, team short names, scores, and finalized status) extracted from public FanCode match detail pages without overwriting known values.

### Running Match Detail Scraper

```bash
# Enrich up to 10 existing matches
python run_match_detail.py --limit 10

# Enrich a specific match URL
python run_match_detail.py --url "https://www.fancode.com/cricket/matches/ipl-2025/csk-vs-mi/10492"

# Enrich by database ID
python run_match_detail.py --match-id 42

# Run in headed mode
python run_match_detail.py --limit 5 --headed

# Dry-run without database modifications
python run_match_detail.py --limit 5 --no-db
```

### Running Phase 5 Tests

```bash
# Run all tests
pytest -v

# Run Match Detail unit & repository tests
pytest tests/unit/test_match_detail_*.py -v

# Run Match Detail Playwright E2E tests
pytest tests/e2e/test_match_detail.py -v
```

---

## Phase 6 — FanCode Live Now Scraper

Phase 6 extracts active fixtures taking place on FanCode, capturing real-time scores, streaming status, and enriching existing database matches with live states while strictly preserving previously known fields.

### Running Live Now Scraper

```bash
# Scrape Live Now and enrich database
python run_live_now.py

# Limit to top 10 live items
python run_live_now.py --max-items 10

# Run in headed mode
python run_live_now.py --headed

# Save raw intercepted payloads for offline inspection
python run_live_now.py --save-raw

# Dry-run without database modifications
python run_live_now.py --no-db
```

### Running Phase 6 Tests

```bash
# Run all tests
pytest -v

# Run Live Now unit & repository tests
pytest tests/unit/test_live_now_*.py -v

# Run Live Now Playwright E2E tests
pytest tests/e2e/test_live_now.py -v
```

---

## Phase 7 — FanCode Videos & Highlights Scraper

Phase 7 extracts publicly accessible video content (match highlights, replays, clips, and post-match interviews), normalizes categories and durations, associates them with existing matches, tours, and sports, and persists them idempotently into the SQLite database.

### Running Videos Scraper

```bash
# Scrape videos and persist to database
python run_videos.py

# Limit to top 20 video items
python run_videos.py --max-items 20

# Discover highlights for a targeted match
python run_videos.py --match-id "match-901"

# Run in headed mode
python run_videos.py --headed

# Save raw intercepted payloads
python run_videos.py --save-raw

# Dry-run without database modifications
python run_videos.py --no-db
```

### Running Phase 7 Tests

```bash
# Run all tests
pytest -v

# Run Videos unit & repository tests
pytest tests/unit/test_videos_*.py -v

# Run Videos Playwright E2E tests
pytest tests/e2e/test_videos.py -v
```

---

## Phase 8 — Change Detection Engine

### Running Change Detection

```bash
# Preview changes without database writes (dry run)
python run_change_detection.py --dry-run

# Run detection for specific entity type
python run_change_detection.py --entity-type MATCH

# Run authoritative snapshot detection (enables removal events)
python run_change_detection.py --complete-snapshot
```

### Running Phase 8 Tests

```bash
# Run change detection test suite
pytest tests/unit/test_change_*.py tests/e2e/test_change_detection.py -v
```

---

## Phase 9 — Alerting & Notification Engine

### Running Notifications

```bash
# Preview notification digests without sending (dry-run)
python run_notifications.py --dry-run

# Run notification engine using configured backend
python run_notifications.py

# Filter by entity type or severity
python run_notifications.py --entity-type MATCH --severity CRITICAL

# Output rendered HTML/text files to a directory
python run_notifications.py --output-dir data/notifications --backend console
```

### Running Phase 9 Tests

```bash
# Run Notification unit & E2E tests
pytest tests/unit/test_notification_*.py tests/unit/test_email_backend.py tests/e2e/test_notifications.py -v
```

---

## Phase 10 — Scheduler & Continuous Monitoring Engine

### Running Monitor

```bash
# Run one-shot monitor pipeline and exit
python run_monitor.py --once

# Dry-run execution without database commits or real alerts
python run_monitor.py --once --dry-run

# Run continuous scheduler polling every 5 minutes (default)
python run_monitor.py

# Run continuous scheduler with custom interval (e.g. 120 seconds)
python run_monitor.py --interval 120

# Query system health and latest run status
python run_monitor.py --status

# Output machine-readable JSON status
python run_monitor.py --status --json
```

---

## Phase 11 — Production Hardening, Observability & Data Maintenance

### Observability & Diagnostics

```bash
# Query system health, lock state, heartbeat, and last run
python run_monitor.py --health

# Run database integrity audit and view operational metrics
python run_monitor.py --diagnostics

# Output diagnostics as machine-readable JSON
python run_monitor.py --diagnostics --json
```

### Data Retention & Safe Cleanup

```bash
# Simulate retention cleanup (dry run - does not delete anything)
python run_monitor.py --cleanup --dry-run

# Execute safe operational data cleanup with explicit confirmation
python run_monitor.py --cleanup --yes
```

### Running Phase 11 Tests

```bash
# Run all Phase 11 observability and maintenance tests
pytest tests/unit/test_observability_*.py tests/unit/test_maintenance_*.py tests/unit/test_config_validation.py tests/unit/test_error_classification.py tests/unit/test_monitor_long_run.py tests/e2e/test_production_hardening.py -v
```

---

## Phase 12 — Final Production Runbook & Operations Guide

### 1. Installation & Fresh Deployment
```bash
# 1. Create and activate a clean virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browser engine
playwright install chromium

# 4. Configure environment
cp .env.example .env
# Edit .env with your deployment configuration

# 5. Initialize database tables
python -c "from app.database.connection import init_db; init_db()"
```

### 2. Monitoring Commands
```bash
# One-shot monitor execution (single cycle, exits immediately)
python run_monitor.py --once

# Safe dry-run execution (inspect without committing DB changes or sending alerts)
python run_monitor.py --once --dry-run

# Continuous automated monitoring (runs on schedule, default interval 300s)
python run_monitor.py --interval 300
```

### 3. Notification Dispatching
```bash
# Preview pending alert digests in dry-run mode
python run_notifications.py --dry-run

# Dispatch pending alerts using configured backend (console, test, or smtp)
python run_notifications.py

# Filter alerts by entity type and severity
python run_notifications.py --entity-type MATCH --severity CRITICAL
```

### 4. Observability & Diagnostics
```bash
# Check system health, lock status, and heartbeat
python run_monitor.py --health

# Run complete database integrity audit and metrics inspection
python run_monitor.py --diagnostics

# Output diagnostics as JSON
python run_monitor.py --diagnostics --json
```

### 5. Maintenance & Data Retention
```bash
# Simulate retention cleanup (dry run - safe preview)
python run_monitor.py --cleanup --dry-run

# Execute safe operational data cleanup (removes expired logs/runs, preserves core data)
python run_monitor.py --cleanup --yes
```

### 6. SMTP Email Testing & Operational Verification

> **Network Note for Gmail**: On restricted or residential networks where outbound connections to port 587 (`STARTTLS`) are blocked or time out, Gmail SMTP should be configured to use **port 465 with implicit SSL** (`SMTP_PORT=465` and `SMTP_USE_SSL=true`).

```bash
# 1. Test SMTP connectivity, TLS/SSL negotiation, and credentials without sending email
python -m app.notifications.smtp_test --check

# 2. Send one controlled test email to confirm end-to-end inbox delivery
python -m app.notifications.smtp_test --send-test

# Optional: Override recipient address for test
python -m app.notifications.smtp_test --send-test --to recipient@example.com
```

#### Gmail SMTP Setup Guidelines:
- **Host**: `smtp.gmail.com`
- **Port**: `465` (Implicit SSL via `smtplib.SMTP_SSL`)
- **Security**: `SMTP_USE_SSL=true`, `SMTP_USE_TLS=false`
- **Authentication**: Requires a dedicated **Google App Password** generated under *Google Account > Security > 2-Step Verification > App passwords*.
- **Caution**: Never use your standard Gmail account password in `.env`, and never commit `.env` to version control.


### 7. How to Verify the Monitor Is Working

To verify that the system is operating properly in production:

#### A. Check the Monitor Process
```bash
# Check system health, lock state, and heartbeat
python run_monitor.py --health
```
- Confirms whether a run is currently active or idle.
- Displays last heartbeat timestamp and lock owner.

#### B. Check Logs and Operational Diagnostics
```bash
# Run database integrity audit and metrics inspection
python run_monitor.py --diagnostics
```
- Confirms SQLite database integrity (`integrity_check: ok`).
- Displays counts of sports, tours, matches, videos, scrape runs, and change events.

#### C. Check Notification Delivery
```bash
# Test SMTP connectivity
python -m app.notifications.smtp_test --check
```
- Confirms the outbound SMTP gateway is reachable and authorized.

#### D. Operational Health Check Sequence
Follow this checklist to confirm end-to-end health:
1. **Monitor process running / scheduled**: Check with `python run_monitor.py --health`.
2. **Recent heartbeat exists**: Confirmed by `data/monitor.heartbeat` timestamp.
3. **Last scrape cycle succeeded**: Shown in recent runs output.
4. **Database is healthy**: Confirmed via `python run_monitor.py --diagnostics`.
5. **No stale run**: Confirmed by diagnostics report (`stale_runs: 0`).
6. **Notification service has no failed delivery**: Confirmed via diagnostics delivery audit.
7. **SMTP test succeeds**: Verified via `python -m app.notifications.smtp_test --check`.

> **Note on Alert Frequency**: Receiving no email does **NOT** mean the monitor is broken. It simply indicates that no meaningful changes (e.g. status changes, new matches/videos) occurred on FanCode during the cycle. Ball-by-ball score fluctuations are intentionally filtered out to avoid alert fatigue.

### 8. Automated Testing
```bash
# Run complete test suite (quiet)
python -m pytest -q

# Run complete test suite with verbose output
python -m pytest -v

# Run Phase 12 validation suite only
python -m pytest tests/validation/ -v

# Run Playwright browser E2E tests
python -m pytest tests/e2e/ -v
```

### 9. Troubleshooting Guide
- **Configuration Errors (`ExitCode.CONFIG_ERROR = 2`)**: Validate all entries in `.env`. Ensure timeouts, intervals, and retention days are positive numbers and URLs are valid HTTP/HTTPS endpoints.
- **Database Errors / Corruption**: Run `python run_monitor.py --diagnostics` to check SQLite integrity. If corrupted, restore from backup or re-initialize using `init_db()`.
- **Stale Monitor Lock (`ExitCode.LOCKED = 3`)**: If a previous process was killed abruptly, `MonitorLock` automatically reclaims locks from dead PIDs. To manually clear if needed, remove `data/monitor.lock`.
- **Scraper Navigation / Playwright Timeout**: Verify network connectivity to `https://www.fancode.com`. Increase `BROWSER_TIMEOUT` in `.env` if operating on slow connections. Note that anti-bot protection is never bypassed.
- **Partial Pipeline Status (`PipelineStatus.PARTIAL`)**: Review logs in `logs/` to identify the failing non-fatal stage. Core data remains uncorrupted and subsequent stages continue.
- **SMTP Delivery Failure**: Check `SMTP_HOST`, `SMTP_PORT`, and credentials in `.env`. Emails fail safely without losing change events, allowing retry on the next cycle.

---

## Phase Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| **0** | Project foundation & test infrastructure | ✅ Complete |
| **1** | FanCode Discovery Engine | ✅ Complete |
| **2** | Database & Persistence Layer | ✅ Complete |
| **3** | FanCode Schedule Scraper | ✅ Complete |
| **4** | FanCode Sports & Tours Scrapers | ✅ Complete |
| **5** | Match Detail Scraper & Enrichment | ✅ Complete |
| **6** | Live Now Scraper | ✅ Complete |
| **7** | Videos & Highlights Scraper | ✅ Complete |
| **8** | Change Detection Engine | ✅ Complete |
| **9** | Alerting / Notification Engine | ✅ Complete |
| **10** | Scheduler & Continuous Monitoring Engine | ✅ Complete |
| **11** | Production Hardening, Observability & Data Maintenance | ✅ Complete |
| **12** | Final Production Validation & Deployment Readiness | ✅ Complete |

---

## Security & Scraping Policy

- Only publicly accessible endpoints are used.
- CAPTCHA, authentication, and paywalls are never bypassed.
- Requests respect the site's `robots.txt` directives.
- Rate limits are applied to avoid overloading the target server.
- No sensitive credentials, authentication tokens, or session cookies are stored in the database.
- Sensitive credentials (passwords, tokens, keys) are automatically redacted in application logs.




