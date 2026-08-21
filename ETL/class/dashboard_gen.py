#!/usr/bin/env python3
"""Generate the Phase 1 Watch Hours dashboard from the canonical daily marts.

Expected input schema (Parquet, one row per daily geographic channel aggregate):
    log_date                  VARCHAR, ISO date (YYYY-MM-DD)
    source                    VARCHAR, e.g. fast or stream
    country                   VARCHAR, geographic region code/name; null is allowed
    channel_name              VARCHAR, canonical channel label; null is allowed
    raw_watch_hours           numeric, watch hours across all status codes

FAST platform input schema (used only when a FAST platform is selected):
    log_date, source, country, channel_name, platform_name/platform_key,
    raw_watch_hours

The current canonical input is:
    output/watch_hours/daily_tables/channel_geo_daily.parquet

The base KPI uses the canonical channel + geography mart. A selected FAST
platform switches to the documented FAST platform + channel geography mart;
the UI labels that selected-platform result as platform-tagged FAST data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb


HERE = Path(__file__).resolve().parent
ETL_ROOT = HERE.parent
DEFAULT_INPUT = ETL_ROOT / "output" / "watch_hours" / "daily_tables" / "channel_geo_daily.parquet"
DEFAULT_PLATFORM_INPUT = ETL_ROOT / "output" / "watch_hours" / "concurrency" / "fast_platform_channel_geo_daily.parquet"
DEFAULT_OUTPUT = HERE / "watch_hours_phase1.html"
REQUIRED_COLUMNS = {
    "log_date",
    "source",
    "country",
    "channel_name",
    "raw_watch_hours",
}
PLATFORM_COLUMNS = {"platform_name", "platform_key"}


def parquet_columns(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Input Parquet was not found: {path}")
    connection = duckdb.connect(":memory:")
    try:
        return {
            row[0]
            for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        }
    finally:
        connection.close()


def validate_input(path: Path) -> set[str]:
    columns = parquet_columns(path)
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"Input Parquet is missing required column(s): {', '.join(missing)}")
    return columns


def validate_platform_input(path: Path) -> set[str]:
    columns = validate_input(path)
    if not PLATFORM_COLUMNS.intersection(columns):
        expected = " or ".join(sorted(PLATFORM_COLUMNS))
        raise ValueError(f"FAST platform Parquet needs one of: {expected}")
    return columns


def load_rows(path: Path) -> list[list[Any]]:
    """Read and aggregate only the five columns used by the base KPI."""
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                COALESCE(NULLIF(TRIM(source), ''), 'Unknown') AS source,
                COALESCE(NULLIF(TRIM(country), ''), 'Unknown / NA') AS region,
                COALESCE(NULLIF(TRIM(channel_name), ''), 'Unknown / NA') AS channel_name,
                SUM(CAST(COALESCE(raw_watch_hours, 0) AS DOUBLE)) AS watch_hours
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
            GROUP BY 1, 2, 3, 4
            """,
            [str(path)],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), str(region), str(channel), float(hours)] for log_date, source, region, channel, hours in rows]


def load_platform_rows(path: Path) -> list[list[Any]]:
    """Read FAST platform + channel geography rows for the optional FAST filter."""
    columns = validate_platform_input(path)
    if {"platform_name", "platform_key"}.issubset(columns):
        platform_expression = "COALESCE(NULLIF(TRIM(platform_name), ''), NULLIF(TRIM(platform_key), ''), 'Unknown / NA')"
    else:
        platform_column = next(iter(PLATFORM_COLUMNS.intersection(columns)))
        platform_expression = f"COALESCE(NULLIF(TRIM({platform_column}), ''), 'Unknown / NA')"
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            f"""
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                'fast' AS source,
                COALESCE(NULLIF(TRIM(country), ''), 'Unknown / NA') AS region,
                COALESCE(NULLIF(TRIM(channel_name), ''), 'Unknown / NA') AS channel_name,
                SUM(CAST(COALESCE(raw_watch_hours, 0) AS DOUBLE)) AS watch_hours,
                {platform_expression} AS platform
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
            GROUP BY 1, 2, 3, 4, 6
            """,
            [str(path)],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), str(region), str(channel), float(hours), str(platform)] for log_date, source, region, channel, hours, platform in rows]


def render_html(rows: list[list[Any]], platform_rows: list[list[Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    platform_payload = json.dumps(platform_rows, ensure_ascii=True, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watch Hours</title>
<style>
*{{box-sizing:border-box}}
:root{{--canvas:#f4f5f7;--surface:#ffffff;--ink:#17202b;--muted:#66717d;--line:#d7dde3;--accent:#b85c38;--accent-dark:#7b3520;--shadow:0 2px 8px rgba(28,38,48,.08)}}
html{{background:var(--canvas)}}
body{{margin:0;background:var(--canvas);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;font-size:14px;line-height:1.4}}
.filter-shell{{position:sticky;top:0;z-index:30;background:rgba(244,245,247,.98);border-bottom:1px solid var(--line);box-shadow:0 2px 8px rgba(28,38,48,.06);padding:8px 12px}}
.filter-bar{{display:flex;flex-wrap:wrap;align-items:end;gap:6px 8px}}
.filter-field{{display:grid;gap:4px;min-width:0;flex:0 0 auto}}
.filter-field label{{font-size:10.5px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:#536277}}
.date-label{{display:flex;align-items:center;gap:5px;white-space:nowrap}}.date-availability{{margin-left:auto;color:var(--muted);font-size:9px;font-weight:650;letter-spacing:0;text-transform:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.filter-field.source{{width:102px}}.filter-field.date{{width:270px}}.filter-field.multi{{width:170px}}.filter-field.platform{{width:170px}}.filter-field[hidden]{{display:none}}
select,input[type=date],.multi-toggle{{width:100%;height:30px;border:1px solid #c5cdd5;border-radius:4px;background:var(--surface);color:var(--ink);font:inherit;font-size:12px;font-weight:650;padding:5px 7px;outline:none}}
select:focus,input[type=date]:focus,.multi-toggle:focus-visible{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(184,92,56,.14)}}
.date-pair{{display:flex;align-items:center;gap:4px}}.date-pair input{{width:123px;min-width:123px}}.date-separator{{color:var(--muted);font-size:10px}}
.multi-picker{{position:relative}}.multi-toggle{{display:flex;align-items:center;justify-content:space-between;gap:8px;text-align:left;cursor:pointer}}.multi-toggle:hover{{border-color:#91a5b7}}.multi-toggle .caret{{color:var(--muted);font-size:11px}}
.multi-menu{{display:none;position:absolute;top:calc(100% + 6px);left:0;width:100%;min-width:260px;max-height:min(400px,calc(100vh - 100px));overflow:hidden;z-index:40;border:1px solid #bdcbd8;border-radius:6px;background:#fff;box-shadow:var(--shadow);padding:7px}}.multi-menu.open{{display:flex;flex-direction:column}}
.picker-search{{height:30px;border:1px solid #c5cdd5;border-radius:4px;padding:5px 7px;font:inherit;font-size:12px;outline:none}}.picker-search:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(184,92,56,.14)}}
.picker-actions{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 1px 6px;border-bottom:1px solid #e3e9ef;color:var(--muted);font-size:11px;font-weight:700}}.text-button{{border:0;background:transparent;color:var(--accent-dark);font:inherit;font-size:11px;font-weight:850;cursor:pointer;padding:2px}}
.option-list{{overflow:auto;padding-top:4px;overscroll-behavior:contain}}.option{{display:flex;align-items:center;gap:8px;padding:7px 5px;border-radius:4px;color:#263348;font-size:12px;font-weight:650;cursor:pointer}}.option:hover{{background:#fff5f0}}.option input{{accent-color:var(--accent);margin:0}}.option[hidden]{{display:none}}
main{{max-width:none;margin:0;padding:14px 12px 0}}.section-head{{margin-bottom:8px}}h1{{margin:0;font-size:20px;letter-spacing:0;font-weight:780;color:#17202b}}
.kpi{{max-width:500px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:5px;background:var(--surface);box-shadow:var(--shadow);padding:16px 18px}}.kpi-label{{color:#5f6974;font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}.kpi-value{{margin-top:6px;font-size:40px;font-weight:780;letter-spacing:0;line-height:1;color:#17202b;font-variant-numeric:tabular-nums}}.kpi-unit{{margin-left:6px;color:var(--accent-dark);font-size:15px;font-weight:750}}.kpi-detail{{margin-top:8px;color:var(--muted);font-size:11px}}
.loading-overlay{{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;gap:9px;background:rgba(245,247,249,.58);opacity:0;pointer-events:none;transition:opacity .12s ease}}.loading-overlay.active{{opacity:1;pointer-events:auto}}.loading-message{{display:flex;align-items:center;gap:8px;border:1px solid #c9d8df;border-radius:5px;background:#fff;box-shadow:var(--shadow);padding:8px 10px;color:var(--accent-dark);font-size:12px;font-weight:750}}.loading-mark{{width:8px;height:8px;border-radius:50%;background:var(--accent)}}
@media(max-width:820px){{.filter-shell{{padding:8px 10px}}main{{padding:12px 10px 0}}}}
@media(max-width:520px){{.filter-field.source{{width:102px}}.filter-field.date{{width:258px}}.filter-field.multi{{width:160px}}.date-pair input{{width:117px;min-width:117px}}.kpi{{padding:18px}}.kpi-value{{font-size:32px}}}}
</style>
</head>
<body>
<div class="loading-overlay" id="loadingOverlay" aria-hidden="true"><div class="loading-message"><span class="loading-mark"></span>Updating filters</div></div>
<header class="filter-shell" aria-label="Dashboard filters">
  <div class="filter-bar">
    <div class="filter-field source"><label for="sourceFilter">Source</label><select id="sourceFilter"></select></div>
    <div class="filter-field date"><label class="date-label" for="dateFrom"><span>Date range</span><span class="date-availability" id="dateHint"></span></label><div class="date-pair"><input id="dateFrom" type="date"><span class="date-separator">to</span><input id="dateTo" type="date"></div></div>
    <div class="filter-field multi"><label>Channel</label><div class="multi-picker" id="channelPicker"></div></div>
    <div class="filter-field multi platform" id="platformField"><label>Platform</label><div class="multi-picker" id="platformPicker"></div></div>
    <div class="filter-field multi"><label>Region</label><div class="multi-picker" id="regionPicker"></div></div>
  </div>
</header>
<main>
  <section aria-labelledby="watchHoursTitle">
    <div class="section-head"><h1 id="watchHoursTitle">Watch Hours</h1></div>
    <div class="kpi" id="watchHoursKpi"><div class="kpi-label" id="kpiLabel">Total Watch Hours</div><div><span class="kpi-value" id="watchHoursValue">0.00</span><span class="kpi-unit">hours</span></div><div class="kpi-detail" id="kpiDetail"></div></div>
  </section>
</main>
<script>
const rows={payload};
const platformRows={platform_payload};
const state={{source:'fast',from:'',to:'',channels:new Set(),regions:new Set(),platforms:new Set()}};
const byId=id=>document.getElementById(id);
const unique=(index)=>[...new Set(rows.map(row=>row[index]))].sort((a,b)=>a.localeCompare(b));
const allSources=['fast','stream'].filter(source=>rows.some(row=>row[1]===source)),allRegions=unique(2);
const allPlatforms=[...new Set(platformRows.map(row=>row[5]))].sort((a,b)=>a.localeCompare(b));
const channelsForSource=source=>[...new Set(rows.filter(row=>row[1]===source).map(row=>row[3]))].sort((a,b)=>a.localeCompare(b));
const formatHours=new Intl.NumberFormat('en-IN',{{minimumFractionDigits:2,maximumFractionDigits:2}});
const formatNumber=new Intl.NumberFormat('en-IN');
const regionNames=typeof Intl.DisplayNames==='function'?new Intl.DisplayNames(['en'],{{type:'region'}}):null;
let renderToken=0;
function selectedText(label,selected,total){{return !selected.size||selected.size===total?`All ${{label.toLowerCase()}}`:`${{selected.size}} selected`}}
function regionLabel(value){{if(value==='Unknown / NA'||!regionNames)return value;try{{const name=regionNames.of(value);return name&&name!==value?`${{value}} - ${{name}}`:value}}catch(error){{return value}}}}
function buildSource(){{const select=byId('sourceFilter');select.innerHTML=allSources.map(value=>`<option value="${{escapeHtml(value)}}">${{escapeHtml(value.toUpperCase())}}</option>`).join('');if(!allSources.includes(state.source))state.source=allSources[0]||'';select.value=state.source;select.addEventListener('change',()=>{{state.source=select.value;state.channels.clear();buildChannelPicker();scheduleRender()}})}}
function buildChannelPicker(){{buildPicker('channelPicker','Channels',channelsForSource(state.source),'channels')}}
function buildPicker(id,label,values,key){{const root=byId(id);root.innerHTML=`<button type="button" class="multi-toggle" aria-expanded="false"><span data-label></span><span class="caret">v</span></button><div class="multi-menu"><input class="picker-search" type="search" placeholder="Search ${{label.toLowerCase()}}s..." autocomplete="off"><div class="picker-actions"><span data-status></span><button class="text-button" type="button">Clear</button></div><div class="option-list">${{values.map(value=>{{const text=label==='Regions'?regionLabel(value):value;return `<label class="option" data-value="${{escapeHtml(value)}}" data-search="${{escapeHtml((value+' '+text).toLocaleLowerCase())}}"><input type="checkbox" value="${{escapeHtml(value)}}"><span>${{escapeHtml(text)}}</span></label>`}}).join('')}}</div></div>`;
  const toggle=root.querySelector('.multi-toggle'),menu=root.querySelector('.multi-menu'),search=root.querySelector('.picker-search'),clear=root.querySelector('.text-button');
  toggle.addEventListener('click',event=>{{event.stopPropagation();document.querySelectorAll('.multi-menu.open').forEach(node=>{{if(node!==menu)node.classList.remove('open')}});const open=!menu.classList.contains('open');menu.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open));if(open)search.focus()}});
  root.querySelectorAll('input[type=checkbox]').forEach(input=>input.addEventListener('change',()=>{{if(input.checked)state[key].add(input.value);else state[key].delete(input.value);scheduleRender()}}));
  search.addEventListener('input',()=>{{const term=search.value.trim().toLocaleLowerCase();root.querySelectorAll('.option').forEach(option=>option.hidden=!option.dataset.search.includes(term))}});
  clear.addEventListener('click',()=>{{state[key].clear();scheduleRender()}});
}}
function refreshPicker(id,label,key,total){{const root=byId(id),selected=state[key],all=!selected.size||selected.size===total;root.querySelector('[data-label]').textContent=selectedText(label,selected,total);root.querySelector('[data-status]').textContent=all?'All selected':`${{selected.size}} selected`;root.querySelectorAll('input[type=checkbox]').forEach(input=>input.checked=selected.has(input.value))}}
function matches(row,includePlatform,channelActive,regionActive,platformActive){{return row[1]===state.source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(!channelActive||state.channels.has(row[3]))&&(!regionActive||state.regions.has(row[2]))&&(!includePlatform||!platformActive||state.platforms.has(row[5]))}}
function render(){{const channelTotal=channelsForSource(state.source).length,regionTotal=allRegions.length,platformTotal=allPlatforms.length;const channelActive=state.channels.size>0&&state.channels.size<channelTotal,regionActive=state.regions.size>0&&state.regions.size<regionTotal,platformActive=state.platforms.size>0&&state.platforms.size<platformTotal;const usePlatform=state.source==='fast'&&platformActive;const activeRows=usePlatform?platformRows:rows;const scoped=activeRows.filter(row=>matches(row,usePlatform,channelActive,regionActive,platformActive));const hours=scoped.reduce((total,row)=>total+Number(row[4]||0),0);byId('kpiLabel').textContent=usePlatform?'FAST platform-tagged watch hours':'Total Watch Hours';byId('watchHoursValue').textContent=formatHours.format(hours);byId('kpiDetail').textContent=usePlatform?`${{formatNumber.format(scoped.length)}} FAST platform-tagged rows matched`:`${{formatNumber.format(scoped.length)}} canonical aggregate rows matched`;byId('platformField').hidden=state.source!=='fast';refreshPicker('channelPicker','Channels','channels',channelTotal);refreshPicker('regionPicker','Regions','regions',regionTotal);refreshPicker('platformPicker','Platforms','platforms',platformTotal)}}
function escapeHtml(value){{return String(value).replace(/[&<>'"]/g,char=>({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[char]))}}
function scheduleRender(){{const token=++renderToken,overlay=byId('loadingOverlay');overlay.classList.add('active');overlay.setAttribute('aria-hidden','false');requestAnimationFrame(()=>{{render();window.setTimeout(()=>{{if(token!==renderToken)return;overlay.classList.remove('active');overlay.setAttribute('aria-hidden','true')}},90)}})}}
function initialise(){{const dates=unique(0);const minDate=dates[0]||'',maxDate=dates.at(-1)||'';state.from=minDate;state.to=maxDate;
  const from=byId('dateFrom'),to=byId('dateTo'),hint=byId('dateHint');
  const syncDateBounds=()=>{{from.min=minDate;from.max=state.to||maxDate;to.min=state.from||minDate;to.max=maxDate}};
  from.value=state.from;to.value=state.to;syncDateBounds();
  hint.textContent=dates.length?`${{formatNumber.format(dates.length)}} dates available`:'No dates available';
  from.addEventListener('change',()=>{{state.from=from.value;if(state.from&&state.to&&state.from>state.to){{state.to=state.from;to.value=state.to}}syncDateBounds();scheduleRender()}});
  to.addEventListener('change',()=>{{state.to=to.value;if(state.from&&state.to&&state.to<state.from){{state.from=state.to;from.value=state.from}}syncDateBounds();scheduleRender()}});
  buildSource();buildChannelPicker();buildPicker('regionPicker','Regions',allRegions,'regions');buildPicker('platformPicker','Platforms',allPlatforms,'platforms');
  document.addEventListener('click',event=>{{if(!event.target.closest('.multi-picker'))document.querySelectorAll('.multi-menu.open').forEach(menu=>menu.classList.remove('open'))}});
  render()}}
initialise();
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the standalone Phase 1 Watch Hours dashboard.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Canonical channel + geography daily Parquet mart.")
    parser.add_argument("--platform-input", type=Path, default=DEFAULT_PLATFORM_INPUT, help="FAST platform + channel geography Parquet mart.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Output standalone HTML path.")
    args = parser.parse_args()
    validate_input(args.input)
    rows = load_rows(args.input)
    platform_rows = load_platform_rows(args.platform_input)
    if not rows:
        raise ValueError(f"Input Parquet contains no usable rows: {args.input}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(rows, platform_rows), encoding="utf-8")
    print(f"Wrote {args.out} with {len(rows):,} aggregate rows.")


if __name__ == "__main__":
    main()
