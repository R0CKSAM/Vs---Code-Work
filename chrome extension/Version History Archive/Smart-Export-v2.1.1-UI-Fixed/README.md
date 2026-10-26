# Smart Export v2.1.1 — UI Fixed

See [README-v2.1.1.md](README-v2.1.1.md) and [UI-AUDIT.md](UI-AUDIT.md) for the current maintenance release. The documentation below describes the unchanged v2.1 data features.

---

# Smart Export v2.1 — Smart Data Picker

Standalone Chrome extension for your signed-in TrafficPeak/Grafana dashboard. **Not connected to Smart Report or Smart Flow.**

## What changed from working v2.0

- **Searchable metric picker** with 21 supported metric choices from 6 verified report categories.
- **Plain-English quick picks:** Daily overview, Top channels, Audience locations, Watch-time & traffic, Top shows, All available.
- **Compatible grouping:** Date (IST), channel, country/state/city, platform/OS, title, or hour (traffic). When more than one category is selected, Smart Export generates **separate Excel tabs** rather than joining incompatible grains.
- **Selective Excel and CSV columns**, including date/dimension keys. Export filters are applied **only when downloading one report**, without changing the saved master.
- **Excel preview** shows selected headings and real previously-fetched rows; it never invents analytics values.
- **Save and load your own views** (up to 20), a sticky Fetch/Excel footer, safe daily updates for the chosen report categories, and a searchable panel inventory under Advanced.
- Existing v2 report masters, original v1 GEO data, and old v2 report export are preserved. A **Classic v2 interface** button opens the old screen in a tab.

## First run

1. **Back up the existing unpacked Smart Export folder.** Stop or pause its running schedule.
2. Extract the new ZIP. To **preserve Chrome local master data and the existing extension identity**, replace the contents of the *same installed unpacked extension folder* and use **Reload** in `chrome://extensions/`. Installing in a different folder may produce another extension ID and a separate data store.
3. Open and sign in to the source Grafana dashboard in Chrome.
4. Open Smart Export and click **Daily overview**, **Top channels**, or search for individual metrics such as `playtime` or `unique IP`.
5. Choose two or three **completed IST dates**, then click **Fetch data** in the sticky footer.
6. When fetching finishes, inspect the first rows under **Preview your Excel** and choose **Excel**. For one category only, CSV is also available.
7. Compare at least one exported date with Grafana **Inspect → Data** before enabling scheduled updates.

## What is selectable today?

| Dataset | Supported output columns | Granularity | Source panels |
|---|---|---|---|
| Audience & overview | Unique device IDs, unique IPs, session IDs, IP+UA sessions, manifest views, playtime, bandwidth | Daily | 2,1,8,12,5,41,15 |
| Channels | Estimated playtime, unique IPs | Daily × channel | 34,68 |
| GEO | Estimated playtime | Daily × country × state × city | 20 |
| Devices & operating systems | Unique device IDs, unique IPs | Daily × platform × OS | 58,55 |
| Content | Manifest views, IPs, device IDs, session IDs | Daily × title | 27 |
| Traffic | IPs, session IDs, manifest views, playtime, bandwidth | Hourly IST | 9,38,3,15 |

The app's **Explore all Grafana sections** reads titles/types/IDs from the signed-in dashboard and marks which panels support existing safe templates. It is **read-only** and does not execute unknown SQL. For example, `Unique Client IP by Geo`, 5-minute graphs, and other panels still need dedicated metric validation before their fields become selectable. Do **not** assume every discovered Grafana panel is exportable.

## Important data caveats

- Unique IP, distinct device, and session counts are not equivalent to individual viewers; day-level distinct counts cannot be summed as accurate monthly unique counts.
- Playtime is estimated using six-second segment requests, not direct player events.
- The source Grafana dashboard's active `var-filter` ad-hoc filters remain unsupported. The extension rejects these rather than silently exporting unfiltered results.
- A dimension filter in the new popup applies to **one report's downloaded rows only**, not to Grafana requests or the local master. It does not make filtered monthly uniques or join different metrics.
- **Multiple selected categories**: maximum 31 completed days per fetch, one source query per chosen category. For one report, the original one-year maximum remains.
- Downloads are snapshots; Chrome does not overwrite existing local Excel files automatically.
- The scheduled refresh runs about 8 AM IST while Chrome and a signed-in Grafana tab are available, and reconciles recent completed dates. The schedule is paused if you change the selected report categories.
- Your old v2 IndexedDB remains unchanged (same DB name and schema); its rows are not erased by the upgrade.

## Permissions and privacy

Uses only existing permissions: `storage`, `alarms`, `tabs`, `scripting`, and the exact TrafficPeak Grafana host. No passwords, tokens or generated raw SQL are saved. There are no external backend/API keys or third-party scripts.

## Troubleshooting

Open **Advanced & help → Download error logs**, then contact **Smarth**. If data query fails, check the signed-in Grafana tab and compare known source panels. The local master is not merged when a selected query fails.

**Verification boundary:** JS syntax, Node logic regressions, XLSX import, and Chromium popup mock interactions passed. Browser policies in this test environment blocked full installed-extension authentication and real Hydrolix queries, so **live Grafana performance and the scheduled fetch require user-side acceptance testing**.
