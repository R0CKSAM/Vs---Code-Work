# Smart Export v2.7.2 QA

- Source order: 9 Grafana sections and 34 exact panel IDs/titles matched the provided dashboard JSON.
- New query validation: all 17 additional report mappings passed source SQL signature checks against the supplied original panel SQL.
- Data correctness tests: per-minute/5-minute source semantics; IST date/time bucket validation; repeated data-frame duplicate safety; CSV safety; output workbook structure; independent report keys.
- Legacy regression: core GEO, v2 reports, metric picker, existing KPI panel parity and background checks passed.
- Rendered Chromium QA: 1919x950, 1650x860, 1366x768, 768x820 and 390x860; no horizontal document or control overflow and no console page errors observed.
- Interactions: independent Per Minute / Per 5 Minute selections, selection retained across sections/search, mock Get Data screen transition.

**Not verified:** Live private Grafana login, Hydrolix SQL execution plans/latency, real-minute figures, 5-minute series comparison against the actual Grafana Inspector, and unattended daily operation. QA browser tests used a mocked extension bridge.
