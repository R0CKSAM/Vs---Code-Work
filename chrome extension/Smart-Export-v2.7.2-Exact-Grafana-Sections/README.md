# Smart Export v2.7.2 — Grafana Panel Sections

**Current release:** The panel picker now mirrors all nine Grafana dashboard sections and all 34 original panel IDs in order: the complete KPI matrix; five distinct Time Series sections, each with Per Minute and Per 5 Minute exports; Viewership Trend; Playtime; Playtime - IP.

**Download options:** Individual CSVs in one ZIP, or Excel with a worksheet per selected metric and a Definitions sheet. The legacy six report datasets and saved records remain supported. The dashboard stays in a separate signed-in Grafana tab.

See [RELEASE-v2.7.2.md](RELEASE-v2.7.2.md) for the mapping, known five-minute calculation caveats, safe upgrade steps, and QA limitations.

---

# Smart Export v2.7.1 — Grafana-Aligned Panel Picker

Independent Chrome extension. This update redesigns **Smart Export's actual full-page workspace**, not the unrelated Smart Report screenshot/email extension.

## What changed

- Grafana-style header and IST date range stay at the top.
- Available validated fields are shown in dashboard order: Session and Users Stats; Time Series (hourly); Viewership Trend; Popular Content; Playtime; Playtime - IP.
- Each checkbox corresponds to exactly one existing certified field; no simulated charts or fabricated numbers.
- The original source panel names are used where the data mappings are equivalent. New hourly and combined platform/OS results are labeled honestly.
- Full-width desktop grids: three-across statistics, two-across hourly fields, four-across viewership/content, three-across location/platform.
- Selected fields, search, date presets, per-parameter Excel sheets and individual CSV ZIP remain functional.
- No technical breakdown chooser or useless disabled metric placeholders.
- Results and Settings screens, the authenticated Grafana fetching engine, local storage, and daily update logic are preserved.

## Installation

1. Back up your working Smart Export folder and download the current Excel master first.
2. Unzip this build and replace the files *in the same unpacked extension folder*; this helps preserve the extension ID and locally stored data. **Do not uninstall** before making a backup.
3. Visit `chrome://extensions/`, click **Reload**, and open **Smart Export Workspace**.
4. Keep Grafana signed in. Confirm connection, select two completed dates, choose 1–2 panels and click **Get data**.
5. Compare results to the matching Grafana panel before wider rollout.

## Metric mapping boundaries (important)

The source Grafana dashboard includes many panels. The current Smart Export backend retains **six report datasets** and now exposes **25 numeric export fields**, including four new daily KPI measures. The extended KPI query still requires live validation. The picker displays those verified fields only.

- **Session and Users Stats**: device IDs, unique IPs, session IDs, IP+UA pairs, master manifest requests. New/returning users are now mapped to source panel 6/7 within each IST day (one distinct session ID versus more than one). These are not true first-time/returning registration cohorts.
- **Time Series**: hourly IST aggregates. This is **not** the original per-minute or five-minute chart granularity, which is not implemented in the current exporter.
- **Viewership Trend**: estimated viewership minutes, video bytes, channel playtime, channel unique IPs. Minutes and bytes are exported as raw numeric quantities.
- **Popular Content**: the columns IP users, device ID users, session IDs, and matching manifest requests, with date and content title included.
- **Playtime**: country/state/city minutes and platform/OS device IDs.
- **Playtime - IP**: platform/OS grouped unique IPs. The source panel calls this 'IP by Platform(sessions)', but the exported field is distinct IPs, not a true session identifier.

Cross-day distinct-user counts are never summed into falsely labeled range-wide unique users. A separate period-level distinct query would be required.

## QA

The `UI-AUDIT-2.7.0.md` file records regression tests, mapping checks, simulated browser viewport sizes, and remaining live-test limitations. Actual signed-in Grafana extraction is still a required user-side verification.

For issues, export diagnostics from Settings and contact Smarth for support.

## v2.7.1 KPI layout and source query changes

See `RELEASE-v2.7.1.md` and `QA-v2.7.1.md`. These documents supersede the v2.7.0 KPI panel counts.
