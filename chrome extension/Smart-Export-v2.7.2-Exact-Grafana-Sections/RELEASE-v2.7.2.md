# Smart Export v2.7.2 — Exact Grafana Sections

## What changed

- Kept the verified **Session and Users Stats** KPI matrix unchanged.
- Replaced the generic **Time Series** category with **five separate Grafana sections**. Each has two independent choices: **Per Minute** and **Per 5 Minute**.
- Followed these with **Viewership Trend** (four summary cards, Viewership minutes, Playtime by Channel, Unique IP users by channel, Popular Content), **Playtime** (GEO, Device IDs by platform, Device IDs by OS), and **Playtime - IP** (Unique Client IP by Geo, IP by Platform, IP by OS).
- Matched panel titles and their order to the supplied Grafana dashboard configuration, using stable source panel IDs (34 selectable source panels, 9 sections).
- Added source-backed, separate Hydrolix datasets for 1-minute and 5-minute series and for the previously combined Device/OS/IP charts. No fabricated sparklines or values are displayed.
- Retained the full-screen theme, date toolbar, collapsible sections, Excel/CSV picker, saved views, source connection, and existing user data store. The separate Smart Report screenshot/email extension was not modified.
- Serialized rapid checkbox saves to avoid stale selections when users click immediately before Get Data.

## Important source definitions

The original Grafana **Per 5 Minute** queries calculate a cumulative sum of **five one-minute aggregate values** and show only rows ranked fifth within each window. In particular, a five-minute unique-IP sum is *not* a five-minute distinct-IP count. The extension deliberately reproduces this definition instead of silently recalculating it.

The **Total Views — Per Minute** source query filters master manifests. The source **Total Views — Per 5 Minute** query counts all requests. Both retain the source queries' separate definitions; these numbers are not directly interchangeable.

Your current exporter is day-scoped, with **Asia/Kolkata (IST)** dates, and these minute-bucket exports also include a readable IST timestamp. Shorten the date range when selecting many high-resolution panels: exports exceeding the estimated 115,000-row safety threshold are blocked before querying.

### Export files

- **Excel:** Individual metric worksheets (plus Definitions). For Grafana combined tables (Total Unique IPs & Session, Popular Content), the underlying selected columns are exported as individual metric sheets under their existing established workflow.
- **CSV:** One CSV per selected metric; multiple files bundled into a ZIP.
- No aggregate is silently calculated across unique-user days; saved master data is not cleared by upgrading.

## Upgrade / rollback

1. Pause automatic updates and export a backup workbook first.
2. Keep a copy of your currently working v2.7.1 extension directory.
3. Replace the files inside the **same unpacked extension folder**, then click Reload in `chrome://extensions/`.
4. Open the Grafana dashboard in another signed-in tab. Test **one Per Minute and one Per 5 Minute panel for a single completed day**; compare figures with Grafana Inspector before wider use.
5. If your environment refuses the new query or the data does not match, use the previous folder as a rollback and export diagnostics via Settings.

## Testing scope

Static SQL/selection/XLSX tests, source-dashboard panel ID/label verification, and actual Chromium rendering of the picker at 1919, 1650, 1366, 768, and 390 px passed. **Live authenticated Hydrolix/Grafana queries were not accessible in this environment.** The new series queries therefore need a real one-day reconciliation test on the company dashboard before unattended production use.
