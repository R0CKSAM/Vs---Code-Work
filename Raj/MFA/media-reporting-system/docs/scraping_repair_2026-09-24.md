# News and advertisement data repair — 24 September 2026

## Reproduced causes

1. **Missing news fields:** scheduled and manual refresh disabled article-page enrichment. Exchange4media accepted an `enrich` option but never implemented it. ET's lead-story summary is an `h3`, not a paragraph; its hero image can be exposed in a preload link. In a direct homepage check, ET yielded 23 articles, 4 images and no summaries; Exchange4media yielded 67 articles and 16 summaries.
2. **Metadata disappeared on refresh:** listing-page omissions overwrote previously saved summaries and images. Publication labels and exclusive flags were extracted but never persisted. Database-backed article reads incorrectly depended on a valid JSON snapshot existing first.
3. **Fake or incomplete ads:** the detector counted empty GPT slots and an Advertorial navigation link. Raw HTTP HTML cannot see JavaScript creatives inside advertising frames. Lazy image placeholders took priority over actual creatives; relative links were unresolved. Impression pixels could be mistaken for creatives.
4. **Ad lifecycle corruption:** returning removed ads attempted another insert against a unique hash. Several ads sharing a broad position such as UNKNOWN could overwrite one record. Static/partial observations marked unseen ads removed. Failed asset downloads could leave a partial file that was subsequently reused.
5. **Display and API inconsistencies:** React news came from mock data; empty ad results were replaced with mock campaigns. The backend dashboard invented sample ads and a count of 34 when no ads existed. The built-in UI ignored locally archived ad images. Website-specific ad routes passed FastAPI Query objects into direct function calls, and filtered totals ignored brand/campaign/type filters.
6. **Refresh and fetch failures:** blocking refresh code ran on the async request loop. Manual refresh did not collect ads and suppressed failures. Missing robots.txt was cached as an uninitialized parser, allowing the first request but potentially denying later requests. Ad repository methods referenced an undefined timestamp helper when no timestamp was supplied.

## Repairs

- Shared article-page enrichment reads OpenGraph and matching JSON-LD, including `@graph`. Updated timestamps are not substituted for publication timestamps. Refresh enriches up to 30 articles per publisher, with existing request delays preserved.
- Missing fields preserve previously collected metadata for the same canonical article. Additive SQLite migration stores publication labels and exclusive flags. Database records remain readable without JSON snapshots.
- Browser-based ad collection uses Playwright/Chromium, reads ad-frame contents and unwraps explicit destination URLs. It extracts campaign names from explicit metadata or `utm_campaign`. Unknown brand/campaign names remain unknown when the source does not expose them. Lazy images and relative URLs are handled; empty slots, navigation and impression pixels are excluded.
- Returning ads reuse their existing records. Ambiguous positions no longer overwrite multiple creatives. An incomplete observation does not prove removal; monitoring preserves unseen ads and their original last-seen timestamps. Consumers should use last-seen time to assess freshness.
- Image downloads use temporary files and atomic replacement; missing downloads are retried on subsequent observations. The built-in dashboard prefers archived images.
- News/ad pages use live API results, display failures, and retain empty results. Dashboard sample ads and fabricated fallback counts were removed. Ad totals now apply the same filters as rows.
- Manual and scheduled refresh share one pipeline, with a per-publisher lock. Manual failure returns HTTP 502; blocking refresh runs in a worker thread.

## Validation and operation

- Python suite: `python -m unittest discover -s tests -q` — 124 tests passed, including 12 new regressions. Fixed obsolete unused imports that previously prevented one existing test module from loading.
- Live article check: five articles from each publisher all supplied images, summaries and publication timestamps after enrichment.
- Live browser ad check: Exchange4media exposed YouTube creatives, the Festive campaign and its destination. ET exposed creatives and tracking destinations, but some brand/campaign metadata was absent. Ad inventory varies by visit, geography and time; counts are not fixed.
- Built-in dashboard JavaScript syntax checked successfully. A full React build could not be completed with the machine's available npm setup; React changes require a normal Node/npm build before deployment.
- All 54 TypeScript/TSX source files passed syntax transpilation. Five HTTP API smoke checks passed (dashboard, both news feeds, ad list, website-specific ad list).
- Full pipeline on a database copy returned 23 ET articles (21 images, 21 summaries) and 68 Exchange4media articles (68 images, 39 summaries). These records and newly observed image ads were then applied to the project database, and both JSON snapshots were refreshed. Missing summaries remain possible beyond the 30-article enrichment budget or when article metadata cannot be fetched.
- Original database backed up under `storage/backups/` before migration/data repair. Schema changes are additive; historical records are retained.

Restart the backend using `python run_server.py`, then use Sync Data or POST `/api/monitoring/run-now`. The backend also runs the scheduled monitoring cycle. Fresh machines need `python -m pip install -r requirements.txt` and `python -m playwright install chromium` for browser ads.

The older phase documents and README describe a much earlier mock-only architecture. The application now includes SQLite persistence, scheduled monitoring and real ad collection. News summaries are publisher-provided descriptions, not generated text. Missing metadata and unavailable browser creatives are not fabricated; browser collection logs failures and retains available HTML observations.
