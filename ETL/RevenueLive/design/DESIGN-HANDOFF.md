# Veto UI Design Handoff

## Essential Files

- `design/kpi-cards-redesign.html`: standalone illustrative KPI preview. Open directly in a browser. Keep `static/lucide.min.js` at the relative path used by the preview. This file is not connected to live revenue.
- `static/quick-insights.js`: live calculations, ranking, comparisons and insight rendering.
- `static/light.css`: current white theme and final component overrides.
- `static/index.html`: page structure and script order.
- `static/app.js`: navigation, authentication, filters and report integration.

## Supporting Context

- `static/style.css`, `static/analytics.css`, `static/dark.css`: earlier CSS layers still affect layout. Include these so the editor understands the cascade.
- `static/revenue-share.js`: dashboard charts, treemap and channel metrics.
- `static/diy-graphs.js`: DIY charts, filters and presets.
- `static/analytics.js`: legacy chart behaviours still loaded by the page.
- `insight_presets.py`: shared preset definitions.
- `app.py`: API contracts and permissions, if functional changes are needed.
- `check_diy_insights.py`, `check_summary_ui.py`, `browser_check.py`: calculation and responsive-layout regression tests.

## Design Rules

Use the preview as visual direction, not as a replacement for live calculations. Show metric name, current value, change and explicit baseline. Label absolute changes as changes, not totals. Use equal-duration inclusive periods: 11-18 August is eight days, not a week. Calculate percentages, differences and bar widths from numeric values. Use two decimals for per-1,000 ratios when integer rounding obscures comparison. Reduced revenue is not proof of lost earnings or lower operational efficiency.

Use white surfaces, bold readable figures, restrained blue accents and semantic red/green with written labels. Maximum card radius: 8px. Static cards must not move on hover. No fake filters or inactive button-like decorations. Full channel names must wrap. Test 320px mobile, laptop and desktop widths, including reduced motion.

Do not send databases, account/session files, credentials, real uploads, logs or `.env` files to a design editor. Use synthetic screenshots.

## Editor Prompt

Use `design/kpi-cards-redesign.html` as the visual reference to improve RevenueLive. Read every CSS layer before editing. Preserve permissions, live data, date/channel behaviour and insight calculations. Use structured metric/value/change/baseline fields, not numeric extraction from prose. Label comparison bars, keep static cards motionless on hover, and run the existing browser checks at desktop, laptop and mobile sizes. Never copy illustrative sample figures into production.
