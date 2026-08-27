#!/usr/bin/env python3
"""Build an incremental VOD STREAM query-string dashboard from event CSV exports.

The source event CSV is deliberately request-level so the dashboard can retain
the raw identifiers requested for audit: CLI IP, device ID, and session ID.
Use --append for a newly exported day; existing dates are preserved and exact
duplicate requests are discarded before the dashboard is regenerated.
"""

from __future__ import annotations

# Compatibility entry point for the original filename. The maintained VOD
# dashboard generator now lives in build_vod_query_dashboard.py.
if __name__ == "__main__":
    from build_vod_query_dashboard import main as _main

    _main()
    raise SystemExit

import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote_plus


HERE = Path(__file__).resolve().parent
ETL_ROOT = HERE.parents[1]
DEFAULT_EVENTS = ETL_ROOT / "output" / "exports" / "vod_stream_query_events.csv"
DEFAULT_OUTPUT = ETL_ROOT / "output" / "exports" / "vod_stream_query_analysis_dashboard.html"


def clean(value: object) -> str:
    return unquote_plus(str(value or "")).strip()


def read_events(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Event CSV was not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: clean(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def event_key(row: dict[str, str]) -> tuple[str, ...]:
    """A request timestamp plus origin/path/identity is stable across exports."""
    return tuple(row.get(key, "") for key in ("request_ist", "cli_ip", "req_host", "req_path", "session_id", "device_id"))


def merge_events(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    incoming_dates = {row.get("log_date", "") for row in incoming}
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    # A rerun for one date replaces that day's earlier manifests or segments.
    for row in [row for row in existing if row.get("log_date", "") not in incoming_dates] + incoming:
        merged[event_key(row)] = row
    return sorted(merged.values(), key=lambda row: (row.get("log_date", ""), row.get("request_ist", "")))


def write_events(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(value: str) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def day_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    cli_ips = {row["cli_ip"] for row in rows if row.get("cli_ip")}
    devices = {row["device_id"] for row in rows if row.get("device_id")}
    sessions = {row["session_id"] for row in rows if row.get("session_id")}
    minute_ips: dict[str, set[str]] = defaultdict(set)
    media_rows = [row for row in rows if number(row.get("is_media_segment", "")) == 1]
    for row in media_rows:
        if row.get("cli_ip"):
            minute_ips[row.get("minute_ist", "")].add(row["cli_ip"])
    return {
        "requests": len(rows),
        "media_segments": len(media_rows),
        "cli_ips": len(cli_ips),
        "device_ids": len(devices),
        "session_ids": len(sessions),
        "watch_hours": round(sum(number(row.get("request_watch_hours", "")) for row in rows), 6),
        "peak_concurrency": max((len(values) for values in minute_ips.values()), default=0),
    }


def dashboard_script() -> str:
    """Client-side dashboard logic kept separate from the HTML shell.

    This follows the Watch Hours dashboard pattern: filter state is read from
    the controls first, then every KPI and table is rendered from that scope.
    """
    return """<script>
const days=__PAYLOAD__;
const by=id=>document.getElementById(id);
const countFmt=new Intl.NumberFormat('en-IN');
const hourFmt=new Intl.NumberFormat('en-IN',{maximumFractionDigits:3});
const minuteFmt=new Intl.NumberFormat('en-IN',{maximumFractionDigits:1});
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let current=null;
let activeRows=[];
const filterState={title:new Set(),category:new Set()};
function duration(hours){return hours<1?`${minuteFmt.format(hours*60)} min`:`${hourFmt.format(hours)} h`;}
function selectedValues(id){return filterState[id==='titleFilter'?'title':'category'];}
function optionValues(field){return [...new Set(days.flatMap(day=>day.rows.map(row=>row[field])).filter(Boolean))].sort((a,b)=>a.localeCompare(b));}
function populateSelect(id,field){const type=id==='titleFilter'?'title':'category',values=optionValues(field);by(id).innerHTML=values.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');by(`${type}Options`).innerHTML=values.map(value=>`<label class="picker-option"><input type="checkbox" value="${esc(value)}"><span>${esc(value)}</span></label>`).join('')+`<div class="picker-empty" id="${type}OptionsEmpty" hidden>No matches</div>`;by(`${type}Options`).querySelectorAll('input').forEach(input=>input.addEventListener('change',()=>{input.checked?filterState[type].add(input.value):filterState[type].delete(input.value);by(id).value=[...filterState[type]][0]||'';updatePicker(type);render();}));updatePicker(type);}
function updatePicker(type){const set=filterState[type],toggle=by(`${type}Toggle`);toggle.textContent=set.size?`${set.size} selected`:`All ${type}s`;by(`${type}Options`).querySelectorAll('input').forEach(input=>input.checked=set.has(input.value));}
function setFilter(type,selectAll){const values=[...by(`${type}Options`).querySelectorAll('input')].map(input=>input.value);filterState[type]=new Set(selectAll?values:[]);updatePicker(type);render();}
function filterDropdown(searchId,optionsId){const query=by(searchId).value.trim().toLowerCase();let visible=0;for(const option of by(optionsId).querySelectorAll('.picker-option')){option.hidden=Boolean(query)&&!option.textContent.toLowerCase().includes(query);if(!option.hidden)visible++;}const empty=by(`${optionsId}Empty`);if(empty)empty.hidden=visible!==0;}
function togglePicker(type){const picker=by(`${type}Picker`);document.querySelectorAll('.picker.open').forEach(item=>{if(item!==picker)item.classList.remove('open');});const open=picker.classList.toggle('open');if(open)setTimeout(()=>by(`${type}Search`).focus(),0);}
function selectedRows(){
  const from=by('dateFrom').value||days[0]?.date||'';
  const to=by('dateTo').value||days.at(-1)?.date||'';
  const selectedDays=days.filter(day=>day.date>=from&&day.date<=to);
  current={date:`${from} to ${to}`,rows:selectedDays.flatMap(day=>day.rows)};
  const titles=selectedValues('titleFilter');
  const categories=selectedValues('categoryFilter');
  return current.rows.filter(row=>(!titles.size||titles.has(row.content_title))&&(!categories.size||categories.has(row.category_name)));
}
function summarize(rows){
  const minuteIps=new Map();
  for(const row of rows){if(row.cli_ip){const minute=row.minute_ist||'';if(!minuteIps.has(minute))minuteIps.set(minute,new Set());minuteIps.get(minute).add(row.cli_ip);}}
  return {requests:rows.length,media_segments:rows.length,cli_ips:new Set(rows.map(row=>row.cli_ip).filter(Boolean)).size,device_ids:new Set(rows.map(row=>row.device_id).filter(Boolean)).size,session_ids:new Set(rows.map(row=>row.session_id).filter(Boolean)).size,watch_hours:rows.reduce((sum,row)=>sum+Number(row.request_watch_hours||0),0),peak_concurrency:Math.max(0,...[...minuteIps.values()].map(ips=>ips.size))};
}
function grouped(rows,key){
  const groups=new Map();
  for(const row of rows){const label=key(row)||'Unknown / NA';const group=groups.get(label)||{label,requests:0,hours:0,ips:new Set(),devices:new Set(),sessions:new Set()};group.requests++;group.hours+=Number(row.request_watch_hours||0);if(row.cli_ip)group.ips.add(row.cli_ip);if(row.device_id)group.devices.add(row.device_id);if(row.session_id)group.sessions.add(row.session_id);groups.set(label,group);}
  return [...groups.values()].sort((a,b)=>b.hours-a.hours||b.requests-a.requests).slice(0,40);
}
function rowsHtml(items,renderer){return items.map(renderer).join('')||'<tr><td colspan="4">No matching data</td></tr>';}
function renderKpis(summary){by('kpis').innerHTML=[['VOD Requests',summary.requests],['Media Segments',summary.media_segments],['Unique CLI IPs',summary.cli_ips],['Device IDs',summary.device_ids],['Session IDs',summary.session_ids],['Segment Watch Time',duration(summary.watch_hours)],['Peak Media CLI IPs',summary.peak_concurrency]].map(([label,value])=>`<div class="kpi"><span>${label}</span><strong>${typeof value==='number'?countFmt.format(value):value}</strong></div>`).join('');}
function renderTables(rows){
  by('titles').innerHTML=rowsHtml(grouped(rows,row=>[row.content_title,row.category_name].filter(Boolean).join(' | ')),group=>`<tr><td>${esc(group.label)}</td><td class="num">${countFmt.format(group.requests)}</td><td class="num">${countFmt.format(group.ips.size)}</td><td class="num">${duration(group.hours)}</td><td class="num">${countFmt.format(group.devices.size)}</td><td class="num">${countFmt.format(group.sessions.size)}</td></tr>`);
  by('regions').innerHTML=rowsHtml(grouped(rows,row=>[row.country,row.state].filter(Boolean).join(' / ')),group=>`<tr><td>${esc(group.label)}</td><td class="num">${countFmt.format(group.ips.size)}</td><td class="num">${countFmt.format(group.sessions.size)}</td><td class="num">${countFmt.format(group.devices.size)}</td><td class="num">${duration(group.hours)}</td></tr>`);
  by('devices').innerHTML=rowsHtml(grouped(rows,row=>[row.platform,row.device].filter(Boolean).join(' / ')),group=>`<tr><td>${esc(group.label)}</td><td class="num">${countFmt.format(group.ips.size)}</td><td class="num">${countFmt.format(group.devices.size)}</td><td class="num">${countFmt.format(group.sessions.size)}</td><td class="num">${duration(group.hours)}</td><td class="num">${countFmt.format(group.requests)}</td></tr>`);
  by('routes').innerHTML=rowsHtml(grouped(rows,row=>[row.req_host,row.req_path].filter(Boolean).join(' / ')),group=>`<tr><td>${esc(group.label)}</td><td class="num">${countFmt.format(group.requests)}</td><td class="num">${countFmt.format(group.ips.size)}</td><td class="num">${duration(group.hours)}</td></tr>`);
  by('minutes').innerHTML=rowsHtml(grouped(rows,row=>row.minute_ist).sort((a,b)=>b.ips.size-a.ips.size||b.requests-a.requests),group=>`<tr><td>${esc(group.label)}</td><td class="num">${countFmt.format(group.ips.size)}</td><td class="num">${countFmt.format(group.requests)}</td></tr>`);
}
function renderSessionDetails(rows){
  const groups=new Map();
  for(const row of rows){
    const session=row.session_id||'Unknown / NA';
    const key=[row.content_title,row.category_name,session,row.device_id||'Unknown / NA',row.state||'Unknown / NA'].join('\u0001');
    const group=groups.get(key)||{title:row.content_title||'Unknown / NA',category:row.category_name||'Unknown / NA',session,device:row.device_id||'Unknown / NA',state:row.state||'Unknown / NA',first:row.request_ist,last:row.request_ist,segments:0,watch:0};
    group.first=group.first<row.request_ist?group.first:row.request_ist;group.last=group.last>row.request_ist?group.last:row.request_ist;group.segments++;group.watch+=Number(row.request_watch_hours||0);groups.set(key,group);
  }
  const items=[...groups.values()].sort((a,b)=>b.watch-a.watch).slice(0,1000);
  by('sessionDetails').innerHTML=items.map(group=>{const observed=Math.max(0,(Date.parse(group.last.replace(' ','T'))-Date.parse(group.first.replace(' ','T')))/3600000);return `<tr><td>${esc(group.title)}</td><td>${esc(group.category)}</td><td>${esc(group.session)}</td><td>${esc(group.device)}</td><td>${esc(group.state)}</td><td>${esc(group.first)}</td><td>${esc(group.last)}</td><td class="num">${duration(observed)}</td><td class="num">${duration(group.watch)}</td></tr>`}).join('')||'<tr><td colspan="9">No matching sessions</td></tr>';
}
function renderLedger(){const query=by('search').value.trim().toLowerCase();const rows=activeRows.filter(row=>!query||Object.values(row).join(' ').toLowerCase().includes(query)).slice(0,1000);by('ledger').innerHTML=rows.map(row=>`<tr><td>${esc(row.request_ist)}</td><td>${esc(row.content_title)}</td><td>${esc(row.channel)}</td><td>${esc(row.cli_ip)}</td><td>${esc(row.device_id)}</td><td>${esc(row.session_id)}</td><td>${esc([row.country,row.state,row.city].filter(Boolean).join(' / '))}</td><td>${esc([row.req_host,row.req_path].filter(Boolean).join(' / '))}</td></tr>`).join('')||'<tr><td colspan="8">No matching requests</td></tr>';}
function render(){activeRows=selectedRows();renderKpis(summarize(activeRows));renderTables(activeRows);renderSessionDetails(activeRows);renderLedger();}
populateSelect('titleFilter','content_title');
populateSelect('categoryFilter','category_name');
const firstDate=days[0]?.date||'',lastDate=days.at(-1)?.date||'';
by('dateFrom').min=firstDate;by('dateFrom').max=lastDate;by('dateFrom').value=firstDate;
by('dateTo').min=firstDate;by('dateTo').max=lastDate;by('dateTo').value=lastDate;
by('dateFrom').addEventListener('change',()=>{if(by('dateFrom').value>by('dateTo').value)by('dateTo').value=by('dateFrom').value;render();});
by('dateTo').addEventListener('change',()=>{if(by('dateTo').value<by('dateFrom').value)by('dateFrom').value=by('dateTo').value;render();});
by('titleToggle').addEventListener('click',()=>togglePicker('title'));
by('categoryToggle').addEventListener('click',()=>togglePicker('category'));
by('titleAll').addEventListener('click',()=>setFilter('title',true));
by('titleClear').addEventListener('click',()=>setFilter('title',false));
by('categoryAll').addEventListener('click',()=>setFilter('category',true));
by('categoryClear').addEventListener('click',()=>setFilter('category',false));
by('titleSearch').addEventListener('input',()=>filterDropdown('titleSearch','titleOptions'));
by('categorySearch').addEventListener('input',()=>filterDropdown('categorySearch','categoryOptions'));
by('titleSearch').addEventListener('click',event=>event.stopPropagation());
by('categorySearch').addEventListener('click',event=>event.stopPropagation());
by('titleSearch').addEventListener('mousedown',event=>event.stopPropagation());
by('categorySearch').addEventListener('mousedown',event=>event.stopPropagation());
by('search').addEventListener('input',renderLedger);
document.addEventListener('click',event=>{if(!event.target.closest('.picker'))document.querySelectorAll('.picker.open').forEach(item=>item.classList.remove('open'));});
render();
</script>"""


def render_html(rows: list[dict[str, str]]) -> str:
    dates = sorted({row.get("log_date", "") for row in rows if row.get("log_date")})
    days = []
    for day in dates:
        day_rows = [row for row in rows if row.get("log_date") == day]
        days.append({"date": day, "summary": day_summary(day_rows), "rows": day_rows})
    # The audit CSV retains every raw field. Send the browser only the fields
    # used by the dashboard so filters remain responsive on segment-heavy days.
    browser_fields = (
        "log_date", "minute_ist", "request_ist", "content_title", "category_name",
        "channel", "platform", "device", "session_id", "device_id", "cli_ip",
        "country", "state", "city", "req_host", "req_path", "request_watch_hours",
    )
    browser_days = [
        {
            "date": day["date"],
            "summary": day["summary"],
            "rows": [{field: row.get(field, "") for field in browser_fields} for row in day["rows"]],
        }
        for day in days
    ]
    payload = json.dumps(browser_days, ensure_ascii=True, separators=(",", ":"))
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VOD STREAM Query Analysis</title>
<style>
*{{box-sizing:border-box}}:root{{--canvas:#f4f6f8;--surface:#fff;--ink:#172033;--muted:#64748b;--line:#dbe3ea;--teal:#0f766e;--orange:#b45309}}body{{margin:0;background:var(--canvas);color:var(--ink);font:13px Inter,Segoe UI,Arial,sans-serif}}header{{position:sticky;top:0;z-index:2;display:flex;align-items:end;gap:18px;padding:12px max(16px,calc((100% - 1440px)/2));background:#fff;border-bottom:1px solid var(--line)}}h1{{margin:0;font-size:18px}}header p{{margin:3px 0 0;color:var(--muted);font-size:11px}}label{{display:grid;gap:4px;margin-left:auto;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}select,input{{height:31px;border:1px solid #bfcbd6;border-radius:4px;background:#fff;color:var(--ink);padding:5px 8px;font:inherit}}main{{max-width:1440px;margin:auto;padding:16px}}.kpis{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}}.kpi{{border:1px solid var(--line);border-top:3px solid var(--teal);background:var(--surface);padding:10px}}.kpi:nth-child(5){{border-top-color:var(--orange)}}.kpi span{{display:block;color:var(--muted);font-size:10px;font-weight:800;text-transform:uppercase}}.kpi strong{{display:block;margin-top:6px;font-size:24px;font-variant-numeric:tabular-nums}}.grid{{display:grid;grid-template-columns:1.35fr 1fr;gap:12px;margin-top:12px}}section{{border:1px solid var(--line);background:var(--surface)}}h2{{margin:0;padding:10px 12px;border-bottom:1px solid var(--line);font-size:13px}}.table-wrap{{max-height:335px;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{padding:7px 9px;border-bottom:1px solid #edf1f4;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#f8fafc;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.04em}}td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}#events{{margin-top:12px}}.event-controls{{display:flex;gap:8px;padding:9px 12px;border-bottom:1px solid var(--line)}}.event-controls input{{width:min(460px,100%)}}.note{{margin:12px 0 0;color:var(--muted);font-size:11px}}@media(max-width:900px){{.kpis{{grid-template-columns:repeat(3,1fr)}}.grid{{grid-template-columns:1fr}}header{{align-items:start;flex-direction:column}}label{{margin-left:0}}}}@media(max-width:520px){{.kpis{{grid-template-columns:repeat(2,1fr)}}main{{padding:10px}}}}
</style><style>
.brand{min-width:260px}.filters{display:grid;grid-template-columns:110px minmax(150px,1fr) minmax(150px,1fr) minmax(180px,1.3fr) minmax(180px,1.3fr);gap:8px;align-items:start;flex:1}.filters label{margin-left:0}.filters select[multiple]{height:76px;padding:2px 4px}.filters option{padding:2px 4px}.filters input{width:100%}@media(max-width:1100px){header{align-items:flex-start}.filters{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){.brand{min-width:0}.filters{width:100%;grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:span 2}}@media(max-width:420px){.filters{grid-template-columns:1fr}.filters label:first-child{grid-column:auto}}
</style><style>
.picker{position:relative;min-width:190px}.picker-toggle{height:31px;width:100%;border:1px solid #bfcbd6;border-radius:4px;background:#fff;color:var(--ink);padding:5px 28px 5px 8px;font:inherit;text-align:left;cursor:pointer;position:relative}.picker-toggle:after{content:'v';position:absolute;right:9px;color:var(--muted)}.picker-toggle:hover,.picker.open .picker-toggle{border-color:var(--teal);box-shadow:0 0 0 2px rgba(15,118,110,.12)}.picker-menu{display:none;position:absolute;z-index:20;top:calc(100% + 4px);left:0;width:max(100%,280px);max-width:calc(100vw - 24px);background:#fff;border:1px solid #bfcbd6;border-radius:5px;box-shadow:0 12px 25px rgba(15,23,42,.16);padding:7px}.picker.open .picker-menu{display:block}.picker-menu input{width:100%;margin-bottom:6px}.picker-options{max-height:240px;overflow:auto}.picker-option{display:flex;align-items:flex-start;gap:7px;padding:7px 6px;margin:0;color:var(--ink);font-size:11px;font-weight:600;text-transform:none;letter-spacing:0;cursor:pointer;border-radius:3px}.picker-option:hover{background:#eef6f5}.picker-option input{width:14px;height:14px;flex:0 0 auto;margin:0;padding:0}.picker-option span{overflow-wrap:anywhere}.filters>label{margin-left:0}.filters>label:first-child{min-width:110px}@media(max-width:700px){.picker{min-width:0;width:100%}}
.brand{display:flex;align-items:baseline;gap:12px;min-width:max-content}.brand p{margin:0;white-space:nowrap}.filters{display:flex;grid-template-columns:none;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.filters>label{flex:0 0 110px}.filters>.picker{flex:1 1 230px;min-width:180px;max-width:280px}.kpis{grid-template-columns:repeat(7,minmax(0,1fr))}
.picker-empty{padding:12px 6px;color:var(--muted);font-size:11px;text-align:center}
.picker-actions{display:flex;gap:6px;margin:0 0 6px}.picker-actions button{border:1px solid #cbd5e1;border-radius:3px;background:#f8fafc;color:var(--ink);padding:4px 8px;font:inherit;font-size:10px;font-weight:800;cursor:pointer}.picker-actions button:hover{background:#e6f2f0;border-color:var(--teal);color:var(--teal)}
@media(max-width:1100px){header{gap:14px}.brand{display:block}.brand p{margin-top:3px}.filters>.picker{min-width:150px}}
@media(max-width:900px){header{align-items:flex-start;flex-direction:column}.brand{min-width:0}.filters{width:100%;justify-content:stretch}.filters>label,.filters>.picker{flex:1 1 0;max-width:none}.kpis{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:520px){.filters{display:grid;grid-template-columns:1fr 1fr}.filters>label,.filters>.picker{width:100%}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
header{align-items:center;padding-left:max(16px,calc((100% - 1440px)/2));padding-right:max(16px,calc((100% - 1440px)/2))}.filters{display:grid!important;grid-template-columns:30fr 35fr 35fr!important;width:100%;gap:10px;align-items:center}.filters>label,.filters>.picker{min-width:0;width:auto;max-width:none}.filters>label:first-child{min-width:0}.filters>.picker{flex:none}.date-range{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:7px;min-width:0}.date-range input{width:100%;min-width:0}.date-range span{color:var(--muted);font-size:10px;font-weight:800;text-align:center;text-transform:uppercase}
@media(max-width:900px){header{align-items:flex-start}.filters{grid-template-columns:1fr 1fr!important}.date-range{grid-column:span 2}}
@media(max-width:520px){.filters{grid-template-columns:1fr!important}.date-range{grid-column:auto}}
</style></head><body>
<header><div class="filters"><div class="date-range"><input id="dateFrom" type="date" aria-label="From date"><span>to</span><input id="dateTo" type="date" aria-label="To date"></div><div class="picker" id="titlePicker"><button type="button" class="picker-toggle" id="titleToggle">All titles</button><div class="picker-menu"><input id="titleSearch" type="search" placeholder="Search titles"><div class="picker-actions"><button type="button" id="titleAll">Select all</button><button type="button" id="titleClear">Clear</button></div><div class="picker-options" id="titleOptions"></div></div><select id="titleFilter" multiple hidden></select></div><div class="picker" id="categoryPicker"><button type="button" class="picker-toggle" id="categoryToggle">All categories</button><div class="picker-menu"><input id="categorySearch" type="search" placeholder="Search categories"><div class="picker-actions"><button type="button" id="categoryAll">Select all</button><button type="button" id="categoryClear">Clear</button></div><div class="picker-options" id="categoryOptions"></div></div><select id="categoryFilter" multiple hidden></select></div></div></header>
<main><div class="kpis" id="kpis"></div><div class="grid"><section><h2>Content Titles</h2><div class="table-wrap"><table><thead><tr><th>Title</th><th class="num">Requests</th><th class="num">CLI IPs</th><th class="num">Watch hrs</th></tr></thead><tbody id="titles"></tbody></table></div></section><section><h2>Regions</h2><div class="table-wrap"><table><thead><tr><th>Country / State</th><th class="num">CLI IPs</th><th class="num">Sessions</th><th class="num">Watch hrs</th></tr></thead><tbody id="regions"></tbody></table></div></section><section><h2>Device and Platform</h2><div class="table-wrap"><table><thead><tr><th>Platform / Device</th><th class="num">CLI IPs</th><th class="num">Device IDs</th><th class="num">Requests</th></tr></thead><tbody id="devices"></tbody></table></div></section><section><h2>Delivery Routes</h2><div class="table-wrap"><table><thead><tr><th>Host / Path</th><th class="num">Requests</th><th class="num">CLI IPs</th><th class="num">Watch hrs</th></tr></thead><tbody id="routes"></tbody></table></div></section><section><h2>Minute Concurrency</h2><div class="table-wrap"><table><thead><tr><th>IST minute</th><th class="num">Concurrent CLI IPs</th><th class="num">Requests</th></tr></thead><tbody id="minutes"></tbody></table></div></section></div><section id="events"><h2>Request Ledger</h2><div class="event-controls"><input id="search" type="search" placeholder="Filter title, CLI IP, device ID, session ID, region, channel, host, or path"></div><div class="table-wrap"><table><thead><tr><th>Request IST</th><th>Title</th><th>Channel</th><th>CLI IP</th><th>Device ID</th><th>Session ID</th><th>Region</th><th>Host / Path</th></tr></thead><tbody id="ledger"></tbody></table></div></section><p class="note">Watch hours use the pipeline's raw 6-second-per-media-request estimate. Peak concurrency is distinct matching CLI IPs in one exact IST minute; it is not a deduplicated viewer count.</p></main>
<script>const days=__PAYLOAD__,fmt=new Intl.NumberFormat('en-IN'),hours=new Intl.NumberFormat('en-IN',{{maximumFractionDigits:3}}),by=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));let current;function rank(map){{return [...map.values()].sort((a,b)=>b.hours-a.hours||b.requests-a.requests)}}function grouped(rows,key,fields){{const map=new Map;for(const r of rows){{const label=key(r)||'Unknown / NA',x=map.get(label)||{{label,requests:0,hours:0,ips:new Set(),devices:new Set(),sessions:new Set()}};x.requests++;x.hours+=Number(r.request_watch_hours||0);if(r.cli_ip)x.ips.add(r.cli_ip);if(r.device_id)x.devices.add(r.device_id);if(r.session_id)x.sessions.add(r.session_id);map.set(label,x)}}return rank(map).slice(0,40)}function rowsHtml(items,fn){{return items.map(fn).join('')||'<tr><td colspan="4">No matching data</td></tr>'}}function render(){{current=days.find(x=>x.date===by('date').value)||days.at(-1);const s=current.summary,r=current.rows;by('kpis').innerHTML=[['Requests',s.requests],['Unique CLI IPs',s.cli_ips],['Device IDs',s.device_ids],['Session IDs',s.session_ids],['Raw Watch Hours',hours.format(s.watch_hours)],['Peak Minute CLI IPs',s.peak_concurrency]].map(([a,b])=>`<div class="kpi"><span>${{a}}</span><strong>${{fmt.format(b)}}</strong></div>`).join('');by('titles').innerHTML=rowsHtml(grouped(r,x=>x.content_title||x.category_name),x=>`<tr><td>${{esc(x.label)}}</td><td class=num>${{fmt.format(x.requests)}}</td><td class=num>${{fmt.format(x.ips.size)}}</td><td class=num>${{hours.format(x.hours)}}</td></tr>`);by('regions').innerHTML=rowsHtml(grouped(r,x=>[x.country,x.state].filter(Boolean).join(' / ')),x=>`<tr><td>${{esc(x.label)}}</td><td class=num>${{fmt.format(x.ips.size)}}</td><td class=num>${{fmt.format(x.sessions.size)}}</td><td class=num>${{hours.format(x.hours)}}</td></tr>`);by('devices').innerHTML=rowsHtml(grouped(r,x=>[x.platform,x.device].filter(Boolean).join(' / ')),x=>`<tr><td>${{esc(x.label)}}</td><td class=num>${{fmt.format(x.ips.size)}}</td><td class=num>${{fmt.format(x.devices.size)}}</td><td class=num>${{fmt.format(x.requests)}}</td></tr>`);by('routes').innerHTML=rowsHtml(grouped(r,x=>[x.req_host,x.req_path].filter(Boolean).join(' / ')),x=>`<tr><td>${{esc(x.label)}}</td><td class=num>${{fmt.format(x.requests)}}</td><td class=num>${{fmt.format(x.ips.size)}}</td><td class=num>${{hours.format(x.hours)}}</td></tr>`);const minutes=grouped(r,x=>x.minute_ist).sort((a,b)=>b.ips.size-a.ips.size||b.requests-a.requests);by('minutes').innerHTML=rowsHtml(minutes,x=>`<tr><td>${{esc(x.label)}}</td><td class=num>${{fmt.format(x.ips.size)}}</td><td class=num>${{fmt.format(x.requests)}}</td></tr>`);renderLedger()}}function renderLedger(){{const q=by('search').value.toLowerCase(),rows=current.rows.filter(r=>!q||Object.values(r).join(' ').toLowerCase().includes(q)).slice(0,1000);by('ledger').innerHTML=rows.map(r=>`<tr><td>${{esc(r.request_ist)}}</td><td>${{esc(r.content_title)}}</td><td>${{esc(r.channel)}}</td><td>${{esc(r.cli_ip)}}</td><td>${{esc(r.device_id)}}</td><td>${{esc(r.session_id)}}</td><td>${{esc([r.country,r.state,r.city].filter(Boolean).join(' / '))}}</td><td>${{esc([r.req_host,r.req_path].filter(Boolean).join(' / '))}}</td></tr>`).join('')||'<tr><td colspan="8">No matching requests</td></tr>'}}by('date').innerHTML=days.map(x=>`<option value="${{x.date}}">${{x.date}}</option>`).join('');by('date').value=days.at(-1)?.date||'';by('date').onchange=render;by('search').oninput=renderLedger;render();</script></body></html>"""
    # Replace the legacy inline script entirely. Keeping the filter controller
    # in its own function prevents HTML substitutions from breaking controls.
    style_start = template.index("<style>")
    style_end = template.index("</style>", style_start)
    css = template[style_start:style_end].replace("{{", "{").replace("}}", "}")
    template = template[:style_start] + css + template[style_end:]
    template = template[: template.index("<script>")] + dashboard_script() + "</body></html>"
    return (
        template.replace("__PAYLOAD__", payload)
        .replace("Raw Watch Hours", "Segment Watch Hours")
        .replace("Watch hrs", "Watch time")
        .replace("Peak Minute CLI IPs", "Peak Media CLI IPs")
        .replace(
            '</section></div><section id="events">',
            '</section></div><section id="sessionSection"><h2>Session Detail</h2><div class="table-wrap"><table><thead><tr><th>Title</th><th>Category</th><th>Session ID</th><th>Device ID</th><th>State</th><th>First request</th><th>Last request</th><th class="num">Observed duration</th><th class="num">Segment watch time</th></tr></thead><tbody id="sessionDetails"></tbody></table></div></section><section id="events">',
        )
        .replace(
            '<th>Title</th><th class="num">Requests</th><th class="num">CLI IPs</th><th class="num">Watch time</th>',
            '<th>Title / Category</th><th class="num">Segments</th><th class="num">CLI IPs</th><th class="num">Watch time</th><th class="num">Devices</th><th class="num">Sessions</th>',
        )
        .replace(
            '<th>Country / State</th><th class="num">CLI IPs</th><th class="num">Sessions</th><th class="num">Watch time</th>',
            '<th>Country / State</th><th class="num">CLI IPs</th><th class="num">Sessions</th><th class="num">Devices</th><th class="num">Watch time</th>',
        )
        .replace(
            '<th>Platform / Device</th><th class="num">CLI IPs</th><th class="num">Device IDs</th><th class="num">Requests</th>',
            '<th>Platform / Device</th><th class="num">CLI IPs</th><th class="num">Device IDs</th><th class="num">Sessions</th><th class="num">Watch time</th><th class="num">Segments</th>',
        )
        .replace("['Requests',s.requests],", "['VOD Requests',s.requests],['Media Segments',s.media_segments],")
        .replace(
            "const s=current.summary,r=current.rows;",
            "const all=current.rows,title=by('titleFilter').value,category=by('categoryFilter').value,r=all.filter(x=>(!title||x.content_title===title)&&(!category||x.category_name===category)),s={...current.summary,requests:r.length,cli_ips:new Set(r.filter(x=>x.cli_ip).map(x=>x.cli_ip)).size,device_ids:new Set(r.filter(x=>x.device_id).map(x=>x.device_id)).size,session_ids:new Set(r.filter(x=>x.session_id).map(x=>x.session_id)).size,media_segments:r.length,watch_hours:r.reduce((n,x)=>n+Number(x.request_watch_hours||0),0)};",
        )
        .replace("x.content_title===title", "x.content_title.toLowerCase().includes(title.toLowerCase())")
        .replace("x.category_name===category", "x.category_name.toLowerCase().includes(category.toLowerCase())")
        .replace(
            "title=by('titleFilter').value,category=by('categoryFilter').value,",
            "titles=[...by('titleFilter').selectedOptions].map(x=>x.value),categories=[...by('categoryFilter').selectedOptions].map(x=>x.value),",
        )
        .replace(
            "(!title||x.content_title.toLowerCase().includes(title.toLowerCase()))&&(!category||x.category_name.toLowerCase().includes(category.toLowerCase()))",
            "(!titles.length||titles.includes(x.content_title))&&(!categories.length||categories.includes(x.category_name))",
        )
        .replace(
            "hours=new Intl.NumberFormat('en-IN',{maximumFractionDigits:3}),by=",
            "hours=new Intl.NumberFormat('en-IN',{maximumFractionDigits:3}),minutes=new Intl.NumberFormat('en-IN',{maximumFractionDigits:1}),duration=v=>v<1?`${minutes.format(v*60)} min`:`${hours.format(v)} h`,by=",
        )
        .replace("hours.format(s.watch_hours)", "duration(s.watch_hours)")
        .replace("hours.format(x.hours)", "duration(x.hours)")
        .replace(
            "by(id).innerHTML='<option value=\"\">All</option>'+values.map(v=>`<option value=\"${esc(v)}\">${esc(v)}</option>`).join('')",
            "by(id).innerHTML=values.map(v=>`<option value=\"${esc(v)}\">${esc(v)}</option>`).join('')",
        )
        .replace("by('titleFilter').oninput=render", "by('titleFilter').onchange=render")
        .replace("by('categoryFilter').oninput=render", "by('categoryFilter').onchange=render")
        .replace(
            "by('search').oninput=renderLedger;render();",
            "const filterList=(searchId,selectId)=>{const q=by(searchId).value.toLowerCase();[...by(selectId).options].forEach(o=>o.hidden=!!q&&!o.text.toLowerCase().includes(q))};by('titleSearch').oninput=()=>filterList('titleSearch','titleFilter');by('categorySearch').oninput=()=>filterList('categorySearch','categoryFilter');by('search').oninput=renderLedger;render();",
        )
        .replace(
            "by('date').innerHTML=days.map(x=>`<option value=\"${x.date}\">${x.date}</option>`).join('');by('date').value=days.at(-1)?.date||'';by('date').onchange=render;by('search').oninput=renderLedger;render();",
            "by('date').innerHTML=days.map(x=>`<option value=\"${x.date}\">${x.date}</option>`).join('');const filterOptions=(id,field)=>{const values=[...new Set(days.flatMap(x=>x.rows.map(r=>r[field])).filter(Boolean))].sort();by(id).innerHTML='<option value=\"\">All</option>'+values.map(v=>`<option value=\"${esc(v)}\">${esc(v)}</option>`).join('')};filterOptions('titleFilter','content_title');filterOptions('categoryFilter','category_name');by('date').value=days.at(-1)?.date||'';by('date').onchange=render;by('titleFilter').onchange=render;by('categoryFilter').onchange=render;by('search').oninput=renderLedger;render();",
        )
        .replace(
            "Watch hours use the pipeline's raw 6-second-per-media-request estimate. Peak concurrency is distinct matching CLI IPs in one exact IST minute; it is not a deduplicated viewer count.",
            "Segment watch hours count only VOD .ts media segments: 6 seconds per segment. Query-string fields attribute every segment to its content, category, user, device, session, host, and path. Peak concurrency uses distinct CLI IPs in one exact IST minute and is not a deduplicated viewer count.",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the incremental VOD STREAM query dashboard.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS, help="Persistent request-level event CSV.")
    parser.add_argument("--append", type=Path, action="append", default=[], help="New daily event CSV to merge once.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Standalone HTML dashboard output.")
    args = parser.parse_args()
    existing = read_events(args.events) if args.events.exists() else []
    incoming = [row for path in args.append for row in read_events(path)]
    rows = merge_events(existing, incoming) if incoming else existing
    if incoming:
        write_events(args.events, rows)
    if not rows:
        raise ValueError("No VOD event rows were supplied. Provide --append for the first daily extract.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(rows), encoding="utf-8")
    latest = max((row.get("log_date", "") for row in rows), default="no dates")
    print(f"Wrote {args.out} with {len(rows):,} requests through {latest}.")


if __name__ == "__main__":
    main()
