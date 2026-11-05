# SmartVOD

Local VOD audience explorer, seeded with 4 November 2026. Open http://127.0.0.1:8766 while the server is running.

From the workspace root:

```powershell
.\ETL\SmartVOD\run.ps1
```

Prepare another available export (stop the SmartVOD server before replacing its database):

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --date 2026-11-04
# Repeat --date to include multiple days. The chosen dates replace the local dataset.
.\venv\Scripts\python.exe ETL/SmartVOD/prepare.py --date 2026-11-03 --date 2026-11-04
```

## Filters and metrics

- Searchable multi-select: title, category, video key, device ID, client IP, OS, region, decoded ISP/ASN and device type. Empty selection means all. Values within a field use OR; different fields use AND.
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

### Extended combination audit

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/audit_combinations.py
.\venv\Scripts\python.exe ETL/SmartVOD/audit_interactions.py
```

The combination audit constructs an independent oracle from the original CSV and ASN lookup. It covers all 511 nonempty subsets of the nine filter dimensions using a representative matching record, all 36 field pairs with multi-select values, 80 seeded randomized multi-select/time combinations, unknown and absent values, date/minute boundaries, cascading facet self-exclusion, pagination, literal special-character search, export reconciliation and invalid API input. This covers every dimension combination, not every possible combination of individual values.

The interaction audit checks cumulative browser filters, reopen/clear/reset, 200-option pagination and selection, hidden-selection preservation during search, applied-versus-draft export behavior, a delayed-query pending-state regression, and keyboard focus containment. Results are saved to `audit/combinations.json` and `audit/interactions.json`.

## Viewer journey

Select exactly one known Device ID, choose the date/time range and click Apply. Viewer Journey shows the observed sequence with previous-five and next-five sessions around the selected session. Click a session card or the full timeline to change the center; Previous/Next match moves between content-filter matches.

Date/time and non-content audience filters apply to journey evidence. Title/category/video-key filters highlight matches while preserving surrounding content. With multiple Device IDs or an unknown ID, the panel asks for one known device rather than mixing viewers.

Consecutive requests for the same video key and host form a session until content/host changes, a known request session-ID changes, or the gap exceeds 30 minutes. Exactly 30 minutes stays in the session. Ordering uses first request timestamps and deterministic tie-breaking; overlapping activity is flagged as ambiguous. Session watch minutes use the same request-based estimate as the rest of the dashboard, not wall-clock duration. Identity provenance distinguishes direct request IDs from manifest-inferred IDs. Data outside the loaded/filtered period is not included; journeys can be incomplete at those boundaries.

Run `python ETL/SmartVOD/audit_journey.py` from the workspace with its venv interpreter to repeat grouping, real-device reconciliation and browser navigation checks.
