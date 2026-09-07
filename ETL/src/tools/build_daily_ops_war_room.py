#!/usr/bin/env python3
"""Build a standalone one-day audience and CDN operations dashboard."""

from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


ETL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ETL_ROOT / "output" / "exports"

MARTS = {
    "source": ETL_ROOT / "output" / "master" / "data" / "master_source_daily.parquet",
    "channel": ETL_ROOT / "output" / "master" / "data" / "master_channel_daily.parquet",
    "ua": ETL_ROOT / "output" / "master" / "data" / "master_ua_daily.parquet",
    "market": ETL_ROOT / "output" / "master" / "data" / "master_market_daily.parquet",
    "asn": ETL_ROOT / "output" / "master" / "data" / "master_asn_daily.parquet",
    "concurrency": ETL_ROOT / "output" / "watch_hours" / "concurrency" / "concurrency_minute.parquet",
    "latency_daily": ETL_ROOT / "output" / "latency" / "profile" / "daily.parquet",
    "latency_hourly": ETL_ROOT / "output" / "latency" / "profile" / "hourly.parquet",
    "status": ETL_ROOT / "output" / "latency" / "profile" / "status_daily.parquet",
    "cache": ETL_ROOT / "output" / "latency" / "profile" / "cache_daily.parquet",
    "hosts": ETL_ROOT / "output" / "watch_hours" / "daily_tables" / "hosts_daily.parquet",
    "identity": ETL_ROOT / "output" / "identity" / "identity_daily.parquet",
    "content": ETL_ROOT / "output" / "content" / "content_daily.parquet",
    "bandwidth": ETL_ROOT / "output" / "watch_hours" / "concurrency" / "fast_platform_channel_bandwidth_daily.parquet",
}


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


class MartReader:
    def __init__(self) -> None:
        missing = [str(path) for path in MARTS.values() if not path.exists()]
        if missing:
            raise FileNotFoundError("Required processed marts are missing:\n" + "\n".join(missing))
        self.connection = duckdb.connect(":memory:")

    def close(self) -> None:
        self.connection.close()

    def rows(self, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, parameters)
        columns = [column[0] for column in cursor.description]
        return [json_value(dict(zip(columns, row))) for row in cursor.fetchall()]

    def row(self, sql: str, parameters: list[Any]) -> dict[str, Any]:
        values = self.rows(sql, parameters)
        return values[0] if values else {}


def build_payload(target_date: str) -> dict[str, Any]:
    reader = MartReader()
    try:
        source_rows = reader.rows(
            """
            SELECT source, watch_hours, clips_watched, ip_users, total_views,
                   total_devices, total_sessions
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            ORDER BY source
            """,
            [str(MARTS["source"]), target_date],
        )
        if not source_rows:
            available = reader.row(
                "SELECT min(log_date) AS first_date, max(log_date) AS last_date FROM read_parquet(?)",
                [str(MARTS["source"])],
            )
            raise RuntimeError(
                f"No processed source data exists for {target_date}. "
                f"Available range: {available.get('first_date')} through {available.get('last_date')}."
            )

        prior = reader.row(
            """
            WITH previous_date AS (
                SELECT max(log_date) AS log_date
                FROM read_parquet(?) WHERE CAST(log_date AS DATE) < CAST(? AS DATE)
            )
            SELECT p.log_date,
                   sum(s.watch_hours) AS watch_hours,
                   sum(s.ip_users) AS ip_activity,
                   sum(s.total_views) AS views
            FROM previous_date p
            LEFT JOIN read_parquet(?) s ON CAST(s.log_date AS DATE) = CAST(p.log_date AS DATE)
            GROUP BY p.log_date
            """,
            [str(MARTS["source"]), target_date, str(MARTS["source"])],
        )

        minute = reader.rows(
            """
            SELECT minute_ist,
                   sum(segment_viewers_estimate) AS active_streams_estimate,
                   sum(raw_ts_rows) AS segment_requests,
                   sum(status_200_ts_rows) AS status_200_segments
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY minute_ist
            ORDER BY minute_ist
            """,
            [str(MARTS["concurrency"]), target_date],
        )

        channels = reader.rows(
            """
            SELECT string_agg(DISTINCT upper(source), ' + ') AS sources,
                   channel_name, sum(watch_hours) AS watch_hours,
                   sum(ip_users) AS ip_activity, sum(total_views) AS views
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY channel_name
            ORDER BY watch_hours DESC
            LIMIT 12
            """,
            [str(MARTS["channel"]), target_date],
        )

        identity = reader.rows(
            """
            SELECT source, total_devices, total_sessions, total_ipua_sessions,
                   new_devices, returning_devices
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            ORDER BY source
            """,
            [str(MARTS["identity"]), target_date],
        )

        latency = reader.row(
            """
            SELECT sum(rows) AS requests,
                   sum(status_200_rows) AS status_200_rows,
                   sum(non_200_rows) AS non_200_rows,
                   sum(status_5xx_rows) AS status_5xx_rows,
                   sum(cache_hit_rows) AS cache_hit_rows,
                   sum(ttfb_rows) AS ttfb_rows,
                   sum(ttfb_p50_ms * ttfb_rows) / nullif(sum(ttfb_rows), 0) AS ttfb_p50_ms,
                   sum(ttfb_p95_ms * ttfb_rows) / nullif(sum(ttfb_rows), 0) AS ttfb_p95_ms,
                   sum(turnaround_p50_ms * rows) / nullif(sum(rows), 0) AS turnaround_p50_ms,
                   sum(transfer_p50_ms * rows) / nullif(sum(rows), 0) AS transfer_p50_ms,
                   sum(throughput_p50 * rows) / nullif(sum(rows), 0) AS throughput_p50
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            """,
            [str(MARTS["latency_daily"]), target_date],
        )

        hourly = reader.rows(
            """
            SELECT hour_ist,
                   sum(rows) AS requests,
                   sum(status_200_rows) AS status_200_rows,
                   sum(ttfb_p50_ms * ttfb_rows) / nullif(sum(ttfb_rows), 0) AS ttfb_p50_ms,
                   sum(ttfb_p95_ms * ttfb_rows) / nullif(sum(ttfb_rows), 0) AS ttfb_p95_ms
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY hour_ist
            ORDER BY hour_ist
            """,
            [str(MARTS["latency_hourly"]), target_date],
        )

        statuses = reader.rows(
            """
            SELECT CAST(status_code AS VARCHAR) AS status_code, sum(rows) AS requests
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY status_code
            ORDER BY requests DESC
            LIMIT 10
            """,
            [str(MARTS["status"]), target_date],
        )

        cache = reader.rows(
            """
            SELECT coalesce(nullif(cacheStatus, ''), 'Unknown') AS cache_status,
                   sum(rows) AS requests
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY cache_status
            ORDER BY requests DESC
            """,
            [str(MARTS["cache"]), target_date],
        )

        hosts = reader.rows(
            """
            SELECT source, reqHost AS host, sum(rows) AS requests,
                   sum(raw_ts_rows) AS segments, sum(raw_watch_hours) AS watch_hours,
                   sum(approx_unique_ips) AS ip_activity
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY source, reqHost
            ORDER BY requests DESC
            LIMIT 10
            """,
            [str(MARTS["hosts"]), target_date],
        )

        content = reader.rows(
            """
            SELECT content_title, sum(raw_watch_hours) AS watch_hours,
                   sum(raw_ts_rows) AS segment_requests,
                   sum(approx_unique_ips) AS approximate_ip_activity
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
              AND source = 'stream'
              AND content_title IS NOT NULL
              AND trim(content_title) <> ''
              AND lower(trim(content_title)) NOT IN ('null', 'unknown', 'unknown / na')
            GROUP BY content_title
            ORDER BY watch_hours DESC
            LIMIT 10
            """,
            [str(MARTS["content"]), target_date],
        )

        devices = reader.rows(
            """
            SELECT dimension, label, sum(raw_ts_rows) AS segment_requests,
                   sum(watch_hours) AS watch_hours
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE) AND scope = 'source'
            GROUP BY dimension, label
            QUALIFY row_number() OVER (PARTITION BY dimension ORDER BY sum(raw_ts_rows) DESC) <= 8
            ORDER BY dimension, segment_requests DESC
            """,
            [str(MARTS["ua"]), target_date],
        )

        markets = reader.rows(
            """
            SELECT market_level, label, sum(raw_ts_rows) AS segment_requests,
                   0 AS approximate_ip_activity
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE) AND scope = 'source'
            GROUP BY market_level, label
            QUALIFY row_number() OVER (PARTITION BY market_level ORDER BY sum(raw_ts_rows) DESC) <= 8
            ORDER BY market_level, segment_requests DESC
            """,
            [str(MARTS["market"]), target_date],
        )

        asns = reader.rows(
            """
            SELECT asn, coalesce(nullif(as_name, ''), 'Unknown network') AS network,
                   sum(raw_ts_rows) AS requests,
                   sum(approx_unique_ips) AS approximate_ip_activity
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            GROUP BY asn, network
            ORDER BY requests DESC
            LIMIT 8
            """,
            [str(MARTS["asn"]), target_date],
        )

        bandwidth = reader.row(
            """
            SELECT sum(total_bytes) AS total_bytes,
                   sum(rows_with_total_bytes) AS rows_with_bytes,
                   sum(raw_ts_rows) AS segment_requests
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) = CAST(? AS DATE)
            """,
            [str(MARTS["bandwidth"]), target_date],
        )

        total_watch_hours = sum(float(row.get("watch_hours") or 0) for row in source_rows)
        total_ip_activity = sum(int(row.get("ip_users") or 0) for row in source_rows)
        total_views = sum(int(row.get("total_views") or 0) for row in source_rows)
        active_values = [float(row.get("active_streams_estimate") or 0) for row in minute]
        peak_index = max(range(len(active_values)), key=active_values.__getitem__) if active_values else None
        stream_source = next((row for row in source_rows if str(row["source"]).lower() == "stream"), {})
        stream_identity = next((row for row in identity if str(row["source"]).lower() == "stream"), {})

        summary = {
            "watch_hours": total_watch_hours,
            "ip_activity": total_ip_activity,
            "views": total_views,
            "active_streams": active_values[-1] if active_values else 0,
            "peak_active_streams": active_values[peak_index] if peak_index is not None else 0,
            "peak_time": minute[peak_index]["minute_ist"] if peak_index is not None else None,
            "stream_devices": int(stream_identity.get("total_devices") or stream_source.get("total_devices") or 0),
            "stream_sessions": int(stream_identity.get("total_sessions") or stream_source.get("total_sessions") or 0),
        }
        return json_value({
            "date": target_date,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": summary,
            "prior": prior,
            "source_rows": source_rows,
            "minute": minute,
            "channels": channels,
            "identity": identity,
            "latency": latency,
            "hourly": hourly,
            "statuses": statuses,
            "cache": cache,
            "hosts": hosts,
            "content": content,
            "devices": devices,
            "markets": markets,
            "asns": asns,
            "bandwidth": bandwidth,
        })
    finally:
        reader.close()


def render_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    display_date = datetime.strptime(payload["date"], "%Y-%m-%d").strftime("%d %b %Y | %a").upper()
    title = f"VETO Audience & CDN Operations - {payload['date']}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#07111b;--surface:#0b1926;--surface2:#0f2232;--line:#244258;--text:#f4f7fa;--muted:#91a5b6;--green:#50d66d;--cyan:#3aa7ff;--violet:#bf62e5;--orange:#ff9f43;--yellow:#e4d44d;--red:#ff5c61}}
*{{box-sizing:border-box}}html,body{{margin:0;background:var(--bg);color:var(--text);font-family:Segoe UI,Arial,sans-serif;letter-spacing:0}}body{{min-width:320px}}
button{{font:inherit}}.shell{{min-height:100vh;display:grid;grid-template-columns:86px minmax(0,1fr)}}
.rail{{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:#081522;padding:14px 8px;display:flex;flex-direction:column;gap:8px}}
.brand{{font-size:20px;font-weight:900;text-align:center;padding:8px 0 16px;border-bottom:1px solid var(--line)}}.brand small{{display:block;font-size:7px;color:var(--muted);margin-top:3px}}
.nav{{height:58px;border:0;border-left:3px solid transparent;background:transparent;color:var(--muted);font-size:10px;font-weight:700;cursor:pointer}}.nav:hover,.nav.active{{background:#10283d;color:#fff;border-left-color:var(--cyan)}}
.rail .stamp{{margin-top:auto;text-align:center;font-size:9px;color:var(--muted);line-height:1.5}}.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}}
main{{padding:10px 12px 16px;min-width:0}}.top{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;padding:4px 8px 10px}}
.top h1{{font-size:21px;text-align:center;margin:0;min-width:0}}.top h1 span{{display:block;font-size:12px;color:var(--green);margin-top:4px}}.date{{justify-self:start;font-size:12px;color:#dbe5ec;line-height:1.5}}
.status{{justify-self:end;border:1px solid #31516a;padding:8px 18px;border-radius:5px;text-align:center;font-size:11px;font-weight:800}}.status small{{display:block;color:var(--green);margin-top:3px}}
.source-strip{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:6px;background:var(--surface);margin-bottom:10px;overflow:hidden}}.source-strip div{{padding:8px 14px;text-align:center;border-right:1px solid var(--line);font-size:11px;min-width:0}}.source-strip div:last-child{{border:0}}.source-strip b{{display:block;font-size:13px;margin-top:3px;overflow-wrap:anywhere}}
.kpis{{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:8px;margin-bottom:10px}}.kpi{{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:9px 10px;min-height:104px;overflow:hidden}}.kpi .label{{font-size:9px;color:#c3d0d9;text-align:center;font-weight:700}}.kpi .value{{font-size:24px;text-align:center;margin:6px 0 2px;white-space:nowrap}}.kpi .sub{{height:15px;text-align:center;font-size:9px;color:var(--muted)}}.kpi canvas{{width:100%;height:27px;display:block}}
.grid{{display:grid;grid-template-columns:1.12fr .9fr .9fr;gap:8px}}.panel{{border:1px solid var(--line);border-radius:6px;background:var(--surface);min-width:0;overflow:hidden}}.panel-head{{height:34px;padding:7px 10px;border-bottom:1px solid var(--line);font-size:12px;font-weight:800;background:#0e2030}}.panel-head .num{{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:5px;background:var(--cyan);margin:-2px 7px -2px 0}}.panel:nth-child(2) .num{{background:var(--violet)}}.panel:nth-child(3) .num{{background:var(--orange)}}.panel:nth-child(4) .num{{background:#2aa666}}.panel:nth-child(5) .num{{background:#ca5257}}.panel:nth-child(6) .num{{background:#7f67d8}}
.panel-body{{padding:10px;min-height:260px}}.split{{display:grid;grid-template-columns:minmax(145px,.65fr) 1.35fr;gap:10px}}.metric-list{{display:grid;align-content:start;gap:7px}}.metric{{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #173044;padding-bottom:5px;font-size:10px;color:#c3d0d9}}.metric b{{font-size:12px;color:var(--green)}}
.chart-title{{font-size:9px;text-align:center;color:#c3d0d9;margin-bottom:4px}}.chart{{width:100%;height:170px;display:block;background:#081522;border-bottom:1px solid #1c3548}}.chart.short{{height:126px}}
.legend{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:9px;color:var(--muted)}}.swatch{{width:8px;height:8px;display:inline-block;margin-right:3px}}
.bars{{display:grid;gap:6px}}.bar-row{{display:grid;grid-template-columns:minmax(80px,1fr) 2fr auto;align-items:center;gap:8px;font-size:9px}}.bar-row .name{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.track{{height:6px;background:#172c3d;border-radius:3px;overflow:hidden}}.fill{{height:100%;background:var(--green)}}.bar-row .amount{{color:#cfe1ec;text-align:right}}
.table{{width:100%;border-collapse:collapse;font-size:9px}}.table th{{color:var(--muted);font-weight:600;text-align:left;padding:4px;border-bottom:1px solid var(--line)}}.table td{{padding:5px 4px;border-bottom:1px solid #142b3c}}.table td:nth-child(n+2),.table th:nth-child(n+2){{text-align:right}}.truncate{{max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.wide{{grid-column:span 2}}.stack{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.badge{{display:inline-block;border:1px solid #2d5068;border-radius:4px;padding:3px 6px;color:#b8c9d4;font-size:9px;margin:2px}}.good{{color:var(--green)}}.warn{{color:var(--yellow)}}.bad{{color:var(--red)}}
.alerts{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}}.alert{{border:1px solid #3b4350;background:#111f2b;border-radius:5px;padding:9px;font-size:9px;min-height:70px}}.alert strong{{display:block;font-size:11px;margin:4px 0}}.alert.good{{border-color:#245b3b}}.alert.warn{{border-color:#766927}}.alert.bad{{border-color:#79373a}}
.footer{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:10px;color:var(--muted);font-size:9px}}.export{{border:1px solid #47708c;background:#10283c;color:#fff;border-radius:4px;padding:7px 10px;cursor:pointer}}.export:hover{{background:#173852}}
@media(max-width:1250px){{.kpis{{grid-template-columns:repeat(4,1fr)}}.grid{{grid-template-columns:1fr 1fr}}.wide{{grid-column:span 2}}}}
@media(max-width:780px){{.shell{{grid-template-columns:1fr}}.rail{{position:static;height:auto;display:grid;grid-template-columns:repeat(4,1fr);padding:6px}}.brand,.rail .stamp{{display:none}}.nav{{height:38px}}main{{padding:8px;min-width:0;overflow:hidden}}.top{{grid-template-columns:1fr;justify-items:center}}.top h1{{text-align:center;font-size:17px;overflow-wrap:anywhere}}.top .date{{display:none}}.status{{justify-self:center;margin-top:8px}}.source-strip{{grid-template-columns:1fr 1fr}}.source-strip div:nth-child(2){{border-right:0}}.kpis{{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}.kpi .value{{font-size:20px}}.grid{{grid-template-columns:minmax(0,1fr)}}.wide{{grid-column:auto}}.split,.stack{{grid-template-columns:minmax(0,1fr)}}.alerts{{grid-template-columns:1fr 1fr}}}}
@media print{{.rail,.export{{display:none}}.shell{{display:block}}main{{padding:0}}body{{background:#fff}}}}
</style>
</head>
<body>
<div class="shell">
<aside class="rail"><div class="brand">VETO<small>SPOTLIGHTING TOMORROW</small></div><button class="nav active" data-target="overview">OVERVIEW</button><button class="nav" data-target="audience">AUDIENCE</button><button class="nav" data-target="delivery">DELIVERY</button><button class="nav" data-target="content">CONTENT</button><div class="stamp"><span class="dot"></span><br>ETL COMPLETE<br>{html.escape(payload['date'])}</div></aside>
<main id="overview">
<header class="top"><div class="date">{display_date}<br>FULL IST DAY</div><h1>VETO AUDIENCE &amp; CDN OPERATIONS<span>DAILY DELIVERY ROOM</span></h1><div class="status">PROCESSED DATA <small><span class="dot"></span> COMPLETE</small></div></header>
<section class="source-strip" id="sourceStrip"></section>
<section class="kpis" id="kpis"></section>
<section class="grid">
<article class="panel wide" id="audience"><div class="panel-head"><span class="num">1</span>AUDIENCE PULSE</div><div class="panel-body split"><div class="metric-list" id="audienceMetrics"></div><div><div class="chart-title">ESTIMATED ACTIVE STREAMS - FULL DAY IST</div><canvas class="chart" id="concurrencyChart"></canvas><div class="legend"><span><i class="swatch" style="background:var(--green)"></i>Estimated active streams</span><span>Channel-level estimate, not measurement-grade CCV</span></div></div></div></article>
<article class="panel" id="delivery"><div class="panel-head"><span class="num">2</span>DELIVERY QUALITY</div><div class="panel-body"><div class="metric-list" id="deliveryMetrics"></div><div class="chart-title" style="margin-top:10px">HOURLY WEIGHTED TTFB</div><canvas class="chart short" id="ttfbChart"></canvas></div></article>
<article class="panel"><div class="panel-head"><span class="num">3</span>CDN / NETWORK HEALTH</div><div class="panel-body"><div class="metric-list" id="networkMetrics"></div><div class="chart-title" style="margin-top:10px">HOURLY REQUEST VOLUME</div><canvas class="chart short" id="requestChart"></canvas></div></article>
<article class="panel wide" id="content"><div class="panel-head"><span class="num">4</span>CHANNELS &amp; STREAM CONTENT</div><div class="panel-body stack"><div><div class="chart-title">TOP CHANNELS BY WATCH TIME</div><div class="bars" id="channelBars"></div></div><div><div class="chart-title">TOP RESOLVED STREAM TITLES BY WATCH TIME</div><table class="table"><thead><tr><th>Title</th><th>Watch</th><th>Segments</th></tr></thead><tbody id="contentRows"></tbody></table></div></div></article>
<article class="panel"><div class="panel-head"><span class="num">5</span>DEVICE &amp; MARKET</div><div class="panel-body"><div class="chart-title">TOP DEVICE / PLATFORM LABELS</div><div class="bars" id="deviceBars"></div><div class="chart-title" style="margin-top:14px">TOP MARKET LABELS</div><div class="bars" id="marketBars"></div></div></article>
<article class="panel"><div class="panel-head"><span class="num">6</span>NETWORKS &amp; HOSTS</div><div class="panel-body stack"><div><div class="chart-title">TOP NETWORKS</div><div class="bars" id="asnBars"></div></div><div><div class="chart-title">TOP REQUEST HOSTS</div><div class="bars" id="hostBars"></div></div></div></article>
<article class="panel wide"><div class="panel-head"><span class="num">7</span>DATA QUALITY &amp; OPERATIONAL FLAGS</div><div class="panel-body"><div class="alerts" id="alerts"></div><div style="margin-top:10px" id="basis"></div></div></article>
<article class="panel"><div class="panel-head"><span class="num">8</span>DAILY SUMMARY</div><div class="panel-body"><div class="metric-list" id="summaryMetrics"></div><div class="chart-title" style="margin-top:12px">TOP STATUS CODES</div><div class="bars" id="statusBars"></div></div></article>
</section>
<footer class="footer"><span id="footerText"></span><button class="export" id="exportButton">Export daily summary CSV</button></footer>
</main></div>
<script id="etl-data" type="application/json">{data_json}</script>
<script>
const D=JSON.parse(document.getElementById('etl-data').textContent);
const n=v=>Number(v||0);const fmt=v=>new Intl.NumberFormat('en-IN',{{maximumFractionDigits:0}}).format(n(v));
const dec=(v,d=1)=>n(v).toLocaleString('en-IN',{{minimumFractionDigits:d,maximumFractionDigits:d}});
const dur=h=>{{h=n(h);const hours=Math.floor(h),mins=Math.round((h-hours)*60);return `${{fmt(hours)}} h ${{mins}} min`;}};
const bytes=v=>{{v=n(v);for(const u of ['B','KB','MB','GB','TB','PB']){{if(Math.abs(v)<1024)return `${{dec(v,v<10?1:0)}} ${{u}}`;v/=1024}}return `${{dec(v)}} EB`;}};
const time=v=>v?new Date(v.replace(' ','T')).toLocaleTimeString('en-IN',{{hour:'2-digit',minute:'2-digit'}}):'Not available';
const pctChange=(now,old)=>old?((now-old)/old*100):null;
const subDelta=(now,old)=>{{const d=pctChange(n(now),n(old));return d===null?'No prior-day baseline':`${{d>=0?'+':'-'}}${{Math.abs(d).toFixed(1)}}% vs ${{D.prior.log_date||'prior day'}}`;}};
const sum=(a,k)=>a.reduce((t,r)=>t+n(r[k]),0);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function line(canvas,values,color,fill=true){{const r=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;canvas.width=Math.max(1,r.width*ratio);canvas.height=Math.max(1,r.height*ratio);const c=canvas.getContext('2d');c.scale(ratio,ratio);const w=r.width,h=r.height,p=10,max=Math.max(...values,1),min=Math.min(...values,0),span=max-min||1;c.strokeStyle='#183246';c.lineWidth=1;for(let i=1;i<4;i++){{const y=p+(h-2*p)*i/4;c.beginPath();c.moveTo(p,y);c.lineTo(w-p,y);c.stroke()}}const pts=values.map((v,i)=>[p+(w-2*p)*i/Math.max(1,values.length-1),h-p-(n(v)-min)*(h-2*p)/span]);if(fill&&pts.length){{const g=c.createLinearGradient(0,p,0,h);g.addColorStop(0,color+'55');g.addColorStop(1,color+'00');c.fillStyle=g;c.beginPath();c.moveTo(pts[0][0],h-p);pts.forEach(q=>c.lineTo(q[0],q[1]));c.lineTo(pts.at(-1)[0],h-p);c.closePath();c.fill()}}c.strokeStyle=color;c.lineWidth=1.7;c.beginPath();pts.forEach((q,i)=>i?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]));c.stroke();}}
function metric(label,value){{return `<div class="metric"><span>${{esc(label)}}</span><b>${{esc(value)}}</b></div>`}}
function bars(id,rows,labelKey,valueKey,formatter=fmt,color='var(--green)',limit=6){{const target=document.getElementById(id),selected=rows.slice(0,limit),max=Math.max(...selected.map(r=>n(r[valueKey])),1);target.innerHTML=selected.map(r=>`<div class="bar-row" title="${{esc(r[labelKey])}}"><span class="name">${{esc(r[labelKey]||'Unknown')}}</span><span class="track"><i class="fill" style="width:${{n(r[valueKey])/max*100}}%;background:${{color}}"></i></span><span class="amount">${{formatter(r[valueKey])}}</span></div>`).join('')||'<span class="badge">No rows</span>';}}
const sourceNames=Object.fromEntries(D.source_rows.map(r=>[String(r.source).toLowerCase(),r]));
document.getElementById('sourceStrip').innerHTML=D.source_rows.map(r=>`<div>${{esc(String(r.source).toUpperCase())}}<b>${{dur(r.watch_hours)}} | ${{fmt(r.ip_users)}} IP activity</b></div>`).join('')+`<div>DAY WINDOW<b>00:00 - 23:59 IST</b></div><div>METRIC BASIS<b>ALL STATUS CODES</b></div>`;
const latency=D.latency,statusTotal=sum(D.statuses,'requests'),status2xx=D.statuses.filter(r=>/^2/.test(String(r.status_code))).reduce((t,r)=>t+n(r.requests),0),success=statusTotal?status2xx/statusTotal*100:0;
const kpis=[
 ['ACTIVE STREAMS',fmt(D.summary.active_streams),'Last observed minute','green'],
 ['PEAK ACTIVE STREAMS',fmt(D.summary.peak_active_streams),time(D.summary.peak_time),'cyan'],
 ['IP ACTIVITY',fmt(D.summary.ip_activity),subDelta(D.summary.ip_activity,D.prior.ip_activity),'violet'],
 ['WATCH TIME',dur(D.summary.watch_hours),subDelta(D.summary.watch_hours,D.prior.watch_hours),'orange'],
 ['STREAM SESSIONS',fmt(D.summary.stream_sessions),'Query identity when present','yellow'],
 ['STREAM DEVICES',fmt(D.summary.stream_devices),'Distinct decoded identity','green'],
 ['HTTP 2XX SHARE',`${{dec(success,2)}}%`,`${{fmt(latency.status_200_rows)}} exact 200 rows`,'red']
];
document.getElementById('kpis').innerHTML=kpis.map((k,i)=>`<div class="kpi"><div class="label">${{k[0]}}</div><div class="value">${{k[1]}}</div><div class="sub">${{k[2]}}</div><canvas id="spark${{i}}"></canvas></div>`).join('');
const conc=D.minute.map(r=>n(r.active_streams_estimate)),req=D.hourly.map(r=>n(r.requests)),ttfb=D.hourly.map(r=>n(r.ttfb_p50_ms));
const colors={{green:'#50d66d',cyan:'#3aa7ff',violet:'#bf62e5',orange:'#ff9f43',yellow:'#e4d44d',red:'#ff5c61'}};
kpis.forEach((k,i)=>line(document.getElementById(`spark${{i}}`),i<2?conc:(i===2?D.minute.map(r=>n(r.segment_requests)):(i===6?D.hourly.map(r=>n(r.status_200_rows)):req)),colors[k[3]],true));
line(document.getElementById('concurrencyChart'),conc,colors.green,true);line(document.getElementById('ttfbChart'),ttfb,colors.cyan,true);line(document.getElementById('requestChart'),req,colors.violet,true);
document.getElementById('audienceMetrics').innerHTML=[metric('Watch time',dur(D.summary.watch_hours)),metric('IP activity (source sum)',fmt(D.summary.ip_activity)),metric('Segment / clip views',fmt(D.summary.views)),metric('Peak estimate',fmt(D.summary.peak_active_streams)),metric('Peak minute',time(D.summary.peak_time)),metric('Observed minutes',fmt(D.minute.length))].join('');
const cacheTotal=sum(D.cache,'requests'),cacheHit=D.cache.filter(r=>/hit/i.test(r.cache_status)||String(r.cache_status)==='1').reduce((t,r)=>t+n(r.requests),0);
document.getElementById('deliveryMetrics').innerHTML=[metric('Requests',fmt(latency.requests)),metric('HTTP 2xx share',dec(success,2)+'%'),metric('5xx rows',fmt(latency.status_5xx_rows)),metric('Weighted TTFB p50',dec(latency.ttfb_p50_ms,1)+' ms'),metric('Weighted TTFB p95',dec(latency.ttfb_p95_ms,1)+' ms'),metric('Median throughput value',dec(latency.throughput_p50,1))].join('');
const byteCoverage=n(D.bandwidth.segment_requests)?n(D.bandwidth.rows_with_bytes)/n(D.bandwidth.segment_requests)*100:0;
document.getElementById('networkMetrics').innerHTML=[metric('FAST traffic bytes',bytes(D.bandwidth.total_bytes)),metric('Byte-field coverage',dec(byteCoverage,1)+'%'),metric('Cache HIT share',cacheTotal?dec(cacheHit/cacheTotal*100,1)+'%':'N/A'),metric('Non-200 rows',fmt(latency.non_200_rows)),metric('Turnaround p50',dec(latency.turnaround_p50_ms,1)+' ms'),metric('Transfer p50',dec(latency.transfer_p50_ms,1)+' ms')].join('');
bars('channelBars',D.channels,'channel_name','watch_hours',dur,'var(--green)',9);
document.getElementById('contentRows').innerHTML=D.content.slice(0,8).map(r=>`<tr><td class="truncate" title="${{esc(r.content_title)}}">${{esc(r.content_title)}}</td><td>${{dur(r.watch_hours)}}</td><td>${{fmt(r.segment_requests)}}</td></tr>`).join('')||'<tr><td colspan="3">No resolved STREAM titles</td></tr>';
const preferredDevice=['device_type','form_factor','platform','os'];let deviceRows=[];for(const d of preferredDevice){{deviceRows=D.devices.filter(r=>String(r.dimension).toLowerCase().includes(d));if(deviceRows.length)break}}if(!deviceRows.length)deviceRows=D.devices;
bars('deviceBars',deviceRows,'label','segment_requests',fmt,'var(--cyan)',6);
let marketRows=D.markets.filter(r=>/state|city/i.test(r.market_level));if(!marketRows.length)marketRows=D.markets;
bars('marketBars',marketRows,'label','segment_requests',fmt,'var(--orange)',6);bars('asnBars',D.asns,'network','requests',fmt,'var(--violet)',6);bars('hostBars',D.hosts,'host','requests',fmt,'var(--cyan)',6);bars('statusBars',D.statuses,'status_code','requests',fmt,'var(--red)',7);
const alerts=[];alerts.push({{level:success>=99?'good':success>=95?'warn':'bad',title:'HTTP delivery',body:`${{dec(success,2)}}% rows returned 200`}});alerts.push({{level:n(latency.status_5xx_rows)===0?'good':n(latency.status_5xx_rows)<n(latency.requests)*.001?'warn':'bad',title:'Server errors',body:`${{fmt(latency.status_5xx_rows)}} 5xx rows`}});alerts.push({{level:byteCoverage>=95?'good':byteCoverage>=70?'warn':'bad',title:'Traffic-byte coverage',body:`${{dec(byteCoverage,1)}}% of FAST segment rows`}});alerts.push({{level:'good',title:'Watch-time basis',body:'All media segments, all status codes'}});
document.getElementById('alerts').innerHTML=alerts.map(a=>`<div class="alert ${{a.level}}"><span>${{a.level.toUpperCase()}}</span><strong>${{a.title}}</strong>${{a.body}}</div>`).join('');
document.getElementById('basis').innerHTML=['Processed Parquet marts','Watch time: segment count x 6 seconds','IP activity is summed by source and may overlap','Concurrency is an active-stream estimate','Devices and sessions are STREAM identity only','Content titles are resolved STREAM metadata only','TTFB percentiles are row-weighted rollups','No revenue, social, score, or broadcast status fabricated'].map(v=>`<span class="badge">${{v}}</span>`).join('');
document.getElementById('summaryMetrics').innerHTML=[metric('FAST watch time',dur(sourceNames.fast?.watch_hours)),metric('STREAM watch time',dur(sourceNames.stream?.watch_hours)),metric('Total requests',fmt(latency.requests)),metric('HTTP 2xx share',dec(success,2)+'%'),metric('Known traffic bytes',bytes(D.bandwidth.total_bytes)),metric('Top channel',D.channels[0]?.channel_name||'Unknown')].join('');
document.getElementById('footerText').textContent=`Generated ${{new Date(D.generated_at).toLocaleString('en-IN')}} from processed ETL Parquet marts. Date: ${{D.date}}.`;
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.target)?.scrollIntoView({{behavior:'smooth'}})));
document.getElementById('exportButton').addEventListener('click',()=>{{const rows=[['date','metric','value'],[D.date,'watch_hours',D.summary.watch_hours],[D.date,'ip_activity_source_sum',D.summary.ip_activity],[D.date,'estimated_peak_active_streams',D.summary.peak_active_streams],[D.date,'stream_devices',D.summary.stream_devices],[D.date,'stream_sessions',D.summary.stream_sessions],[D.date,'requests',latency.requests],[D.date,'http_2xx_share_pct',success],[D.date,'status_5xx_rows',latency.status_5xx_rows],[D.date,'fast_total_bytes',D.bandwidth.total_bytes]];const csv=rows.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\\r\\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));a.download=`veto_ops_${{D.date}}.csv`;a.click();URL.revokeObjectURL(a.href);}});
window.addEventListener('resize',()=>{{line(document.getElementById('concurrencyChart'),conc,colors.green,true);line(document.getElementById('ttfbChart'),ttfb,colors.cyan,true);line(document.getElementById('requestChart'),req,colors.violet,true)}});
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Processed IST date in YYYY-MM-DD format.")
    parser.add_argument("--out", type=Path, help="Standalone HTML output path.")
    args = parser.parse_args()

    target_date = args.date
    if not target_date:
        connection = duckdb.connect(":memory:")
        try:
            target_date = str(
                connection.execute(
                    "SELECT max(log_date) FROM read_parquet(?)", [str(MARTS["source"])]
                ).fetchone()[0]
            )
        finally:
            connection.close()
    datetime.strptime(target_date, "%Y-%m-%d")

    output = args.out or DEFAULT_OUTPUT_DIR / f"veto_audience_cdn_war_room_{target_date}.html"
    payload = build_payload(target_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload), encoding="utf-8")

    print(f"Built {output}")
    print(
        f"{target_date}: {payload['summary']['watch_hours']:,.2f} watch hours, "
        f"{payload['summary']['ip_activity']:,} source-summed IP activity, "
        f"{payload['summary']['peak_active_streams']:,.0f} estimated peak active streams."
    )


if __name__ == "__main__":
    main()
