# SmartVOD

The current full audit is saved in `audit/audit_report.html` and
`audit/audit_summary.json`. Repeat it with the workspace venv interpreter:
`audit_comprehensive_api.py`, `audit_comprehensive_ui.py`, then
`audit_final_journeys.py` (all under `ETL/SmartVOD`, with the server running).
These cover source/SQL reconciliation, all filter pairs, sorting, time windows,
both audience views, exports, saved/shared views, responsive layouts and error
handling. Closing a filter picker cancels its staged edits; its action button
commits them. Pending edits disable CSV export. Older query responses cannot
replace newer results or errors.

`audit_ux_walkthrough.py` exercises normal clicks, deliberate delays, connection
failure/Retry, pagination, sticky controls, contrast and short landscape screens.
`audit_ux_cache.py` verifies result-cache isolation and invalidation with
disposable database fixtures. The in-memory cache holds at most eight completed
views and is keyed by the actual database path, size, modification timestamp
and request. New data snapshots invalidate old cached results.

Queries show visible progress and completion feedback. After four seconds the
message confirms that processing is still underway; failed requests offer
Retry. Query requests time out after two minutes rather than waiting forever.
Previous results cannot be clicked during an update. Pending advanced changes
are labelled on More filters, and the filter bar stays reachable while scrolling.

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
- Delivery snapshot lists every observed HTTP status code in one neutral table: code, response description, segment-request count, share and estimated watch hours. Codes sort numerically, with Unknown last. No code or response family is highlighted; the former successful-delivery hero and meter are removed. Narrow panels scroll horizontally to keep counts on one line. Counts use the export's segment_count rather than the number of aggregated rows, and follow all applied filters. This covers the segment requests in the VOD export, not unrelated manifest or other CDN requests.
- Unique counts exclude missing IDs/IPs. Device IDs and IPs are not people; do not sum grouped distinct counts to obtain global viewers. Source identities may be inferred by the existing ETL; this project does not strengthen their reliability.
- Source CSVs and production dashboards are not modified. This is a separate local SQLite store, read-only during serving. Raw IDs/IPs stay on the local machine; the server binds only to 127.0.0.1.

## Audit

### Stakeholder insights

**Content decisions is now the default.** It reviews assets by `(req_host, video_key)` rather than grouping title text or reused keys across hosts. The content view exposes demand change, period-distinct known-ID reach, estimated minutes per known ID (known-ID hours only), ID activity on two or more selected dates, 2xx delivery share, first observed dates, audience mix and explicit catalogue-readiness limits. **Review last 7 days** is a shared-filter shortcut; publication age is not inferred from first observation.

The decision worklist is a review queue, not an automatic budget/catalogue action. Missing/unverified title checks, implausibly high request activity, missing identity and delivery checks precede promotion-test eligibility. SEO renames and historical aliases are normal, retained for the same asset, and do not block promotion-test screening. A promotion-test candidate needs a consistent/verified log label, at least 50 known IDs, 50% ID-hour coverage, complete comparison windows, at least 20% growth and at least the larger of 1 hour or 0.5% of current portfolio hours in additional estimated demand. A decline prompts investigation, not retirement; zero prior activity is labelled newly observed demand, not a new release. Source category can describe a placement rather than genre. Runtime/completion, player behaviour, publication/availability, impressions/CTR, costs, rights and revenue/ROI require additional authoritative inputs.

The shortlist combines the 100 highest-hour active assets and up to ten promotion/decline priorities each. Actions counts are catalogue-wide; search is shortlist-only. Focused asset evidence is scoped to the exact host/key. CSV exports preserve the same identity, comparison, quality and recommendation evidence. Audience brief, Regional trends, Rises & drops, Top audience and Change breakdown remain secondary views. Content and audience analyses load independently on tab changes.

The reviewed snapshot (6 October–9 November 2026) has 3,163 host/key assets and 3,152 distinct video keys. Approximately 63.7% of estimated hours have historical title aliases (legacy source status: Conflicting log titles), 29.0% have unknown titles, 48.7% have no source category and 49.1% lack a Device ID. Historical aliases include normal SEO edits and are not quality failures. Only missing/unverified labels contribute to the title-review percentage. The existing longer-history content mart is title-based and lacks host/key identity; it is not silently merged into this asset-level report. See `audit/content_data_inventory.json` and `audit/content_business_metric_matrix.csv` for the reviewed inputs and business decision matrix.

The Dashboard / Stakeholder insights menu shares the applied master filters. Insights has Executive brief, Regional trends, Rises & drops, Top audience, Change breakdown, and How this is measured tabs. It supports estimated hours, period-distinct known Device IDs or client IPs; country/state/city geography; and device/OS/ISP/title/category change breakdowns. The brief selects a small set of current leaders, material increases/decreases and daily review flags. Top audience ranks identifiers by estimated hours and can open the matching journey. CSV exports include comparison windows and the kind/coverage of baseline used.

Period change compares against the immediately preceding equal-length calendar range. Both ranges need every date loaded; otherwise comparison values are unavailable, not zero. Distinct counts are calculated across each whole period, not summed from daily counts. Regional movement screens for at least 20% change and an absolute change of at least the larger of 0.5% of current total or 1 hour / 10 identifiers. New activity has no fabricated percentage. Daily flags compare the selected final day with the median of up to seven prior loaded dates, requiring four dates, 30% change where a nonzero baseline exists, and a robust deviation score of 3. The Methods tab exposes the exact scale calculation and data limits. These rules do not prove causes, significance, source completeness or unique people.

Ask your data routes supported phrases (for example “Which regions dropped?”, “trend in Uttar Pradesh”, “Which ISP increased?” or “top client IPs”) to measured views and matching controls. It is a local intent router, not an unrestricted language model. Unmatched locations and unsupported questions are reported rather than substituted. The regional ranking is capped at 100 rows; all returned movement/alert rows retain their own trend series. Source filters can narrow larger datasets.

While Insights is active, applying master filters runs only the insight workload. Dashboard graphs refresh on return; pending analysis and navigation are coordinated to avoid showing stale graphs. The compact DuckDB projection uses two threads and a 1GB engine memory limit. It is built from the published SQLite snapshot, verifies row/hour/request totals, and is accepted only when the source path/size/mtime matches exactly. Snapshot preparation refreshes it automatically; failures leave the dashboard usable with an explicit slower analysis fallback. No schedules are enabled by these changes. Keep the existing environment's duckdb and pyarrow packages for acceleration. Manual rebuild:

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/insight_store.py
```

The initial projection contains 6,780,267 rows in approximately 267 MiB. One measured 35-day analysis took 131.72 seconds using SQLite and 5.25 seconds using the columnar projection; these are observed local timings, not a performance guarantee. Large historical Dashboard graph queries remain a separate workload.

Every watch-hour and audience graph has **Expand**. It opens a native modal with a larger plot, full category names, applied date/time scope, and the same chart modes and legend selections. Top 5 totals also expand as bars. **Close chart**, Escape, or clicking the backdrop returns to the dashboard and restores focus. Expansion uses the loaded results without another API request and does not change filters or saved panel geometry. Timeline position survives legend changes. **Show all lines** recovers hidden series; hiding every series produces an explicit message. Focus a plot and use Left/Right or Home/End to inspect points. The modal traps keyboard focus, keeps Close reachable, and adapts to phone/landscape screens. Comparison charts account for container padding so the final hour is not clipped.

The hourly chart has **Compare days** (one independently toggleable line per loaded date, on a shared 24-hour IST axis) and **Continuous** (consecutive hourly dates with horizontal scrolling, about one day per viewport). The watch-hour scale stays pinned while scrolling. Unloaded calendar dates are gaps; known dates with no matching requests have zero hours. Hover or tap the chart for exact values. Device type, OS, Region and ISP each offer **Totals**, **Daily/Hourly trend**, and **Hourly timeline**, using the same fixed Top 5 labels ranked across the applied selection. Their trend totals reconcile to the existing breakdown totals. Chart modes remain selected across filter refreshes in the current visit. All trends use the applied date, time and audience filters.

Delivery snapshot shows estimated hours, delivered hours and segment requests with equal emphasis. Per-code rows show requests, share and estimated watch hours, also with equal styling. Delivered hours represent 2xx requests; all watch-hour values remain request-derived estimates. Loading feedback is centered, including while the More filters drawer is open, with reduced-motion support and the existing error/Retry behavior.

Journey cards are hidden until exactly one known identifier is applied for that basis; missing, Unknown, or multiple selections leave no empty layout tile. Device ID and Client IP visibility are independent. The hourly chart uses two-thirds of the default wide-screen row; below 1200px it and Delivery snapshot each occupy a full row. The former spacing/density selector is removed; older saved filter views with a density property still load, ignoring that obsolete setting.

Use **More filters > Edit layout** to move and resize all 17 panels. Drag a named handle onto another panel to reorder. Drag the right edge for width, the bottom edge for height, or the plain corner grip for both. Changes save automatically in `smartvod.panelLayout.v1` in this browser. **Done editing** locks the panels. **More filters > Reset layout** restores default positions and automatic heights without changing filters. Keyboard: focus a handle and use arrows to reorder, Shift + arrows to resize; resize handles also accept arrow keys. Double-click an edge grip to restore its default dimension, or the corner to restore both. Escape cancels an active drag. KPI numbers shrink to fit, labels wrap, and overflowing panel content scrolls. Cards have translucent backgrounds with backdrop blur. Panels snap to a 12-column grid; small screens stack them while retaining desktop sizes. Browser storage restrictions are reported visibly; settings do not transfer to another browser or computer.

```powershell
.\venv\Scripts\python.exe ETL/SmartVOD/audit.py
```

The starter audit uses 4 November and checks totals against source CSV, filter OR/AND behavior, time bounds, decoded ISP lookup, filtered CSV totals, actual browser interactions, downloads, invalid input, and layouts from 320px to 1920px. Results and screenshots are saved under `audit/`.

Files: `prepare.py` imports data, `server.py` serves parameterized query APIs, `web/` contains the responsive UI, `run.ps1` starts the app. `data/` and generated screenshots are excluded from Git.

## Daily refresh, titles and workspace tools

- Scheduled task `SmartVOD Daily Refresh` runs `refresh.ps1` daily at 09:00 local/IST with StartWhenAvailable and no overlapping task instances. The machine must be available and have access to the shared lake. The current Windows task account must be able to run it. It adds completed days, reimports changed exports and preserves existing history. Manual run: `.\ETL\SmartVOD\refresh.ps1`.
- Missing future exports are generated into SmartVOD's own `data/sources` only after STREAM full-day structural validation. Incomplete days are skipped explicitly in `data/refresh_status.json`; failed imports preserve the prior published snapshot. A subsequent refresh retries uncompleted dates. No production export or dashboard is overwritten.
- Publication uses versioned SQLite databases and an atomic manifest pointer. The latest two versions are retained; older unlocked versions are removed after successful publication. Refresh is idempotent when inputs, ASN lookup and overrides are unchanged.
- Titles are reconciled by **host + video key**, preserving `raw_title`. Log titles with mapping evidence rank ahead of unsupported titles, then by segment volume. Multiple labels are retained as **Title history / SEO aliases** and do not imply an identity or mapping problem. Content decisions displays the latest request-observed title in the selected data, preserves explicit verified overrides, and exposes earlier aliases with observation dates. Those dates do not establish exact SEO edit times. A consistent log title still is not an authoritative content-catalog verification. Unknown titles stay unknown. Download the title review from the page. To supply an authoritative correction, add `host,video_key,title,evidence` to `title_overrides.csv` and refresh; empty evidence is rejected. No titles are invented.
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

Each journey has **Back to device list** or **Back to IP list**. Explorer
drill-downs remember the previously applied filters, list scroll positions and
clicked identifier. Back restores that view and keyboard focus. Nested device/IP
drill-downs return one step at a time. If there is no navigation history (for
example, an identifier was selected directly), Back clears that identifier while
retaining the other applied filters. Reset or loading a saved view clears the
old explorer history. `audit_explorer_return.py` covers these flows and failed
return recovery.

### Device ID / Client IP basis

Both Device ID and Client IP views are visible by default: separate averages, explorer lists, content-table averages and independent journeys. There is no audience-basis selector. Both views keep all explicit audience/date/time filters active. IP activity can combine viewers behind NAT/shared networks or split a viewer across changing addresses; it is not a person-level journey.

The top bar contains SmartVOD, date range, title and More filters. **Apply dates** and **Apply title** update results directly without opening the drawer. More filters contains the remaining filters, time window, saved views, Reset, Export CSV and Apply. Matched-record counts and date/time notes appear at the bottom of its scroll area.

Average minutes = estimated watch minutes on rows with a known identifier / distinct known identifiers on those same rows, computed independently for each basis. Missing identifiers are excluded from both numerator and denominator; an empty denominator displays N/A. The content table computes this per host/video/title group; it is not average session duration. Saved views and local view links preserve filters, while both audience views remain visible. Each journey CSV uses its own `identity_basis` and `identity_value`; standard CSV includes `average_device_minutes` and `average_ip_minutes` alongside the legacy basis-specific columns. Group averages are not additive.

`audit_both_audiences.py` verifies the current dual-view UI against SQL, missing-only selections, per-content averages, independent journeys/exports, direct date/title application and mobile alignment. Older UI audits target the previous basis-selector layout.

Select exactly one known Device ID, choose the date/time range and click Apply. Viewer Journey shows the observed sequence with previous-five and next-five sessions around the selected session. Click a session card or the full timeline to change the center; Previous/Next match moves between content-filter matches.

Date/time and non-content audience filters apply to journey evidence. Title/category/video-key filters highlight matches while preserving surrounding content. With multiple Device IDs or an unknown ID, the panel asks for one known device rather than mixing viewers.

Consecutive requests for the same video key and host form a session until content/host changes, a known request session-ID changes, or the gap exceeds 30 minutes. Exactly 30 minutes stays in the session. Ordering uses first request timestamps and deterministic tie-breaking; overlapping activity is flagged as ambiguous. Session watch minutes use the same request-based estimate as the rest of the dashboard, not wall-clock duration. Identity provenance distinguishes direct request IDs from manifest-inferred IDs. Data outside the loaded/filtered period is not included; journeys can be incomplete at those boundaries.

Run `python ETL/SmartVOD/audit_journey.py` from the workspace with its venv interpreter to repeat grouping, real-device reconciliation and browser navigation checks.
