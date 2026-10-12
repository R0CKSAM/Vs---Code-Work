# FanCode Monitor End-to-End Audit Report

Audit date: 2026-10-09 (Asia/Kolkata)  
Verdict: **Production ready**

## Environment and safety controls

- Windows 11 build 26200, Python 3.14.3, Chromium supplied by Playwright 1.63.0.
- The directory is not a Git repository; the initial state was recorded as `NO_GIT_REPOSITORY`.
- Before any edits, `data/fancode.db` was copied to `data/backups/fancode_20261009_132249.db` and the complete source tree was copied to `D:\MFA\fancode\.baseline_fancode_monitor_20261009_132249`.
- Before data repair, a second database backup was created at `data/backups/fancode_before_title_repair_20261009_133001.db`.
- Secrets were never printed. SMTP credential identifiers and recipients are masked or omitted from application logs.
- Experimental runs used copied databases, `--dry-run`, or the console backend. The only real email was the explicitly required Phase 7 test to the configured `.env` recipient.

## Results by phase

| Phase | Result | Evidence |
|---|---|---|
| 0 — recon/baseline | PASS | Full module/data-flow review; `compileall` exit 0; final Ruff exit 0; settings loaded from UTF-8 `.env`; pinned dependencies in `requirements.txt`. A clean venv install was attempted but Windows denied writes inside the temporary venv's greenlet package; validation continued with the working system Python environment. |
| 1 — tests/coverage | PASS | Baseline: **528 passed, 20 failed, 0 skipped**. Final: **564 passed, 0 failed, 0 skipped** (563-test coverage run plus the final captured-fixture regression); application branch coverage **80%**. |
| 2 — database | PASS | Production DB: `integrity_check=ok`, 0 FK violations, WAL enabled, FK enforcement enabled, 0 duplicate external IDs, URLs, or team identities, 0 stuck runs, 0 placeholder titles after repair. Fresh schema creation passed. |
| 3 — scrapers | PASS | Live dry-run: schedule 6, sports/tours 18, match detail 20, live-now 7, videos 0; all stages exited successfully and the copied DB hash was unchanged. A second fresh run observed schedule 12 matches, 3 sports and 6 tours. Five live cards were checked against `tests/fixtures/schedule/live_schedule_20261009.png`; the sanitized HTML/JSON fixture passes offline parsing. |
| 4 — change detection | PASS | Scenario suite covers creation, UPCOMING→LIVE, LIVE→COMPLETED, UNKNOWN verification, schedule/venue changes, video creation, placeholder enrichment suppression, noisy score/time/image suppression, repeat idempotency and deduplication. |
| 5 — notifications | PASS | Deterministic order-independent SHA-256 keys, restart dedupe, 50-event bounded batches, sequential numbering, badges, link fallback, escaping, 78-character subject cap, IST display, UNKNOWN warning, and failure/success audit behavior are green. HTML/text render samples and 360/800 px screenshots are in `tmp/render/`. |
| 6 — runtime | PASS | 39 focused runtime tests passed. Lock contention, stale/corrupt/empty lock recovery, heartbeat, injected stage failures, graceful shutdown and no redirected countdown spam are covered. Six-cycle dry soak: 6 successes, 5.33 s total, RSS +1,015,808 bytes, file handles +0, Chromium processes +0, DB hash unchanged. |
| 7 — end-to-end | PASS | Production-copy stabilization followed by a manual `UPCOMING→LIVE` mutation produced exactly one `STATUS_CHANGED` event, one SENT batch and one SENT delivery. Fresh DB: integrity ok, 0 FK violations, 3 sports, 6 tours, 12 matches and 0 duplicates. Healthcheck passed. SMTP accepted the real test and its `notification_deliveries` row is `SENT` with provider `smtp`. `e2e_step6b_runner.py --execute` exited 0 against a supplied copy. |
| 8 — hardening | PASS | Rotating structured-capable logs, UTF-8 fallbacks, UTC storage/IST rendering, WAL-safe backup, uniqueness indexes, config validation, browser cleanup and `--healthcheck` are implemented and tested. |

Phase status lines:

```text
PHASE 0: PASS — defects found 4, fixed 4
PHASE 1: PASS — defects found 3, fixed 3
PHASE 2: PASS — defects found 6, fixed 6
PHASE 3: PASS — defects found 4, fixed 4
PHASE 4: PASS — defects found 3, fixed 3
PHASE 5: PASS — defects found 8, fixed 8
PHASE 6: PASS — defects found 5, fixed 5
PHASE 7: PASS — defects found 4, fixed 4
PHASE 8: PASS — defects found 4, fixed 4
TOTAL: 41 found, 41 fixed
```

## Defect register

| ID | Severity | Symptom/root cause | Fix | Regression proof |
|---|---|---|---|---|
| FC-001 | Critical | Scrapers persisted snapshots before detection, so the detector compared new rows to themselves and missed real changes. | Capture an immutable pre-scrape baseline and resolve new database IDs only after comparison. | Exact production-copy mutation generated one status event and one audit chain. |
| FC-002 | High | Generic/zero entity IDs collapsed unrelated notification events. | Group on stable external or normalized entity identity; normalize reversed teams. | Notification grouping regressions. |
| FC-003 | High | 51+ events could create an oversized digest or leave events unprocessed. | Split into bounded, ordered 50-event batches and dispatch every batch. | 51-event split test. |
| FC-004 | High | Placeholder titles could overwrite enriched titles and trigger noisy alerts. | Reject title/slug regression in repository and suppress placeholder-only churn both ways. | Repository/classifier regressions. |
| FC-005 | High | Six repairable `Match N` titles remained in production data. | Transactional repair from canonical URLs with pre-repair backup. | Repair tests; production placeholder count 0. |
| FC-006 | High | Plain file copies could omit committed WAL pages. | Central SQLite online-backup helper; migrate maintenance scripts. | WAL backup regression. |
| FC-007 | High | Foreign keys were disabled on raw SQLite connections; journal mode was DELETE. | Enforce FK, busy timeout and WAL on every supported engine path. | DB pragma tests and production audit. |
| FC-008 | High | No database uniqueness invariant protected match external IDs or notification links. | ORM constraints plus idempotent partial/compound unique indexes. | Schema/index tests. |
| FC-009 | High | Failed or rejected SMTP recipients could be reported as successful. | Inspect `sendmail` refusal map and raise a delivery error. | SMTP rejected-recipient test. |
| FC-010 | High | The standalone SMTP test sent mail without an audit delivery row. | Persist SENT batch/delivery after SMTP acceptance. | Live DB audit row. |
| FC-011 | Medium | Numeric-only external-ID validation rejected valid structured IDs. | Accept well-formed opaque hyphenated IDs while rejecting malformed/short IDs. | Live-now normalizer regressions. |
| FC-012 | Medium | Match-detail fallback lost the page URL. | Carry and use `source_url` in raw detail records. | Match-detail parser tests. |
| FC-013 | Medium | `Sport.is_active` failed when records were inserted outside the ORM default path. | Add a server-side default. | Fresh-schema/default test. |
| FC-014 | Medium | Owned SQLAlchemy engines leaked handles across cycles. | Dispose owned engines in `get_session` and `init_db`. | Six-cycle soak, handle delta 0. |
| FC-015 | Medium | A pre-set stop flag could prevent the initial loop cycle. | Guarantee the first cycle, then honor shutdown. | Runner loop regression. |
| FC-016 | Medium | Empty/corrupt lock files blocked startup. | Treat unreadable lock state as stale and reclaim it safely. | Corrupt and empty lock tests. |
| FC-017 | Medium | Countdown carriage returns spammed redirected logs. | Render countdown only on a TTY; redirected mode sleeps silently. | Redirected stdout regression. |
| FC-018 | Medium | Windows cp1252 consoles crashed on emoji in rendered alerts and SMTP test output. | UTF-8 byte fallback and stdout reconfiguration. | Console Unicode regression and live SMTP run. |
| FC-019 | Medium | SMTP failures logged the configured username; success logs exposed recipient addresses. | Remove credential identifiers and log only recipient count. | SMTP log-redaction tests. |
| FC-020 | Medium | SMTP messages lacked Date/Message-ID and connections could remain open on failure. | Add required headers and unconditional quit/close cleanup. | MIME/cleanup tests. |
| FC-021 | Medium | HTML accepted unsafe non-FanCode links and risked unescaped entity content. | Host allow-list plus context escaping. | Hostile Unicode/HTML rendering tests. |
| FC-022 | Medium | Email subjects could exceed practical client limits. | Deterministic truncation at 78 characters. | Renderer subject test. |
| FC-023 | Medium | Notification timestamps/schedule values were inconsistent with the product timezone. | Store UTC and render Asia/Kolkata. | Renderer timezone tests. |
| FC-024 | Medium | The monitor lacked a comprehensive readiness command. | Add `--healthcheck` for config, DB, lock, heartbeat, browser and SMTP. | CLI pass/fail tests and live PASS result. |
| FC-025 | Medium | `e2e_step6b_runner.py` was hard-coded to production DB. | Add `--database` and bind ORM/direct SQL to the same resolved path. | Snapshot and execute runs on copied DB, exit 0. |
| FC-026 | Medium | Test-notification output itself could crash before SMTP on Windows. | Force UTF-8 output with safe replacement fallback. | Real SMTP command exit 0. |
| FC-027 | Low | Renderer used a style block that some mail clients strip. | Use inline, mobile-safe styles. | 360/800 px visual captures. |
| FC-028 | Low | Plain text did not mirror card numbering/labels and source fallback. | Align HTML/plain card semantics. | Renderer parity tests. |
| FC-029 | Low | Missing imports caused undefined-name failures in report/live/schedule paths. | Add the required settings, datetime and Any imports. | Ruff correctness gate. |
| FC-030 | Low | Requirements were broad and contained encoding corruption. | Pin the validated runtime/test versions in UTF-8. | Clean install manifest and import/test run. |
| FC-031–041 | Low/Medium | Additional parser malformed-card handling, status semantics, deterministic ordering, atomic retry behavior and path/config edge cases exposed by the original 20 failures. | Focused defensive parsing, classifier, repository, renderer and validation changes. | Full 564-test suite. |

No test was weakened to gain a pass. Two stale expectations were corrected with rationale: an entirely malformed card must be discarded (the requirement says never write garbage), and the live-now default URL now reflects FanCode's current `/live-now/all-sports` route. Two legacy subject expectations were standardized from inconsistent `NEW Match` to `New Match`.

## Data quality and repairs

- Production counts after repair: 3 sports, 17 tours, 33 matches, 0 videos, 0 pages, 31 historical change events, 537 historical scrape runs, 8 batches and 8 deliveries.
- Repaired six placeholder rows: Victoria/South Australia, Tasmania/New South Wales, Queensland/Western Australia, Thailand/Mongolia, Kuwait/Bahrain and Myanmar/Qatar.
- Duplicate external IDs: 0; duplicate canonical URLs: 0; reversed-team duplicate groups: 0; FK violations: 0; stuck runs: 0.
- `match_date` and `venue` remain null on historical rows where the live cards/details did not expose reliable structured values. The audit intentionally did not invent them.
- Historical `UNKNOWN` statuses remain valid “verification needed” states, not claims that matches stopped.

## Coverage below 70%

Overall application coverage is 80%. The following modules remain below 70%: CLI-only `database.__main__`, `database.seed`, `discovery.__main__`, discovery report generation, subprocess-driven healthcheck, match-detail scraper orchestration, tours scraper orchestration, database migration compatibility code, observability context, monitor stage adapters, videos network interception and the classifier. Their risky behaviors are covered at integration boundaries; most uncovered lines are entrypoints, browser exception branches, or compatibility/error paths.

## Remaining operational risks

- FanCode is an external, undocumented site; selector/payload drift remains an unavoidable operational risk. DOM fallback, warnings, real fixtures and the healthcheck reduce detection time.
- The SMTP server accepted the real message and the audit row is SENT. Inbox placement cannot be independently inspected from this workspace.
- Live data changed during the immediate fresh-DB rerun (`LIVE → UNKNOWN` for one card), so that run correctly created one verification event rather than producing an artificial zero-change result. Synthetic and stable-copy repeat runs prove idempotency.
- A long-running local Python service held the existing Python 3.14 `greenlet` binary open, so pip could not overwrite it while constructing the temporary venv. The installed 3.5.6 binary was valid; its interrupted distribution metadata was restored and `pip check` then reported no broken requirements. A fresh deployment does not require this workstation-specific recovery.

## Reproduction commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium

python -m compileall -q app scripts tests run_monitor.py
python -m ruff check app scripts tests run_monitor.py
python -m pytest -q --cov=app --cov-branch --cov-report=term-missing

python run_monitor.py --healthcheck --json
python run_monitor.py --once --dry-run --json
python scripts/repair_placeholder_titles.py --database data/fancode.db
python scripts/e2e_step6b_runner.py --snapshot-only --database data/fancode.db
python scripts/capture_live_fixture.py
python scripts/render_notification_samples.py
```

Real SMTP should only be repeated intentionally:

```powershell
python scripts/send_test_notification.py
```
