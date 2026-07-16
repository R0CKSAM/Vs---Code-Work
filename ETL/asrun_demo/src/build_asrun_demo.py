"""Build a standalone ASRUN delivery demo from fixed-width broadcast logs."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


HERE = Path(__file__).resolve()
DEMO_ROOT = HERE.parents[1]
RAW_DIR = DEMO_ROOT / "data" / "raw"
PARSED_DIR = DEMO_ROOT / "data" / "parsed"
CONFIG_DIR = DEMO_ROOT / "config"
OUTPUT_DIR = DEMO_ROOT / "output"
# Reuse the exact processed mart that powers Audience Operations; the demo writes
# only ASRUN-date rows into its own parsed folder to stay light and portable.
DEFAULT_IDENTITY_MINUTE = DEMO_ROOT.parent / "output" / "watch_hours" / "concurrency" / "identity_minute.parquet"

# Positions come from the dash ruler in the ASRUN header, not from whitespace.
FIELD_SLICES = {
    # The first two fields start immediately after the one-character row margin.
    # Correct boundaries preserve 14:20 and 20:16 rather than dropping the first hour digit.
    "on_air_date": (1, 9),
    "on_air_time": (10, 21),
    "event_id": (22, 55),
    "s": (55, 58),
    "creative_title": (58, 91),
    "duration_text": (91, 103),
    "status": (103, 111),
    "device": (111, 131),
    "ch": (131, 134),
    "reconciliation_id": (134, 144),
    "event_type": (144, 152),
    "sec": (152, 157),
}
AD_TYPE_RULES = (("C00", "Spot"), ("LBD", "L-band"))
ASRUN_DAILY_FILENAME = re.compile(r"^ASRUN-\d{6}\.txt$", re.IGNORECASE)


def parse_duration_seconds(value: str) -> float | None:
    """Convert ASRUN HH:MM:SS.xx into seconds; blank/invalid values stay null."""
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,2}))?", value.strip())
    if not match:
        return None
    hours, minutes, seconds, fractions = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + float(f"0.{fractions or '0'}")


def classify_ad(event_id: str) -> str | None:
    cleaned = event_id.strip().upper()
    for prefix, ad_type in AD_TYPE_RULES:
        if cleaned.startswith(prefix):
            return ad_type
    return None


def parse_asrun(path: Path, channel: str) -> pd.DataFrame:
    """Parse one ASRUN file and preserve every valid fixed-width data event."""
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="latin-1").splitlines(), start=1):
        # A valid ASRUN event begins with the fixed MM/DD/YY on-air date.
        if not re.match(r"^\s*\d{2}/\d{2}/\d{2}\s", raw_line):
            continue
        row = {name: raw_line[start:end].strip() for name, (start, end) in FIELD_SLICES.items()}
        try:
            on_air_start = datetime.strptime(
                f"{row['on_air_date']} {row['on_air_time']}", "%m/%d/%y %H:%M:%S.%f"
            )
        except ValueError as exc:
            raise ValueError(f"Invalid ASRUN timestamp in {path.name}, line {line_number}") from exc
        duration_seconds = parse_duration_seconds(row["duration_text"])
        ad_type = classify_ad(row["event_id"])
        rows.append(
            {
                "source_file": path.name,
                "source_line": line_number,
                "channel_name": channel,
                "on_air_start_ist": on_air_start,
                "on_air_end_ist": on_air_start + pd.to_timedelta(duration_seconds or 0, unit="s"),
                "on_air_date": on_air_start.date().isoformat(),
                "hour_ist": on_air_start.hour,
                "event_id": row["event_id"],
                "ad_type": ad_type,
                "is_ad": ad_type is not None,
                "creative_title": row["creative_title"],
                "actual_duration_seconds": duration_seconds,
                "status": row["status"],
                "device": row["device"],
                "channel_code": row["ch"],
                "reconciliation_id": row["reconciliation_id"],
                "event_type": row["event_type"],
                "sec": row["sec"],
            }
        )
    if not rows:
        raise ValueError(f"No fixed-width ASRUN data rows found in {path}")
    return pd.DataFrame(rows)


def apply_brand_map(events: pd.DataFrame) -> pd.DataFrame:
    """Join only explicit manual mappings; unknown creatives must stay visible."""
    map_path = CONFIG_DIR / "creative_brand_map.csv"
    if not map_path.exists() or map_path.stat().st_size == 0:
        events["brand"] = pd.NA
        events["campaign"] = pd.NA
        events["mapping_confidence"] = pd.NA
        return events
    mapping = pd.read_csv(map_path, dtype="string").dropna(how="all")
    required = {"creative_id", "creative_title", "brand", "campaign", "confidence"}
    if mapping.empty or not required.issubset(mapping.columns):
        events["brand"] = pd.NA
        events["campaign"] = pd.NA
        events["mapping_confidence"] = pd.NA
        return events
    mapping = mapping.rename(columns={"creative_id": "event_id", "confidence": "mapping_confidence"})
    mapping = mapping.drop_duplicates(["event_id", "creative_title"], keep="last")
    return events.merge(
        mapping[["event_id", "creative_title", "brand", "campaign", "mapping_confidence"]],
        how="left",
        on=["event_id", "creative_title"],
        validate="many_to_one",
    )


def load_viewer_minute_snapshot(events: pd.DataFrame, mart_path: Path) -> pd.DataFrame:
    """Load the ASRUN-date subset of the Audience Operations identity-minute mart."""
    columns = ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"]
    if not mart_path.is_file():
        raise FileNotFoundError(
            "Audience Operations identity-minute mart is missing: "
            f"{mart_path}. Run the normal ETL concurrency/identity-minute step first."
        )
    ads = events.loc[events["is_ad"]]
    if ads.empty:
        return pd.DataFrame(columns=columns)
    start_date = ads["on_air_start_ist"].min().date().isoformat()
    end_date = ads["on_air_end_ist"].max().date().isoformat()
    # Read only the six columns required for the ASRUN exposure view.
    viewer = pd.read_parquet(mart_path, columns=columns)
    viewer["log_date"] = viewer["log_date"].astype("string").str.slice(0, 10)
    viewer["source"] = viewer["source"].astype("string").str.lower()
    viewer = viewer[
        viewer["source"].isin(["fast", "stream"])
        & viewer["log_date"].between(start_date, end_date)
    ].copy()
    viewer["minute_ist"] = pd.to_datetime(viewer["minute_ist"], errors="coerce")
    viewer = viewer[viewer["minute_ist"].notna()].copy()
    viewer["platform_name"] = viewer["platform_name"].fillna("Unknown / NA").astype("string")
    viewer["channel_name"] = viewer["channel_name"].fillna("Unknown / NA").astype("string")
    viewer["distinct_cliips"] = pd.to_numeric(viewer["distinct_cliips"], errors="coerce").fillna(0)
    # Audience Operations sums matching minute rows after channel/platform filtering.
    # Aggregate hidden host/candidate rows here so the demo stores that same visible metric.
    visible_keys = ["log_date", "source", "minute_ist", "platform_name", "channel_name"]
    return (
        viewer.groupby(visible_keys, as_index=False, dropna=False)["distinct_cliips"]
        .sum()
        .sort_values(["source", "minute_ist", "platform_name", "channel_name"])
    )


def records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    """Convert dashboard data to JSON-safe records without a JSON string round-trip."""
    return json.loads(frame.loc[:, columns].to_json(orient="records", date_format="iso"))


def build_payload(events: pd.DataFrame, viewer_minute: pd.DataFrame) -> dict[str, Any]:
    ads = events.loc[events["is_ad"]].copy()
    ads["actual_duration_seconds"] = pd.to_numeric(ads["actual_duration_seconds"], errors="coerce")
    ads["actual_duration_seconds"] = ads["actual_duration_seconds"].fillna(0)
    ads["duration_minutes"] = ads["actual_duration_seconds"] / 60
    creative = (
        ads.groupby(["ad_type", "event_id", "creative_title"], dropna=False, as_index=False)
        .agg(plays=("event_id", "size"), duration_seconds=("actual_duration_seconds", "sum"))
        .sort_values(["duration_seconds", "plays"], ascending=False)
    )
    hourly = (
        ads.groupby(["on_air_date", "hour_ist"], as_index=False)
        .agg(plays=("event_id", "size"), duration_seconds=("actual_duration_seconds", "sum"))
        .sort_values(["on_air_date", "hour_ist"])
    )
    ad_types = (
        ads.groupby("ad_type", as_index=False)
        .agg(plays=("event_id", "size"), duration_seconds=("actual_duration_seconds", "sum"))
        .sort_values("duration_seconds", ascending=False)
    )
    unmapped = creative.loc[~creative["event_id"].isin(
        events.loc[events["brand"].notna(), "event_id"]
    )]
    return {
        "generated_at_ist": datetime.now().astimezone().strftime("%d/%m/%y %I:%M:%S %p IST"),
        "source_files": sorted(events["source_file"].dropna().unique().tolist()),
        "channels": sorted(events["channel_name"].dropna().unique().tolist()),
        # This is an ad-delivery dashboard, so coverage must exclude non-ad ASRUN control events.
        "true_range": {
            "start": ads["on_air_start_ist"].min().strftime("%d-%m-%y %I:%M:%S %p IST"),
            "end": ads["on_air_end_ist"].max().strftime("%d-%m-%y %I:%M:%S %p IST"),
        },
        "kpis": {
            "all_events": int(len(events)),
            "ad_plays": int(len(ads)),
            "ad_minutes": round(float(ads["duration_minutes"].sum()), 2),
            "unique_creatives": int(ads[["event_id", "creative_title"]].drop_duplicates().shape[0]),
            "unmapped_creatives": int(unmapped[["event_id", "creative_title"]].drop_duplicates().shape[0]),
        },
        "ad_types": records(ad_types, ["ad_type", "plays", "duration_seconds"]),
        "hourly": records(hourly, ["on_air_date", "hour_ist", "plays", "duration_seconds"]),
        "creatives": records(creative, ["ad_type", "event_id", "creative_title", "plays", "duration_seconds"]),
        "events": records(
            ads.sort_values("on_air_start_ist"),
            ["on_air_start_ist", "on_air_end_ist", "ad_type", "event_id", "creative_title",
             "actual_duration_seconds", "brand", "campaign"],
        ),
        "viewer_minute": records(
            viewer_minute,
            ["log_date", "source", "minute_ist", "platform_name", "channel_name", "distinct_cliips"],
        ),
    }


def render_dashboard(payload: dict[str, Any]) -> str:
    """Render the standalone ASRUN delivery and audience-minute demo."""
    blob = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    title = html.escape(" / ".join(payload["channels"]))
    # Token replacement keeps the HTML/JS free of Python f-string brace escaping.
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veto ASRUN Delivery Demo</title><style>
:root{color-scheme:light;--ink:#162431;--muted:#5b6b7a;--line:#d7e0e8;--panel:#fff;--canvas:#f4f7fa;--blue:#1967d2;--fast:#1368ce;--stream:#17805b;--orange:#d67508;--combined:#eab308}*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.4 Arial,sans-serif}.wrap{max-width:1440px;margin:auto;padding:0 20px}.topbar{background:#fff;border-bottom:1px solid var(--line)}.topbar-inner{min-height:46px;display:flex;align-items:center;gap:14px;white-space:nowrap;overflow:hidden}.title-group{display:flex;align-items:baseline;gap:9px;min-width:0}.title-group h1{margin:0;font-size:18px}.source-label{color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;gap:14px;margin-left:auto;color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis}.meta span{white-space:nowrap}h2{font-size:17px;margin:0}p{margin:0;color:var(--muted)}.filter-shell{position:sticky;top:0;z-index:10;height:min(8vh,52px);background:#eef3f8;border-bottom:1px solid #cbd5e1;box-shadow:0 3px 8px rgba(22,36,49,.08)}.filters{height:100%;display:grid;grid-template-columns:200px 200px 150px 180px minmax(230px,1fr) auto;gap:8px;align-items:center}.filter-label{display:flex;align-items:center;gap:5px;min-width:0;color:var(--muted);font-size:11px;line-height:1;white-space:nowrap}.filter-label input,.filter-label select{flex:1}input,select{width:100%;height:29px;border:1px solid #aebdca;border-radius:4px;padding:3px 6px;background:#fff;color:var(--ink);font-size:12px;min-width:0}button{height:29px;border:0;border-radius:4px;background:var(--blue);color:#fff;padding:0 11px;cursor:pointer;white-space:nowrap;font-size:12px}main{padding:16px 0}.grid{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}.label{font-size:12px;color:var(--muted)}.value{font-weight:700;font-size:24px;margin-top:6px}.card-note{margin-top:4px;color:var(--muted);font-size:12px;line-height:1.25}.rank-grid,.audience-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px}.rank-panel,.audience-panel{min-width:0}.rank-list{max-height:520px;overflow-y:auto;border-top:1px solid var(--line);padding-top:4px}.barrow{display:grid;grid-template-columns:minmax(220px,340px) minmax(70px,1fr) 92px;gap:8px;align-items:center;margin:5px 0}.bar-label{display:grid;gap:2px;min-width:0;overflow-wrap:anywhere;line-height:1.25}.bar-label strong{font-size:12px}.bar-label small,.rank-meta{color:var(--muted);font-size:11px}.rank-meta{white-space:nowrap;text-align:right}.bar{height:8px;background:#e5edf5;border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--blue)}.panel-head{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;margin-bottom:10px}.panel-head small{display:block;color:var(--muted);font-size:11px;font-weight:400;margin-top:2px}.panel-actions{display:flex;align-items:center;gap:7px}.panel-actions button{background:#fff;color:var(--blue);border:1px solid #9dbde7}.source-tag{font-size:11px;font-weight:700;padding:2px 6px;border-radius:3px;color:#fff}.fast-tag{background:var(--fast)}.stream-tag{background:var(--stream)}.combined-tag{background:var(--combined);color:#2c2500}.audience-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:8px 0;margin-bottom:8px}.audience-controls .filter-label{font-size:11px}.multi-select{position:relative;flex:1;min-width:0}.multi-toggle{width:100%;height:29px;background:#fff;color:var(--ink);border:1px solid #aebdca;text-align:left;overflow:hidden;text-overflow:ellipsis;padding-right:22px;position:relative}.multi-toggle:after{content:"?";position:absolute;right:7px;color:var(--muted)}.multi-menu{display:none;position:absolute;left:0;right:0;top:calc(100% + 3px);z-index:30;max-height:230px;overflow-y:auto;background:#fff;border:1px solid #aebdca;border-radius:4px;box-shadow:0 5px 14px rgba(22,36,49,.16);padding:4px}.multi-menu.open{display:block}.multi-option{display:flex;align-items:center;gap:6px;padding:5px 4px;font-size:12px;line-height:1.2;cursor:pointer}.multi-option:hover{background:#eef3f8}.multi-option input{width:14px;height:14px;flex:0 0 auto}.multi-all{border-bottom:1px solid var(--line);font-weight:700}.event-columns{display:grid;grid-template-columns:96px 82px minmax(105px,1fr) 48px 108px;gap:7px;padding:0 2px 5px;color:var(--muted);font-size:10px;font-weight:700}.audience-list{max-height:520px;overflow-y:auto;border-top:1px solid var(--line)}.event-line{display:grid;grid-template-columns:96px 82px minmax(105px,1fr) 48px 108px;gap:7px;align-items:center;padding:7px 2px;border-bottom:1px solid var(--line);font-size:11px}.event-line>span{min-width:0;overflow-wrap:anywhere}.event-line small{display:block;color:var(--muted);font-size:10px}.audience-value{font-weight:700;text-align:right}.audience-empty{padding:12px 2px;color:var(--muted);font-size:12px}.audience-note{margin-top:8px;color:var(--muted);font-size:11px;line-height:1.35}.combined-panel{margin-top:16px}.combined-columns,.combined-line{display:grid;grid-template-columns:105px 86px minmax(170px,1fr) 58px 120px 120px 130px;gap:8px;align-items:center}.combined-columns{padding:0 2px 5px;color:var(--muted);font-size:10px;font-weight:700}.combined-list{max-height:520px;overflow-y:auto;border-top:1px solid var(--line)}.combined-line{padding:7px 2px;border-bottom:1px solid var(--line);font-size:11px}.combined-line>span{min-width:0;overflow-wrap:anywhere}.combined-line small{display:block;color:var(--muted);font-size:10px}.combined-value{font-weight:700;text-align:right}.notice{margin-top:16px;border-left:4px solid var(--orange);padding:12px 14px;background:#fff7e9;color:#614004;font-size:12px;line-height:1.4}@media(max-width:1100px){.topbar-inner{min-height:54px;align-items:flex-start;padding:7px 0;flex-wrap:wrap;gap:3px 12px}.meta{width:100%;margin-left:0}.filters{grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(2,1fr);gap:3px 8px}.filter-shell{height:min(10vh,76px)}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rank-grid,.audience-grid{grid-template-columns:1fr}}@media(max-width:560px){.wrap{padding:0 12px}.topbar-inner{min-height:0;padding:8px 0}.title-group{width:100%}.meta{display:grid;gap:2px}.filters{grid-template-columns:repeat(2,minmax(0,1fr));height:auto;padding:5px 0}.filter-shell{height:auto;min-height:0}.grid{grid-template-columns:1fr}.filters button{width:100%}.event-line,.event-columns{grid-template-columns:82px 75px minmax(0,1fr);gap:5px}.event-line .duration,.event-columns .duration{display:none}.audience-value{grid-column:3;text-align:left}.event-columns .metric{grid-column:3}.combined-columns,.combined-line{grid-template-columns:82px 75px minmax(0,1fr);gap:5px}.combined-columns .duration,.combined-line .duration{display:none}.combined-columns .fast-col,.combined-columns .stream-col,.combined-columns .total-col{grid-column:3}.combined-line .fast-col,.combined-line .stream-col,.combined-line .total-col{grid-column:3;text-align:left}.audience-controls{grid-template-columns:1fr}}
</style></head><body><header class="topbar"><div class="wrap topbar-inner"><div class="title-group"><h1>Veto ASRUN Delivery Demo</h1><span class="source-label">__TITLE__ | ASRUN playout evidence</span></div><div class="meta"><span id="range"></span><span id="updated"></span></div></div></header><section class="filter-shell"><div class="wrap filters"><label class="filter-label">Date from<input id="from" type="date"></label><label class="filter-label">Date to<input id="to" type="date"></label><label class="filter-label">Ad type<select id="type"><option value="All">All ad types</option><option>Spot</option><option>L-band</option></select></label><label class="filter-label">Ad ID<select id="adId"><option value="All">All ad IDs</option></select></label><label class="filter-label">Creative title<select id="creative"><option value="All">All creative titles</option></select></label><button id="reset" type="button">Reset</button></div></section><main class="wrap"><section class="grid" id="kpis"></section><section class="rank-grid"><div class="panel rank-panel"><div class="panel-head"><h2>Spot Creative Delivery</h2><span class="source-tag fast-tag">SPOT</span></div><div class="rank-list" id="spotBars"></div></div><div class="panel rank-panel"><div class="panel-head"><h2>L-band Creative Delivery</h2><span class="source-tag stream-tag">L-BAND</span></div><div class="rank-list" id="lbandBars"></div></div></section><section class="audience-grid"><div class="panel audience-panel"><div class="panel-head"><div><h2>FAST Delivered Ad Events</h2><small>5-Minute Unique IP Sum from Audience Operations</small></div><span class="source-tag fast-tag">FAST</span></div><div class="audience-controls"><label class="filter-label">Platform<span class="multi-select"><button id="fastPlatformToggle" class="multi-toggle" type="button">All platforms</button><span id="fastPlatformMenu" class="multi-menu"></span></span></label><label class="filter-label">Channel<span class="multi-select"><button id="fastChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="fastChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">5-Minute Unique IP Sum</span></div><div class="audience-list" id="fastRows"></div><div class="audience-note" id="fastNote"></div></div><div class="panel audience-panel"><div class="panel-head"><div><h2>STREAM Delivered Ad Events</h2><small>Unique IP Minute Sum from Audience Operations</small></div><span class="source-tag stream-tag">STREAM</span></div><div class="audience-controls"><label class="filter-label">Platform<select disabled><option>STREAM</option></select></label><label class="filter-label">Channel<span class="multi-select"><button id="streamChannelToggle" class="multi-toggle" type="button">Choose channels</button><span id="streamChannelMenu" class="multi-menu"></span></span></label></div><div class="event-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="metric">5-Minute Unique IP Sum</span></div><div class="audience-list" id="streamRows"></div><div class="audience-note" id="streamNote"></div></div></section><section class="panel combined-panel"><div class="panel-head"><div><h2>All Delivered Ad Events</h2><small>FAST + STREAM selected 5-minute cliIP sums</small></div><div class="panel-actions"><button id="exportAllEvents" type="button">Export CSV</button><span class="source-tag combined-tag">FAST + STREAM</span></div></div><div class="combined-columns"><span>On-air IST</span><span>Ad ID / Type</span><span>Creative title</span><span class="duration">Duration</span><span class="fast-col">FAST 5m Sum</span><span class="stream-col">STREAM 5m Sum</span><span class="total-col">Combined 5m Sum</span></div><div class="combined-list" id="allRows"></div><div class="audience-note" id="allNote"></div></section><div class="notice"><strong>5-Minute Unique IP Sum is not deduplicated ad reach.</strong> Each ASRUN ad uses its start-time concurrency bucket: :00-:04, :05-:09, and so on. The displayed value is the sum of five Audience Operations distinct cliIP minute counts using all HTTP-status .ts rows. Select the correct channel before interpreting a value; FAST can additionally be scoped to one platform.</div></main><script>const DATA=__BLOB__;const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n),mins=s=>fmt(s/60)+' min',esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));const canonical=String((DATA.channels||[])[0]||'');const dates=DATA.events.map(x=>x.on_air_start_ist.slice(0,10)),minDate=[...dates].sort()[0],maxDate=[...dates].sort().at(-1);$('from').value=minDate;$('to').value=maxDate;$('from').min=minDate;$('from').max=maxDate;$('to').min=minDate;$('to').max=maxDate;$('range').textContent='Ad data range: '+DATA.true_range.start+' to '+DATA.true_range.end;$('updated').textContent='Dashboard created: '+DATA.generated_at_ist;
function option(value,label){return '<option value="'+esc(value)+'">'+esc(label)+'</option>'}function scope(){const from=$('from').value,to=$('to').value,type=$('type').value;return DATA.events.filter(e=>e.on_air_start_ist.slice(0,10)>=from&&e.on_air_start_ist.slice(0,10)<=to&&(type==='All'||e.ad_type===type));}function refill(select,items,allLabel){const old=select.value;select.innerHTML=option('All',allLabel);for(const item of items)select.insertAdjacentHTML('beforeend',option(item,item));select.value=items.includes(old)?old:'All'}function refreshDependentOptions(){const eligible=scope(),ids=[...new Set(eligible.map(e=>e.event_id))].sort();refill($('adId'),ids,'All ad IDs');const selectedId=$('adId').value,titles=[...new Set(eligible.filter(e=>selectedId==='All'||e.event_id===selectedId).map(e=>e.creative_title))].sort();refill($('creative'),titles,'All creative titles');}function filtered(){const selectedId=$('adId').value,creative=$('creative').value;return scope().filter(e=>(selectedId==='All'||e.event_id===selectedId)&&(creative==='All'||e.creative_title===creative));}function formatIst(value){const [datePart,timePart='00:00']=String(value).split('T'),[year,month,day]=datePart.split('-'),[rawHour='0',minute='00']=timePart.split(':');const hour=Number(rawHour),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return day+'-'+month+'-'+year.slice(-2)+' '+String(twelve).padStart(2,'0')+':'+minute+' '+suffix;}
function rankingBars(node,items){const max=Math.max(1,...items.map(x=>x.seconds));node.innerHTML=items.length?items.map(x=>'<div class="barrow"><span class="bar-label"><strong>'+esc(x.id)+'</strong><small>'+esc(x.title)+'</small></span><div class="bar"><i style="width:'+((x.seconds/max)*100)+'%"></i></div><span class="rank-meta">'+fmt(x.plays)+' plays<br>'+mins(x.seconds)+'</span></div>').join(''):'<p>No delivery events in this selection.</p>';}function minuteKey(value){return String(value).slice(0,16)+':00'}function viewerScope(source){const from=$('from').value,to=$('to').value;return (DATA.viewer_minute||[]).filter(r=>r.source===source&&String(r.minute_ist).slice(0,10)>=from&&String(r.minute_ist).slice(0,10)<=to)}function selectedMulti(id){return new Set([...$(id+'Menu').querySelectorAll('input[data-value]:checked')].map(input=>input.dataset.value))}function closeMultiMenus(exceptId){for(const menu of document.querySelectorAll('.multi-menu'))if(menu.id!==exceptId+'Menu')menu.classList.remove('open')}function multiSummary(id,kind){const values=[...selectedMulti(id)],button=$(id+'Toggle');if(!values.length){button.textContent='Choose '+kind;return}const all=[...$(id+'Menu').querySelectorAll('input[data-value]')].map(input=>input.dataset.value);if(values.length===all.length){button.textContent='All '+kind;return}button.textContent=values.length===1?values[0]:values.length+' '+kind+' selected'}function buildMulti(id,items,kind,defaultValues,onChange){const menu=$(id+'Menu'),old=selectedMulti(id),allowed=new Set(items),selected=new Set([...old].filter(value=>allowed.has(value)));if(!old.size)for(const value of defaultValues)if(allowed.has(value))selected.add(value);const allChecked=items.length>0&&selected.size===items.length;menu.innerHTML='<label class="multi-option multi-all"><input type="checkbox" data-all '+(allChecked?'checked':'')+'>All '+kind+'</label>'+items.map(value=>'<label class="multi-option"><input type="checkbox" data-value="'+esc(value)+'" '+(selected.has(value)?'checked':'')+'>'+esc(value)+'</label>').join('');multiSummary(id,kind);$(id+'Toggle').onclick=event=>{event.stopPropagation();const open=!menu.classList.contains('open');closeMultiMenus(id);menu.classList.toggle('open',open)};menu.onchange=event=>{const all=menu.querySelector('input[data-all]');if(event.target.hasAttribute('data-all'))for(const input of menu.querySelectorAll('input[data-value]'))input.checked=event.target.checked;else all.checked=[...menu.querySelectorAll('input[data-value]')].every(input=>input.checked);multiSummary(id,kind);onChange()};}function refreshAudienceFilters(){const fast=viewerScope('fast'),platforms=[...new Set(fast.map(r=>String(r.platform_name)))].sort();buildMulti('fastPlatform',platforms,'platforms',platforms,()=>{refreshAudienceFilters();render()});const selectedPlatforms=selectedMulti('fastPlatform'),fastChannels=[...new Set(fast.filter(r=>!selectedPlatforms.size||selectedPlatforms.has(String(r.platform_name))).map(r=>String(r.channel_name)))].sort();buildMulti('fastChannel',fastChannels,'channels',fastChannels,render);const streamChannels=[...new Set(viewerScope('stream').map(r=>String(r.channel_name)))].sort();buildMulti('streamChannel',streamChannels,'channels',streamChannels,render);}function audienceMinuteMap(source){const channels=selectedMulti(source==='fast'?'fastChannel':'streamChannel'),platforms=source==='fast'?selectedMulti('fastPlatform'):null;if(!channels.size)return {message:'Choose one or more channels to show audience numbers.',map:null};if(source==='fast'&&!platforms.size)return {message:'Choose one or more platforms to show FAST audience numbers.',map:null};const rows=viewerScope(source).filter(r=>(source!=='fast'||platforms.has(String(r.platform_name)))&&channels.has(String(r.channel_name)));if(!rows.length)return {message:'No matching Audience Operations minute data.',map:null};const map=new Map();for(const r of rows){const key=minuteKey(r.minute_ist);map.set(key,(map.get(key)||0)+Number(r.distinct_cliips||0));}return {message:'',map};}function naiveMillis(value){const [d,t='00:00:00']=String(value).split('T'),[year,month,day]=d.split('-').map(Number),[hour=0,minute=0,seconds=0]=t.split(':').map(Number);return Date.UTC(year,month-1,day,hour,minute,seconds);}function fiveMinuteWindow(event){const bucket=Math.floor(naiveMillis(event.on_air_start_ist)/(5*60000))*(5*60000),keys=[];for(let offset=0;offset<5;offset++)keys.push(new Date(bucket+offset*60000).toISOString().slice(0,16)+':00');const start=new Date(bucket),end=new Date(bucket+4*60000),clock=d=>{const hour=d.getUTCHours(),suffix=hour>=12?'PM':'AM',twelve=hour%12||12;return String(twelve).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0')+' '+suffix;};return {keys,label:clock(start)+'-'+clock(end)+' IST'};}function audienceValue(event,state){const window=fiveMinuteWindow(event);if(!state.map)return {value:state.message,window:window.label,total:null};let total=0,found=false;for(const key of window.keys){if(state.map.has(key)){found=true;total+=state.map.get(key);}}return {value:found?fmt(total):'No minute data',window:window.label,total:found?total:null};}function audienceLines(events,state){if(!events.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const metric=audienceValue(e,state);return '<div class="event-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="audience-value">'+esc(metric.value)+'<small>'+esc(metric.window)+'</small></span></div>';}).join('');}function combinedRows(events,fast,stream){return events.sort((a,b)=>a.on_air_start_ist.localeCompare(b.on_air_start_ist)).map(e=>{const fastMetric=audienceValue(e,fast),streamMetric=audienceValue(e,stream);return {event:e,fast:fastMetric,stream:streamMetric,total:fastMetric.total===null||streamMetric.total===null?null:fastMetric.total+streamMetric.total};});}function combinedLines(events,fast,stream){const rows=combinedRows(events,fast,stream);if(!rows.length)return '<div class="audience-empty">No delivered ad events in this selection.</div>';return rows.map(row=>{const e=row.event,total=row.total===null?'No combined data':fmt(row.total);return '<div class="combined-line"><span>'+formatIst(e.on_air_start_ist)+'</span><span><strong>'+esc(e.event_id)+'</strong><small>'+esc(e.ad_type)+'</small></span><span>'+esc(e.creative_title)+'</span><span class="duration">'+fmt(e.actual_duration_seconds)+' sec</span><span class="combined-value fast-col">'+esc(row.fast.value)+'</span><span class="combined-value stream-col">'+esc(row.stream.value)+'</span><span class="combined-value total-col">'+esc(total)+'<small>'+esc(row.fast.window)+'</small></span></div>';}).join('');}function renderAudience(events){const fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream');$('fastRows').innerHTML=audienceLines(events,fast);$('streamRows').innerHTML=audienceLines(events,stream);$('allRows').innerHTML=combinedLines(events,fast,stream);$('fastNote').textContent=fast.map?'All HTTP-status .ts rows; fixed start-time 5-minute bucket sum.':' ';$('streamNote').textContent=stream.map?'All HTTP-status .ts rows; fixed start-time 5-minute bucket sum. STREAM platform is fixed at source level.':' ';$('allNote').textContent=fast.map&&stream.map?'Combined 5m Sum is the arithmetic FAST + STREAM sum for the active source selections; it is not cross-source deduplicated unique IP reach.':'Choose valid FAST and STREAM selections to calculate the combined sum.';}function csvCell(value){const text=String(value??'');return text.includes(',')||text.includes('\"')||text.split(String.fromCharCode(10)).length>1?'\"'+text.replace(/\"/g,'\"\"')+'\"':text}function exportAllEventsCsv(){const events=filtered(),fast=audienceMinuteMap('fast'),stream=audienceMinuteMap('stream'),fastPlatforms=[...selectedMulti('fastPlatform')].join(' | '),fastChannels=[...selectedMulti('fastChannel')].join(' | '),streamChannels=[...selectedMulti('streamChannel')].join(' | '),header=['On-air IST','Ad Type','Ad ID','Creative Title','Actual Duration Seconds','5-Minute Window IST','FAST Platforms','FAST Channels','STREAM Channels','FAST 5-Minute Unique IP Sum','STREAM 5-Minute Unique IP Sum','Combined 5-Minute Sum'],rows=combinedRows(events,fast,stream).map(row=>[formatIst(row.event.on_air_start_ist),row.event.ad_type,row.event.event_id,row.event.creative_title,row.event.actual_duration_seconds,row.fast.window,fastPlatforms,fastChannels,streamChannels,row.fast.value,row.stream.value,row.total===null?'No combined data':fmt(row.total)]),csv=[header,...rows].map(row=>row.map(csvCell).join(',')).join(String.fromCharCode(13,10)),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='asrun_all_delivered_events_'+$('from').value+'_to_'+$('to').value+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),0);}
function render(){const ev=filtered(),seconds=ev.reduce((n,e)=>n+(+e.actual_duration_seconds||0),0),grouped=new Map();for(const e of ev){const k=e.ad_type+'\u0000'+e.event_id+'\u0000'+e.creative_title,g=grouped.get(k)||{type:e.ad_type,id:e.event_id,title:e.creative_title,plays:0,seconds:0};g.plays++;g.seconds+=+e.actual_duration_seconds||0;grouped.set(k,g);}const rankings=[...grouped.values()].sort((a,b)=>b.seconds-a.seconds),spot=rankings.filter(x=>x.type==='Spot'),lband=rankings.filter(x=>x.type==='L-band'),spotPlays=ev.filter(x=>x.ad_type==='Spot').length,lbandPlays=ev.filter(x=>x.ad_type==='L-band').length,cards=[{label:'Total delivered ad plays',value:fmt(ev.length),note:'All Spot and L-band playout events'},{label:'Total actual ad duration',value:mins(seconds),note:'Sum of ASRUN delivered durations'},{label:'Total unique creatives',value:fmt(rankings.length),note:'Distinct Ad ID + creative title combinations'},{label:'Spot delivery',value:fmt(spotPlays)+' plays',note:fmt(spot.length)+' unique Spot creatives'},{label:'L-band delivery',value:fmt(lbandPlays)+' plays',note:fmt(lband.length)+' unique L-band creatives'}];$('kpis').innerHTML=cards.map(c=>'<div class="card"><div class="label">'+c.label+'</div><div class="value">'+c.value+'</div><div class="card-note">'+c.note+'</div></div>').join('');rankingBars($('spotBars'),spot);rankingBars($('lbandBars'),lband);renderAudience(ev);}
['from','to','type'].forEach(id=>$(id).addEventListener('change',()=>{refreshDependentOptions();refreshAudienceFilters();render()}));$('adId').addEventListener('change',()=>{refreshDependentOptions();render()});$('creative').addEventListener('change',render);$('exportAllEvents').addEventListener('click',exportAllEventsCsv);document.addEventListener('click',event=>{if(!event.target.closest('.multi-select'))closeMultiMenus('')});$('reset').onclick=()=>{$('from').value=minDate;$('to').value=maxDate;$('type').value='All';refreshDependentOptions();refreshAudienceFilters();render()};refreshDependentOptions();refreshAudienceFilters();render();</script></body></html>"""
    return template.replace("__BLOB__", blob).replace("__TITLE__", title)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", help="One or more ASRUN .txt files. Defaults to data/raw/*.txt.")
    parser.add_argument("--channel", required=True, help="Canonical Veto channel for these ASRUN files.")
    parser.add_argument(
        "--identity-minute",
        type=Path,
        default=DEFAULT_IDENTITY_MINUTE,
        help="Audience Operations identity_minute.parquet used for FAST/STREAM Unique IP Minute Sum.",
    )
    args = parser.parse_args()
    input_paths = args.input or sorted(
        path for path in RAW_DIR.iterdir()
        if path.is_file() and ASRUN_DAILY_FILENAME.fullmatch(path.name)
    )
    if not input_paths:
        raise SystemExit(
            f"No daily ASRUN files found in {RAW_DIR}. Expected names like ASRUN-150726.txt."
        )
    missing = [path for path in input_paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing input file(s): " + ", ".join(str(path) for path in missing))
    invalid_names = [path.name for path in input_paths if not ASRUN_DAILY_FILENAME.fullmatch(path.name)]
    if invalid_names:
        raise SystemExit(
            "Invalid ASRUN filename(s): " + ", ".join(invalid_names)
            + ". Use ASRUN-DDMMYY.txt, for example ASRUN-150726.txt."
        )
    events = apply_brand_map(pd.concat([parse_asrun(path, args.channel) for path in input_paths], ignore_index=True))
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed_path = PARSED_DIR / "asrun_events.parquet"
    events.to_parquet(parsed_path, index=False)
    viewer_minute = load_viewer_minute_snapshot(events, args.identity_minute)
    viewer_snapshot_path = PARSED_DIR / "audience_ops_identity_minute_asrun_dates.parquet"
    viewer_minute.to_parquet(viewer_snapshot_path, index=False)
    payload = build_payload(events, viewer_minute)
    (OUTPUT_DIR / "asrun_ad_events.csv").write_text(
        events.loc[events["is_ad"]].to_csv(index=False), encoding="utf-8-sig"
    )
    html_path = OUTPUT_DIR / "asrun_delivery_demo.html"
    html_path.write_text(render_dashboard(payload), encoding="utf-8")
    print(f"Parsed events : {len(events):,}")
    print(f"Ad events     : {payload['kpis']['ad_plays']:,}")
    print(f"Viewer rows   : {len(viewer_minute):,} (Audience Operations identity-minute snapshot)")
    print(f"Parquet       : {parsed_path}")
    print(f"Viewer mart   : {viewer_snapshot_path}")
    print(f"Dashboard     : {html_path}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
