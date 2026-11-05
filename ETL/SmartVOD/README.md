# SmartVOD

Local VOD audience explorer, loaded with 6 October–4 November 2026 (30 days, including 31 October). Open http://127.0.0.1:8766 while the server is running. Initial view/reset selects the latest loaded day; use the date inputs to explore history.

From the workspace root:

```powershell
.\ETL\SmartVOD\run.ps1
```

Prepare another available export (a private version is built first; the running server switches after successful publication):

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --date 2026-11-04
# Repeat --date to include multiple days. The chosen dates replace the local dataset.
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --date 2026-11-03 --date 2026-11-04
# Load the latest 30 days, or add/update dates without removing existing history:
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --history-days 30
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --date 2026-11-05 --incremental
```

## Filters and metrics

- Searchable multi-select: title, category, video key, device ID, client IP, OS, region, decoded ISP/ASN, device type, identity confidence and title quality. Empty selection means all. Values within a field use OR; different fields use AND.
- Options reflect other draft filters and date/time selections. Options are paginated in batches of 100; search covers all matching values, not just the visible page. “Select shown” selects only the displayed options.
- Apply updates every metric/chart/table. Draft selections do not change the currently applied results. CSV exports the **applied** selection, including all matching content groups, not just the top-100 table.
- Date range is inclusive. Time is IST, minute-level and inclusive, repeated daily across the range. A reversed clock range selects an overnight window (for example 23:00–01:00); date bounds still apply to each record's calendar date.
- Region values contain country / state / city and can be searched by any component. ISP labels use `ETL/data/asn/asnDecoded.csv`; unresolved ASNs remain explicitly unknown.
- Watch hours come directly from the existing export: six seconds per segment request. Successful-delivery hours count 2xx requests only. Neither metric proves actual playback or measures buffering.
- Unique counts exclude missing IDs/IPs. Device IDs and IPs are not people; do not sum grouped distinct counts to obtain global viewers. Source identities may be inferred by the existing ETL; this project does not strengthen their reliability.
- Source CSVs and production dashboards are not modified. This is a separate local SQLite store, read-only during serving. Raw IDs/IPs stay on the local machine; the server binds only to 127.0.0.1.

## Audit

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/audit.py
```

The starter audit uses 4 November and checks totals against source CSV, filter OR/AND behavior, time bounds, decoded ISP lookup, filtered CSV totals, actual browser interactions, downloads, invalid input, and layouts from 320px to 1920px. Results and screenshots are saved under `audit/`.

Files: `prepare.py` imports data, `server.py` serves parameterized query APIs, `web/` contains the responsive UI, `run.ps1` starts the app. `data/` and generated screenshots are excluded from Git.

## Daily refresh, titles and workspace tools

- Scheduled task `SmartVOD Daily Refresh` runs `refresh.ps1` daily at 09:00 local/IST with StartWhenAvailable and no overlapping task instances. The machine must be available and have access to the shared lake. The current Windows task account must be able to run it. It adds completed days, reimports changed exports and preserves existing history. Manual run: `.\ETL\SmartVOD\refresh.ps1`.
- Missing future exports are generated into SmartVOD's own `data/sources` only after STREAM full-day structural validation. Incomplete days are skipped explicitly in `data/refresh_status.json`; failed imports preserve the prior published snapshot. A subsequent refresh retries uncompleted dates. No production export or dashboard is overwritten.
- Publication uses versioned SQLite databases and an atomic manifest pointer. The latest two versions are retained; older unlocked versions are removed after successful publication. Refresh is idempotent when inputs, ASN lookup and overrides are unchanged.
- Titles are reconciled by **host + video key**, preserving `raw_title`. Log titles with mapping evidence rank ahead of unsupported titles, then by segment volume. Multiple distinct labels are flagged **Conflicting log titles**; a consistent log title still is not an authoritative content-catalog verification. Unknown titles stay unknown. Download the title review from the page. To supply an authoritative correction, add `host,video_key,title,evidence` to `title_overrides.csv` and refresh; empty evidence is rejected. No titles are invented.
- Identity confidence is derived per row. **Direct Device ID** requires a matching device ID in a direct request query. Manifest-inferred identities remain explicitly inferred; missing or unverified IDs are not promoted. Counts describe devices, not people.
- Dropdown sort supports segment count descending, estimated hours descending, A–Z and Z–A, with stable paging. Device explorer shows the top 20 matching devices by estimated hours; click one to apply its ID and open the journey. Search the Device ID filter for other devices.
- Save/load/delete named views using browser localStorage. Views contain the applied filters, dates, times, sort and layout. Copy view link encodes the same state in the URL fragment (not server logs). Links may contain IDs/IPs; they work on the machine serving this localhost app, not a remote colleague's machine. No external sharing service is used.
- Journey CSV includes every scoped session, not only the visible previous/next cards, with device, title, key, host, first/last request, estimated minutes, segment count, identity confidence, title quality, content-match flag and overlap flag.

Run `audit_upgrade.py` for the post-upgrade source totals, host-scoped title joins, confidence classification, all 55 field pairs, all four sorting modes, saved/shareable views, journey CSV, drill-down and responsive-layout audit. Earlier audit JSON files record earlier versions and should not be presented as current post-upgrade results.

### Extended combination audit

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/audit_combinations.py
.\venv\Scripts\python.exe ETL/SmartVOD/audit_interactions.py
```

The combination audit constructs an independent oracle from the original CSV and ASN lookup. It covers all 511 nonempty subsets of the nine filter dimensions using a representative matching record, all 36 field pairs with multi-select values, 80 seeded randomized multi-select/time combinations, unknown and absent values, date/minute boundaries, cascading facet self-exclusion, pagination, literal special-character search, export reconciliation and invalid API input. This covers every dimension combination, not every possible combination of individual values.

The interaction audit checks cumulative browser filters, reopen/clear/reset, 200-option pagination and selection, hidden-selection preservation during search, applied-versus-draft export behavior, a delayed-query pending-state regression, and keyboard focus containment. Results are saved to `audit/combinations.json` and `audit/interactions.json`.

## Viewer journey

### Device ID / Client IP basis

Use **Audience basis** above saved views, then Apply. The basis controls the explorer cards, journey selection, average estimated watch minutes and CSV basis labels. Device ID remains the default. IP mode represents activity at an address and can combine viewers behind NAT/shared networks or split a viewer across changing addresses; it is not a person-level journey. Other explicit filters, including Device ID and identity confidence, remain in force when switching basis.

Average minutes = estimated watch minutes on rows with a known selected-basis identifier / distinct known identifiers on those same rows. Missing identifiers are excluded from both numerator and denominator; an empty denominator displays N/A. The content table computes this per host/video/title group; it is not average session duration. Saved views and local view links preserve the basis. Journey CSV uses `identity_basis` and `identity_value`; standard CSV also includes the basis and group-level average minutes. Group averages are not additive.

`audit_identity_basis.py` verifies both bases against SQL, missing-only selections, per-content averages, scoped journeys, exports, saved-state restoration and mobile layout.

Select exactly one known Device ID, choose the date/time range and click Apply. Viewer Journey shows the observed sequence with previous-five and next-five sessions around the selected session. Click a session card or the full timeline to change the center; Previous/Next match moves between content-filter matches.

Date/time and non-content audience filters apply to journey evidence. Title/category/video-key filters highlight matches while preserving surrounding content. With multiple Device IDs or an unknown ID, the panel asks for one known device rather than mixing viewers.

Consecutive requests for the same video key and host form a session until content/host changes, a known request session-ID changes, or the gap exceeds 30 minutes. Exactly 30 minutes stays in the session. Ordering uses first request timestamps and deterministic tie-breaking; overlapping activity is flagged as ambiguous. Session watch minutes use the same request-based estimate as the rest of the dashboard, not wall-clock duration. Identity provenance distinguishes direct request IDs from manifest-inferred IDs. Data outside the loaded/filtered period is not included; journeys can be incomplete at those boundaries.

Run `python ETL/SmartVOD/audit_journey.py` from the workspace with its venv interpreter to repeat grouping, real-device reconciliation and browser navigation checks.
