import csv
import json
from datetime import datetime
from pathlib import Path

CSV_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT.csv")
OUTPUT_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT Dashboard.html")
COLUMN_MAPPINGS_PATH = Path(r"D:\Vs - Code Work\Codex\column_mappings.json")
VALUE_MAPPINGS_PATH = Path(r"D:\Vs - Code Work\Codex\value_mappings.json")
XLSX_BUNDLE_PATH = Path(r"D:\Vs - Code Work\Codex\xlsx.full.min.js")
EXCLUDED = [
    "ASTROLOGERS",
    "CHANNEL IMAGERY",
    "PROMO CHANNEL PROPERTIES",
    "PROMO CHANNEL/BRAND",
    "PROMO PROGRAM",
    "PROMO TAG",
    "SHORT PROGRAM",
    "TELEVISIONS",
]
TOP_N_OPTIONS = '<option value="10">Top 10</option><option value="20">Top 20</option>'
TIME_OPTIONS = '<option value="minutes">Minutes</option><option value="seconds">Seconds</option>'
CATEGORY_FIELDS = ["category", "categoryDropdown", "categoryTrigger", "categoryValue", "categorySearch", "categoryOptions", "categoryAll", "categoryClear"]
CHANNEL_FIELDS = ["channel", "channelDropdown", "channelTrigger", "channelValue", "channelSearch", "channelOptions", "channelAll", "channelClear"]
ADVERTISOR_FIELDS = ["advertisor", "advertisorDropdown", "advertisorTrigger", "advertisorValue", "advertisorSearch", "advertisorOptions", "advertisorAll", "advertisorClear"]
DOM_FIELD_SUFFIXES = {"topN": "TopN", "start": "Start", "end": "End", "channel": "Channel", "channelDropdown": "ChannelDropdown", "channelTrigger": "ChannelTrigger", "channelValue": "ChannelValue", "channelSearch": "ChannelSearch", "channelOptions": "ChannelOptions", "channelAll": "ChannelAll", "channelClear": "ChannelClear", "category": "Category", "categoryDropdown": "CategoryDropdown", "categoryTrigger": "CategoryTrigger", "categoryValue": "CategoryValue", "categorySearch": "CategorySearch", "categoryOptions": "CategoryOptions", "categoryAll": "CategoryAll", "categoryClear": "CategoryClear", "reset": "Reset", "legend": "Legend", "chart": "Chart", "metric": "Metric", "fullBtn": "FullBtn", "barBtn": "BarBtn", "heatmapBtn": "HeatmapBtn", "pieBtn": "PieBtn", "advertisor": "Advertisor", "advertisorDropdown": "AdvertisorDropdown", "advertisorTrigger": "AdvertisorTrigger", "advertisorValue": "AdvertisorValue", "advertisorSearch": "AdvertisorSearch", "advertisorOptions": "AdvertisorOptions", "advertisorAll": "AdvertisorAll", "advertisorClear": "AdvertisorClear", "time": "Time", "totalGrid": "TotalGrid", "insight": "Insight", "compareCount": "CompareCount"}
def section_config(key: str, section_class: str, title: str, chart_id: str, controls: list[tuple], extras: str = "", head_actions: str = "", state: str = "", dom_fields: list[str] | None = None) -> dict:
    return {"key": key, "section_class": section_class, "title": title, "chart_id": chart_id, "controls": controls, "extras": extras, "head_actions": head_actions, "state": state, "dom_fields": dom_fields or []}
SECTION_CONFIGS = [
    section_config("g1", "section graph1-scope", "Top Advertiser (FCT)", "g1Chart", [("select", "TopN", "Top N", TOP_N_OPTIONS), ("date", "Start", "Start Date"), ("date", "End", "End Date"), ("multi", "channel", "Channel", "All Channels", "Search channels"), ("category",), ("reset", "Reset")], extras='        <div class="legend" id="g1Legend"></div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], view: 'bar' }", dom_fields=["topN", "start", "end", *CHANNEL_FIELDS, *CATEGORY_FIELDS, "reset", "legend", "chart", "panel", "fullBtn"]),
    section_config("g2", "section", "Top Advertiser by Channels (FCT)", "g2Chart", [("select", "TopN", "Top N", TOP_N_OPTIONS), ("date", "Start", "Start Date"), ("date", "End", "End Date"), ("multi", "channel", "Channel", "All Channels", "Search channels"), ("category",), ("reset", "Reset")], extras='        <div class="legend" id="g2Legend"></div>\n        <div class="chart-metric" id="g2Metric"></div>', head_actions='            <div class="toggle-group">\n              <button class="toggle-btn active" id="g2BarBtn" type="button">Bar Chart</button>\n              <button class="toggle-btn" id="g2PieBtn" type="button">Pie Chart</button>\n            </div>\n', state="{ topN: '10', start: '', end: '', channel: [], category: [], view: 'bar' }", dom_fields=["topN", "start", "end", *CHANNEL_FIELDS, *CATEGORY_FIELDS, "reset", "legend", "chart", "metric", "panel", "fullBtn", "barBtn", "pieBtn"]),
    section_config("g3", "section", "Top Advertiser by Date (FCT)", "g3Chart", [("select", "TopN", "Top N", TOP_N_OPTIONS), ("date", "Start", "Start Date"), ("date", "End", "End Date"), ("multi", "channel", "Channel", "All Channels", "Search channels"), ("category",), ("reset", "Reset")], extras='        <div class="legend" id="g3Legend"></div>', head_actions='            <div class="toggle-group">\n              <button class="toggle-btn active" id="g3HeatmapBtn" type="button">Heatmap</button>\n              <button class="toggle-btn" id="g3BarBtn" type="button">Bar Chart</button>\n            </div>\n', state="{ topN: '10', start: '', end: '', channel: [], category: [], view: 'heat' }", dom_fields=["topN", "start", "end", *CHANNEL_FIELDS, *CATEGORY_FIELDS, "reset", "legend", "chart", "panel", "fullBtn", "heatmapBtn", "barBtn"]),
    section_config("g4", "section", "Channel Category Overview", "g4Chart", [("select", "TopN", "Category View", TOP_N_OPTIONS), ("date", "Start", "Start Date"), ("date", "End", "End Date"), ("multi", "channel", "Channel", "All Channels", "Search channels"), ("reset", "Reset")], state="{ topN: '10', start: '', end: '', channel: [], category: '', view: 'heat' }", dom_fields=["topN", "start", "end", *CHANNEL_FIELDS, "reset", "chart", "panel", "fullBtn"]),
    section_config("g5", "section", "FCT Hourly Analysis", "g5Chart", [("date", "Start", "Start Date"), ("date", "End", "End Date"), ("multi", "channel", "Channel", "All Channels", "Search channels"), ("category",), ("multi", "advertisor", "Advertiser", "All Advertisers", "Search advertisers"), ("select", "Time", "Time", TIME_OPTIONS), ("reset", "Reset")], extras='        <div class="legend-scale" id="g5Legend">\n          <span>Low AD Duration</span>\n          <div class="legend-gradient"></div>\n          <span>High AD Duration</span>\n        </div>\n        <div class="total-panel">\n          <div class="total-title">Total</div>\n          <div class="total-grid" id="g5TotalGrid"></div>\n        </div>', state="{ start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'heat' }", dom_fields=["start", "end", *CHANNEL_FIELDS, *CATEGORY_FIELDS, *ADVERTISOR_FIELDS, "time", "reset", "legend", "chart", "totalGrid", "panel", "fullBtn"]),
    section_config("g6", "section", "Average Creative Duration", "g6Chart", [], extras='        <div class="legend" id="g6Legend"></div>\n        <div class="chart-metric" id="g6Metric"></div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' }", dom_fields=["legend", "chart", "metric", "panel", "fullBtn"]),
    section_config("g7", "section", "Day-wise Advertising Activity", "g7Chart", [], state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'line' }", dom_fields=["chart", "panel", "fullBtn"]),
    section_config("g8", "section", "Leading Advertising Categories", "g8Chart", [], extras='        <div class="legend" id="g8Legend"></div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' }", dom_fields=["legend", "chart", "panel", "fullBtn"]),
    section_config("g9", "section", "High-value Programmes", "g9Chart", [], extras='        <div class="legend" id="g9Legend"></div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'cherry' }", dom_fields=["legend", "chart", "panel", "fullBtn"]),
    section_config("g10", "section", "Category Programme Preference", "g10Chart", [], extras='        <div class="legend-scale g10-legend-scale" id="g10Legend">\n          <span>Low Volume</span>\n          <div class="legend-gradient"></div>\n          <span>High Volume</span>\n        </div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'heat' }", dom_fields=["legend", "chart", "panel", "fullBtn"]),
    section_config("g11", "section", "Advertiser Share of Voice Trend", "g11Chart", [], extras='        <div class="legend" id="g11Legend"></div>\n        <div class="chart-metric" id="g11Metric"></div>', head_actions='            <div class="chart-inline-filter">\n              <label for="g11CompareCount">Advertisers</label>\n              <select id="g11CompareCount">\n                <option value="1">Top 1</option>\n                <option value="2">Top 2</option>\n                <option value="3" selected>Top 3</option>\n                <option value="5">Top 5</option>\n                <option value="7">Top 7</option>\n                <option value="10">Top 10</option>\n                <option value="15">Top 15</option>\n                <option value="all">All Advertisers</option>\n              </select>\n            </div>\n', state="{ topN: '3', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'stacked' }", dom_fields=["compareCount", "legend", "metric", "chart", "panel", "fullBtn"]),
    section_config("g12", "section", "Channel Efficiency Matrix", "g12Chart", [], extras='        <div class="chart-metric" id="g12Metric"></div>', state="{ topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' }", dom_fields=["metric", "chart", "panel", "fullBtn"]),
    section_config("g13", "section", "Advertiser Concentration by Channel", "g13Chart", [], extras='        <div class="legend" id="g13Legend"></div>\n        <div class="chart-metric" id="g13Metric"></div>', state="{ topN: '5', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' }", dom_fields=["legend", "metric", "chart", "panel", "fullBtn"]),
]
def parse_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%d-%m-%y").strftime("%Y-%m-%d")
    except ValueError:
        return value
def parse_int(value: str) -> int:
    try:
        return int(float((value or "0").replace(",", "").strip()))
    except ValueError:
        return 0
def load_json_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
def load_text_asset(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
def load_seed_rows() -> list[dict[str, object]]:
    sample_paths = [
        CSV_PATH,
        Path(r"D:\Vs - Code Work\Codex\CTV FCT - Copy.csv"),
        Path(r"D:\Vs - Code Work\Codex\Codex\CTV FCT.csv"),
        Path(r"D:\Vs - Code Work\Codex\Codex\CTV FCT - Copy.csv"),
    ]
    source = next((path for path in sample_paths if path.exists()), None)
    if source is None:
        return []
    rows: list[dict[str, object]] = []
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            rows.append({"channel": (record.get("Channel Name") or "").strip(), "date": parse_date(record.get("Pdate") or ""), "adtime": (record.get("Adst") or "").strip(), "product": (record.get("Brand Name") or "").strip(), "company": (record.get("Company") or "").strip(), "aaddur": parse_int(record.get("Aaddur") or "0"), "category": (record.get("Category") or "").strip()})
    return rows
rows = load_seed_rows()
column_mapping_config = load_json_config(COLUMN_MAPPINGS_PATH)
value_mapping_config = load_json_config(VALUE_MAPPINGS_PATH)
xlsx_bundle = load_text_asset(XLSX_BUNDLE_PATH)
generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
report_date = datetime.now().strftime("%d %b %Y")
payload = {"rows": [], "excluded": EXCLUDED, "generatedAt": generated_at}
def select_control(control_id: str, label: str, options: str = "", extra: str = "") -> str:
    return f'<div><label class="label" for="{control_id}">{label}</label><select id="{control_id}"{extra}>{options}</select></div>'
def date_control(control_id: str, label: str) -> str:
    return f'<div><label class="label" for="{control_id}">{label}</label><input id="{control_id}" type="date"></div>'
def reset_control(control_id: str) -> str:
    return f'<div><label class="label">&nbsp;</label><button id="{control_id}" type="button">Reset</button></div>'
def multi_dropdown(section_key: str, field_suffix: str, label: str, all_label: str, search_placeholder: str) -> str:
    return f"""          <div class="multi-dropdown" id="{section_key}{field_suffix}Dropdown">
            <label class="label" for="{section_key}{field_suffix}Trigger">{label}</label>
            <button class="multi-dropdown-trigger" id="{section_key}{field_suffix}Trigger" type="button">
              <span class="multi-dropdown-value" id="{section_key}{field_suffix}Value">{all_label}</span>
              <span>&#9660;</span>
            </button>
            <div class="multi-dropdown-panel">
              <input class="multi-dropdown-search" id="{section_key}{field_suffix}Search" type="text" placeholder="{search_placeholder}">
              <div class="multi-dropdown-actions">
                <button id="{section_key}{field_suffix}All" type="button">Select All</button>
                <button id="{section_key}{field_suffix}Clear" type="button">Clear All</button>
              </div>
              <div class="multi-dropdown-options" id="{section_key}{field_suffix}Options"></div>
            </div>
            <select id="{section_key}{field_suffix}" multiple hidden></select>
          </div>"""
def category_dropdown(section_key: str) -> str:
    return multi_dropdown(section_key, "Category", "Category", "All Categories", "Search categories")
def build_controls(section_key: str, controls: list[tuple]) -> list[str]:
    built = []
    for control in controls:
        kind = control[0]
        if kind == "select":
            _, suffix, label, options = control
            built.append(select_control(f"{section_key}{suffix}", label, options))
        elif kind == "date":
            _, suffix, label = control
            built.append(date_control(f"{section_key}{suffix}", label))
        elif kind == "reset":
            _, suffix = control
            built.append(reset_control(f"{section_key}{suffix}"))
        elif kind == "category":
            built.append(category_dropdown(section_key))
        elif kind == "multi":
            _, suffix, label, all_label, search_placeholder = control
            built.append(multi_dropdown(section_key, suffix.title(), label, all_label, search_placeholder))
    return built
def build_global_filter_html() -> str:
    return f"""    <section class="section sticky-filter-wrap" id="stickyFilterWrap">
      <div class="panel section-card sticky-filter-shell" id="stickyFilterShell">
        <div class="section-controls global-controls">
          {select_control("globalTopN", "Top N", TOP_N_OPTIONS)}
          {date_control("globalStart", "Start Date")}
          {date_control("globalEnd", "End Date")}
          {multi_dropdown("global", "Channel", "Channel", "All Channels", "Search channels")}
          {category_dropdown("global")}
          {multi_dropdown("global", "Advertisor", "Advertiser", "All Advertisers", "Search advertisers")}
          {select_control("globalTime", "Time", TIME_OPTIONS)}
          {reset_control("globalReset")}
        </div>
        <div class="filter-error" id="filterErrorText" hidden></div>
      </div>
    </section>"""
def section_block(section_class: str, title: str, controls: list[str], chart_id: str, extras: str = "", head_actions: str = "") -> str:
    controls_html = f"""        <div class="section-controls">
{chr(10).join(controls)}
        </div>
""" if controls else ""
    full_btn_id = chart_id.replace("Chart", "FullBtn")
    section_key = chart_id.replace("Chart", "")
    return f"""    <section class="{section_class}">
      <div class="section-head">
        <h2>{title}</h2>
      </div>
      <div class="panel section-card">
        <div class="fullscreen-focus-header" aria-hidden="true">
          <h3>{title}</h3>
          <div class="chart-insight" id="{section_key}Insight"></div>
        </div>
{controls_html}        <div class="chart-head">
          <div class="chart-actions">
{head_actions}
            <button class="full-btn" id="{full_btn_id}" type="button">Full Screen</button>
          </div>
        </div>
{extras}
        <div class="chart-box" id="{chart_id}"></div>
      </div>
    </section>"""
def build_sections_html() -> str:
    config_map = {config["key"]: config for config in SECTION_CONFIGS}
    pre_summary_grid_keys = ["g6", "g13", "g7", "g11"]
    leading_keys = [config["key"] for config in SECTION_CONFIGS if config["key"] not in pre_summary_grid_keys]
    leading_sections = [
        section_block(
            config_map[key]["section_class"],
            config_map[key]["title"],
            build_controls(config_map[key]["key"], config_map[key]["controls"]),
            config_map[key]["chart_id"],
            config_map[key]["extras"],
            config_map[key]["head_actions"]
        )
        for key in leading_keys
    ]
    pre_summary_sections = [
        section_block(
            config_map[key]["section_class"],
            config_map[key]["title"],
            build_controls(config_map[key]["key"], config_map[key]["controls"]),
            config_map[key]["chart_id"],
            config_map[key]["extras"],
            config_map[key]["head_actions"]
        )
        for key in pre_summary_grid_keys
    ]
    pre_summary_grid = f"""    <section class="section pre-summary-grid-wrap" id="preSummaryGraphGrid">
      <div class="pre-summary-grid">
{chr(10).join(pre_summary_sections)}
      </div>
    </section>"""
    return "\n\n".join([*leading_sections, pre_summary_grid])
def build_tail_summary_html() -> str:
    return ""
def build_dataset_summary_html() -> str:
    return """    <section class="section" id="datasetSummarySection">
      <div class="panel section-card dataset-summary-card">
        <div class="section-head">
          <h2>Dataset Summary</h2>
        </div>
        <div class="dataset-summary-grid">
          <div class="dataset-summary-block">
            <div class="dataset-summary-block-title">Original Dataset</div>
            <div class="dataset-kpi-row">
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Rows</div>
                <div class="dataset-kpi-value" id="datasetSummaryOriginalRows">0</div>
              </div>
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Categories</div>
                <div class="dataset-kpi-value" id="datasetSummaryOriginalCategories">0</div>
              </div>
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Advertisers</div>
                <div class="dataset-kpi-value" id="datasetSummaryOriginalAdvertisers">0</div>
              </div>
            </div>
          </div>
          <div class="dataset-summary-block">
            <div class="dataset-summary-block-title">Filtered Dataset</div>
            <div class="dataset-kpi-row">
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Rows</div>
                <div class="dataset-kpi-value" id="datasetSummaryFilteredRows">0</div>
              </div>
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Categories</div>
                <div class="dataset-kpi-value" id="datasetSummaryFilteredCategories">0</div>
              </div>
              <div class="dataset-kpi-card">
                <div class="dataset-kpi-label">Total Advertisers</div>
                <div class="dataset-kpi-value" id="datasetSummaryFilteredAdvertisers">0</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>"""
def build_state_sections_js() -> str:
    return "\n".join(f"        {config['key']}: {config['state']}{',' if index < len(SECTION_CONFIGS) - 1 else ''}" for index, config in enumerate(SECTION_CONFIGS))
def build_dom_sections_js() -> str:
    blocks = []
    for config in SECTION_CONFIGS:
        key = config["key"]
        fields = config["dom_fields"] + ([] if "insight" in config["dom_fields"] else ["insight"])
        lines = [f"        {key}: {{"]
        for field in fields:
            lines.append(
                f"          panel: document.getElementById('{key}Chart').closest('.panel'),"
                if field == "panel"
                else f"          {field}: document.getElementById('{key}{DOM_FIELD_SUFFIXES[field]}'),"
            )
        lines[-1] = lines[-1].rstrip(",")
        lines.append("        }")
        blocks.append("\n".join(lines))
    return ",\n".join(blocks)
html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CTV FCT Dashboard</title>
  <style>
    :root {
      --bg: #ffffff;
      --bg-2: #f8fafc;
      --panel: #ffffff;
      --panel-2: #ffffff;
      --line: #e5e7eb;
      --line-strong: #d1d5db;
      --text: #1f2937;
      --muted: #6b7280;
      --shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
      --font: "Segoe UI", Arial, sans-serif;
      --brand: #2563eb;
      --teal: #0f766e;
      --accent-1: #2563eb;
      --accent-2: #60a5fa;
      --accent-3: #1d4ed8;
      --accent-4: #93c5fd;
      --surface-soft: #f8fafc;
      --surface-muted: #f3f4f6;
      --chart-text: #1f2937;
      --chart-muted: #6b7280;
      --chart-grid: #e5e7eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: var(--font);
      background: var(--bg-2);
      min-height: 100vh;
      overflow-x: hidden;
    }
    .page {
      width: min(100%, 1800px);
      max-width: none;
      margin: 0 auto;
      padding: clamp(14px, 2vw, 24px) clamp(14px, 2.4vw, 28px) clamp(22px, 3vw, 34px);
      position: relative;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 14px;
      margin-bottom: 6px;
      padding: 0;
      background: transparent;
      border: 0;
      border-radius: 0;
      box-shadow: none;
      position: relative;
      z-index: 1;
    }
    .top-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .title-block {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
      min-width: 0;
    }
    .title-block h1 {
      margin: 0;
      color: var(--text);
      font-size: 30px;
      font-weight: 800;
      letter-spacing: 0.2px;
      line-height: 1.05;
    }
    .title-meta {
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      line-height: 1.2;
    }
    .title-range {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.3;
      margin-top: 2px;
    }
    .title-meta strong {
      color: var(--text);
      font-weight: 700;
    }
    .top-actions {
      display: flex;
      flex-direction: row;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      min-width: auto;
      position: relative;
      z-index: 1;
    }
    .action-row {
      display: flex;
      gap: 6px;
      align-items: center;
      justify-content: flex-end;
      width: auto;
    }
    .header-icon-group {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
      transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
    }
    .meta-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0;
      border-radius: 0;
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .upload-input-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .label {
      display: block;
      margin-bottom: 3px;
      font-size: 9.5px;
      font-weight: 800;
      text-transform: none;
      letter-spacing: 0.2px;
      line-height: 1.15;
      color: #000000;
    }
    .sticky-filter-shell .label {
      color: #000000;
    }
    .sticky-filter-shell,
    .sticky-filter-shell .meta-pill,
    .sticky-filter-shell .multi-dropdown-value,
    .sticky-filter-shell .multi-dropdown-trigger,
    .sticky-filter-shell .multi-dropdown-option,
    .sticky-filter-shell .multi-dropdown-option span {
      color: #000000;
    }
    label[for$="TopN"],
    label[for$="Start"],
    label[for$="End"],
    label[for$="CategoryTrigger"],
    label[for$="Advertisor"],
    label[for$="Time"] {
      color: #ffffff;
    }
    input, select, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 5px 8px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      font-size: 12px;
      line-height: 1.2;
      transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease, background 160ms ease;
    }
    input:hover, select:hover, button:hover,
    input:focus, select:focus, button:focus {
      border-color: #60a5fa;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.10);
      outline: none;
    }
    input[type="date"] {
      background: #ffffff;
      color: var(--text);
      color-scheme: light;
      caret-color: var(--text);
    }
    input[type="date"]::-webkit-datetime-edit,
    input[type="date"]::-webkit-datetime-edit-fields-wrapper,
    input[type="date"]::-webkit-datetime-edit-text,
    input[type="date"]::-webkit-datetime-edit-month-field,
    input[type="date"]::-webkit-datetime-edit-day-field,
    input[type="date"]::-webkit-datetime-edit-year-field {
      color: var(--text);
    }
    input[type="date"]::placeholder {
      color: var(--muted);
      opacity: 1;
    }
    input[type="date"]::-webkit-calendar-picker-indicator {
      filter: none;
      opacity: 1;
      cursor: pointer;
    }
    input::file-selector-button {
      border: 0;
      border-radius: 8px;
      padding: 5px 8px;
      margin-right: 6px;
      background: rgba(107, 181, 255, 0.16);
      color: var(--text);
      cursor: pointer;
      font-weight: 700;
      font-size: 11px;
    }
    .status {
      display: none;
      max-width: 260px;
      font-size: 11px;
      line-height: 1.3;
    }
    .filter-error {
      margin-top: 4px;
      color: #b91c1c;
      font-size: 11px;
      font-weight: 700;
      line-height: 1.25;
    }
    .filter-error[hidden] {
      display: none !important;
    }
    .section {
      margin-top: 14px;
    }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 10px;
    }
    .section-head h2 {
      margin: 0;
      font-size: 22px;
      font-weight: 900;
      letter-spacing: 0.2px;
      color: var(--text);
    }
    .section-card {
      padding: 16px;
    }
    .panel:hover {
      transform: none;
      box-shadow: 0 0 0 1px rgba(251, 146, 60, 0.12), 0 0 22px rgba(251, 146, 60, 0.14);
      border-color: var(--line);
      background: var(--panel);
    }
    .section-controls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 120px), 1fr));
      gap: 6px;
      margin-bottom: 6px;
      align-items: end;
    }
    .global-controls {
      margin-bottom: 0;
    }
    .section:not(.sticky-filter-wrap) .section-controls {
      display: none;
    }
    .sticky-filter-wrap {
      position: relative;
      z-index: 40;
    }
    .sticky-filter-wrap.is-stuck {
      min-height: var(--sticky-filter-height, 0px);
    }
    .sticky-filter-shell {
      position: relative;
      z-index: 40;
      background: rgb(184, 127, 123);
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.14);
      padding: 6px 8px;
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
    }
    .chart-box:hover,
    .total-panel:hover,
    .summary-line:hover {
      background: inherit;
      border-color: inherit;
      box-shadow: 0 0 0 1px rgba(251, 146, 60, 0.10), 0 0 20px rgba(251, 146, 60, 0.12);
    }
    .sticky-filter-shell:hover {
      background: rgb(184, 127, 123);
      border-color: var(--line);
      box-shadow: 0 0 0 1px rgba(251, 146, 60, 0.08), 0 0 18px rgba(251, 146, 60, 0.10);
    }
    .sticky-filter-shell .section-controls > div,
    .sticky-filter-shell .multi-dropdown {
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      min-height: 40px;
    }
    .sticky-filter-shell.is-stuck {
      position: fixed;
      top: 10px;
      z-index: 80;
    }
    .graph1-scope,
    .graph1-scope .label,
    .graph1-scope .legend,
    .graph1-scope .legend *,
    .graph1-scope button,
    .graph1-scope input,
    .graph1-scope select {
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .multi-dropdown {
      position: relative;
      display: grid;
      gap: 2px;
      animation: none !important;
      transition: none !important;
    }
    .multi-dropdown-trigger {
      min-height: 30px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      text-align: left;
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .multi-dropdown-value {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
    }
    .multi-dropdown-panel {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      right: 0;
      z-index: 30;
      padding: 6px;
      border-radius: 7px;
      border: 1px solid var(--line);
      background: #ffffff;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.10);
      display: none;
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .multi-dropdown.open .multi-dropdown-panel {
      display: block;
    }
    .multi-dropdown-search {
      margin-bottom: 4px;
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .multi-dropdown-actions {
      display: flex;
      gap: 6px;
      margin-bottom: 4px;
    }
    .multi-dropdown-actions button {
      min-width: 0;
      padding: 5px 7px;
      font-size: 11px;
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .multi-dropdown-options {
      max-height: 180px;
      overflow: auto;
      display: grid;
      gap: 4px;
      padding-right: 2px;
    }
    .multi-dropdown-option {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 7px;
      background: #ffffff;
      font-size: 12px;
      cursor: pointer;
      color: var(--text);
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .multi-dropdown-option:hover {
      background: #eff6ff;
    }
    .multi-dropdown-option input {
      width: auto;
      margin: 0;
      animation: none !important;
      transition: none !important;
      transform: none !important;
    }
    .chart-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .chart-actions {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-left: auto;
    }
    .chart-title {
      margin: 0;
      color: var(--text);
      font-size: 18px;
      font-weight: 800;
    }
    .chart-metric {
      margin-bottom: 8px;
      color: #000000;
      font-size: 14px;
      font-weight: 600;
      line-height: 1.4;
    }
    .toggle-group {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: var(--surface-soft);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px;
    }
    .toggle-btn {
      border: 0;
      border-radius: 999px;
      padding: 8px 14px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.3px;
      cursor: pointer;
    }
    .toggle-btn.active {
      background: #2563eb;
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(37, 99, 235, 0.20);
    }
    .full-btn {
      width: auto;
      min-width: 96px;
      padding: 6px 9px;
      border-radius: 8px;
      background: #ffffff;
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.3px;
      cursor: pointer;
    }
    .pdf-btn {
      width: auto;
      min-width: 34px;
      height: 34px;
      border-radius: 999px;
      padding: 0 12px;
      background: #ffffff;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.35px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
      white-space: nowrap;
    }
    .pdf-btn:hover,
    .icon-btn:hover,
    .full-btn:hover {
      color: #2563eb;
      border-color: #93c5fd;
      background: #ffffff;
    }
    .icon-btn {
      width: 34px;
      min-width: 34px;
      height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 0;
      cursor: pointer;
    }
    .upload-btn {
      min-width: 34px;
      width: 34px;
      justify-content: center;
      padding: 0;
    }
    .sheet-btn {
      min-width: 34px;
      width: 34px;
      justify-content: center;
      padding: 0;
    }
    .upload-btn.success,
    .sheet-btn.success {
      border-color: #22c55e;
      color: #15803d;
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.12);
    }
    .sheet-btn[hidden] {
      display: none !important;
    }
    .sheet-btn:disabled {
      opacity: 0.45;
      cursor: not-allowed;
      box-shadow: none;
    }
    .sheet-menu {
      position: absolute;
      right: 0;
      top: calc(100% + 8px);
      min-width: 220px;
      max-width: min(640px, calc(100vw - 32px));
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #ffffff;
      box-shadow: 0 12px 24px rgba(15, 23, 42, 0.14);
      z-index: 120;
      display: none;
    }
    .sheet-menu.open {
      display: block;
    }
    .sheet-menu-title {
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.8px;
    }
    .sheet-menu-list {
      display: flex;
      flex-wrap: nowrap;
      gap: 6px;
      max-width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      padding-bottom: 2px;
      scrollbar-width: thin;
    }
    .sheet-menu-item {
      width: auto;
      min-width: 0;
      border-radius: 8px;
      justify-content: center;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 700;
      text-transform: none;
      letter-spacing: 0;
      color: var(--text);
      background: #ffffff;
      white-space: nowrap;
      flex: 0 0 auto;
    }
    .sheet-menu-item.active {
      border-color: #22c55e;
      background: #f0fdf4;
      color: #166534;
    }
    .control-check {
      width: 18px;
      height: 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: #dcfce7;
      color: #15803d;
      font-size: 11px;
      font-weight: 900;
      line-height: 1;
    }
    .control-check[hidden] {
      display: none !important;
    }
    .share-fab {
      position: fixed;
      right: 28px;
      bottom: 28px;
      width: 46px;
      height: 46px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      border: 1px solid rgba(37, 99, 235, 0.18);
      background: #2563eb;
      color: #ffffff;
      box-shadow: 0 12px 26px rgba(37, 99, 235, 0.25);
      cursor: pointer;
      z-index: 90;
    }
    .share-fab:hover,
    .share-fab:focus {
      color: #ffffff;
      border-color: rgba(147, 197, 253, 0.5);
      background: #1d4ed8;
      box-shadow: 0 14px 30px rgba(29, 78, 216, 0.28);
    }
    .share-fab svg {
      width: 19px;
      height: 19px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .share-modal[hidden] {
      display: none !important;
    }
    .share-modal {
      position: fixed;
      inset: 0;
      z-index: 140;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(15, 23, 42, 0.5);
      backdrop-filter: blur(6px);
    }
    .share-modal-card {
      width: min(420px, 100%);
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.3);
      background: #ffffff;
      box-shadow: 0 28px 60px rgba(15, 23, 42, 0.24);
      padding: 22px;
    }
    .share-modal-title {
      margin: 0 0 8px;
      color: var(--text);
      font-size: 20px;
      font-weight: 800;
    }
    .share-modal-copy {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }
    .share-modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .share-modal-btn {
      border: 1px solid rgba(148, 163, 184, 0.35);
      border-radius: 12px;
      background: #ffffff;
      color: var(--text);
      min-height: 40px;
      padding: 0 14px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      transition: background 180ms ease, border-color 180ms ease, color 180ms ease, box-shadow 180ms ease;
    }
    .share-modal-btn:hover,
    .share-modal-btn:focus {
      border-color: #93c5fd;
      box-shadow: 0 10px 18px rgba(37, 99, 235, 0.12);
      outline: none;
    }
    .share-modal-btn.primary {
      border-color: #2563eb;
      background: #2563eb;
      color: #ffffff;
    }
    .share-modal-btn.primary:hover,
    .share-modal-btn.primary:focus {
      border-color: #1d4ed8;
      background: #1d4ed8;
      color: #ffffff;
    }
    .icon-btn svg {
      width: 14px;
      height: 14px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.9;
      stroke-linecap: round;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .chart-box {
      height: clamp(360px, 48vw, 520px);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 14px;
      transition: background 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
      overflow: hidden;
    }
    @keyframes chartFadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .chart-animated {
      animation: chartFadeIn 220ms ease;
      transform-origin: center;
    }
    .chart-box.top20-mode {
      height: clamp(520px, 64vw, 760px);
    }
    .legend {
      margin-bottom: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      color: var(--text);
      font-size: 13px;
    }
    .legend-scale {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      color: var(--text);
      font-size: 14px;
      font-weight: 700;
    }
    .total-panel {
      margin-top: 10px;
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #ffffff;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
      transition: background 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
    }
    .total-title {
      color: var(--text);
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.3px;
      margin-bottom: 10px;
    }
    .total-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));
      gap: 8px 10px;
    }
    .total-chip {
      padding: 8px 10px;
      border-radius: 6px;
      background: var(--surface-soft);
      border: 1px solid var(--line);
    }
    .total-chip-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .total-chip-value {
      color: var(--text);
      font-size: 16px;
      font-weight: 800;
    }
    .legend-gradient {
      flex: 1;
      height: 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: linear-gradient(90deg, rgba(46, 107, 16, 0.080) 0%, rgba(46, 107, 16, 0.180) 35%, rgba(46, 107, 16, 0.280) 68%, rgba(46, 107, 16, 0.364) 100%);
    }
    .g10-legend-scale .legend-gradient {
      background: linear-gradient(90deg, rgba(23, 59, 92, 0.18) 0%, rgba(23, 59, 92, 0.26) 35%, rgba(23, 59, 92, 0.35) 68%, rgba(23, 59, 92, 0.44) 100%);
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--text);
      font-weight: 600;
    }
    .legend-swatch {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }
    svg.chart {
      width: 100%;
      height: 100%;
      display: block;
      overflow: visible;
    }
    svg.chart text,
    svg.chart tspan,
    .chart-label {
      fill: var(--text);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .excluded-inline {
      color: #7f1d1d;
      font-size: 14px;
      line-height: 1.5;
      letter-spacing: 0.2px;
      padding: 10px 12px;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 8px;
    }
    .excluded-items {
      color: #374151;
      font-weight: 400;
    }
    .excluded-inline,
    .summary-line,
    .total-chip,
    .multi-dropdown-option,
    .meta-pill {
      box-shadow: none;
    }
    .empty {
      height: 100%;
      min-height: 180px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 15px;
    }
    .summary-lines {
      display: grid;
      gap: 6px;
      color: var(--text);
      font-size: 14px;
      line-height: 1.45;
      font-family: Calibri, "Segoe UI", Arial, sans-serif;
    }
    .summary-line {
      position: relative;
      padding: 10px 12px 10px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      font-weight: 400;
      white-space: normal;
      overflow: hidden;
      text-overflow: initial;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      line-clamp: 2;
      transition: background 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
    }
    .summary-line::before {
      content: "";
      position: absolute;
      left: 0;
      top: 10px;
      bottom: 10px;
      width: 4px;
      border-radius: 999px;
      background: #2563eb;
    }
    .summary-line strong {
      font-weight: 400;
    }
    .dataset-summary-card {
      display: grid;
      gap: 8px;
    }
    .pre-summary-grid-wrap {
      margin-top: 14px;
    }
    .pre-summary-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      align-items: stretch;
    }
    .pre-summary-grid > .section {
      margin-top: 0;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .pre-summary-grid > .section .section-card {
      height: 100%;
      display: flex;
      flex-direction: column;
    }
    .pre-summary-grid > .section .chart-box {
      flex: 1 1 auto;
      min-height: 0;
    }
    .dataset-summary-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .dataset-summary-block {
      display: grid;
      gap: 8px;
      min-width: 0;
    }
    .dataset-summary-block-title {
      color: var(--text);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.1px;
    }
    .dataset-kpi-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .dataset-kpi-card {
      min-width: 0;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #ffffff;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
      display: grid;
      gap: 4px;
      align-content: center;
    }
    .dataset-kpi-label {
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.1px;
    }
    .dataset-kpi-value {
      color: var(--text);
      font-size: 18px;
      font-weight: 800;
      line-height: 1.1;
      word-break: break-word;
    }
    .chart-inline-filter {
      display: inline-grid;
      gap: 4px;
      min-width: 146px;
    }
    .chart-inline-filter label {
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.15px;
    }
    .chart-inline-filter select {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #ffffff;
      color: var(--text);
      padding: 0 10px;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
    }
    .tail-summary-card {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      padding: 0;
      background: transparent !important;
      border: 0 !important;
      box-shadow: none !important;
    }
    .tail-summary-section,
    .tail-summary-section .panel,
    .tail-summary-section .tail-summary-card,
    .tail-summary-section .tail-summary-block,
    .tail-summary-section .tail-card-grid,
    .tail-summary-section .tail-card-grid-single {
      max-width: 100%;
      min-width: 0;
      box-sizing: border-box;
    }
    .tail-summary-section .section-card {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 0;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .05);
      min-width: 0;
      overflow: hidden;
    }
    .tail-summary-block {
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .tail-summary-panel {
      background:
        radial-gradient(circle at top right, rgba(96, 165, 250, 0.14), transparent 34%),
        linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      border: 1px solid rgba(148, 163, 184, 0.22);
      border-radius: 16px;
      padding: 18px 18px 16px;
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.06);
      min-height: 100%;
    }
    .tail-summary-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: nowrap;
    }
    .tail-summary-heading {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    .tail-summary-title {
      margin: 0;
      color: var(--text);
      font-size: 19px;
      font-weight: 900;
      line-height: 1.1;
    }
    .tail-filter-field {
      display: grid;
      gap: 6px;
      min-width: 180px;
      max-width: 220px;
      width: 100%;
    }
    .tail-filter-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.35px;
      text-transform: uppercase;
    }
    .tail-filter-select {
      width: 100%;
      min-width: 0;
      min-height: 42px;
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.28);
      background: rgba(255, 255, 255, 0.92);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
    }
    .tail-card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
    }
    .tail-card-grid-single {
      grid-template-columns: minmax(0, 1fr);
      justify-content: stretch;
    }
    .tail-stat-card {
      padding: 15px 15px 14px;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(241, 245, 249, 0.92) 100%);
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
      display: grid;
      gap: 6px;
      min-height: 116px;
      align-content: start;
      min-width: 0;
      overflow: hidden;
      position: relative;
    }
    .tail-stat-card::before {
      content: "";
      position: absolute;
      left: 0;
      top: 14px;
      bottom: 14px;
      width: 4px;
      border-radius: 999px;
      background: linear-gradient(180deg, var(--brand), var(--teal));
    }
    .tail-stat-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.35px;
      text-transform: uppercase;
      padding-left: 10px;
    }
    .tail-stat-value {
      color: var(--text);
      font-size: 22px;
      font-weight: 900;
      line-height: 1.05;
      word-break: break-word;
      padding-left: 10px;
    }
    .tail-stat-note {
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      padding-left: 10px;
    }
    .tail-summary-section .tail-stat-value,
    .tail-summary-section .tail-stat-note,
    .tail-summary-section .tail-stat-label,
    .tail-summary-section .tail-summary-title,
    .tail-summary-section .tail-filter-label {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .fullscreen-focus-header {
      display: none;
      margin-bottom: 12px;
    }
    .fullscreen-focus-header h3 {
      margin: 0 0 10px;
      color: var(--text);
      font-size: 26px;
      font-weight: 800;
      letter-spacing: 0.2px;
      line-height: 1.1;
    }
    .chart-insight {
      display: none;
      padding: 10px 12px;
      border: 1px solid rgba(37, 99, 235, 0.14);
      border-radius: 10px;
      background: linear-gradient(90deg, rgba(37, 99, 235, 0.10), rgba(15, 118, 110, 0.08));
      color: var(--text);
      font-size: 13px;
      line-height: 1.45;
      font-weight: 700;
    }
    .chart-insight.visible {
      display: block;
    }
    .chart-insight-label {
      color: var(--accent-3);
      font-weight: 800;
      margin-right: 6px;
    }
    .info-note {
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .panel:fullscreen, .panel:-webkit-full-screen {
      width: 100vw;
      height: 100vh;
      margin: 0;
      padding: 22px;
      border-radius: 0;
      overflow: auto;
      background: #f8fafc;
    }
    .panel:fullscreen > .section-controls,
    .panel:-webkit-full-screen > .section-controls {
      display: none !important;
    }
    .panel:fullscreen .sticky-filter-shell .section-controls,
    .panel:-webkit-full-screen .sticky-filter-shell .section-controls {
      display: grid;
    }
    .panel:fullscreen .sticky-filter-shell,
    .panel:-webkit-full-screen .sticky-filter-shell {
      display: inline-block;
      position: sticky;
      top: 0;
      left: auto !important;
      width: fit-content !important;
      max-width: 100%;
      margin-bottom: 14px;
      z-index: 5;
    }
    .panel:fullscreen .sticky-filter-shell .section-controls,
    .panel:-webkit-full-screen .sticky-filter-shell .section-controls {
      display: inline-flex;
      flex-wrap: wrap;
      align-items: flex-end;
      width: fit-content;
      max-width: 100%;
    }
    .panel:fullscreen .section-controls,
    .panel:-webkit-full-screen .section-controls {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-start;
      align-items: end;
      gap: 6px;
      margin-bottom: 14px;
      position: sticky;
      top: 0;
      z-index: 4;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
    }
    .panel:fullscreen .global-controls,
    .panel:-webkit-full-screen .global-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .panel:fullscreen .section-controls > div,
    .panel:fullscreen .section-controls .multi-dropdown,
    .panel:-webkit-full-screen .section-controls > div,
    .panel:-webkit-full-screen .section-controls .multi-dropdown {
      flex: 0 0 auto;
      width: auto;
      min-width: 0;
      max-width: max-content;
    }
    .panel:fullscreen .section-controls .label,
    .panel:-webkit-full-screen .section-controls .label {
      font-size: 11px;
      line-height: 1.2;
      margin-bottom: 3px;
    }
    .panel:fullscreen .section-controls input,
    .panel:fullscreen .section-controls select,
    .panel:fullscreen .section-controls button,
    .panel:-webkit-full-screen .section-controls input,
    .panel:-webkit-full-screen .section-controls select,
    .panel:-webkit-full-screen .section-controls button {
      min-height: 34px;
      padding-top: 6px;
      padding-bottom: 6px;
      font-size: 12px;
    }
    .panel:fullscreen .chart-inline-filter,
    .panel:-webkit-full-screen .chart-inline-filter {
      min-width: 118px;
      gap: 3px;
    }
    .panel:fullscreen .chart-inline-filter label,
    .panel:-webkit-full-screen .chart-inline-filter label {
      font-size: 11px;
    }
    .panel:fullscreen .chart-inline-filter select,
    .panel:-webkit-full-screen .chart-inline-filter select {
      min-height: 34px;
      padding: 6px 26px 6px 10px;
      font-size: 12px;
    }
    @media (max-width: 640px) {
      .panel:fullscreen .section-controls,
      .panel:-webkit-full-screen .section-controls {
        gap: 4px;
        padding: 6px;
      }
      .panel:fullscreen .section-controls > div,
      .panel:fullscreen .section-controls .multi-dropdown,
      .panel:-webkit-full-screen .section-controls > div,
      .panel:-webkit-full-screen .section-controls .multi-dropdown {
        max-width: none;
      }
      .panel:fullscreen .section-controls input,
      .panel:fullscreen .section-controls select,
      .panel:fullscreen .section-controls button,
      .panel:-webkit-full-screen .section-controls input,
      .panel:-webkit-full-screen .section-controls select,
      .panel:-webkit-full-screen .section-controls button {
        min-height: 32px;
        font-size: 11px;
      }
      .panel:fullscreen .chart-inline-filter,
      .panel:-webkit-full-screen .chart-inline-filter {
        min-width: 104px;
      }
      .panel:fullscreen .chart-head,
      .panel:-webkit-full-screen .chart-head,
      .panel:fullscreen .chart-actions,
      .panel:-webkit-full-screen .chart-actions {
        width: fit-content;
        max-width: 100%;
      }
    }
    .panel:fullscreen .chart-head,
    .panel:-webkit-full-screen .chart-head {
      display: inline-flex;
      width: fit-content;
      max-width: 100%;
      align-items: center;
      justify-content: flex-start;
      margin-top: 6px;
    }
    .panel:fullscreen .chart-actions,
    .panel:-webkit-full-screen .chart-actions {
      width: auto;
      margin-left: 0;
      justify-content: flex-start;
      flex-wrap: wrap;
    }
    .panel:fullscreen .fullscreen-focus-header,
    .panel:-webkit-full-screen .fullscreen-focus-header {
      display: block;
    }
    .panel:fullscreen .chart-insight.visible,
    .panel:-webkit-full-screen .chart-insight.visible {
      display: block;
    }
    .panel:fullscreen .chart-box, .panel:-webkit-full-screen .chart-box {
      height: calc(100vh - 280px);
      min-height: 520px;
    }
    .panel:fullscreen .section-head h2, .panel:-webkit-full-screen .section-head h2 {
      font-size: 32px;
    }
    .panel:fullscreen .legend,
    .panel:fullscreen .legend-scale,
    .panel:-webkit-full-screen .legend,
    .panel:-webkit-full-screen .legend-scale {
      font-size: 15px;
    }
    @media print {
      body {
        background: #ffffff !important;
      }
      .page {
        max-width: none;
        padding: 0;
      }
      .hero, .panel {
        box-shadow: none;
      }
      button, input, select {
        print-color-adjust: exact;
        -webkit-print-color-adjust: exact;
      }
    }
    @media (max-width: 1280px) {
      .global-controls {
        grid-template-columns: 1fr;
      }
      .topbar {
        flex-direction: column;
        align-items: stretch;
      }
      .title-block {
        align-items: flex-start;
      }
      .top-actions {
        align-items: flex-end;
        justify-content: space-between;
        flex-wrap: wrap;
      }
      .action-row {
        justify-content: flex-end;
        flex-wrap: wrap;
      }
      .header-icon-group {
        width: auto;
        justify-content: flex-end;
      }
    }
    @media (max-width: 900px) {
      .page {
        width: 100%;
      }
      .pre-summary-grid {
        grid-template-columns: 1fr;
      }
      .section-card {
        padding: 14px;
      }
      .dataset-summary-grid {
        grid-template-columns: 1fr;
      }
      .dataset-kpi-row {
        grid-template-columns: 1fr;
      }
      .section-head {
        flex-wrap: wrap;
      }
      .chart-head {
        flex-wrap: wrap;
        align-items: flex-start;
      }
      .chart-actions {
        width: 100%;
        justify-content: flex-start;
        flex-wrap: wrap;
      }
      .chart-box {
        height: clamp(320px, 64vw, 460px);
        padding: 10px;
      }
      .chart-box.top20-mode {
        height: clamp(460px, 88vw, 700px);
      }
      .tail-card-grid,
      .tail-card-grid-single {
        grid-template-columns: 1fr;
      }
      .tail-summary-card {
        grid-template-columns: 1fr;
      }
      .tail-summary-panel {
        min-height: 0;
      }
      .tail-summary-header {
        align-items: flex-start;
        flex-wrap: wrap;
      }
      .tail-summary-heading {
        width: 100%;
      }
      .tail-filter-field {
        width: 100%;
        max-width: none;
      }
      .tail-stat-card {
        min-height: 0;
      }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="topbar" id="dashboardHeaderSection">
      <div class="title-block">
        <h1>CTV FCT Dashboard</h1>
        <div class="title-range">Date Range: <span id="activeDateRangeText">__REPORT_DATE__</span></div>
        <div class="title-meta">Total Records: <strong id="totalRecordsText">0</strong></div>
      </div>
      <div class="top-actions">
        <div class="action-row" id="headerActionRow">
          <div class="header-icon-group">
            <input class="upload-input-hidden" id="fileUpload" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
            <button class="upload-btn icon-btn" id="uploadBtn" type="button" title="Upload File" aria-label="Upload File">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 20V8"></path>
                <path d="M7 13l5-5 5 5"></path>
                <path d="M4 4h16"></path>
              </svg>
              <span class="sr-only">Upload File</span>
            </button>
            <span class="control-check" id="uploadCheck" hidden>&#10003;</span>
            <button class="sheet-btn icon-btn" id="sheetBtn" type="button" title="Select Sheet" aria-label="Select Sheet" hidden disabled>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 3h9l3 3v15H6z"></path>
                <path d="M9 13h6"></path>
                <path d="M9 17h6"></path>
              </svg>
              <span class="sr-only">Select Sheet</span>
            </button>
            <span class="control-check" id="sheetCheck" hidden>&#10003;</span>
            <button class="pdf-btn icon-btn" id="pdfBtn" type="button" title="Download Dashboard" aria-label="Download Dashboard">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 4v12"></path>
                <path d="M7 11l5 5 5-5"></path>
                <path d="M4 20h16"></path>
              </svg>
              <span class="sr-only">Download Dashboard</span>
            </button>
            <div class="sheet-menu" id="sheetMenu" hidden>
              <div class="sheet-menu-title">Select Sheet</div>
              <div class="sheet-menu-list" id="sheetMenuList"></div>
            </div>
          </div>
        </div>
        <div class="status" id="statusText">Choose a CSV or Excel file to generate the dashboard.</div>
      </div>
    </section>
    <section class="section">
      <div class="excluded-inline">
        <span class="excluded-items" id="excludedChips"></span>
      </div>
    </section>
__GLOBAL_FILTER_HTML__
    <section class="section" id="dashboardSummarySection">
      <div class="panel section-card">
        <div class="section-head">
          <h2>Dashboard Summary</h2>
        </div>
        <div class="summary-lines" id="summaryLines"></div>
      </div>
    </section>
__SECTIONS_HTML__
__DATASET_SUMMARY_HTML__
    <button class="share-fab" id="shareBtn" type="button" title="Share Dashboard" aria-label="Share Dashboard">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 16V5"></path>
        <path d="M8 9l4-4 4 4"></path>
        <path d="M5 19h14"></path>
      </svg>
      <span class="sr-only">Share Dashboard</span>
    </button>
    <div class="share-modal" id="shareModal" hidden>
      <div class="share-modal-card" role="dialog" aria-modal="true" aria-labelledby="shareModalTitle">
        <h3 class="share-modal-title" id="shareModalTitle">Share Dashboard</h3>
        <p class="share-modal-copy">Download a read-only HTML snapshot of the current dashboard with the embedded dataset, active filters, charts, heatmaps, tables, and full-screen viewing preserved.</p>
        <div class="share-modal-actions">
          <button class="share-modal-btn" id="shareCancelBtn" type="button">Cancel</button>
          <button class="share-modal-btn primary" id="shareDownloadBtn" type="button">Download Shareable Dashboard</button>
        </div>
      </div>
    </div>
  <script>
__XLSX_BUNDLE__
  </script>
  <script>
    const PAYLOAD = __PAYLOAD_JSON__;
    const COLUMN_MAPPING_CONFIG = __COLUMN_MAPPING_CONFIG_JSON__;
    const VALUE_MAPPING_CONFIG = __VALUE_MAPPING_CONFIG_JSON__;
    const EXCLUDED = new Set(PAYLOAD.excluded);
    const numberFormat = new Intl.NumberFormat('en-US');
    const longDate = new Intl.DateTimeFormat('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
    const CHANNEL_COLORS = {
      'AAJ TAK': '#22c55e',
      'ABP NEWS': '#3b82f6',
      'INDIA TV': '#ef4444',
      'NEWS18 INDIA': '#a855f7'
    };
    const chartPalettes = {
      g1: ['#3b82f6', '#22c55e', '#ef4444', '#a855f7'],
      g2: ['#3b82f6', '#22c55e', '#ef4444', '#a855f7'],
      g3: ['#1d4ed8', '#0f766e', '#b45309', '#7c3aed', '#be123c', '#0369a1', '#166534', '#7f1d1d'],
      g6: ['#dbeafe', '#93c5fd', '#67e8f9', '#5eead4'],
      g7: '#2563eb',
      g8: ['#93c5fd'],
      g9: ['#2563eb', '#22c55e', '#f59e0b', '#7c3aed', '#ef4444', '#14b8a6'],
      g10: ['rgba(23, 59, 92, 0.18)', 'rgba(23, 59, 92, 0.26)', 'rgba(23, 59, 92, 0.35)', 'rgba(23, 59, 92, 0.40)', 'rgba(23, 59, 92, 0.44)'],
      g11: ['#2563eb', '#16a34a', '#f59e0b', '#7c3aed', '#94a3b8'],
      g12: ['#93c5fd'],
      g13: ['#93c5fd'],
      heat: ['#eef4ff', '#dbeafe', '#93c5fd', '#60a5fa', '#2563eb'],
      g4heat: ['#e0f2fe', '#7dd3fc', '#7dd3fc'],
      g5heat: ['#f3f4f6', '#e5e7eb', '#d1d5db', '#9ca3af', '#9ca3af']
    };
    const state = {
      rawRows: [],
      standardizedRows: [],
      cleanedRows: [],
      preprocessMetadata: null,
      initialized: false,
      pendingWorkbook: null,
      pendingWorkbookFileName: '',
      pendingWorkbookSelectedSheet: '',
      supplemental: {
        dayType: 'weekday'
      },
      global: {
        topN: '10',
        start: '',
        end: '',
        channel: [],
        category: [],
        advertisor: [],
        time: 'minutes'
      },
      sections: {
__STATE_SECTIONS_JS__
      }
    };
    const dom = {
      fileUpload: document.getElementById('fileUpload'),
      uploadBtn: document.getElementById('uploadBtn'),
      uploadCheck: document.getElementById('uploadCheck'),
      sheetBtn: document.getElementById('sheetBtn'),
      sheetCheck: document.getElementById('sheetCheck'),
      sheetMenu: document.getElementById('sheetMenu'),
      sheetMenuList: document.getElementById('sheetMenuList'),
      pdfBtn: document.getElementById('pdfBtn'),
      shareBtn: document.getElementById('shareBtn'),
      shareModal: document.getElementById('shareModal'),
      shareCancelBtn: document.getElementById('shareCancelBtn'),
      shareDownloadBtn: document.getElementById('shareDownloadBtn'),
      statusText: document.getElementById('statusText'),
      filterErrorText: document.getElementById('filterErrorText'),
      activeDateRangeText: document.getElementById('activeDateRangeText'),
      totalRecordsText: document.getElementById('totalRecordsText'),
      excludedChips: document.getElementById('excludedChips'),
      summaryLines: document.getElementById('summaryLines'),
      datasetSummaryOriginalRows: document.getElementById('datasetSummaryOriginalRows'),
      datasetSummaryOriginalCategories: document.getElementById('datasetSummaryOriginalCategories'),
      datasetSummaryOriginalAdvertisers: document.getElementById('datasetSummaryOriginalAdvertisers'),
      datasetSummaryFilteredRows: document.getElementById('datasetSummaryFilteredRows'),
      datasetSummaryFilteredCategories: document.getElementById('datasetSummaryFilteredCategories'),
      datasetSummaryFilteredAdvertisers: document.getElementById('datasetSummaryFilteredAdvertisers'),
      headerSection: document.getElementById('dashboardHeaderSection'),
      summarySection: document.getElementById('dashboardSummarySection'),
      stickyFilterWrap: document.getElementById('stickyFilterWrap'),
      stickyFilterShell: document.getElementById('stickyFilterShell'),
      global: {
        topN: document.getElementById('globalTopN'),
        start: document.getElementById('globalStart'),
        end: document.getElementById('globalEnd'),
        channel: document.getElementById('globalChannel'),
        channelDropdown: document.getElementById('globalChannelDropdown'),
        channelTrigger: document.getElementById('globalChannelTrigger'),
        channelValue: document.getElementById('globalChannelValue'),
        channelSearch: document.getElementById('globalChannelSearch'),
        channelOptions: document.getElementById('globalChannelOptions'),
        channelAll: document.getElementById('globalChannelAll'),
        channelClear: document.getElementById('globalChannelClear'),
        category: document.getElementById('globalCategory'),
        categoryDropdown: document.getElementById('globalCategoryDropdown'),
        categoryTrigger: document.getElementById('globalCategoryTrigger'),
        categoryValue: document.getElementById('globalCategoryValue'),
        categorySearch: document.getElementById('globalCategorySearch'),
        categoryOptions: document.getElementById('globalCategoryOptions'),
        categoryAll: document.getElementById('globalCategoryAll'),
        categoryClear: document.getElementById('globalCategoryClear'),
        advertisor: document.getElementById('globalAdvertisor'),
        advertisorDropdown: document.getElementById('globalAdvertisorDropdown'),
        advertisorTrigger: document.getElementById('globalAdvertisorTrigger'),
        advertisorValue: document.getElementById('globalAdvertisorValue'),
        advertisorSearch: document.getElementById('globalAdvertisorSearch'),
        advertisorOptions: document.getElementById('globalAdvertisorOptions'),
        advertisorAll: document.getElementById('globalAdvertisorAll'),
        advertisorClear: document.getElementById('globalAdvertisorClear'),
        time: document.getElementById('globalTime'),
        reset: document.getElementById('globalReset')
      },
      sections: {
__DOM_SECTIONS_JS__
      }
    };
    const SECTION_KEYS = ['g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8', 'g9', 'g10', 'g11', 'g12', 'g13'];
    const CATEGORY_SECTION_KEYS = ['g1', 'g2', 'g3', 'g5'];
    function formatNumber(value) { return numberFormat.format(value || 0); }
    function sentenceCaseName(value) {
      const raw = String(value || '').trim().toLowerCase();
      return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : '';
    }
    function titleCaseName(value) {
      return String(value || '')
        .trim()
        .toLowerCase()
        .replace(/\b([a-z])/g, letter => letter.toUpperCase());
    }
    function activeTimeUnit() { return state.global.time || 'minutes'; }
    function formatDurationValue(value, withUnit = false) {
      const unit = activeTimeUnit();
      if (unit === 'minutes') {
        const minutes = (value || 0) / 60;
        const formatted = minutes.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
        return withUnit ? `${formatted} min` : formatted;
      }
      const formatted = formatNumber(Math.round(value || 0));
      return withUnit ? `${formatted} sec` : formatted;
    }
    function metricLabel() {
      return activeTimeUnit() === 'minutes'
        ? 'Advertisement Duration (Min)'
        : 'Advertisement Duration (Sec)';
    }
    function advertisorLabel() { return 'Advertiser'; }
    function formatDate(value) {
      if (!value) return '';
      const d = new Date(value + 'T00:00:00');
      return Number.isNaN(d.getTime()) ? value : longDate.format(d);
    }
    function uniqueSorted(values) {
      return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    function normalizeDate(value) {
      const raw = String(value || '').trim();
      if (!raw) return '';
      if (/^\\d{1,2}:\\d{2}(:\\d{2})?$/.test(raw)) return '';
      if (/^\\d{4}-\\d{2}-\\d{2}$/.test(raw)) return raw;
      if (/^\\d{1,2}[\\/\\-]\\d{1,2}[\\/\\-]\\d{2,4}$/.test(raw)) {
        const [left, middle, right] = raw.split(/[\\/\\-]/).map(part => part.trim());
        const year = right.length === 2 ? `20${right}` : right;
        return `${year.padStart(4, '0')}-${middle.padStart(2, '0')}-${left.padStart(2, '0')}`;
      }
      const parsed = new Date(raw);
      if (!Number.isNaN(parsed.getTime())) {
        return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}-${String(parsed.getDate()).padStart(2, '0')}`;
      }
      const parts = raw.split('-').map(p => p.trim());
      if (parts.length === 3) {
        let [day, month, year] = parts;
        if (year.length === 2) year = '20' + year.padStart(2, '0');
        return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
      }
      return raw;
    }
    function normalizeHeader(value, fallbackIndex) {
      const cleaned = String(value || '').replace(/^\\uFEFF/, '').trim();
      return cleaned || `Column ${fallbackIndex + 1}`;
    }
    function normalizeColumnKey(value) {
      return String(value || '').toLowerCase().replace(/[_-]+/g, ' ').replace(/\\s+/g, ' ').trim();
    }
    function parseNumericValue(value) {
      if (value === null || value === undefined || value === '') return 0;
      const normalized = String(value).replace(/,/g, '').trim();
      const numeric = Number.parseFloat(normalized);
      return Number.isFinite(numeric) ? numeric : 0;
    }
    function detectDelimiter(text) {
      const sample = String(text || '').split(/\\r?\\n/).slice(0, 10).join('\\n');
      const candidates = [',', '\\t', ';', '|'];
      let best = ',';
      let bestScore = -1;
      candidates.forEach(delimiter => {
        let score = 0;
        let inQuotes = false;
        for (let i = 0; i < sample.length; i++) {
          const ch = sample[i];
          if (ch === '"') inQuotes = !inQuotes;
          else if (ch === delimiter && !inQuotes) score += 1;
        }
        if (score > bestScore) {
          best = delimiter;
          bestScore = score;
        }
      });
      return best;
    }
    function normalizeRow(record) {
      const aaddur = parseNumericValue(record['Aaddur'] || '0');
      return {
        channel: String(record['Channel Name'] || '').trim(),
        date: normalizeDate(record['Pdate'] || ''),
        adtime: normalizeTimeValue(record['Adst'] || ''),
        product: String(record['Brand Name'] || '').trim(),
        company: String(record['Company'] || '').trim(),
        aaddur: Number.isFinite(aaddur) ? aaddur : 0,
        category: String(record['Category'] || '').trim(),
        programme: String(record['Programme Name'] || record['Program Name'] || '').trim(),
        programmeType: String(record['Programme Type'] || record['Program Type'] || '').trim()
      };
    }
    function logPreprocessInfo(message, details) {
      if (details !== undefined) console.info(`[Preprocess] ${message}`, details);
      else console.info(`[Preprocess] ${message}`);
    }
    function logPreprocessWarn(message, details) {
      if (details !== undefined) console.warn(`[Preprocess] ${message}`, details);
      else console.warn(`[Preprocess] ${message}`);
    }
    function getStandardColumnAliases() {
      return (COLUMN_MAPPING_CONFIG && COLUMN_MAPPING_CONFIG.standard_columns) || {};
    }
    function buildColumnAliasLookup() {
      const lookup = new Map();
      Object.entries(getStandardColumnAliases()).forEach(([standardName, aliases]) => {
        lookup.set(normalizeColumnKey(standardName), standardName);
        (aliases || []).forEach(alias => lookup.set(normalizeColumnKey(alias), standardName));
      });
      return lookup;
    }
    function getStandardFieldLabels() {
      return {
        feed_name: 'Feed Name',
        channel_name: 'Channel Name',
        report_date: 'Pdate',
        time_slot: 'Adst',
        brand_name: 'Brand Name',
        company_name: 'Company',
        metric_value: 'Aaddur',
        category_name: 'Category',
        programme_name: 'Programme Name',
        programme_type: 'Programme Type'
      };
    }
    function loadDatasetFromCsvText(text) {
      const delimiter = detectDelimiter(text);
      const matrix = parseDelimitedText(text, delimiter);
      if (!matrix.length) throw new Error('The selected CSV file is empty.');
      return buildObjectsFromMatrix(matrix);
    }
    function loadDatasetFromWorksheetMatrix(matrix) {
      if (!matrix.length || !matrix.some(row => row.some(cell => String(cell || '').trim()))) {
        throw new Error('The selected worksheet is empty.');
      }
      return buildObjectsFromMatrix(matrix);
    }
    function parseDelimitedText(text, delimiter = ',') {
      const rows = [];
      const lines = [];
      let field = '';
      let row = [];
      let inQuotes = false;
      for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        const next = text[i + 1];
        if (ch === '"') {
          if (inQuotes && next === '"') {
            field += '"';
            i++;
          } else {
            inQuotes = !inQuotes;
          }
        } else if (ch === delimiter && !inQuotes) {
          row.push(field);
          field = '';
        } else if ((ch === '\\n' || ch === '\\r') && !inQuotes) {
          if (ch === '\\r' && next === '\\n') i++;
          row.push(field);
          lines.push(row);
          row = [];
          field = '';
        } else {
          field += ch;
        }
      }
      if (field.length || row.length) {
        row.push(field);
        lines.push(row);
      }
      return lines.filter(line => line.some(cell => String(cell || '').trim()));
    }
    function buildObjectsFromMatrix(matrix) {
      if (!matrix.length) return [];
      const headers = matrix[0].map((value, index) => normalizeHeader(value, index));
      const seen = new Map();
      const uniqueHeaders = headers.map(header => {
        const count = seen.get(header) || 0;
        seen.set(header, count + 1);
        return count ? `${header} (${count + 1})` : header;
      });
      return matrix.slice(1).map(line => Object.fromEntries(uniqueHeaders.map((header, index) => [header, line[index] || ''])));
    }
    function detectColumnProfiles(records) {
      const headers = Object.keys(records[0] || {});
      return headers.map(header => {
        const values = records.map(record => record[header]).filter(value => String(value || '').trim());
        const sample = values.slice(0, 200);
        const numericCount = sample.filter(value => {
          const normalized = String(value).replace(/,/g, '').trim();
          return normalized && Number.isFinite(Number.parseFloat(normalized));
        }).length;
        const dateCount = sample.filter(value => !!normalizeDate(value)).length;
        const timeCount = sample.filter(value => !!normalizeTimeValue(value)).length;
        return {
          header,
          key: normalizeColumnKey(header),
          values,
          sampleCount: sample.length,
          numericRatio: sample.length ? numericCount / sample.length : 0,
          dateRatio: sample.length ? dateCount / sample.length : 0,
          timeRatio: sample.length ? timeCount / sample.length : 0
        };
      });
    }
    function scoreProfile(profile, aliases) {
      return aliases.reduce((score, alias) => score + (profile.key.includes(alias) ? 10 : 0), 0);
    }
    function inferGenericColumnMapping(records) {
      if (!records.length) throw new Error('The selected dataset does not contain any data rows.');
      const profiles = detectColumnProfiles(records);
      const used = new Set();
      function choose(aliases, predicate, fallback = false) {
        const matches = profiles
          .filter(profile => !used.has(profile.header) && (!predicate || predicate(profile)))
          .map(profile => ({
            profile,
            score: scoreProfile(profile, aliases)
          }))
          .sort((a, b) => b.score - a.score || b.profile.values.length - a.profile.values.length);
        const picked = matches.find(item => item.score > 0) || (fallback ? matches[0] : null);
        if (picked) {
          used.add(picked.profile.header);
          return picked.profile.header;
        }
        return '';
      }
      const date = choose(['date', 'day', 'month', 'year', 'period'], profile => profile.dateRatio >= 0.5, true);
      const adtime = choose(['time', 'slot', 'hour', 'adst'], profile => profile.timeRatio >= 0.5);
      const aaddur = choose(['duration', 'amount', 'value', 'metric', 'total', 'count', 'qty', 'quantity', 'revenue', 'sales', 'aaddur'], profile => profile.numericRatio >= 0.7, true);
      const textPredicate = profile => profile.numericRatio < 0.7;
      const feed = choose(['feed', 'network', 'station', 'source'], textPredicate, true);
      const channel = choose(['channel', 'channel name'], textPredicate);
      const company = choose(['company', 'client', 'customer', 'account', 'owner', 'group'], textPredicate, true);
      const product = choose(['brand', 'product', 'advertiser', 'campaign', 'item', 'title', 'name'], textPredicate, true);
      const category = choose(['category', 'segment', 'type', 'class', 'genre', 'vertical'], textPredicate, true);
      const programme = choose(['programme', 'program', 'show', 'content', 'property'], textPredicate);
      const programmeType = choose(['programme type', 'program type', 'show type', 'content type', 'genre'], textPredicate);
      return {
        report_date: date,
        time_slot: adtime,
        metric_value: aaddur,
        feed_name: feed,
        channel_name: channel,
        company_name: company,
        brand_name: product,
        category_name: category,
        programme_name: programme,
        programme_type: programmeType
      };
    }
    function standardizeColumns(records) {
      if (!records.length) throw new Error('The selected dataset does not contain any data rows.');
      const aliasLookup = buildColumnAliasLookup();
      const appliedMappings = [];
      const unknownColumns = new Set();
      const standardizedRecords = records.map(record => {
        const next = {};
        Object.entries(record).forEach(([column, value]) => {
          const normalizedKey = normalizeColumnKey(column);
          const standardName = aliasLookup.get(normalizedKey);
          const targetKey = standardName || column;
          if (standardName) {
            if (!appliedMappings.some(item => item.from === column && item.to === standardName)) {
              appliedMappings.push({ from: column, to: standardName });
            }
          } else {
            unknownColumns.add(column);
          }
          if (next[targetKey] === undefined || next[targetKey] === '') {
            next[targetKey] = value;
          }
        });
        return next;
      });

      const inferredMappings = inferGenericColumnMapping(standardizedRecords);
      Object.entries(inferredMappings).forEach(([standardName, sourceColumn]) => {
        if (!sourceColumn) return;
        if (standardizedRecords.some(record => record[standardName] !== undefined && String(record[standardName]).trim() !== '')) return;
        standardizedRecords.forEach(record => {
          record[standardName] = record[sourceColumn];
        });
        appliedMappings.push({ from: sourceColumn, to: standardName, inferred: true });
      });

      logPreprocessInfo('Column mappings applied.', appliedMappings);
      if (unknownColumns.size) {
        logPreprocessWarn('Unknown columns encountered and preserved in memory.', Array.from(unknownColumns));
      }
      return { records: standardizedRecords, appliedMappings, unknownColumns: Array.from(unknownColumns) };
    }
    function standardizeValues(records) {
      const config = VALUE_MAPPING_CONFIG || {};
      const normalizedConfigs = Object.fromEntries(Object.entries(config).map(([column, mappings]) => [
        column,
        Object.fromEntries(Object.entries(mappings || {}).map(([rawValue, standardValue]) => [normalizeColumnKey(rawValue), standardValue]))
      ]));
      const appliedColumns = [];
      const unknownValues = {};
      const standardizedRecords = records.map(record => {
        const next = { ...record };
        Object.entries(normalizedConfigs).forEach(([column, mapping]) => {
          if (!(column in next)) return;
          const rawValue = String(next[column] || '').trim();
          if (!rawValue) return;
          const normalizedValue = normalizeColumnKey(rawValue);
          if (Object.prototype.hasOwnProperty.call(mapping, normalizedValue)) {
            next[column] = mapping[normalizedValue];
            if (!appliedColumns.includes(column)) appliedColumns.push(column);
          } else {
            if (!unknownValues[column]) unknownValues[column] = [];
            if (!unknownValues[column].includes(rawValue) && unknownValues[column].length < 20) {
              unknownValues[column].push(rawValue);
            }
          }
        });
        return next;
      });
      logPreprocessInfo('Value mappings applied.', appliedColumns);
      Object.entries(unknownValues).forEach(([column, values]) => {
        if (values.length) logPreprocessWarn(`Unknown values preserved for ${column}.`, values);
      });
      return { records: standardizedRecords, appliedColumns, unknownValues };
    }
    function deriveChannelName(records) {
      const derivedRecords = records.map(record => {
        const next = { ...record };
        const feedValue = String(next.feed_name || '').trim();
        const channelValue = String(next.channel_name || '').trim();
        if (feedValue) {
          next.channel_name = feedValue;
        } else if (channelValue) {
          next.channel_name = channelValue;
        } else {
          next.channel_name = '';
        }
        return next;
      });
      logPreprocessInfo('Derived channel_name from standardized feed_name values.');
      return derivedRecords;
    }
    function transformStandardizedRecord(record) {
      const labels = getStandardFieldLabels();
      return normalizeRow({
        [labels.channel_name]: record.channel_name || record.feed_name || '',
        [labels.report_date]: record.report_date || '',
        [labels.time_slot]: record.time_slot || '',
        [labels.brand_name]: record.brand_name || '',
        [labels.company_name]: record.company_name || '',
        [labels.metric_value]: record.metric_value ?? '1',
        [labels.category_name]: record.category_name || '',
        [labels.programme_name]: record.programme_name || '',
        [labels.programme_type]: record.programme_type || ''
      });
    }
    function preprocessDataset(records, sourceLabel) {
      logPreprocessInfo(`Dataset loaded successfully from ${sourceLabel}.`, { rows: records.length });
      const standardizedColumns = standardizeColumns(records);
      const standardizedValues = standardizeValues(standardizedColumns.records);
      const channelStandardizedRecords = deriveChannelName(standardizedValues.records);
      const rows = channelStandardizedRecords
        .map(transformStandardizedRecord)
        .filter(record => record.channel || record.company || record.product || record.category || record.aaddur);
      if (!rows.length) throw new Error('The selected dataset does not contain any usable rows after preprocessing.');
      logPreprocessInfo('Preprocessing completed successfully.', { rows: rows.length });
      return {
        dashboardRows: rows,
        standardizedRecords: channelStandardizedRecords,
        metadata: {
          columnMappings: standardizedColumns.appliedMappings,
          unknownColumns: standardizedColumns.unknownColumns,
          valueMappedColumns: standardizedValues.appliedColumns,
          unknownValues: standardizedValues.unknownValues
        }
      };
    }
    function setStatus(message, isError = false) {
      if (!dom.statusText) return;
      dom.statusText.textContent = message || '';
      dom.statusText.style.display = message ? 'block' : 'none';
      dom.statusText.style.color = isError ? '#b91c1c' : '#0f172a';
    }
    function readUploadedFile(file, encoding = 'UTF-8') {
      return new Promise((resolve, reject) => {
        if (!file) {
          reject(new Error('No file selected'));
          return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Could not read CSV file'));
        reader.onload = event => resolve(String(event.target && event.target.result || '').replace(/^\\uFEFF/, ''));
        reader.readAsText(file, encoding);
      });
    }
    function readUploadedArrayBuffer(file) {
      return new Promise((resolve, reject) => {
        if (!file) {
          reject(new Error('No file selected'));
          return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Could not read Excel file'));
        reader.onload = event => resolve(event.target && event.target.result);
        reader.readAsArrayBuffer(file);
      });
    }
    function setUploadSuccessState(isSuccess) {
      if (dom.uploadCheck) dom.uploadCheck.hidden = !isSuccess;
      if (dom.uploadBtn) dom.uploadBtn.classList.toggle('success', isSuccess);
    }
    function setSheetSuccessState(isSuccess) {
      if (dom.sheetCheck) dom.sheetCheck.hidden = !isSuccess;
      if (dom.sheetBtn) dom.sheetBtn.classList.toggle('success', isSuccess);
    }
    function hideSheetMenu() {
      if (!dom.sheetMenu) return;
      dom.sheetMenu.hidden = true;
      dom.sheetMenu.classList.remove('open');
    }
    function populateSheetMenu(sheetNames) {
      if (!dom.sheetMenuList) return;
      dom.sheetMenuList.innerHTML = '';
      sheetNames.forEach((name, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sheet-menu-item';
        if (name === state.pendingWorkbookSelectedSheet) {
          button.classList.add('active');
        }
        button.textContent = `${index + 1}. ${name}`;
        button.title = name;
        button.addEventListener('click', () => {
          try {
            const result = parseSelectedWorksheet(String(index));
            setSheetSuccessState(true);
            hideSheetMenu();
            loadRows(
              result.rows,
              `Loaded workbook: ${state.pendingWorkbookFileName || 'Excel file'} | Sheet: ${result.sheetName}`,
              result.metadata,
              { preserveSheetSuccessState: true, preserveWorkbookSelection: true }
            );
            populateSheetMenu(state.pendingWorkbook.SheetNames || []);
          } catch (error) {
            setSheetSuccessState(false);
            setStatus(error.message || 'Could not load worksheet', true);
          }
        });
        dom.sheetMenuList.appendChild(button);
      });
    }
    function toggleSheetMenu() {
      if (!dom.sheetMenu || !dom.sheetBtn || dom.sheetBtn.disabled) return;
      const willOpen = dom.sheetMenu.hidden;
      if (willOpen && state.pendingWorkbook && Array.isArray(state.pendingWorkbook.SheetNames)) {
        populateSheetMenu(state.pendingWorkbook.SheetNames);
      }
      dom.sheetMenu.hidden = !willOpen;
      dom.sheetMenu.classList.toggle('open', willOpen);
    }
    async function parseUploadedCsvFile(file) {
      const encodings = ['UTF-8', 'windows-1252', 'iso-8859-1'];
      let lastError = null;
      for (const encoding of encodings) {
        try {
          const text = await readUploadedFile(file, encoding);
          const records = loadDatasetFromCsvText(text);
          return preprocessDataset(records, file.name);
        } catch (error) {
          lastError = error;
        }
      }
      throw lastError || new Error('Could not read CSV file');
    }
    async function prepareWorkbookSelection(file) {
      if (typeof XLSX === 'undefined') {
        throw new Error('Excel import is unavailable because the workbook parser could not be loaded.');
      }
      const buffer = await readUploadedArrayBuffer(file);
      let workbook;
      try {
        workbook = XLSX.read(buffer, { type: 'array', dense: true, cellDates: false });
      } catch (error) {
        throw new Error('The selected Excel file is corrupted or invalid.');
      }
      if (!workbook.SheetNames || !workbook.SheetNames.length) {
        throw new Error('The selected Excel file does not contain any worksheets.');
      }
      state.pendingWorkbook = workbook;
      state.pendingWorkbookFileName = file.name;
      state.pendingWorkbookSelectedSheet = '';
      if (dom.sheetBtn) {
        dom.sheetBtn.hidden = false;
        dom.sheetBtn.disabled = false;
      }
      populateSheetMenu(workbook.SheetNames);
      setUploadSuccessState(true);
      setSheetSuccessState(false);
      setStatus(`Workbook ready: ${file.name}. Choose a worksheet before importing.`, false);
    }
    function clearWorkbookSelection(options = {}) {
      if (!options.preserveWorkbook) {
        state.pendingWorkbook = null;
        state.pendingWorkbookFileName = '';
        state.pendingWorkbookSelectedSheet = '';
      }
      if (dom.sheetBtn) {
        dom.sheetBtn.hidden = !!(!options.preserveWorkbook);
        dom.sheetBtn.disabled = !!(!options.preserveWorkbook);
      }
      if (dom.sheetMenuList && !options.preserveWorkbook) dom.sheetMenuList.innerHTML = '';
      hideSheetMenu();
      if (!options.preserveSuccessState) {
        setSheetSuccessState(false);
      }
    }
    function parseSelectedWorksheet(selectedIndex) {
      if (!state.pendingWorkbook) {
        throw new Error('Select an Excel file first.');
      }
      if (selectedIndex === '' || selectedIndex === undefined || selectedIndex === null) {
        throw new Error('Choose a worksheet before importing the Excel file.');
      }
      const sheetName = state.pendingWorkbook.SheetNames[Number.parseInt(selectedIndex, 10)];
      const sheet = state.pendingWorkbook.Sheets[sheetName];
      const matrix = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '', raw: false, blankrows: false });
      if (!matrix.length || !matrix.some(row => row.some(cell => String(cell || '').trim()))) {
        throw new Error(`The selected worksheet "${sheetName}" is empty.`);
      }
      state.pendingWorkbookSelectedSheet = sheetName;
      const records = loadDatasetFromWorksheetMatrix(matrix);
      const preprocessed = preprocessDataset(records, `${state.pendingWorkbookFileName} / ${sheetName}`);
      return { rows: preprocessed.dashboardRows, sheetName, metadata: preprocessed.metadata };
    }
    function cleanRows(rows) {
      return rows.filter(row => !EXCLUDED.has(row.category));
    }
    function hexToRgb(hex) {
      const clean = String(hex || '').replace('#', '');
      const full = clean.length === 3 ? clean.split('').map(ch => ch + ch).join('') : clean;
      const value = Number.parseInt(full, 16);
      return {
        r: (value >> 16) & 255,
        g: (value >> 8) & 255,
        b: value & 255
      };
    }
    function colorForValue(value, maxValue, paletteKey = 'heat') {
      const scale = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)));
      const palette = chartPalettes[paletteKey] || chartPalettes.heat;
      if (scale === 0) return palette[0];
      if (scale < 0.25) return palette[1];
      if (scale < 0.5) return palette[2];
      if (scale < 0.75) return palette[3];
      return palette[4];
    }
    function interpolateHexColor(startHex, endHex, factor) {
      const start = hexToRgb(startHex);
      const end = hexToRgb(endHex);
      const mix = Math.max(0, Math.min(1, factor));
      const r = Math.round(start.r + (end.r - start.r) * mix);
      const g = Math.round(start.g + (end.g - start.g) * mix);
      const b = Math.round(start.b + (end.b - start.b) * mix);
      return `rgb(${r}, ${g}, ${b})`;
    }
    function interpolateRgbaColor(start, end, factor) {
      const mix = Math.max(0, Math.min(1, factor));
      const r = Math.round(start.r + (end.r - start.r) * mix);
      const g = Math.round(start.g + (end.g - start.g) * mix);
      const b = Math.round(start.b + (end.b - start.b) * mix);
      const a = start.a + (end.a - start.a) * mix;
      return `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`;
    }
    function themeVar(name, fallback) {
      const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return value || fallback;
    }
    function appendLinearGradient(svg, gradientId, startColor, endColor, horizontal = true) {
      let defs = svg.querySelector('defs');
      if (!defs) {
        defs = svgEl('defs');
        svg.appendChild(defs);
      }
      const gradient = svgEl('linearGradient', horizontal
        ? { id: gradientId, x1: '0%', y1: '0%', x2: '100%', y2: '0%' }
        : { id: gradientId, x1: '0%', y1: '100%', x2: '0%', y2: '0%' });
      gradient.appendChild(svgEl('stop', { offset: '0%', 'stop-color': startColor }));
      gradient.appendChild(svgEl('stop', { offset: '100%', 'stop-color': endColor }));
      defs.appendChild(gradient);
      return `url(#${gradientId})`;
    }
    function graph4HeatColor(value, maxValue) {
      const scale = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)));
      return interpolateRgbaColor(
        { r: 74, g: 65, b: 168, a: 0.060 },
        { r: 74, g: 65, b: 168, a: 0.313 },
        scale
      );
    }
    function graph10HeatColor(value, maxValue) {
      const scale = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)));
      return interpolateRgbaColor(
        { r: 23, g: 59, b: 92, a: 0.18 },
        { r: 23, g: 59, b: 92, a: 0.44 },
        scale
      );
    }
    function graph10LabelColor(value, maxValue) {
      return '#ffffff';
    }
    function channelColor(channel, paletteKey) {
      const fixed = CHANNEL_COLORS[String(channel || '').trim().toUpperCase()];
      if (fixed) return fixed;
      const palette = chartPalettes[paletteKey] || chartPalettes.g1;
      let hash = 0;
      for (let i = 0; i < channel.length; i++) hash = channel.charCodeAt(i) + ((hash << 5) - hash);
      return palette[Math.abs(hash) % palette.length];
    }
    function channelHeatColor(channel, value, maxValue) {
      const scale = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)));
      return interpolateRgbaColor(
        { r: 46, g: 107, b: 16, a: 0.080 },
        { r: 46, g: 107, b: 16, a: 0.364 },
        scale
      );
    }
    function parseHourValue(value) {
      const raw = String(value || '').trim();
      if (!raw) return null;
      const match = raw.match(/^(\\d{1,2}):(\\d{2})(?::(\\d{2}))?$/);
      if (!match) return null;
      const hour = Number.parseInt(match[1], 10);
      if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;
      return hour;
    }
    function normalizeTimeValue(value) {
      const raw = String(value || '').trim();
      if (!raw) return '';
      const match = raw.match(/^(\\d{1,2})[:.](\\d{2})(?:[:.](\\d{2}))?$/);
      if (!match) return raw;
      const hour = match[1].padStart(2, '0');
      const minute = match[2].padStart(2, '0');
      const second = (match[3] || '00').padStart(2, '0');
      return `${hour}:${minute}:${second}`;
    }
    function hourLabel(hour) {
      return `${String(hour).padStart(2, '0')}:00`;
    }
    function hourSlotLabel(hour) {
      return `${hourLabel(hour)} - ${hourLabel((hour + 1) % 24)}`;
    }
    function makeSvg(box) {
      const width = Math.max(box.clientWidth || 900, 320);
      const height = Math.max(box.clientHeight || 500, 260);
      box.style.overflowX = 'hidden';
      box.innerHTML = '';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('class', 'chart chart-animated');
      svg.style.fontFamily = '"Segoe UI", Arial, sans-serif';
      box.appendChild(svg);
      return { svg, width, height };
    }
    function svgEl(name, attrs = {}) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
      return el;
    }
    function chartLabelColor() {
      return themeVar('--text', '#172033');
    }
    function addWrappedText(svg, text, x, y, maxChars, fill, size, anchor, weight) {
      const parts = [];
      let remaining = text || '';
      while (remaining.length > maxChars) {
        let idx = remaining.lastIndexOf(' ', maxChars);
        if (idx < 5) idx = maxChars;
        parts.push(remaining.slice(0, idx));
        remaining = remaining.slice(idx).trim();
      }
      if (remaining) parts.push(remaining);
      const scaledSize = Math.round((size || 12) * 1.18 * 10) / 10;
      const textEl = svgEl('text', {
        x, y, fill: fill || chartLabelColor(),
        'font-size': scaledSize,
        'font-weight': weight || 700,
        'text-anchor': anchor || 'middle'
      });
      parts.forEach((part, i) => {
        const tspan = svgEl('tspan', { x, dy: i === 0 ? 0 : Math.max(12, Math.round(scaledSize * 0.95)) });
        tspan.textContent = part;
        textEl.appendChild(tspan);
      });
      svg.appendChild(textEl);
    }
    function drawEmpty(box, message) {
      box.style.overflowX = 'hidden';
      box.innerHTML = `<div class="empty">${message}</div>`;
    }
    function populateSelect(select, values, placeholder) {
      if (select.multiple) {
        select.innerHTML = '';
      } else {
        select.innerHTML = `<option value="">${placeholder}</option>`;
      }
      values.forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
    }
    function sharedCategorySections() { return CATEGORY_SECTION_KEYS; }
    function getCategoryValues() {
      return uniqueSorted(state.cleanedRows.map(row => row.category).filter(Boolean));
    }
    function formatMinutes(value) { return formatDurationValue(value, false); }
    function withAxisHeadroom(value) {
      return value > 0 ? value * 1.08 : 1;
    }
    function isTop20Mode(sectionKey) {
      return String(state.sections[sectionKey] && state.sections[sectionKey].topN || '') === '20';
    }
    function applyChartDensity(sectionKey) {
      const chart = dom.sections[sectionKey] && dom.sections[sectionKey].chart;
      if (!chart) return;
      chart.classList.toggle('top20-mode', isTop20Mode(sectionKey));
    }
    function setChartBoxHeight(box, height) {
      if (!box) return;
      box.style.height = `${Math.max(height, 500)}px`;
    }
    function resetChartBoxHeight(box) {
      if (!box) return;
      box.style.height = '';
    }
    let viewportSyncToken = null;
    function handleViewportChange() {
      updateStickyFilterPosition();
      if (!state.initialized) return;
      if (viewportSyncToken) {
        window.cancelAnimationFrame(viewportSyncToken);
      }
      viewportSyncToken = window.requestAnimationFrame(() => {
        viewportSyncToken = null;
        renderAll();
      });
    }
    function rerenderSections(sectionKeys) {
      sectionKeys.forEach(renderSection);
    }
    function renderHeaderStats() {
      const rows = getDashboardSummaryRows();
      const visibleDates = rows.map(row => row.date).filter(Boolean).sort((a, b) => a.localeCompare(b));
      const activeRange = visibleDates.length
        ? `${formatDate(visibleDates[0])} - ${formatDate(visibleDates[visibleDates.length - 1])}`
        : getSelectedDateRangeText();
      if (dom.totalRecordsText) dom.totalRecordsText.textContent = formatNumber(rows.length);
      if (dom.activeDateRangeText) dom.activeDateRangeText.textContent = activeRange;
    }
    function renderDatasetSummary() {
      const originalRows = state.rawRows || [];
      const filteredRows = getDashboardSummaryRows();
      const originalCategories = new Set(originalRows.map(row => String(row.category || '').trim()).filter(Boolean));
      const originalAdvertisers = new Set(originalRows.map(row => String(row.company || '').trim()).filter(Boolean));
      const filteredCategories = new Set(filteredRows.map(row => String(row.category || '').trim()).filter(Boolean));
      const filteredAdvertisers = new Set(filteredRows.map(row => String(row.company || '').trim()).filter(Boolean));
      if (dom.datasetSummaryOriginalRows) dom.datasetSummaryOriginalRows.textContent = formatNumber(originalRows.length);
      if (dom.datasetSummaryOriginalCategories) dom.datasetSummaryOriginalCategories.textContent = formatNumber(originalCategories.size);
      if (dom.datasetSummaryOriginalAdvertisers) dom.datasetSummaryOriginalAdvertisers.textContent = formatNumber(originalAdvertisers.size);
      if (dom.datasetSummaryFilteredRows) dom.datasetSummaryFilteredRows.textContent = formatNumber(filteredRows.length);
      if (dom.datasetSummaryFilteredCategories) dom.datasetSummaryFilteredCategories.textContent = formatNumber(filteredCategories.size);
      if (dom.datasetSummaryFilteredAdvertisers) dom.datasetSummaryFilteredAdvertisers.textContent = formatNumber(filteredAdvertisers.size);
    }
    function resetDashboardState() {
      state.rawRows = [];
      state.standardizedRows = [];
      state.cleanedRows = [];
      state.preprocessMetadata = null;
      state.pendingWorkbook = null;
      state.pendingWorkbookFileName = '';
      state.pendingWorkbookSelectedSheet = '';
      state.supplemental = {
        dayType: 'weekday'
      };
      state.global = {
        topN: '10',
        start: '',
        end: '',
        channel: [],
        category: [],
        advertisor: [],
        time: 'minutes'
      };
      state.sections = {
        g1: { topN: '10', start: '', end: '', channel: [], category: [], view: 'bar' },
        g2: { topN: '10', start: '', end: '', channel: [], category: [], view: 'bar' },
        g3: { topN: '10', start: '', end: '', channel: [], category: [], view: 'heat' },
        g4: { topN: '10', start: '', end: '', channel: [], category: '', view: 'heat' },
        g5: { start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'heat' },
        g6: { topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' },
        g7: { topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'line' },
        g8: { topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'bar' },
        g9: { topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'cherry' },
        g10: { topN: '10', start: '', end: '', channel: [], category: [], advertisor: [], time: 'minutes', view: 'heat' }
      };
      if (dom.totalRecordsText) dom.totalRecordsText.textContent = '0';
      if (dom.activeDateRangeText) dom.activeDateRangeText.textContent = 'All Dates';
      if (dom.summaryLines) {
        dom.summaryLines.innerHTML = '<div class="summary-line">Upload a CSV or XLSX file to generate dashboard insights.</div>';
      }
      renderDatasetSummary();
      SECTION_KEYS.forEach(sectionKey => {
        const controls = dom.sections[sectionKey];
        if (!controls) return;
        if (controls.topN) controls.topN.value = '10';
        if (controls.start) {
          controls.start.value = '';
          controls.start.min = '';
          controls.start.max = '';
        }
        if (controls.end) {
          controls.end.value = '';
          controls.end.min = '';
          controls.end.max = '';
        }
        if (controls.channel) controls.channel.innerHTML = '';
        if (controls.channelValue) controls.channelValue.textContent = 'All Channels';
        if (controls.channelOptions) controls.channelOptions.innerHTML = '';
        if (controls.channelSearch) controls.channelSearch.value = '';
        if (controls.channelDropdown) controls.channelDropdown.classList.remove('open');
        if (controls.advertisor) controls.advertisor.innerHTML = '';
        if (controls.advertisorValue) controls.advertisorValue.textContent = 'All Advertisers';
        if (controls.advertisorOptions) controls.advertisorOptions.innerHTML = '';
        if (controls.advertisorSearch) controls.advertisorSearch.value = '';
        if (controls.advertisorDropdown) controls.advertisorDropdown.classList.remove('open');
        if (controls.time) controls.time.value = 'minutes';
        if (controls.category) {
          controls.category.innerHTML = '';
        }
        if (controls.categoryValue) controls.categoryValue.textContent = 'All Categories';
        if (controls.categoryOptions) controls.categoryOptions.innerHTML = '';
        if (controls.categorySearch) controls.categorySearch.value = '';
        if (controls.categoryDropdown) controls.categoryDropdown.classList.remove('open');
        if (controls.legend) controls.legend.innerHTML = '';
        if (controls.metric) controls.metric.textContent = '';
        if (controls.totalGrid) controls.totalGrid.innerHTML = '';
        if (controls.insight) {
          controls.insight.classList.remove('visible');
          controls.insight.innerHTML = '';
        }
        if (controls.chart) drawEmpty(controls.chart, 'Upload a file to generate this visualization.');
      });
      if (dom.global.topN) dom.global.topN.value = '10';
      if (dom.global.start) {
        dom.global.start.value = '';
        dom.global.start.min = '';
        dom.global.start.max = '';
      }
      if (dom.global.end) {
        dom.global.end.value = '';
        dom.global.end.min = '';
        dom.global.end.max = '';
      }
      if (dom.global.channel) dom.global.channel.innerHTML = '';
      if (dom.global.channelValue) dom.global.channelValue.textContent = 'All Channels';
      if (dom.global.channelOptions) dom.global.channelOptions.innerHTML = '';
      if (dom.global.channelSearch) dom.global.channelSearch.value = '';
      if (dom.global.channelDropdown) dom.global.channelDropdown.classList.remove('open');
      if (dom.global.advertisor) dom.global.advertisor.innerHTML = '';
      if (dom.global.advertisorValue) dom.global.advertisorValue.textContent = 'All Advertisers';
      if (dom.global.advertisorOptions) dom.global.advertisorOptions.innerHTML = '';
      if (dom.global.advertisorSearch) dom.global.advertisorSearch.value = '';
      if (dom.global.advertisorDropdown) dom.global.advertisorDropdown.classList.remove('open');
      if (dom.global.time) dom.global.time.value = 'minutes';
      if (dom.global.category) dom.global.category.innerHTML = '';
      if (dom.global.categoryValue) dom.global.categoryValue.textContent = 'All Categories';
      if (dom.global.categoryOptions) dom.global.categoryOptions.innerHTML = '';
      if (dom.global.categorySearch) dom.global.categorySearch.value = '';
      if (dom.global.categoryDropdown) dom.global.categoryDropdown.classList.remove('open');
      setDateValidationError('');
      clearWorkbookSelection();
      setUploadSuccessState(false);
      setStatus('Choose a CSV or Excel file to generate the dashboard.', false);
      updateFullButtons();
    }
    function updateStickyFilterPosition() {
      const wrap = dom.stickyFilterWrap;
      const shell = dom.stickyFilterShell;
      const header = dom.headerSection;
      if (!wrap || !shell || !header) return;
      if (document.fullscreenElement) {
        wrap.classList.remove('is-stuck');
        wrap.style.removeProperty('--sticky-filter-height');
        shell.classList.remove('is-stuck');
        shell.style.left = '';
        shell.style.width = '';
        return;
      }
      const headerBottom = header.getBoundingClientRect().bottom;
      const shouldStick = headerBottom <= 10;
      if (shouldStick) {
        const rect = wrap.getBoundingClientRect();
        wrap.classList.add('is-stuck');
        wrap.style.setProperty('--sticky-filter-height', `${shell.offsetHeight}px`);
        shell.classList.add('is-stuck');
        shell.style.left = `${rect.left}px`;
        shell.style.width = `${rect.width}px`;
      } else {
        wrap.classList.remove('is-stuck');
        wrap.style.removeProperty('--sticky-filter-height');
        shell.classList.remove('is-stuck');
        shell.style.left = '';
        shell.style.width = '';
      }
    }
    function syncAndRenderSections(sectionKeys) {
      applyGlobalStateToSections();
      rerenderSections(sectionKeys);
      renderSummary();
      renderHeaderStats();
      updateStickyFilterPosition();
    }
    const DATE_VALIDATION_MESSAGE = 'Start Date cannot be later than End Date.';
    function setDateValidationError(message = '') {
      if (!dom.filterErrorText) return;
      dom.filterErrorText.textContent = message;
      dom.filterErrorText.hidden = !message;
    }
    function refreshDateBounds(controls) {
      if (!controls || !controls.start || !controls.end) return;
      const min = controls.start.dataset.boundMin || '';
      const max = controls.end.dataset.boundMax || '';
      controls.start.min = min;
      controls.end.max = max;
      controls.start.max = controls.end.value || max;
      controls.end.min = controls.start.value || min;
    }
    function rememberValidDateValues(controls) {
      if (!controls || !controls.start || !controls.end) return;
      controls.start.dataset.prevValue = controls.start.value || '';
      controls.end.dataset.prevValue = controls.end.value || '';
    }
    function handleDateRangeChange(controls, changedField) {
      if (!controls || !controls.start || !controls.end) return true;
      refreshDateBounds(controls);
      if (controls.start.value && controls.end.value && controls.start.value > controls.end.value) {
        const input = controls[changedField];
        if (input) input.value = input.dataset.prevValue || '';
        refreshDateBounds(controls);
        setDateValidationError(DATE_VALIDATION_MESSAGE);
        return false;
      }
      rememberValidDateValues(controls);
      setDateValidationError('');
      return true;
    }
    function validateDateRange(startValue, endValue) {
      if (startValue && endValue && startValue > endValue) {
        setDateValidationError(DATE_VALIDATION_MESSAGE);
        return false;
      }
      setDateValidationError('');
      return true;
    }
    function updateMultiDropdownValue(controls, field, selectedValues, allLabel, noun) {
      const selected = selectedValues || [];
      const valueNode = controls && controls[`${field}Value`];
      if (!valueNode) return;
      if (!selected.length) {
        valueNode.textContent = allLabel;
        return;
      }
      valueNode.textContent = selected.length <= 2
        ? selected.join(', ')
        : `${selected.length} ${noun} Selected`;
    }
    function getChannelValues() {
      return uniqueSorted(state.cleanedRows.map(row => row.channel));
    }
    function matchesMultiFilter(value, filterValues) {
      if (Array.isArray(filterValues) && filterValues.length) return filterValues.includes(value);
      if (!Array.isArray(filterValues) && filterValues) return value === filterValues;
      return true;
    }
    function getAdvertisorValues(channelFilter = state.global.channel) {
      return uniqueSorted(
        state.cleanedRows
          .filter(row => matchesMultiFilter(row.channel, channelFilter))
          .map(row => row.product)
      );
    }
    function sanitizeAdvertisorSelection() {
      const valid = new Set(getAdvertisorValues(state.global.channel));
      state.global.advertisor = uniqueSorted((state.global.advertisor || []).filter(value => valid.has(value)));
    }
    function populateMultiSelect(select, values, selectedValues) {
      if (!select) return;
      const selected = new Set(selectedValues || []);
      select.innerHTML = '';
      values.forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        option.selected = selected.has(value);
        select.appendChild(option);
      });
    }
    function populateMultiDropdownOptions(controls, field, values, selectedValues, filterText, onChange, isValid = () => true) {
      const optionsNode = controls && controls[`${field}Options`];
      if (!optionsNode) return;
      const selected = new Set(selectedValues || []);
      const query = String(filterText || '').trim().toLowerCase();
      const filtered = values.filter(value => !query || value.toLowerCase().includes(query));
      optionsNode.innerHTML = '';
      filtered.forEach(value => {
        const label = document.createElement('label');
        label.className = 'multi-dropdown-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = value;
        input.checked = selected.has(value);
        const span = document.createElement('span');
        span.textContent = value;
        label.appendChild(input);
        label.appendChild(span);
        optionsNode.appendChild(label);
        input.addEventListener('change', () => {
          if (!isValid()) {
            input.checked = selected.has(value);
            return;
          }
          const next = new Set(selectedValues || []);
          if (input.checked) next.add(value);
          else next.delete(value);
          onChange([...next]);
        });
      });
    }
    function updateCategoryDropdownValue(controls, selectedValues) {
      updateMultiDropdownValue(controls, 'category', selectedValues, 'All Categories', 'Categories');
    }
    function syncGlobalCategorySelection(selectedValues, options = {}) {
      const controls = dom.global;
      state.global.category = uniqueSorted(selectedValues || []);
      if (controls.categorySearch && !options.preserveSearchText) {
        controls.categorySearch.value = '';
      }
      populateGlobalCategoryDropdown(controls.categorySearch ? controls.categorySearch.value : '');
    }
    function populateCategoryDropdown(sectionKey, filterText = '') {
      const controls = dom.sections[sectionKey];
      if (!controls || !controls.categoryOptions || !controls.category) return;
      const selected = new Set(state.global.category || []);
      const values = getCategoryValues();
      const query = String(filterText || '').trim().toLowerCase();
      const filtered = values.filter(value => !query || value.toLowerCase().includes(query));
      setMultiSelectValues(controls.category, state.global.category || []);
      controls.categoryOptions.innerHTML = '';
      filtered.forEach(value => {
        const label = document.createElement('label');
        label.className = 'multi-dropdown-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = value;
        input.checked = selected.has(value);
        const span = document.createElement('span');
        span.textContent = value;
        label.appendChild(input);
        label.appendChild(span);
        controls.categoryOptions.appendChild(label);
        input.addEventListener('change', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) {
            input.checked = selected.has(value);
            return;
          }
          const next = new Set(state.global.category || []);
          if (input.checked) next.add(input.value);
          else next.delete(input.value);
          syncSharedCategorySelection([...next], sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
        });
      });
      updateCategoryDropdownValue(controls, state.global.category || []);
    }
    function syncSharedCategorySelection(selectedValues, sourceSectionKey, options = {}) {
      state.global.category = uniqueSorted(selectedValues || []);
      setMultiSelectValues(dom.global.category, state.global.category);
      updateCategoryDropdownValue(dom.global, state.global.category);
      populateGlobalCategoryDropdown(dom.global.categorySearch ? dom.global.categorySearch.value : '');
      sharedCategorySections().forEach(sectionKey => {
        const controls = dom.sections[sectionKey];
        if (!controls.category) return;
        if (controls.categorySearch && !options.preserveSearchText && sectionKey === sourceSectionKey) {
          controls.categorySearch.value = '';
        }
        setMultiSelectValues(controls.category, state.global.category);
        populateCategoryDropdown(sectionKey, controls.categorySearch ? controls.categorySearch.value : '');
      });
      applyGlobalStateToSections();
    }
    function populateGlobalCategoryDropdown(filterText = '') {
      const controls = dom.global;
      const select = controls.category;
      const selected = new Set(state.global.category || []);
      const values = getCategoryValues();
      const query = String(filterText || '').trim().toLowerCase();
      const filtered = values.filter(value => !query || value.toLowerCase().includes(query));
      select.innerHTML = '';
      values.forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        option.selected = selected.has(value);
        select.appendChild(option);
      });
      controls.categoryOptions.innerHTML = '';
      filtered.forEach(value => {
        const label = document.createElement('label');
        label.className = 'multi-dropdown-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = value;
        input.checked = selected.has(value);
        const span = document.createElement('span');
        span.textContent = value;
        label.appendChild(input);
        label.appendChild(span);
        controls.categoryOptions.appendChild(label);
        input.addEventListener('change', () => {
          if (!validateDateRange(dom.global.start.value, dom.global.end.value)) {
            input.checked = selected.has(value);
            return;
          }
          const next = new Set(state.global.category || []);
          if (input.checked) next.add(input.value);
          else next.delete(input.value);
          syncGlobalCategorySelection([...next], { preserveSearchText: true });
          syncAndRenderSections(SECTION_KEYS);
        });
      });
      updateCategoryDropdownValue(controls, state.global.category || []);
    }
    function syncGlobalChannelSelection(selectedValues, options = {}) {
      state.global.channel = uniqueSorted(selectedValues || []);
      sanitizeAdvertisorSelection();
      if (dom.global.channelSearch && !options.preserveSearchText) dom.global.channelSearch.value = '';
      populateGlobalChannelDropdown(dom.global.channelSearch ? dom.global.channelSearch.value : '');
      populateGlobalAdvertisorDropdown(dom.global.advertisorSearch ? dom.global.advertisorSearch.value : '');
    }
    function syncSharedChannelSelection(selectedValues, sourceSectionKey, options = {}) {
      syncGlobalChannelSelection(selectedValues, options);
      SECTION_KEYS.forEach(sectionKey => {
        const controls = dom.sections[sectionKey];
        if (!controls.channel) return;
        if (controls.channelSearch && !options.preserveSearchText && sectionKey === sourceSectionKey) {
          controls.channelSearch.value = '';
        }
        setMultiSelectValues(controls.channel, state.global.channel);
        populateChannelDropdown(sectionKey, controls.channelSearch ? controls.channelSearch.value : '');
      });
      if (dom.sections.g5.advertisor) {
        setMultiSelectValues(dom.sections.g5.advertisor, state.global.advertisor);
        populateAdvertisorDropdown('g5', dom.sections.g5.advertisorSearch ? dom.sections.g5.advertisorSearch.value : '');
      }
      applyGlobalStateToSections();
    }
    function populateChannelDropdown(sectionKey, filterText = '') {
      const controls = dom.sections[sectionKey];
      if (!controls || !controls.channel) return;
      const values = getChannelValues();
      populateMultiSelect(controls.channel, values, state.global.channel);
      populateMultiDropdownOptions(controls, 'channel', values, state.global.channel, filterText, next => {
        syncSharedChannelSelection(next, sectionKey, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      }, () => validateDateRange(controls.start.value, controls.end.value));
      updateMultiDropdownValue(controls, 'channel', state.global.channel, 'All Channels', 'Channels');
    }
    function populateGlobalChannelDropdown(filterText = '') {
      const controls = dom.global;
      const values = getChannelValues();
      populateMultiSelect(controls.channel, values, state.global.channel);
      populateMultiDropdownOptions(controls, 'channel', values, state.global.channel, filterText, next => {
        syncGlobalChannelSelection(next, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      }, () => validateDateRange(dom.global.start.value, dom.global.end.value));
      updateMultiDropdownValue(controls, 'channel', state.global.channel, 'All Channels', 'Channels');
    }
    function syncGlobalAdvertisorSelection(selectedValues, options = {}) {
      const valid = new Set(getAdvertisorValues(state.global.channel));
      state.global.advertisor = uniqueSorted((selectedValues || []).filter(value => valid.has(value)));
      if (dom.global.advertisorSearch && !options.preserveSearchText) dom.global.advertisorSearch.value = '';
      populateGlobalAdvertisorDropdown(dom.global.advertisorSearch ? dom.global.advertisorSearch.value : '');
    }
    function syncSharedAdvertisorSelection(selectedValues, sourceSectionKey, options = {}) {
      syncGlobalAdvertisorSelection(selectedValues, options);
      if (dom.sections.g5.advertisor) {
        if (dom.sections.g5.advertisorSearch && !options.preserveSearchText && sourceSectionKey === 'g5') {
          dom.sections.g5.advertisorSearch.value = '';
        }
        setMultiSelectValues(dom.sections.g5.advertisor, state.global.advertisor);
        populateAdvertisorDropdown('g5', dom.sections.g5.advertisorSearch ? dom.sections.g5.advertisorSearch.value : '');
      }
      applyGlobalStateToSections();
    }
    function populateAdvertisorDropdown(sectionKey, filterText = '') {
      const controls = dom.sections[sectionKey];
      if (!controls || !controls.advertisor) return;
      const values = getAdvertisorValues(state.global.channel);
      populateMultiSelect(controls.advertisor, values, state.global.advertisor);
      populateMultiDropdownOptions(controls, 'advertisor', values, state.global.advertisor, filterText, next => {
        syncSharedAdvertisorSelection(next, sectionKey, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      }, () => validateDateRange(controls.start.value, controls.end.value));
      updateMultiDropdownValue(controls, 'advertisor', state.global.advertisor, 'All Advertisers', 'Advertisers');
    }
    function populateGlobalAdvertisorDropdown(filterText = '') {
      const controls = dom.global;
      const values = getAdvertisorValues(state.global.channel);
      populateMultiSelect(controls.advertisor, values, state.global.advertisor);
      populateMultiDropdownOptions(controls, 'advertisor', values, state.global.advertisor, filterText, next => {
        syncGlobalAdvertisorSelection(next, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      }, () => validateDateRange(dom.global.start.value, dom.global.end.value));
      updateMultiDropdownValue(controls, 'advertisor', state.global.advertisor, 'All Advertisers', 'Advertisers');
    }
    function initializeGlobalControls() {
      const rows = state.cleanedRows;
      const dates = uniqueSorted(rows.map(row => row.date));
      dom.global.topN.value = state.global.topN || '10';
      dom.global.time.value = state.global.time || 'minutes';
      dom.global.start.value = dates[0] || '';
      dom.global.end.value = dates[dates.length - 1] || '';
      dom.global.start.dataset.boundMin = dates[0] || '';
      dom.global.start.dataset.boundMax = dates[dates.length - 1] || '';
      dom.global.end.dataset.boundMin = dates[0] || '';
      dom.global.end.dataset.boundMax = dates[dates.length - 1] || '';
      refreshDateBounds(dom.global);
      rememberValidDateValues(dom.global);
      state.global.start = dom.global.start.value;
      state.global.end = dom.global.end.value;
      sanitizeAdvertisorSelection();
      populateGlobalChannelDropdown();
      populateGlobalAdvertisorDropdown();
      populateGlobalCategoryDropdown();
    }
    function syncGlobalState() {
      state.global.topN = dom.global.topN.value;
      state.global.start = dom.global.start.value;
      state.global.end = dom.global.end.value;
      state.global.channel = Array.from(dom.global.channel.selectedOptions).map(option => option.value);
      state.global.category = Array.from(dom.global.category.selectedOptions).map(option => option.value);
      state.global.advertisor = Array.from(dom.global.advertisor.selectedOptions).map(option => option.value);
      state.global.time = dom.global.time.value;
    }
    function setMultiSelectValues(select, values) {
      const selected = new Set(values || []);
      Array.from(select.options).forEach(option => {
        option.selected = selected.has(option.value);
      });
    }
    function applyGlobalStateToSections() {
      SECTION_KEYS.forEach(sectionKey => {
        const controls = dom.sections[sectionKey];
        if (!state.sections[sectionKey]) {
          state.sections[sectionKey] = {
            topN: state.global.topN,
            start: state.global.start,
            end: state.global.end,
            channel: [...state.global.channel],
            category: [...state.global.category],
            advertisor: [...state.global.advertisor],
            time: state.global.time,
            view: ''
          };
        }
        const target = state.sections[sectionKey];
        if (!controls || !target) return;
        if (controls.topN) controls.topN.value = state.global.topN;
        if (controls.start) controls.start.value = state.global.start;
        if (controls.end) controls.end.value = state.global.end;
        if (controls.channel) setMultiSelectValues(controls.channel, state.global.channel);
        if (controls.category) setMultiSelectValues(controls.category, state.global.category);
        if (controls.advertisor) setMultiSelectValues(controls.advertisor, state.global.advertisor);
        if (controls.time) controls.time.value = state.global.time;
        if (controls.channelValue) updateMultiDropdownValue(controls, 'channel', state.global.channel, 'All Channels', 'Channels');
        if (controls.categoryValue) updateCategoryDropdownValue(controls, state.global.category);
        if (controls.advertisorValue) updateMultiDropdownValue(controls, 'advertisor', state.global.advertisor, 'All Advertisers', 'Advertisers');
        if (controls.channelOptions) {
          populateChannelDropdown(sectionKey, controls.channelSearch ? controls.channelSearch.value : '');
        }
        if (sharedCategorySections().includes(sectionKey)) {
          populateCategoryDropdown(sectionKey, controls.categorySearch ? controls.categorySearch.value : '');
        }
        if (controls.advertisorOptions) {
          populateAdvertisorDropdown(sectionKey, controls.advertisorSearch ? controls.advertisorSearch.value : '');
        }
        target.topN = state.global.topN;
        target.start = state.global.start;
        target.end = state.global.end;
        target.channel = [...state.global.channel];
        target.category = [...state.global.category];
        target.advertisor = [...state.global.advertisor];
        target.time = state.global.time;
        if (sectionKey === 'g5') {
          target.advertisor = [...state.global.advertisor];
          target.time = state.global.time;
        }
      });
    }
    function bindGlobalControls() {
      ['topN', 'time'].forEach(key => {
        dom.global[key].addEventListener('change', () => {
          if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
          syncGlobalState();
          syncAndRenderSections(SECTION_KEYS);
        });
      });
      ['start', 'end'].forEach(key => {
        dom.global[key].addEventListener('change', () => {
          if (!handleDateRangeChange(dom.global, key)) return;
          syncGlobalState();
          syncAndRenderSections(SECTION_KEYS);
        });
      });
      dom.global.channelTrigger.addEventListener('click', event => {
        event.preventDefault();
        dom.global.channelDropdown.classList.toggle('open');
        if (dom.global.channelDropdown.classList.contains('open')) dom.global.channelSearch.focus();
      });
      dom.global.channelSearch.addEventListener('input', () => {
        populateGlobalChannelDropdown(dom.global.channelSearch.value);
      });
      dom.global.channelAll.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.channelDropdown.classList.add('open');
        syncGlobalChannelSelection(getChannelValues(), { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.channelClear.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.channelDropdown.classList.add('open');
        syncGlobalChannelSelection([], { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.categoryTrigger.addEventListener('click', event => {
        event.preventDefault();
        dom.global.categoryDropdown.classList.toggle('open');
        if (dom.global.categoryDropdown.classList.contains('open')) {
          dom.global.categorySearch.focus();
        }
      });
      dom.global.categorySearch.addEventListener('input', () => {
        populateGlobalCategoryDropdown(dom.global.categorySearch.value);
      });
      dom.global.categoryAll.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.categoryDropdown.classList.add('open');
        syncGlobalCategorySelection(getCategoryValues(), { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.categoryClear.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.categoryDropdown.classList.add('open');
        syncGlobalCategorySelection([], { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.advertisorTrigger.addEventListener('click', event => {
        event.preventDefault();
        dom.global.advertisorDropdown.classList.toggle('open');
        if (dom.global.advertisorDropdown.classList.contains('open')) dom.global.advertisorSearch.focus();
      });
      dom.global.advertisorSearch.addEventListener('input', () => {
        populateGlobalAdvertisorDropdown(dom.global.advertisorSearch.value);
      });
      dom.global.advertisorAll.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.advertisorDropdown.classList.add('open');
        syncGlobalAdvertisorSelection(getAdvertisorValues(state.global.channel), { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.advertisorClear.addEventListener('click', () => {
        if (!validateDateRange(dom.global.start.value, dom.global.end.value)) return;
        dom.global.advertisorDropdown.classList.add('open');
        syncGlobalAdvertisorSelection([], { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      dom.global.reset.addEventListener('click', () => {
        state.global.topN = '10';
        state.global.channel = [];
        state.global.category = [];
        state.global.advertisor = [];
        state.global.time = 'minutes';
        initializeGlobalControls();
        dom.global.time.value = 'minutes';
        syncGlobalCategorySelection([]);
        syncGlobalChannelSelection([]);
        syncGlobalAdvertisorSelection([]);
        syncGlobalState();
        syncAndRenderSections(SECTION_KEYS);
      });
    }
    function initializeSectionControls(sectionKey) {
      const rows = state.cleanedRows;
      const dates = uniqueSorted(rows.map(row => row.date));
      const section = dom.sections[sectionKey];
      if (section.channel) populateMultiSelect(section.channel, getChannelValues(), state.global.channel);
      if (section.category) populateSelect(section.category, getCategoryValues(), 'All Categories');
      if (sectionKey === 'g5' && section.advertisor) {
        populateMultiSelect(section.advertisor, getAdvertisorValues(state.global.channel), state.global.advertisor);
        section.time.value = 'minutes';
      }
      if (section.start && section.end) {
        section.start.value = dates[0] || '';
        section.end.value = dates[dates.length - 1] || '';
        section.start.dataset.boundMin = dates[0] || '';
        section.start.dataset.boundMax = dates[dates.length - 1] || '';
        section.end.dataset.boundMin = dates[0] || '';
        section.end.dataset.boundMax = dates[dates.length - 1] || '';
        refreshDateBounds(section);
        rememberValidDateValues(section);
      }
    }
    function filterRows(rows, filters = {}, options = {}) {
      return rows.filter(row => {
        if (!matchesMultiFilter(row.channel, filters.channel)) return false;
        if (!matchesMultiFilter(row.category, filters.category)) return false;
        if (filters.start && (!row.date || row.date < filters.start)) return false;
        if (filters.end && (!row.date || row.date > filters.end)) return false;
        if (!matchesMultiFilter(row.product, filters.advertisor)) return false;
        if (options.requireHourlySlot) {
          const hour = parseHourValue(row.adtime);
          if (hour === null || hour < 6) return false;
        }
        return true;
      });
    }
    function getGlobalFilteredRows() {
      return filterRows(state.cleanedRows, {
        start: state.global.start,
        end: state.global.end,
        channel: state.global.channel,
        category: state.global.category,
        advertisor: state.global.advertisor
      });
    }
    function parseDateValue(value) {
      if (!value) return null;
      const date = new Date(`${value}T00:00:00`);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    function isWeekendDateValue(value) {
      const date = parseDateValue(value);
      if (!date) return false;
      const day = date.getDay();
      return day === 0 || day === 6;
    }
    function weekdayWeekendRows(rows, dayType) {
      return rows.filter(row => dayType === 'weekend' ? isWeekendDateValue(row.date) : !isWeekendDateValue(row.date));
    }
    function topBrandSummary(rows) {
      const totals = new Map();
      rows.forEach(row => {
        const key = String(row.product || '').trim() || 'Unknown Brand';
        const bucket = totals.get(key) || { label: key, total: 0, spots: 0 };
        bucket.total += row.aaddur || 0;
        bucket.spots += 1;
        totals.set(key, bucket);
      });
      return [...totals.values()].sort((a, b) => b.total - a.total || b.spots - a.spots || a.label.localeCompare(b.label))[0] || null;
    }
    function topCategorySummary(rows) {
      const totals = new Map();
      rows.forEach(row => {
        const key = String(row.category || '').trim() || 'Unknown Category';
        const bucket = totals.get(key) || { label: key, total: 0, spots: 0 };
        bucket.total += row.aaddur || 0;
        bucket.spots += 1;
        totals.set(key, bucket);
      });
      return [...totals.values()].sort((a, b) => b.total - a.total || b.spots - a.spots || a.label.localeCompare(b.label))[0] || null;
    }
    function topSpotLengthSummary(rows) {
      const totals = new Map();
      rows.forEach(row => {
        const key = `${creativeDurationBucket(row.aaddur)} sec`;
        const bucket = totals.get(key) || { label: key, spots: 0 };
        bucket.spots += 1;
        totals.set(key, bucket);
      });
      return [...totals.values()].sort((a, b) => b.spots - a.spots || a.label.localeCompare(b.label))[0] || null;
    }
    function startOfWeek(date) {
      const result = new Date(date.getTime());
      const day = result.getDay();
      const diff = day === 0 ? -6 : 1 - day;
      result.setDate(result.getDate() + diff);
      result.setHours(0, 0, 0, 0);
      return result;
    }
    function endOfWeek(date) {
      const result = startOfWeek(date);
      result.setDate(result.getDate() + 6);
      return result;
    }
    function latestPeriodRows(rows, period) {
      const datedRows = rows.filter(row => !!parseDateValue(row.date));
      if (!datedRows.length) return { rows: [], label: 'No data available' };
      const latestDate = datedRows.map(row => parseDateValue(row.date)).sort((a, b) => b - a)[0];
      if (!latestDate) return { rows: [], label: 'No data available' };
      let filteredRows = [];
      let label = '';
      if (period === 'day') {
        const target = latestDate.toISOString().slice(0, 10);
        filteredRows = datedRows.filter(row => row.date === target);
        label = formatDate(target);
      } else if (period === 'week') {
        const start = startOfWeek(latestDate);
        const end = endOfWeek(latestDate);
        filteredRows = datedRows.filter(row => {
          const date = parseDateValue(row.date);
          return date && date >= start && date <= end;
        });
        label = `${formatDate(start.toISOString().slice(0, 10))} to ${formatDate(end.toISOString().slice(0, 10))}`;
      } else {
        const year = latestDate.getFullYear();
        const month = latestDate.getMonth();
        filteredRows = datedRows.filter(row => {
          const date = parseDateValue(row.date);
          return date && date.getFullYear() === year && date.getMonth() === month;
        });
        label = latestDate.toLocaleString('en-US', { month: 'long', year: 'numeric' });
      }
      return { rows: filteredRows, label };
    }
    function getSectionRows(sectionKey) {
      const sectionState = state.sections[sectionKey] || {
        start: state.global.start,
        end: state.global.end,
        channel: state.global.channel,
        category: state.global.category,
        advertisor: state.global.advertisor
      };
      return filterRows(state.cleanedRows, {
        start: sectionState.start,
        end: sectionState.end,
        channel: sectionState.channel,
        category: sectionState.category,
        advertisor: sectionKey === 'g5' ? (sectionState.advertisor || state.global.advertisor) : state.global.advertisor
      }, {
        requireHourlySlot: sectionKey === 'g5'
      });
    }
    function aggregateAdvertisors(rows) {
      const map = new Map();
      rows.forEach(row => {
        const key = row.company || 'Unknown';
        const current = map.get(key) || { advertisor: key, total: 0 };
        current.total += row.aaddur;
        map.set(key, current);
      });
      return [...map.values()].sort((a, b) => b.total - a.total || a.advertisor.localeCompare(b.advertisor));
    }
    function buildAdvertisorChannelMatrix(rows, topAdvertisors) {
      const advertisorSet = new Set(topAdvertisors.map(item => item.advertisor));
      const channels = uniqueSorted(rows.filter(r => advertisorSet.has(r.company)).map(r => r.channel));
      const matrix = new Map();
      rows.forEach(row => {
        if (!advertisorSet.has(row.company)) return;
        const bucket = matrix.get(row.company) || Object.fromEntries(channels.map(channel => [channel, 0]));
        bucket[row.channel] += row.aaddur;
        matrix.set(row.company, bucket);
      });
      const sortedAdvertisors = topAdvertisors
        .slice()
        .sort((a, b) => b.total - a.total || a.advertisor.localeCompare(b.advertisor));
      return {
        channels,
        rows: sortedAdvertisors.map(item => ({
          advertisor: item.advertisor,
          total: item.total,
          values: matrix.get(item.advertisor) || Object.fromEntries(channels.map(channel => [channel, 0]))
        }))
      };
    }
    function buildAdvertisorDateMatrix(rows, topAdvertisors) {
      const advertisorSet = new Set(topAdvertisors.map(item => item.advertisor));
      const dates = uniqueSorted(rows.filter(r => advertisorSet.has(r.company)).map(r => r.date));
      const matrix = new Map();
      rows.forEach(row => {
        if (!advertisorSet.has(row.company)) return;
        const bucket = matrix.get(row.date) || Object.fromEntries(topAdvertisors.map(item => [item.advertisor, 0]));
        bucket[row.company] += row.aaddur;
        matrix.set(row.date, bucket);
      });
      return {
        dates,
        rows: dates.map(date => ({
          date,
          values: matrix.get(date) || Object.fromEntries(topAdvertisors.map(item => [item.advertisor, 0]))
        }))
      };
    }
    function buildChannelDistribution(rows) {
      const map = new Map();
      rows.forEach(row => {
        map.set(row.channel, (map.get(row.channel) || 0) + row.aaddur);
      });
      return [...map.entries()]
        .map(([channel, total]) => ({ channel, total }))
        .sort((a, b) => b.total - a.total || a.channel.localeCompare(b.channel));
    }
    function buildHeatmapMatrix(rows, topN) {
      const categoryTotals = new Map();
      rows.forEach(row => {
        categoryTotals.set(row.category, (categoryTotals.get(row.category) || 0) + row.aaddur);
      });
      const categories = [...categoryTotals.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, topN)
        .map(([category]) => category);
      const channels = uniqueSorted(rows.map(row => row.channel));
      const map = new Map();
      rows.forEach(row => {
        if (!categories.includes(row.category)) return;
        const key = `${row.channel}|||${row.category}`;
        map.set(key, (map.get(key) || 0) + row.aaddur);
      });
      let maxValue = 0;
      map.forEach(value => { maxValue = Math.max(maxValue, value); });
      return { channels, categories, map, maxValue: Math.max(maxValue, 1) };
    }
    function buildCategoryDistribution(rows) {
      const map = new Map();
      rows.forEach(row => {
        map.set(row.category, (map.get(row.category) || 0) + row.aaddur);
      });
      return [...map.entries()]
        .map(([category, total]) => ({ category, total }))
        .sort((a, b) => b.total - a.total || a.category.localeCompare(b.category));
    }
    function buildDateTotals(rows) {
      const map = new Map();
      rows.forEach(row => {
        map.set(row.date, (map.get(row.date) || 0) + row.aaddur);
      });
      return [...map.entries()]
        .map(([date, total]) => ({ date, total }))
        .sort((a, b) => a.date.localeCompare(b.date));
    }
    function buildChannelTotals(rows) {
      const map = new Map();
      rows.forEach(row => {
        map.set(row.channel, (map.get(row.channel) || 0) + row.aaddur);
      });
      return [...map.entries()]
        .map(([channel, total]) => ({ channel, total }))
        .sort((a, b) => b.total - a.total || a.channel.localeCompare(b.channel));
    }
    function buildChannelHourlyMatrix(rows) {
      const totals = new Map();
      rows.forEach(row => {
        const hour = parseHourValue(row.adtime);
        if (hour === null || hour < 6) return;
        totals.set(row.channel, (totals.get(row.channel) || 0) + row.aaddur);
      });
      const channels = [...totals.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([channel]) => channel);
      const hours = Array.from({ length: 24 }, (_, i) => i);
      const visibleHours = hours.filter(hour => hour >= 6);
      const map = new Map();
      rows.forEach(row => {
        const hour = parseHourValue(row.adtime);
        if (hour === null || hour < 6 || !channels.includes(row.channel)) return;
        const key = `${row.channel}|||${hour}`;
        map.set(key, (map.get(key) || 0) + row.aaddur);
      });
      let maxValue = 0;
      map.forEach(value => { maxValue = Math.max(maxValue, value); });
      return { channels, hours: visibleHours, map, maxValue: Math.max(maxValue, 1) };
    }
    function getTopNLimit(sectionKey = 'g8', fallback = 10) {
      const sectionState = state.sections[sectionKey] || {};
      return Number.parseInt(sectionState.topN || state.global.topN || String(fallback), 10) || fallback;
    }
    function formatCount(value) {
      return formatNumber(Math.round(value || 0));
    }
    function creativeDurationBucket(value) {
      const duration = Math.max(0, Math.round(value || 0));
      const buckets = [10, 20, 30, 60];
      let best = buckets[0];
      let bestDistance = Math.abs(duration - best);
      buckets.slice(1).forEach(bucket => {
        const distance = Math.abs(duration - bucket);
        if (distance < bestDistance) {
          best = bucket;
          bestDistance = distance;
        }
      });
      return best;
    }
    function buildCreativeDurationDistribution(rows) {
      const buckets = [10, 20, 30, 60].map(seconds => ({
        label: `${seconds} sec`,
        seconds,
        spots: 0
      }));
      rows.forEach(row => {
        const seconds = creativeDurationBucket(row.aaddur);
        const bucket = buckets.find(item => item.seconds === seconds);
        if (bucket) bucket.spots += 1;
      });
      const totalSpots = buckets.reduce((sum, item) => sum + item.spots, 0);
      return buckets.map(item => ({
        ...item,
        share: totalSpots ? (item.spots / totalSpots) * 100 : 0
      }));
    }
    function buildDayWiseActivity(rows) {
      const totals = new Map();
      rows.forEach(row => {
        if (!row.date) return;
        const bucket = totals.get(row.date) || { date: row.date, spots: 0, airtime: 0 };
        bucket.spots += 1;
        bucket.airtime += row.aaddur || 0;
        totals.set(row.date, bucket);
      });
      return [...totals.values()].sort((a, b) => a.date.localeCompare(b.date));
    }
    function buildCategoryVolume(rows, limit) {
      const totals = new Map();
      rows.forEach(row => {
        const key = row.category || 'Unknown';
        const bucket = totals.get(key) || { category: key, spots: 0, airtime: 0 };
        bucket.spots += 1;
        bucket.airtime += row.aaddur || 0;
        totals.set(key, bucket);
      });
      return [...totals.values()]
        .sort((a, b) => b.spots - a.spots || b.airtime - a.airtime || a.category.localeCompare(b.category))
        .slice(0, limit);
    }
    function normalizeProgrammeTypeLabel(value) {
      const normalized = String(value || '').trim();
      if (!normalized) return '';
      const allowed = new Set(['Morning', 'Afternoon', 'Prime Time', 'Late Night', 'Channel Slot', 'Unspecified']);
      return allowed.has(normalized) ? normalized : '';
    }
    function deriveProgrammeType(row) {
      const explicit = normalizeProgrammeTypeLabel(row.programmeType);
      if (explicit) return explicit;
      const hour = parseHourValue(row.adtime);
      if (hour === null) return row.channel ? 'Channel Slot' : 'Unspecified';
      if (hour >= 6 && hour < 12) return 'Morning';
      if (hour >= 12 && hour < 17) return 'Afternoon';
      if (hour >= 17 && hour < 21) return 'Prime Time';
      return 'Late Night';
    }
    function programmeTypeLabel(row) {
      return deriveProgrammeType(row);
    }
    function programmeLabel(row) {
      const explicit = String(row.programme || '').trim();
      if (explicit) return explicit;
      const channel = String(row.channel || '').trim() || 'Unknown Channel';
      const hour = parseHourValue(row.adtime);
      if (hour !== null) return `${channel} • ${hourSlotLabel(hour)}`;
      const derivedType = deriveProgrammeType(row);
      if (derivedType && derivedType !== 'Unspecified') return `${channel} • ${derivedType}`;
      if (row.category) return `${channel} • ${row.category}`;
      return channel;
    }
    function buildProgrammeInsights(rows, limit) {
      const totals = new Map();
      rows.forEach(row => {
        const programme = programmeLabel(row);
        if (!programme) return;
        const bucket = totals.get(programme) || {
          programme,
          type: programmeTypeLabel(row) || 'Unspecified',
          spots: 0,
          airtime: 0,
          advertisers: new Set(),
          categories: new Set()
        };
        bucket.spots += 1;
        bucket.airtime += row.aaddur || 0;
        if (row.company) bucket.advertisers.add(row.company);
        if (row.category) bucket.categories.add(row.category);
        if (!bucket.type || bucket.type === 'Unspecified') bucket.type = programmeTypeLabel(row) || bucket.type;
        totals.set(programme, bucket);
      });
      return [...totals.values()]
        .map(item => ({
          programme: item.programme,
          type: item.type || 'Unspecified',
          spots: item.spots,
          airtime: item.airtime,
          advertiserCount: item.advertisers.size,
          categoryCount: item.categories.size
        }))
        .sort((a, b) => b.airtime - a.airtime || b.spots - a.spots || a.programme.localeCompare(b.programme))
        .slice(0, limit);
    }
    function buildCategoryProgrammeMatrix(rows, limit) {
      const preferredProgrammeOrder = ['Morning', 'Afternoon', 'Prime Time', 'Late Night'];
      const categoryTotals = new Map();
      const typeTotals = new Map();
      const map = new Map();
      rows.forEach(row => {
        const category = String(row.category || '').trim();
        const programmeType = programmeTypeLabel(row);
        if (!category || !programmeType) return;
        categoryTotals.set(category, (categoryTotals.get(category) || 0) + 1);
        typeTotals.set(programmeType, (typeTotals.get(programmeType) || 0) + 1);
        const key = `${category}|||${programmeType}`;
        const bucket = map.get(key) || { spots: 0, airtime: 0 };
        bucket.spots += 1;
        bucket.airtime += row.aaddur || 0;
        map.set(key, bucket);
      });
      const categories = [...categoryTotals.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, limit)
        .map(([category]) => category);
      const programmeTypes = [...typeTotals.entries()]
        .sort((a, b) => {
          const orderA = preferredProgrammeOrder.indexOf(a[0]);
          const orderB = preferredProgrammeOrder.indexOf(b[0]);
          if (orderA !== -1 || orderB !== -1) {
            if (orderA === -1) return 1;
            if (orderB === -1) return -1;
            if (orderA !== orderB) return orderA - orderB;
          }
          return b[1] - a[1] || a[0].localeCompare(b[0]);
        })
        .slice(0, limit)
        .map(([type]) => type);
      let maxSpots = 0;
      categories.forEach(category => {
        programmeTypes.forEach(type => {
          const bucket = map.get(`${category}|||${type}`);
          if (bucket) maxSpots = Math.max(maxSpots, bucket.spots);
        });
      });
      return {
        categories,
        programmeTypes,
        map,
        maxSpots: Math.max(maxSpots, 1)
      };
    }
    function buildAdvertiserShareOfVoiceTrend(rows, limit = 4) {
      const dates = uniqueSorted(rows.map(row => row.date).filter(Boolean));
      const advertiserTotals = new Map();
      const dateTotals = new Map();
      const dateAdvertiserTotals = new Map();
      rows.forEach(row => {
        const date = String(row.date || '').trim();
        const advertiser = String(row.product || '').trim() || 'Unknown Brand';
        const amount = row.aaddur || 0;
        if (!date) return;
        advertiserTotals.set(advertiser, (advertiserTotals.get(advertiser) || 0) + amount);
        dateTotals.set(date, (dateTotals.get(date) || 0) + amount);
        const key = `${date}|||${advertiser}`;
        dateAdvertiserTotals.set(key, (dateAdvertiserTotals.get(key) || 0) + amount);
      });
      const rankedAdvertisers = [...advertiserTotals.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      const normalizedLimit = limit === 'all' ? 'all' : Number(limit || 4);
      const leaders = (normalizedLimit === 'all' ? rankedAdvertisers : rankedAdvertisers.slice(0, normalizedLimit))
        .map(([advertiser]) => advertiser);
      const advertisers = leaders.length ? (normalizedLimit === 'all' ? [...leaders] : [...leaders, 'Others']) : [];
      const points = dates.map(date => {
        const total = dateTotals.get(date) || 0;
        const values = {};
        let leaderTotal = 0;
        leaders.forEach(advertiser => {
          const value = dateAdvertiserTotals.get(`${date}|||${advertiser}`) || 0;
          values[advertiser] = total ? (value / total) * 100 : 0;
          leaderTotal += value;
        });
        if (normalizedLimit !== 'all') {
          values.Others = total ? Math.max(0, ((total - leaderTotal) / total) * 100) : 0;
        }
        return { date, total, values };
      });
      return { dates, advertisers, points };
    }
    function buildChannelEfficiency(rows) {
      const map = new Map();
      rows.forEach(row => {
        const channel = String(row.channel || '').trim();
        if (!channel) return;
        const bucket = map.get(channel) || { channel, spots: 0, total: 0 };
        bucket.spots += 1;
        bucket.total += row.aaddur || 0;
        map.set(channel, bucket);
      });
      return [...map.values()]
        .map(item => ({ ...item, average: item.spots ? item.total / item.spots : 0 }))
        .sort((a, b) => b.total - a.total || b.spots - a.spots || a.channel.localeCompare(b.channel));
    }
    function buildChannelConcentration(rows, limit = 5) {
      const channelMap = new Map();
      rows.forEach(row => {
        const channel = String(row.channel || '').trim();
        const advertiser = String(row.product || '').trim() || 'Unknown Brand';
        if (!channel) return;
        const bucket = channelMap.get(channel) || { total: 0, advertisers: new Map(), uniqueAdvertisers: new Set() };
        const amount = row.aaddur || 0;
        bucket.total += amount;
        bucket.advertisers.set(advertiser, (bucket.advertisers.get(advertiser) || 0) + amount);
        bucket.uniqueAdvertisers.add(advertiser);
        channelMap.set(channel, bucket);
      });
      return [...channelMap.entries()]
        .map(([channel, data]) => {
          const ranked = [...data.advertisers.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
          const topTotal = ranked.slice(0, limit).reduce((sum, [, value]) => sum + value, 0);
          return {
            channel,
            share: data.total ? (topTotal / data.total) * 100 : 0,
            topTotal,
            total: data.total,
            advertiserCount: data.uniqueAdvertisers.size
          };
        })
        .sort((a, b) => b.share - a.share || b.total - a.total || a.channel.localeCompare(b.channel));
    }
    const GRAPH9_TIME_ORDER = ['Morning', 'Afternoon', 'Prime Time', 'Late Night'];
    const GRAPH9_TIME_LABELS = {
      'Morning': 'Morning',
      'Afternoon': 'after noon',
      'Prime Time': 'Prime Time',
      'Late Night': 'Late Night'
    };
    const GRAPH9_TIME_COLORS = {
      'Morning': '#2563eb',
      'Afternoon': '#f59e0b',
      'Prime Time': '#16a34a',
      'Late Night': '#7c3aed'
    };
    const GRAPH11_OTHERS_COLOR = '#94a3b8';
    function graph9TimeKey(type) {
      if (type === 'Morning' || type === 'Afternoon' || type === 'Prime Time' || type === 'Late Night') {
        return type;
      }
      return 'Late Night';
    }
    function graph9TimeLabel(type) {
      return GRAPH9_TIME_LABELS[graph9TimeKey(type)] || String(type || 'Late Night');
    }
    function programmeTypeColor(type) {
      return GRAPH9_TIME_COLORS[graph9TimeKey(type)] || chartPalettes.g9[0];
    }
    function drawAxes(svg, margin, plotW, plotH, xTitle, yTitle, width, height, maxValue) {
      for (let i = 0; i <= 4; i++) {
        const y = margin.top + plotH - (plotH * i / 4);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x: margin.left - 8, y: y + 5, fill: chartLabelColor(), 'font-size': 12, 'text-anchor': 'end' });
        tick.textContent = formatDurationValue(maxValue * i / 4);
        svg.appendChild(tick);
      }
      const xAxisLabel = svgEl('text', {
        x: margin.left + plotW / 2,
        y: height - 6,
        fill: chartLabelColor(),
        'font-size': 15,
        'font-weight': 700,
        'text-anchor': 'middle'
      });
      xAxisLabel.textContent = xTitle;
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 20,
        y: margin.top + plotH / 2,
        fill: chartLabelColor(),
        'font-size': 15,
        'font-weight': 700,
        'text-anchor': 'middle',
        transform: `rotate(-90 20 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = yTitle;
      svg.appendChild(yAxisLabel);
    }
    function renderLegend(container, items) {
      container.innerHTML = items.map(item =>
        `<span class="legend-item chart-label"><i class="legend-swatch" style="background:${item.color}"></i>${item.label}</span>`
      ).join('');
    }
    function formatInsightPercent(value) {
      return `${(value || 0).toFixed(1)}%`;
    }
    function setSectionInsight(sectionKey, text) {
      const node = dom.sections[sectionKey] && dom.sections[sectionKey].insight;
      if (!node) return;
      if (!text) {
        node.classList.remove('visible');
        node.innerHTML = '';
        return;
      }
      node.innerHTML = `<span class="chart-insight-label">💡 Insight:</span>${text}`;
      node.classList.add('visible');
    }
    function buildGraph1Insight(rows) {
      const topAdvertiser = aggregateAdvertisors(rows)[0];
      if (!topAdvertiser) return 'No data is available for the current selection.';
      const total = rows.reduce((sum, row) => sum + row.aaddur, 0) || 1;
      return `${titleCaseName(topAdvertiser.advertisor)} leads the filtered view with ${formatDurationValue(topAdvertiser.total, true)}, contributing ${formatInsightPercent((topAdvertiser.total / total) * 100)} of total ad duration.`;
    }
    function buildGraph2Insight(rows) {
      const topAdvertiser = aggregateAdvertisors(rows)[0];
      const topChannel = buildChannelDistribution(rows)[0];
      if (!topAdvertiser || !topChannel) return 'No data is available for the current selection.';
      return `${titleCaseName(topAdvertiser.advertisor)} is the dominant advertiser, while ${titleCaseName(topChannel.channel)} carries the strongest channel contribution at ${formatDurationValue(topChannel.total, true)}.`;
    }
    function buildGraph3Insight(rows) {
      const dates = buildDateTotals(rows);
      const topAdvertiser = aggregateAdvertisors(rows)[0];
      if (!dates.length || !topAdvertiser) return 'No data is available for the current selection.';
      const peakDay = dates.reduce((best, item) => item.total > best.total ? item : best, dates[0]);
      return `${titleCaseName(topAdvertiser.advertisor)} stays most prominent, with advertising intensity peaking on ${formatDate(peakDay.date)} at ${formatDurationValue(peakDay.total, true)}.`;
    }
    function buildGraph4Insight(rows) {
      const matrix = buildHeatmapMatrix(rows, getTopNLimit('g4'));
      let best = null;
      matrix.categories.forEach(category => {
        matrix.channels.forEach(channel => {
          const value = matrix.map.get(`${channel}|||${category}`) || 0;
          if (!best || value > best.value) best = { channel, category, value };
        });
      });
      if (!best || !best.value) return 'No data is available for the current selection.';
      return `${sentenceCaseName(best.category)} on ${titleCaseName(best.channel)} is the strongest category-channel combination, generating ${formatDurationValue(best.value, true)} in the filtered period.`;
    }
    function buildGraph5Insight(rows) {
      const matrix = buildChannelHourlyMatrix(rows);
      let best = null;
      matrix.channels.forEach(channel => {
        matrix.hours.forEach(hour => {
          const value = matrix.map.get(`${channel}|||${hour}`) || 0;
          if (!best || value > best.value) best = { channel, hour, value };
        });
      });
      if (!best || !best.value) return 'No data is available for the current selection.';
      return `${titleCaseName(best.channel)} delivers the heaviest hourly load during ${hourSlotLabel(best.hour)}, when ad duration reaches ${formatDurationValue(best.value, true)}.`;
    }
    function buildGraph6Insight(rows) {
      const distribution = buildCreativeDurationDistribution(rows).sort((a, b) => b.spots - a.spots);
      const leader = distribution[0];
      if (!leader || !leader.spots) return 'No data is available for the current selection.';
      return `${leader.label} creatives are used most often, accounting for ${formatCount(leader.spots)} advertisement spots and ${formatInsightPercent(leader.share)} of the filtered mix.`;
    }
    function buildGraph7Insight(rows) {
      const points = buildDayWiseActivity(rows);
      if (!points.length) return 'No data is available for the current selection.';
      const highest = points.reduce((best, point) => point.spots > best.spots ? point : best, points[0]);
      const lowest = points.reduce((best, point) => point.spots < best.spots ? point : best, points[0]);
      return `Advertising activity peaked on ${formatDate(highest.date)} with ${formatCount(highest.spots)} spots, while ${formatDate(lowest.date)} recorded the lightest activity at ${formatCount(lowest.spots)} spots.`;
    }
    function buildGraph8Insight(rows) {
      const categories = buildCategoryVolume(rows, getTopNLimit('g8'));
      const leader = categories[0];
      const totalSpots = categories.reduce((sum, item) => sum + item.spots, 0) || 1;
      if (!leader) return 'No data is available for the current selection.';
      return `${sentenceCaseName(leader.category)} is the leading advertising category with ${formatCount(leader.spots)} spots, representing ${formatInsightPercent((leader.spots / totalSpots) * 100)} of the top category set.`;
    }
    function buildGraph9Insight(rows) {
      const programmes = buildProgrammeInsights(rows, getTopNLimit('g9'));
      const leader = programmes[0];
      if (!leader) return 'No data is available for the current selection.';
      return `${leader.programme} attracts the strongest value concentration with ${formatCount(leader.advertiserCount)} advertisers and ${formatDurationValue(leader.airtime, true)} of total airtime.`;
    }
    function buildGraph10Insight(rows) {
      const matrix = buildCategoryProgrammeMatrix(rows, getTopNLimit('g10'));
      let best = null;
      matrix.categories.forEach(category => {
        matrix.programmeTypes.forEach(type => {
          const bucket = matrix.map.get(`${category}|||${type}`);
          const spots = bucket ? bucket.spots : 0;
          if (!best || spots > best.spots) best = { category, type, spots };
        });
      });
      if (!best || !best.spots) return 'No data is available for the current selection.';
      return `${sentenceCaseName(best.category)} shows the strongest programme preference for ${best.type}, where the filtered dataset records the highest interaction at ${formatCount(best.spots)} spots.`;
    }
    function buildGraph11Insight(rows) {
      const trend = buildAdvertiserShareOfVoiceTrend(rows, 4);
      if (trend.points.length < 2 || trend.advertisers.length < 2) return 'No data is available for the current selection.';
      const primary = trend.advertisers[0];
      const first = trend.points[0].values[primary] || 0;
      const last = trend.points[trend.points.length - 1].values[primary] || 0;
      const direction = last > first ? 'gained' : last < first ? 'lost' : 'held';
      return `${titleCaseName(primary)} ${direction} share of voice across the filtered period, moving from ${formatPercent(first)} to ${formatPercent(last)} of daily ad duration.`;
    }
    function buildGraph12Insight(rows) {
      const channels = buildChannelEfficiency(rows);
      const leader = channels[0];
      if (!leader) return 'No data is available for the current selection.';
      return `${titleCaseName(leader.channel)} combines the heaviest total load with ${formatCount(leader.spots)} spots and an average creative duration of ${formatDurationValue(leader.average, true)}.`;
    }
    function buildGraph13Insight(rows) {
      const concentration = buildChannelConcentration(rows, 5);
      const leader = concentration[0];
      if (!leader) return 'No data is available for the current selection.';
      return `${titleCaseName(leader.channel)} is the most concentrated channel, with its top five advertisers accounting for ${formatPercent(leader.share)} of total ad duration.`;
    }
    function buildSectionInsight(sectionKey, rows) {
      if (!rows.length) return 'No data is available for the current selection.';
      if (sectionKey === 'g1') return buildGraph1Insight(rows);
      if (sectionKey === 'g2') return buildGraph2Insight(rows);
      if (sectionKey === 'g3') return buildGraph3Insight(rows);
      if (sectionKey === 'g4') return buildGraph4Insight(rows);
      if (sectionKey === 'g5') return buildGraph5Insight(rows);
      if (sectionKey === 'g6') return buildGraph6Insight(rows);
      if (sectionKey === 'g7') return buildGraph7Insight(rows);
      if (sectionKey === 'g8') return buildGraph8Insight(rows);
      if (sectionKey === 'g9') return buildGraph9Insight(rows);
      if (sectionKey === 'g10') return buildGraph10Insight(rows);
      if (sectionKey === 'g11') return buildGraph11Insight(rows);
      if (sectionKey === 'g12') return buildGraph12Insight(rows);
      if (sectionKey === 'g13') return buildGraph13Insight(rows);
      return '';
    }
    function drawGraph1(rows) {
      applyChartDensity('g1');
      const topAdvertisers = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g1.topN, 10));
      if (!topAdvertisers.length) {
        drawEmpty(dom.sections.g1.chart, 'No data available for selected filters');
        dom.sections.g1.legend.innerHTML = '';
        return;
      }
      resetChartBoxHeight(dom.sections.g1.chart);
      const { svg, width, height } = makeSvg(dom.sections.g1.chart);
      svg.style.fontFamily = '"Segoe UI", Arial, sans-serif';
      const margin = { top: 18, right: 24, bottom: 118, left: 70 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const compact = isTop20Mode('g1');
      const maxValue = withAxisHeadroom(Math.max(...topAdvertisers.map(item => item.total), 1));
      drawAxes(svg, margin, plotW, plotH, 'Top Advertisers', metricLabel(), width, height, maxValue);
      const slotCount = Math.max(Number.parseInt(state.sections.g1.topN, 10) || topAdvertisers.length, 1);
      const groupW = plotW / slotCount;
      const barW = Math.max(groupW - 18, 18);
      topAdvertisers.forEach((item, index) => {
        const x = margin.left + index * groupW + (groupW - barW) / 2;
        const h = (item.total / maxValue) * plotH;
        const y = margin.top + plotH - h;
        svg.appendChild(svgEl('rect', { x, y, width: barW, height: h, rx: 5, fill: chartPalettes.g1[0] }));
        const dataLabel = svgEl('text', {
          x: x + barW / 2,
          y: Math.max(y - 6, margin.top + 10),
          fill: '#1f2937',
          'font-size': compact ? 9.5 : 11,
          'font-weight': 800,
          'text-anchor': 'middle'
        });
        if (!compact) {
          dataLabel.textContent = formatDurationValue(item.total);
          svg.appendChild(dataLabel);
        }
        addWrappedText(svg, item.advertisor, x + barW / 2, margin.top + plotH + 18, compact ? 10 : 12, '#1f2937', compact ? 8.8 : 10, 'middle', 700);
      });
      renderLegend(dom.sections.g1.legend, [{ label: metricLabel(), color: chartPalettes.g1[0] }]);
    }
    function drawGraph2Bar(rows) {
      applyChartDensity('g2');
      if (dom.sections.g2.metric) dom.sections.g2.metric.textContent = '';
      const topAdvertisors = aggregateAdvertisors(rows)
        .slice(0, Number.parseInt(state.sections.g2.topN, 10))
        .sort((a, b) => b.total - a.total || a.advertisor.localeCompare(b.advertisor));
      const matrix = buildAdvertisorChannelMatrix(rows, topAdvertisors);
      if (!matrix.rows.length || !matrix.channels.length) {
        drawEmpty(dom.sections.g2.chart, 'No data available for selected filters');
        dom.sections.g2.legend.innerHTML = '';
        if (dom.sections.g2.metric) dom.sections.g2.metric.textContent = 'No data available';
        return;
      }
      resetChartBoxHeight(dom.sections.g2.chart);
      const { svg, width, height } = makeSvg(dom.sections.g2.chart);
      const margin = { top: 18, right: 24, bottom: 118, left: 58 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const compact = isTop20Mode('g2');
      const maxValue = withAxisHeadroom(Math.max(...matrix.rows.flatMap(row => matrix.channels.map(channel => row.values[channel] || 0)), 1));
      drawAxes(svg, margin, plotW, plotH, advertisorLabel(), metricLabel(), width, height, maxValue);
      const groupW = plotW / Math.max(matrix.rows.length, 1);
      const barW = Math.max((groupW - 14) / Math.max(matrix.channels.length, 1) - 2, 4);
      matrix.rows.forEach((row, gi) => {
        const startX = margin.left + gi * groupW + 7;
        if (gi > 0) {
          const dividerX = margin.left + gi * groupW;
          svg.appendChild(svgEl('line', {
            x1: dividerX,
            y1: margin.top + 2,
            x2: dividerX,
            y2: margin.top + plotH + 28,
            stroke: '#e5e7eb',
            'stroke-width': 1
          }));
        }
        matrix.channels.forEach((channel, ci) => {
          const value = row.values[channel] || 0;
          const h = (value / maxValue) * plotH;
          const x = startX + ci * (barW + 2);
          const y = margin.top + plotH - h;
          svg.appendChild(svgEl('rect', { x, y, width: barW, height: h, rx: 2, fill: channelColor(channel, 'g2') }));
          const dataLabel = svgEl('text', {
            x: x + barW / 2, y: Math.max(y - 6, margin.top + 10),
            fill: '#000000', 'font-size': compact ? 9.5 : 11.5, 'font-weight': 700, 'text-anchor': 'middle'
          });
          if (!compact) {
            dataLabel.textContent = value ? formatDurationValue(value) : '';
            svg.appendChild(dataLabel);
          }
        });
        addWrappedText(
          svg,
          row.advertisor,
          startX + ((matrix.channels.length * (barW + 2)) - 2) / 2,
          margin.top + plotH + 18,
          compact ? 10 : 12,
          '#1f2937',
          compact ? 8.8 : 10.5,
          'middle',
          700
        );
      });
      renderLegend(dom.sections.g2.legend, matrix.channels.map(channel => ({
        label: channel,
        color: channelColor(channel, 'g2')
      })));
    }
    function drawGraph2Pie(rows) {
      applyChartDensity('g2');
      const distribution = buildChannelDistribution(rows);
      if (!distribution.length) {
        drawEmpty(dom.sections.g2.chart, 'No data available for selected filters');
        dom.sections.g2.legend.innerHTML = '';
        if (dom.sections.g2.metric) dom.sections.g2.metric.textContent = '';
        return;
      }
      resetChartBoxHeight(dom.sections.g2.chart);
      const { svg, width, height } = makeSvg(dom.sections.g2.chart);
      const cx = width * 0.44;
      const cy = height * 0.53;
      const radius = Math.min(width, height) * 0.31;
      const innerRadius = radius * 0.42;
      const total = distribution.reduce((sum, item) => sum + item.total, 0) || 1;
      const compact = isTop20Mode('g2');
      if (dom.sections.g2.metric) {
        dom.sections.g2.metric.textContent = `Total advertisement duration: ${formatDurationValue(total, true)}`;
      }
      let startAngle = -Math.PI / 2;
      function polar(r, angle) {
        return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
      }
      distribution.forEach(item => {
        const fraction = item.total / total;
        const endAngle = startAngle + fraction * Math.PI * 2;
        const outerStart = polar(radius, startAngle);
        const outerEnd = polar(radius, endAngle);
        const innerStart = polar(innerRadius, endAngle);
        const innerEnd = polar(innerRadius, startAngle);
        const largeArc = fraction > 0.5 ? 1 : 0;
        const path = [
          `M ${outerStart.x} ${outerStart.y}`,
          `A ${radius} ${radius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
          `L ${innerStart.x} ${innerStart.y}`,
          `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerEnd.x} ${innerEnd.y}`,
          'Z'
        ].join(' ');
        const fill = channelColor(item.channel, 'g2');
        svg.appendChild(svgEl('path', { d: path, fill, stroke: '#ffffff', 'stroke-width': 1.2 }));
        const title = svgEl('title');
        title.textContent = `Channel: ${item.channel}\n${metricLabel()}: ${formatDurationValue(item.total, true)}\nShare: ${(fraction * 100).toFixed(0)}%`;
        svg.lastChild.appendChild(title);
        const mid = startAngle + (endAngle - startAngle) / 2;
        const label = polar(radius + 38, mid);
        addWrappedText(svg, `${item.channel} ${formatDurationValue(item.total, true)} ${(fraction * 100).toFixed(0)}%`, label.x, label.y, compact ? 13 : 16, '#1f2937', compact ? 8.6 : 10, mid > Math.PI / 2 || mid < -Math.PI / 2 ? 'end' : 'start', 700);
        startAngle = endAngle;
      });
      renderLegend(dom.sections.g2.legend, distribution.map(item => ({
        label: item.channel,
        color: channelColor(item.channel, 'g2')
      })));
    }
    function drawGraph3Bar(rows) {
      applyChartDensity('g3');
      const topAdvertisors = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g3.topN, 10));
      const matrix = buildAdvertisorDateMatrix(rows, topAdvertisors);
      if (!matrix.rows.length || !topAdvertisors.length) {
        drawEmpty(dom.sections.g3.chart, 'No data available for selected filters');
        dom.sections.g3.legend.innerHTML = '';
        return;
      }
      const compact = isTop20Mode('g3');
      const dynamicHeight = compact
        ? 620 + Math.max(0, topAdvertisors.length - 10) * 16 + Math.max(0, matrix.rows.length - 7) * 10
        : 540;
      setChartBoxHeight(dom.sections.g3.chart, dynamicHeight);
      const { svg, width, height } = makeSvg(dom.sections.g3.chart);
      const margin = {
        top: 18,
        right: compact ? 34 : 24,
        bottom: compact ? 116 : 86,
        left: compact ? 70 : 58
      };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxValue = withAxisHeadroom(Math.max(...matrix.rows.flatMap(row => topAdvertisors.map(item => row.values[item.advertisor] || 0)), 1));
      drawAxes(svg, margin, plotW, plotH, 'Date', metricLabel(), width, height, maxValue);
      const groupW = plotW / Math.max(matrix.rows.length, 1);
      const barW = Math.max((groupW - 14) / Math.max(topAdvertisors.length, 1) - 2, compact ? 4 : 3);
      for (let gi = 0; gi <= matrix.rows.length; gi++) {
        const x = margin.left + gi * groupW;
        svg.appendChild(svgEl('line', {
          x1: x,
          y1: margin.top,
          x2: x,
          y2: margin.top + plotH,
          stroke: '#e5e7eb',
          'stroke-width': 1
        }));
      }
      matrix.rows.forEach((row, gi) => {
        const startX = margin.left + gi * groupW + 7;
        topAdvertisors.forEach((item, pi) => {
          const value = row.values[item.advertisor] || 0;
          const h = (value / maxValue) * plotH;
          const x = startX + pi * (barW + 2);
          const y = margin.top + plotH - h;
          svg.appendChild(svgEl('rect', {
            x, y, width: barW, height: h, rx: 2,
            fill: chartPalettes.g3[pi % chartPalettes.g3.length],
            stroke: 'rgba(255,255,255,0.18)',
            'stroke-width': 0.8
          }));
          if (value && ((compact && barW >= 8 && h >= 18) || (!compact && barW >= 7 && h >= 14))) {
            const dataLabel = svgEl('text', {
              x: x + barW / 2, y: Math.max(y - 6, margin.top + 10),
              fill: '#000000', 'font-size': compact ? 8.8 : 11.5, 'font-weight': 700, 'text-anchor': 'middle'
            });
            dataLabel.textContent = value ? formatDurationValue(value) : '';
            svg.appendChild(dataLabel);
          }
        });
        addWrappedText(
          svg,
          formatDate(row.date),
          startX + ((topAdvertisors.length * (barW + 2)) - 2) / 2,
          margin.top + plotH + 18,
          compact ? 7 : 10,
          '#1f2937',
          compact ? 8.2 : 10.5,
          'middle',
          700
        );
      });
      renderLegend(dom.sections.g3.legend, topAdvertisors.map((item, idx) => ({
        label: item.advertisor,
        color: chartPalettes.g3[idx % chartPalettes.g3.length]
      })));
    }
    function drawGraph3Heatmap(rows) {
      applyChartDensity('g3');
      const topAdvertisors = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g3.topN, 10));
      const matrix = buildAdvertisorDateMatrix(rows, topAdvertisors);
      if (!matrix.rows.length || !topAdvertisors.length) {
        drawEmpty(dom.sections.g3.chart, 'No data available for selected filters');
        dom.sections.g3.legend.innerHTML = '';
        return;
      }
      const compact = isTop20Mode('g3');
      const dynamicHeight = compact
        ? 700 + Math.max(0, topAdvertisors.length - 10) * 18 + Math.max(0, matrix.rows.length - 7) * 12
        : 220 + topAdvertisors.length * 24;
      setChartBoxHeight(dom.sections.g3.chart, dynamicHeight);
      const { svg, width, height } = makeSvg(dom.sections.g3.chart);
      const margin = {
        top: 24,
        right: compact ? 36 : 28,
        bottom: compact ? 118 : 92,
        left: compact ? 196 : 160
      };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxValue = Math.max(...matrix.rows.flatMap(row => topAdvertisors.map(item => row.values[item.advertisor] || 0)), 1);
      const cellW = plotW / Math.max(matrix.rows.length, 1);
      const cellH = plotH / Math.max(topAdvertisors.length, 1);
      const backgroundFill = '#ffffff';
      const xAxisLabel = svgEl('text', {
        x: margin.left + plotW / 2,
        y: height - 10,
        fill: '#1f2937',
        'font-size': 17,
        'font-weight': 800,
        'text-anchor': 'middle'
      });
      xAxisLabel.textContent = 'Date';
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 28,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 17,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 28 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = 'Advertiser';
      svg.appendChild(yAxisLabel);
      for (let gi = 0; gi <= matrix.rows.length; gi++) {
        const x = margin.left + gi * cellW;
        svg.appendChild(svgEl('line', {
          x1: x,
          y1: margin.top,
          x2: x,
          y2: margin.top + plotH,
          stroke: '#e5e7eb',
          'stroke-width': 1
        }));
      }
      for (let ri = 0; ri <= topAdvertisors.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', {
          x1: margin.left,
          y1: y,
          x2: margin.left + plotW,
          y2: y,
          stroke: '#e5e7eb',
          'stroke-width': 1
        }));
      }
      const dateLabelSize = compact ? 8.2 : (topAdvertisors.length >= 20 ? 8.8 : 10.5);
      matrix.rows.forEach((row, ci) => {
        addWrappedText(svg, formatDate(row.date), margin.left + ci * cellW + cellW / 2, margin.top + plotH + 18, compact ? 8 : 10, '#1f2937', dateLabelSize, 'middle', 700);
      });
      topAdvertisors.forEach((item, ri) => {
        addWrappedText(svg, item.advertisor, margin.left - 10, margin.top + ri * cellH + cellH * 0.56, compact ? 14 : 16, '#1f2937', compact ? 8.8 : 11, 'end', 700);
      });
      topAdvertisors.forEach((item, ri) => {
        matrix.rows.forEach((row, ci) => {
          const value = row.values[item.advertisor] || 0;
          const x = margin.left + ci * cellW;
          const y = margin.top + ri * cellH;
          const rect = svgEl('rect', {
            x: x + 1.5,
            y: y + 1.5,
            width: Math.max(cellW - 3, 2),
            height: Math.max(cellH - 3, 2),
            rx: 3,
            fill: value ? colorForValue(value, maxValue) : backgroundFill,
            stroke: value ? '#e5e7eb' : '#ffffff',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = `Advertiser: ${item.advertisor}\nDate: ${formatDate(row.date)}\n${metricLabel()}: ${formatDurationValue(value, true)}\nChannel: ${multiFilterLabel(state.global.channel, 'All')}\nCategory: ${(state.global.category || []).length ? state.global.category.join(', ') : 'All'}`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (value && ((compact && cellW >= 38 && cellH >= 22) || (!compact && cellW >= 52 && cellH >= 28))) {
            const label = svgEl('text', {
              x: x + cellW / 2,
              y: y + cellH * 0.58,
              fill: '#000000',
              'font-size': compact ? 8.5 : 11,
              'font-weight': 700,
              'text-anchor': 'middle'
            });
            label.textContent = formatDurationValue(value);
            svg.appendChild(label);
          }
        });
      });
      renderLegend(dom.sections.g3.legend, [
        { label: 'Low Duration', color: chartPalettes.heat[1] },
        { label: 'High Duration', color: chartPalettes.heat[4] }
      ]);
    }
    function drawGraph4(rows) {
      applyChartDensity('g4');
      const matrix = buildHeatmapMatrix(rows, Number.parseInt(state.sections.g4.topN, 10));
      if (!matrix.channels.length || !matrix.categories.length) {
        drawEmpty(dom.sections.g4.chart, 'No data available for selected filters');
        return;
      }
      const compact = isTop20Mode('g4');
      const dynamicHeight = compact
        ? 700 + Math.max(0, matrix.categories.length - 10) * 18 + Math.max(0, matrix.channels.length - 5) * 10
        : 340 + matrix.categories.length * 28 + Math.max(0, matrix.channels.length - 5) * 8;
      setChartBoxHeight(dom.sections.g4.chart, dynamicHeight);
      dom.sections.g4.chart.style.overflowX = 'auto';
      const box = dom.sections.g4.chart;
      const clientWidth = Math.max(box.clientWidth || 900, 320);
      const width = Math.max(clientWidth, (compact ? 280 : 240) + matrix.channels.length * (compact ? 112 : 96));
      const height = Math.max(box.clientHeight || dynamicHeight, dynamicHeight);
      box.innerHTML = '';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.setAttribute('class', 'chart');
      box.appendChild(svg);
      const margin = {
        top: 24,
        right: compact ? 36 : 28,
        bottom: compact ? 122 : 96,
        left: compact ? 196 : 168
      };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const cellW = plotW / Math.max(matrix.channels.length, 1);
      const cellH = plotH / Math.max(matrix.categories.length, 1);
      const backgroundFill = '#ffffff';
      svg.appendChild(svgEl('rect', {
        x: margin.left, y: margin.top, width: plotW, height: plotH, rx: 12,
        fill: 'rgba(255,255,255,0.02)', stroke: 'rgba(255,255,255,0.08)'
      }));
      const xAxisLabel = svgEl('text', {
        x: margin.left + plotW / 2, y: height - 10, fill: '#1f2937',
        'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle'
      });
      xAxisLabel.textContent = 'Channel';
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 28, y: margin.top + plotH / 2, fill: '#1f2937',
        'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle',
        transform: `rotate(-90 28 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = 'Category';
      svg.appendChild(yAxisLabel);
      for (let ci = 0; ci <= matrix.channels.length; ci++) {
        const x = margin.left + ci * cellW;
        svg.appendChild(svgEl('line', {
          x1: x, y1: margin.top, x2: x, y2: margin.top + plotH,
          stroke: '#e5e7eb', 'stroke-width': 1
        }));
      }
      for (let ri = 0; ri <= matrix.categories.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', {
          x1: margin.left, y1: y, x2: margin.left + plotW, y2: y,
          stroke: '#e5e7eb', 'stroke-width': 1
        }));
      }
      matrix.channels.forEach((channel, ci) => {
        addWrappedText(
          svg,
          channel,
          margin.left + ci * cellW + cellW / 2,
          margin.top + plotH + 18,
          compact ? 8 : 10,
          '#1f2937',
          compact ? 8.6 : 10.8,
          'middle',
          700
        );
      });
      matrix.categories.forEach((category, ri) => {
        addWrappedText(
          svg,
          category,
          margin.left - 10,
          margin.top + ri * cellH + cellH * 0.56,
          compact ? 14 : 18,
          '#1f2937',
          compact ? 8.8 : 10.8,
          'end',
          700
        );
      });
      matrix.categories.forEach((category, ri) => {
        matrix.channels.forEach((channel, ci) => {
          const x = margin.left + ci * cellW;
          const y = margin.top + ri * cellH;
          const value = matrix.map.get(`${channel}|||${category}`);
          const hasValue = typeof value === 'number' && value > 0;
          const rect = svgEl('rect', {
            x: x + 1.5,
            y: y + 1.5,
            width: Math.max(cellW - 3, 2),
            height: Math.max(cellH - 3, 2),
            rx: 3,
            fill: hasValue ? graph4HeatColor(value, matrix.maxValue) : backgroundFill,
            stroke: hasValue ? '#e5e7eb' : '#ffffff',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = hasValue
            ? `Channel: ${channel}\nCategory: ${category}\n${metricLabel()}: ${formatDurationValue(value, true)}`
            : `Channel: ${channel}\nCategory: ${category}\nNo data available`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (hasValue && ((compact && cellW >= 44 && cellH >= 24) || (!compact && cellW >= 52 && cellH >= 28))) {
            const label = svgEl('text', {
              x: x + cellW / 2, y: y + cellH * 0.58,
              fill: '#1f2937', 'font-size': compact ? 8.8 : 11, 'font-weight': 800, 'text-anchor': 'middle'
            });
            label.textContent = formatDurationValue(value);
            svg.appendChild(label);
          }
        });
      });
    }
    function drawGraph5(rows) {
      const matrix = buildChannelHourlyMatrix(rows);
      const unitMeta = graph5UnitMeta();
      if (!matrix.channels.length) {
        drawEmpty(dom.sections.g5.chart, 'No data available for the selected filters.');
        if (dom.sections.g5.totalGrid) dom.sections.g5.totalGrid.innerHTML = '<div class="empty">No data available</div>';
        return;
      }
      resetChartBoxHeight(dom.sections.g5.chart);
      const { svg, width, height } = makeSvg(dom.sections.g5.chart);
      const margin = { top: 28, right: 28, bottom: 78, left: 140 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const cellW = plotW / Math.max(matrix.hours.length, 1);
      const cellH = plotH / Math.max(matrix.channels.length, 1);
      const xAxisLabel = svgEl('text', { x: margin.left + plotW / 2, y: height - 8, fill: '#1f2937', 'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle' });
      xAxisLabel.textContent = 'Hour of Day';
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 24, y: margin.top + plotH / 2, fill: '#1f2937',
        'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle',
        transform: `rotate(-90 24 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = 'Channel';
      svg.appendChild(yAxisLabel);
      matrix.hours.forEach((hour, ci) => {
        addWrappedText(svg, hourLabel(hour), margin.left + ci * cellW + cellW / 2, margin.top + plotH + 18, 5, '#6b7280', 10.5, 'middle', 700);
      });
      matrix.channels.forEach((channel, ri) => {
        addWrappedText(svg, channel, margin.left - 10, margin.top + ri * cellH + cellH * 0.56, 14, '#1f2937', 11, 'end', 700);
      });
      for (let ci = 0; ci <= matrix.hours.length; ci++) {
        const x = margin.left + ci * cellW;
        svg.appendChild(svgEl('line', {
          x1: x, y1: margin.top, x2: x, y2: margin.top + plotH,
          stroke: '#e5e7eb', 'stroke-width': 1
        }));
      }
      for (let ri = 0; ri <= matrix.channels.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', {
          x1: margin.left, y1: y, x2: margin.left + plotW, y2: y,
          stroke: '#e5e7eb', 'stroke-width': 1
        }));
      }
      matrix.channels.forEach((channel, ri) => {
        matrix.hours.forEach((hour, ci) => {
          const x = margin.left + ci * cellW;
          const y = margin.top + ri * cellH;
          const value = matrix.map.get(`${channel}|||${hour}`) || 0;
          const displayValue = unitMeta.convert(value);
          const rect = svgEl('rect', {
            x: x + 1.5,
            y: y + 1.5,
            width: Math.max(cellW - 3, 2),
            height: Math.max(cellH - 3, 2),
            rx: 3,
            fill: channelHeatColor(channel, value, matrix.maxValue),
            stroke: '#e5e7eb',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = `Channel: ${channel}\nTime Slot: ${hourSlotLabel(hour)}\nAD Duration: ${unitMeta.format(displayValue)}`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (value && cellW >= 28 && cellH >= 22) {
            const label = svgEl('text', {
              x: x + cellW / 2, y: y + cellH * 0.58,
              fill: '#000000', 'font-size': 11.5, 'font-weight': 800, 'text-anchor': 'middle'
            });
            label.textContent = unitMeta.unit === 'minutes'
              ? displayValue.toFixed(1)
              : formatNumber(displayValue);
            svg.appendChild(label);
          }
        });
      });
      const channelTotals = matrix.channels.map(channel => {
        let total = 0;
        matrix.hours.forEach(hour => {
          total += matrix.map.get(`${channel}|||${hour}`) || 0;
        });
        const displayValue = unitMeta.convert(total);
        return { channel, displayValue };
      });
      dom.sections.g5.totalGrid.innerHTML = channelTotals.map(item => `
        <div class="total-chip">
          <div class="total-chip-label">${item.channel}</div>
          <div class="total-chip-value">${unitMeta.unit === 'minutes' ? item.displayValue.toFixed(1) + ' min' : formatNumber(Math.round(item.displayValue)) + ' sec'}</div>
        </div>
      `).join('');
    }
    function drawGraph6Donut(rows) {
      const distribution = buildCreativeDurationDistribution(rows);
      const totalSpots = distribution.reduce((sum, item) => sum + item.spots, 0);
      if (!totalSpots) {
        drawEmpty(dom.sections.g6.chart, 'No data available for selected filters');
        dom.sections.g6.legend.innerHTML = '';
        if (dom.sections.g6.metric) dom.sections.g6.metric.textContent = '';
        return;
      }
      resetChartBoxHeight(dom.sections.g6.chart);
      const { svg, width, height } = makeSvg(dom.sections.g6.chart);
      const cx = width * 0.38;
      const cy = height * 0.52;
      const radius = Math.min(width, height) * 0.26;
      const innerRadius = radius * 0.52;
      let startAngle = -Math.PI / 2;
      function polar(r, angle) {
        return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
      }
      distribution.forEach((item, index) => {
        const fraction = item.spots / totalSpots;
        const endAngle = startAngle + fraction * Math.PI * 2;
        const outerStart = polar(radius, startAngle);
        const outerEnd = polar(radius, endAngle);
        const innerStart = polar(innerRadius, endAngle);
        const innerEnd = polar(innerRadius, startAngle);
        const largeArc = fraction > 0.5 ? 1 : 0;
        const path = [
          `M ${outerStart.x} ${outerStart.y}`,
          `A ${radius} ${radius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
          `L ${innerStart.x} ${innerStart.y}`,
          `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerEnd.x} ${innerEnd.y}`,
          'Z'
        ].join(' ');
        const segment = svgEl('path', {
          d: path,
          fill: chartPalettes.g6[index % chartPalettes.g6.length],
          stroke: '#ffffff',
          'stroke-width': 1.5
        });
        const title = svgEl('title');
        title.textContent = `${item.label}\nTotal Spots: ${formatCount(item.spots)}\nShare: ${item.share.toFixed(1)}%`;
        segment.appendChild(title);
        svg.appendChild(segment);
        const mid = startAngle + (endAngle - startAngle) / 2;
        const labelPoint = polar(radius + 34, mid);
        addWrappedText(
          svg,
          `${item.label} ${item.share.toFixed(1)}%`,
          labelPoint.x,
          labelPoint.y,
          14,
          '#1f2937',
          9.5,
          mid > Math.PI / 2 || mid < -Math.PI / 2 ? 'end' : 'start',
          800
        );
        startAngle = endAngle;
      });
      const totalLabel = svgEl('text', {
        x: cx,
        y: cy - 8,
        fill: '#1f2937',
        'font-size': 24,
        'font-weight': 800,
        'text-anchor': 'middle'
      });
      totalLabel.textContent = formatCount(totalSpots);
      svg.appendChild(totalLabel);
      const totalSubLabel = svgEl('text', {
        x: cx,
        y: cy + 18,
        fill: '#6b7280',
        'font-size': 13,
        'font-weight': 700,
        'text-anchor': 'middle'
      });
      totalSubLabel.textContent = 'Total Spots';
      svg.appendChild(totalSubLabel);
      if (dom.sections.g6.metric) {
        const leader = distribution.slice().sort((a, b) => b.spots - a.spots)[0];
        dom.sections.g6.metric.textContent = `Most used creative: ${leader.label} • ${formatCount(leader.spots)} spots • ${leader.share.toFixed(1)}% share`;
      }
      renderLegend(dom.sections.g6.legend, distribution.map((item, index) => ({
        label: `${item.label} (${formatCount(item.spots)})`,
        color: chartPalettes.g6[index % chartPalettes.g6.length]
      })));
    }
    function drawGraph6Bar(rows) {
      const distribution = buildCreativeDurationDistribution(rows);
      const totalSpots = distribution.reduce((sum, item) => sum + item.spots, 0);
      if (!totalSpots) {
        drawEmpty(dom.sections.g6.chart, 'No data available for selected filters');
        dom.sections.g6.legend.innerHTML = '';
        if (dom.sections.g6.metric) dom.sections.g6.metric.textContent = '';
        return;
      }
      setChartBoxHeight(dom.sections.g6.chart, 500);
      const { svg, width, height } = makeSvg(dom.sections.g6.chart);
      const barGradient = appendLinearGradient(
        svg,
        'g6BarGradient',
        themeVar('--brand', '#2563eb'),
        themeVar('--teal', '#0f766e')
      );
      const margin = { top: 26, right: 104, bottom: 48, left: 152 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxSpots = Math.max(...distribution.map(item => item.spots), 1);
      for (let i = 0; i <= 4; i++) {
        const x = margin.left + (plotW * i / 4);
        svg.appendChild(svgEl('line', { x1: x, y1: margin.top, x2: x, y2: margin.top + plotH, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x, y: margin.top + plotH + 22, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'middle' });
        tick.textContent = formatCount((maxSpots * i) / 4);
        svg.appendChild(tick);
      }
      distribution.forEach((item, index) => {
        const rowHeight = plotH / distribution.length;
        const barHeight = Math.max(rowHeight - 16, 24);
        const y = margin.top + index * rowHeight + (rowHeight - barHeight) / 2;
        const widthValue = (item.spots / maxSpots) * plotW;
        const bar = svgEl('rect', {
          x: margin.left,
          y,
          width: Math.max(widthValue, item.spots ? 4 : 0),
          height: barHeight,
          rx: 8,
          fill: barGradient
        });
        const title = svgEl('title');
        title.textContent = `${item.label}\nTotal Spots: ${formatCount(item.spots)}\nShare: ${item.share.toFixed(1)}%`;
        bar.appendChild(title);
        svg.appendChild(bar);
        addWrappedText(svg, item.label, margin.left - 14, y + barHeight * 0.58, 14, '#1f2937', 10.6, 'end', 800);
        const valueLabel = svgEl('text', {
          x: Math.min(margin.left + widthValue + 10, width - margin.right + 18),
          y: y + barHeight * 0.6,
          fill: '#1f2937',
          'font-size': 11.5,
          'font-weight': 800,
          'text-anchor': 'start'
        });
        valueLabel.textContent = `${formatCount(item.spots)} (${item.share.toFixed(1)}%)`;
        svg.appendChild(valueLabel);
      });
      const xAxisTitle = svgEl('text', {
        x: margin.left + plotW / 2,
        y: height - 10,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle'
      });
      xAxisTitle.textContent = 'Number of Advertisement Spots';
      svg.appendChild(xAxisTitle);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Creative Duration (Seconds)';
      svg.appendChild(yAxisTitle);
      if (dom.sections.g6.metric) {
        dom.sections.g6.metric.textContent = `Creative duration mix across ${formatCount(totalSpots)} filtered ad spots`;
      }
      renderLegend(dom.sections.g6.legend, distribution.map((item, index) => ({
        label: item.label,
        color: chartPalettes.g6[index % chartPalettes.g6.length]
      })));
    }
    function drawGraph7(rows) {
      const points = buildDayWiseActivity(rows);
      if (!points.length) {
        drawEmpty(dom.sections.g7.chart, 'No data available for selected filters');
        return;
      }
      setChartBoxHeight(dom.sections.g7.chart, 500);
      const { svg, width, height } = makeSvg(dom.sections.g7.chart);
      const margin = { top: 28, right: 34, bottom: 98, left: 76 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxSpots = withAxisHeadroom(Math.max(...points.map(point => point.spots), 1));
      for (let i = 0; i <= 4; i++) {
        const y = margin.top + plotH - (plotH * i / 4);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x: margin.left - 8, y: y + 5, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'end' });
        tick.textContent = formatCount((maxSpots * i) / 4);
        svg.appendChild(tick);
      }
      const pathPoints = points.map((point, index) => {
        const x = points.length === 1
          ? margin.left + (plotW / 2)
          : margin.left + (plotW * index / Math.max(points.length - 1, 1));
        const y = margin.top + plotH - ((point.spots / maxSpots) * plotH);
        return { ...point, x, y };
      });
      const areaPath = pathPoints.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ')
        + ` L ${pathPoints[pathPoints.length - 1].x} ${margin.top + plotH}`
        + ` L ${pathPoints[0].x} ${margin.top + plotH} Z`;
      svg.appendChild(svgEl('path', { d: areaPath, fill: 'rgba(37, 99, 235, 0.12)' }));
      const linePath = pathPoints.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
      svg.appendChild(svgEl('path', {
        d: linePath,
        fill: 'none',
        stroke: chartPalettes.g7,
        'stroke-width': 3.5,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round'
      }));
      const highest = pathPoints.reduce((best, point) => point.spots > best.spots ? point : best, pathPoints[0]);
      const lowest = pathPoints.reduce((best, point) => point.spots < best.spots ? point : best, pathPoints[0]);
      pathPoints.forEach(point => {
        const isExtreme = point === highest || point === lowest;
        const circle = svgEl('circle', {
          cx: point.x,
          cy: point.y,
          r: isExtreme ? 6 : 4.5,
          fill: isExtreme ? '#ffffff' : chartPalettes.g7,
          stroke: isExtreme ? '#ef4444' : '#1d4ed8',
          'stroke-width': isExtreme ? 3 : 2
        });
        const title = svgEl('title');
        title.textContent = `Date: ${formatDate(point.date)}\nAd Spots: ${formatCount(point.spots)}\nAirtime: ${formatDurationValue(point.airtime, true)}`;
        circle.appendChild(title);
        svg.appendChild(circle);
        addWrappedText(
          svg,
          formatCount(point.spots),
          point.x,
          Math.max(point.y - (isExtreme ? 16 : 12), margin.top + 10),
          18,
          '#1f2937',
          9.5,
          'middle',
          800
        );
      });
      addWrappedText(svg, 'Date', margin.left + plotW / 2, height - 12, 20, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Number of Ad Spots';
      svg.appendChild(yAxisTitle);
      pathPoints.forEach((point, index) => {
        if (points.length > 12 && index % 2 === 1) return;
        addWrappedText(svg, formatDate(point.date), point.x, margin.top + plotH + 20, 10, '#1f2937', 9.2, 'middle', 700);
      });
    }
    function drawGraph8(rows) {
      const categories = buildCategoryVolume(rows, getTopNLimit('g8'));
      if (!categories.length) {
        drawEmpty(dom.sections.g8.chart, 'No data available for selected filters');
        dom.sections.g8.legend.innerHTML = '';
        return;
      }
      const compact = getTopNLimit('g8') >= 20;
      setChartBoxHeight(dom.sections.g8.chart, compact ? 620 : 500);
      const { svg, width, height } = makeSvg(dom.sections.g8.chart);
      const barGradient = appendLinearGradient(
        svg,
        'g8BarGradient',
        themeVar('--brand', '#2563eb'),
        themeVar('--teal', '#0f766e')
      );
      const margin = { top: 28, right: 28, bottom: compact ? 132 : 110, left: 78 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxSpots = withAxisHeadroom(Math.max(...categories.map(item => item.spots), 1));
      for (let i = 0; i <= 4; i++) {
        const y = margin.top + plotH - (plotH * i / 4);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x: margin.left - 10, y: y + 5, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'end' });
        tick.textContent = formatCount((maxSpots * i) / 4);
        svg.appendChild(tick);
      }
      const groupW = plotW / Math.max(categories.length, 1);
      const barW = Math.max(groupW - 18, compact ? 18 : 26);
      categories.forEach((item, index) => {
        const x = margin.left + index * groupW + (groupW - barW) / 2;
        const barHeight = (item.spots / maxSpots) * plotH;
        const y = margin.top + plotH - barHeight;
        const bar = svgEl('rect', {
          x,
          y,
          width: barW,
          height: barHeight,
          rx: 6,
          fill: barGradient
        });
        const title = svgEl('title');
        title.textContent = `Category: ${item.category}\nTotal Spots: ${formatCount(item.spots)}\nAirtime: ${formatDurationValue(item.airtime, true)}`;
        bar.appendChild(title);
        svg.appendChild(bar);
        const valueLabel = svgEl('text', {
          x: x + barW / 2,
          y: Math.max(y - 8, margin.top + 12),
          fill: '#1f2937',
          'font-size': compact ? 9.5 : 11.5,
          'font-weight': 800,
          'text-anchor': 'middle'
        });
        valueLabel.textContent = formatCount(item.spots);
        svg.appendChild(valueLabel);
        addWrappedText(svg, item.category, x + barW / 2, margin.top + plotH + 18, compact ? 10 : 12, '#1f2937', compact ? 8.8 : 10.2, 'middle', 700);
      });
      addWrappedText(svg, 'Advertiser Categories', margin.left + plotW / 2, height - 10, 24, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Number of Ad Spots';
      svg.appendChild(yAxisTitle);
      renderLegend(dom.sections.g8.legend, [{
        label: 'Advertisement Spots',
        color: themeVar('--brand', '#2563eb')
      }]);
    }
    function drawGraph9(rows) {
      const programmes = buildProgrammeInsights(rows, getTopNLimit('g9'));
      if (!programmes.length) {
        drawEmpty(dom.sections.g9.chart, 'No programme data available for the selected filters');
        dom.sections.g9.legend.innerHTML = '';
        return;
      }
      const compact = programmes.length >= 15;
      setChartBoxHeight(dom.sections.g9.chart, compact ? 620 : 520);
      const { svg, width, height } = makeSvg(dom.sections.g9.chart);
      const margin = { top: 32, right: 34, bottom: compact ? 126 : 112, left: 72 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxAirtime = withAxisHeadroom(Math.max(...programmes.map(item => item.airtime), 1));
      for (let i = 0; i <= 4; i++) {
        const y = margin.top + plotH - (plotH * i / 4);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const yTick = svgEl('text', { x: margin.left - 8, y: y + 5, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'end' });
        yTick.textContent = formatDurationValue((maxAirtime * i) / 4);
        svg.appendChild(yTick);
      }
      const slotCount = Math.max(programmes.length, 1);
      const groupW = plotW / slotCount;
      const stemStroke = 3;
      programmes.forEach((item, index) => {
        const x = margin.left + index * groupW + groupW / 2;
        const y = margin.top + plotH - ((item.airtime / maxAirtime) * plotH);
        const radius = compact ? 11 : 12.5;
        const fill = programmeTypeColor(item.type);
        const stem = svgEl('line', {
          x1: x,
          y1: margin.top + plotH,
          x2: x,
          y2: y,
          stroke: fill,
          'stroke-width': stemStroke,
          'stroke-linecap': 'round'
        });
        const cherry = svgEl('circle', {
          cx: x,
          cy: y,
          r: radius,
          fill,
          stroke: '#ffffff',
          'stroke-width': 2.2
        });
        const title = svgEl('title');
        title.textContent = `Programme: ${item.programme}\nTime Category: ${graph9TimeLabel(item.type)}\nAdvertisers: ${formatCount(item.advertiserCount)}\nCategories: ${formatCount(item.categoryCount)}\nTotal Airtime: ${formatDurationValue(item.airtime, true)}\nTotal Spots: ${formatCount(item.spots)}`;
        cherry.appendChild(title);
        svg.appendChild(stem);
        svg.appendChild(cherry);
        const valueLabel = svgEl('text', {
          x,
          y: Math.max(y - 14, margin.top + 12),
          fill: '#1f2937',
          'font-size': compact ? 9.5 : 10.5,
          'font-weight': 800,
          'text-anchor': 'middle'
        });
        valueLabel.textContent = formatDurationValue(item.airtime);
        svg.appendChild(valueLabel);
        addWrappedText(svg, item.programme, x, margin.top + plotH + 18, compact ? 8 : 10, '#1f2937', compact ? 8.6 : 9.4, 'middle', 700);
      });
      addWrappedText(svg, 'Programme', margin.left + plotW / 2, height - 10, 20, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Total Airtime';
      svg.appendChild(yAxisTitle);
      renderLegend(dom.sections.g9.legend, GRAPH9_TIME_ORDER.map(type => ({
        label: graph9TimeLabel(type),
        color: programmeTypeColor(type)
      })));
    }
    function drawGraph10(rows) {
      const matrix = buildCategoryProgrammeMatrix(rows, getTopNLimit('g10'));
      if (!matrix.categories.length || !matrix.programmeTypes.length) {
        drawEmpty(dom.sections.g10.chart, 'No programme type data available for the selected filters');
        return;
      }
      const compact = matrix.categories.length >= 12 || matrix.programmeTypes.length >= 12;
      const dynamicHeight = compact
        ? 680 + Math.max(0, matrix.categories.length - 10) * 18
        : 360 + matrix.categories.length * 28;
      setChartBoxHeight(dom.sections.g10.chart, dynamicHeight);
      dom.sections.g10.chart.style.overflowX = 'auto';
      const box = dom.sections.g10.chart;
      const clientWidth = Math.max(box.clientWidth || 900, 320);
      const width = Math.max(clientWidth, 280 + matrix.programmeTypes.length * (compact ? 110 : 96));
      const height = Math.max(box.clientHeight || dynamicHeight, dynamicHeight);
      box.innerHTML = '';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.setAttribute('class', 'chart chart-animated');
      box.appendChild(svg);
      const margin = { top: 26, right: 28, bottom: compact ? 124 : 94, left: compact ? 196 : 164 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const cellW = plotW / Math.max(matrix.programmeTypes.length, 1);
      const cellH = plotH / Math.max(matrix.categories.length, 1);
      for (let ci = 0; ci <= matrix.programmeTypes.length; ci++) {
        const x = margin.left + ci * cellW;
        svg.appendChild(svgEl('line', { x1: x, y1: margin.top, x2: x, y2: margin.top + plotH, stroke: '#e5e7eb', 'stroke-width': 1 }));
      }
      for (let ri = 0; ri <= matrix.categories.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
      }
      matrix.programmeTypes.forEach((type, ci) => {
        addWrappedText(svg, type, margin.left + ci * cellW + cellW / 2, margin.top + plotH + 18, compact ? 10 : 12, '#1f2937', compact ? 8.8 : 10.5, 'middle', 700);
      });
      matrix.categories.forEach((category, ri) => {
        addWrappedText(svg, category, margin.left - 10, margin.top + ri * cellH + cellH * 0.56, compact ? 14 : 18, '#1f2937', compact ? 8.8 : 10.8, 'end', 700);
      });
      matrix.categories.forEach((category, ri) => {
        matrix.programmeTypes.forEach((type, ci) => {
          const x = margin.left + ci * cellW;
          const y = margin.top + ri * cellH;
          const bucket = matrix.map.get(`${category}|||${type}`);
          const spots = bucket ? bucket.spots : 0;
          const airtime = bucket ? bucket.airtime : 0;
          const insetX = Math.min(7, Math.max(3, cellW * 0.08));
          const insetY = Math.min(8, Math.max(3, cellH * 0.08));
          const rect = svgEl('rect', {
            x: x + insetX,
            y: y + insetY,
            width: Math.max(cellW - (insetX * 2), 2),
            height: Math.max(cellH - (insetY * 2), 2),
            rx: 7,
            fill: spots ? graph10HeatColor(spots, matrix.maxSpots) : '#ffffff',
            stroke: spots ? 'rgba(23, 59, 92, 0.16)' : '#ffffff',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = spots
            ? `Category: ${category}\nProgramme Type: ${type}\nAd Spots: ${formatCount(spots)}\nAirtime: ${formatDurationValue(airtime, true)}`
            : `Category: ${category}\nProgramme Type: ${type}\nNo data available`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (spots && ((compact && cellW >= 44 && cellH >= 24) || (!compact && cellW >= 54 && cellH >= 28))) {
            const label = svgEl('text', {
              x: x + cellW / 2,
              y: y + cellH * 0.57,
              fill: graph10LabelColor(spots, matrix.maxSpots),
              'font-size': 11,
              'font-weight': 900,
              'text-anchor': 'middle'
            });
            label.textContent = formatCount(spots);
            svg.appendChild(label);
          }
        });
      });
      addWrappedText(svg, 'Programme Type', margin.left + plotW / 2, height - 10, 20, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Category';
      svg.appendChild(yAxisTitle);
    }
    function drawGraph11(rows) {
      const compareCount = (state.sections.g11 && state.sections.g11.topN) || '3';
      if (dom.sections.g11.compareCount) {
        dom.sections.g11.compareCount.value = compareCount;
      }
      const trend = buildAdvertiserShareOfVoiceTrend(rows, compareCount);
      if (!trend.points.length || trend.advertisers.length < 2) {
        drawEmpty(dom.sections.g11.chart, 'No advertiser share trend is available for the selected filters');
        dom.sections.g11.legend.innerHTML = '';
        dom.sections.g11.metric.textContent = '';
        return;
      }
      setChartBoxHeight(dom.sections.g11.chart, 520);
      const { svg, width, height } = makeSvg(dom.sections.g11.chart);
      const margin = { top: 24, right: 28, bottom: 92, left: 62 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      for (let i = 0; i <= 4; i++) {
        const share = i * 25;
        const y = margin.top + plotH - (plotH * share / 100);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x: margin.left - 10, y: y + 5, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'end' });
        tick.textContent = `${share}%`;
        svg.appendChild(tick);
      }
      const isSingle = trend.points.length === 1;
      const step = isSingle ? 0 : plotW / Math.max(trend.points.length - 1, 1);
      const xForIndex = index => isSingle ? margin.left + plotW / 2 : margin.left + (index * step);
      if (isSingle) {
        const barWidth = Math.min(140, plotW * 0.36);
        const x = margin.left + (plotW - barWidth) / 2;
        let offset = 0;
        trend.advertisers.forEach((advertiser, index) => {
          const share = trend.points[0].values[advertiser] || 0;
          const barHeight = plotH * (share / 100);
          const y = margin.top + plotH - offset - barHeight;
          const rect = svgEl('rect', {
            x,
            y,
            width: barWidth,
            height: Math.max(barHeight, 0),
            fill: advertiser === 'Others' ? GRAPH11_OTHERS_COLOR : chartPalettes.g11[index % chartPalettes.g11.length],
            'fill-opacity': advertiser === 'Others' ? 0.50 : 0.72
          });
          const title = svgEl('title');
          title.textContent = `${advertiser}: ${formatPercent(share)} share on ${formatDate(trend.points[0].date)}`;
          rect.appendChild(title);
          svg.appendChild(rect);
          offset += barHeight;
        });
      } else {
        const cumulative = trend.points.map(() => 0);
        trend.advertisers.forEach((advertiser, index) => {
          const color = advertiser === 'Others' ? GRAPH11_OTHERS_COLOR : chartPalettes.g11[index % chartPalettes.g11.length];
          const upperPoints = [];
          const lowerPoints = [];
          trend.points.forEach((point, pointIndex) => {
            const base = cumulative[pointIndex];
            const next = base + (point.values[advertiser] || 0);
            upperPoints.push([xForIndex(pointIndex), margin.top + plotH - ((next / 100) * plotH)]);
            lowerPoints.push([xForIndex(pointIndex), margin.top + plotH - ((base / 100) * plotH)]);
            cumulative[pointIndex] = next;
          });
          const polygon = svgEl('polygon', {
            points: [...upperPoints, ...lowerPoints.reverse()].map(([x, y]) => `${x},${y}`).join(' '),
            fill: color,
            'fill-opacity': advertiser === 'Others' ? 0.42 : 0.22,
            stroke: color,
            'stroke-width': 1.4
          });
          const title = svgEl('title');
          title.textContent = advertiser;
          polygon.appendChild(title);
          svg.appendChild(polygon);
        });
      }
      trend.points.forEach((point, index) => {
        const x = xForIndex(index);
        svg.appendChild(svgEl('line', { x1: x, y1: margin.top + plotH, x2: x, y2: margin.top + plotH + 6, stroke: '#cbd5e1', 'stroke-width': 1 }));
        if (trend.points.length <= 8 || index % 2 === 0 || index === trend.points.length - 1) {
          addWrappedText(svg, formatDate(point.date), x, margin.top + plotH + 18, 10, '#1f2937', 9.1, 'middle', 700);
        }
      });
      addWrappedText(svg, 'Date', margin.left + plotW / 2, height - 10, 20, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 20,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 20 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Share of Voice (%)';
      svg.appendChild(yAxisTitle);
      renderLegend(dom.sections.g11.legend, trend.advertisers.map((advertiser, index) => ({
        label: advertiser === 'Others' ? 'Others' : titleCaseName(advertiser),
        color: advertiser === 'Others' ? GRAPH11_OTHERS_COLOR : chartPalettes.g11[index % chartPalettes.g11.length]
      })));
      const compareLabel = compareCount === 'all'
        ? 'all advertisers'
        : `top ${compareCount} advertisers${trend.advertisers.includes('Others') ? ' plus Others' : ''}`;
      dom.sections.g11.metric.textContent = `Daily share of total ad duration for ${compareLabel}.`;
    }
    function drawGraph12(rows) {
      const channels = buildChannelEfficiency(rows);
      if (!channels.length) {
        drawEmpty(dom.sections.g12.chart, 'No channel efficiency data is available for the selected filters');
        dom.sections.g12.metric.textContent = '';
        return;
      }
      const compact = channels.length >= 10;
      setChartBoxHeight(dom.sections.g12.chart, compact ? 620 : 540);
      const { svg, width, height } = makeSvg(dom.sections.g12.chart);
      const gradient = appendLinearGradient(
        svg,
        'g12BarGradient',
        themeVar('--brand', '#2563eb'),
        themeVar('--teal', '#0f766e')
      );
      const margin = { top: 26, right: 110, bottom: 70, left: 132 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxTotal = withAxisHeadroom(Math.max(...channels.map(item => item.total), 1));
      const rowH = plotH / Math.max(channels.length, 1);
      for (let i = 0; i <= 4; i++) {
        const x = margin.left + (plotW * i / 4);
        svg.appendChild(svgEl('line', { x1: x, y1: margin.top, x2: x, y2: margin.top + plotH, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x, y: margin.top + plotH + 24, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'middle' });
        tick.textContent = formatDurationValue((maxTotal * i) / 4);
        svg.appendChild(tick);
      }
      channels.forEach((item, index) => {
        const y = margin.top + index * rowH + (rowH * 0.18);
        const barH = Math.max(rowH * 0.56, 18);
        const barW = (item.total / maxTotal) * plotW;
        svg.appendChild(svgEl('rect', {
          x: margin.left,
          y,
          width: plotW,
          height: barH,
          rx: 7,
          fill: '#eef2ff'
        }));
        const bar = svgEl('rect', {
          x: margin.left,
          y,
          width: Math.max(barW, 0),
          height: barH,
          rx: 7,
          fill: gradient
        });
        const title = svgEl('title');
        title.textContent = `Channel: ${item.channel}\nAd Spots: ${formatCount(item.spots)}\nTotal Duration: ${formatDurationValue(item.total, true)}\nAverage Creative Duration: ${formatDurationValue(item.average, true)}`;
        bar.appendChild(title);
        svg.appendChild(bar);
        addWrappedText(svg, item.channel, margin.left - 10, y + (barH * 0.58), 14, '#1f2937', 10, 'end', 700);
        const valueLabel = svgEl('text', {
          x: Math.min(margin.left + barW + 8, margin.left + plotW - 4),
          y: y + (barH * 0.46),
          fill: '#1f2937',
          'font-size': 10.5,
          'font-weight': 800,
          'text-anchor': 'start'
        });
        valueLabel.textContent = formatDurationValue(item.total, true);
        svg.appendChild(valueLabel);
        const detailLabel = svgEl('text', {
          x: Math.min(margin.left + barW + 8, margin.left + plotW - 4),
          y: y + (barH * 0.83),
          fill: '#6b7280',
          'font-size': 9.4,
          'font-weight': 700,
          'text-anchor': 'start'
        });
        detailLabel.textContent = `${formatCount(item.spots)} spots | Avg ${formatDurationValue(item.average, true)}`;
        svg.appendChild(detailLabel);
      });
      addWrappedText(svg, `Total Ad Duration (${activeTimeUnit() === 'minutes' ? 'Min' : 'Sec'})`, margin.left + plotW / 2, height - 10, 26, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Channel';
      svg.appendChild(yAxisTitle);
      dom.sections.g12.metric.textContent = 'Bar length shows total ad duration, with inline labels for ad spots and average creative duration.';
    }
    function drawGraph13(rows) {
      const concentration = buildChannelConcentration(rows, 5);
      if (!concentration.length) {
        drawEmpty(dom.sections.g13.chart, 'No concentration data is available for the selected filters');
        dom.sections.g13.legend.innerHTML = '';
        dom.sections.g13.metric.textContent = '';
        return;
      }
      const compact = concentration.length >= 10;
      setChartBoxHeight(dom.sections.g13.chart, compact ? 620 : 520);
      const { svg, width, height } = makeSvg(dom.sections.g13.chart);
      const gradient = appendLinearGradient(
        svg,
        'g13BarGradient',
        themeVar('--brand', '#2563eb'),
        themeVar('--teal', '#0f766e')
      );
      const margin = { top: 24, right: 36, bottom: 72, left: 132 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const rowH = plotH / Math.max(concentration.length, 1);
      for (let i = 0; i <= 4; i++) {
        const percent = i * 25;
        const x = margin.left + (plotW * percent / 100);
        svg.appendChild(svgEl('line', { x1: x, y1: margin.top, x2: x, y2: margin.top + plotH, stroke: '#e5e7eb', 'stroke-width': 1 }));
        const tick = svgEl('text', { x, y: margin.top + plotH + 24, fill: '#6b7280', 'font-size': 12, 'text-anchor': 'middle' });
        tick.textContent = `${percent}%`;
        svg.appendChild(tick);
      }
      concentration.forEach((item, index) => {
        const y = margin.top + index * rowH + (rowH * 0.18);
        const barH = Math.max(rowH * 0.54, 18);
        const barW = plotW * (item.share / 100);
        svg.appendChild(svgEl('rect', {
          x: margin.left,
          y,
          width: plotW,
          height: barH,
          rx: 7,
          fill: '#eef2ff'
        }));
        const bar = svgEl('rect', {
          x: margin.left,
          y,
          width: Math.max(barW, 0),
          height: barH,
          rx: 7,
          fill: gradient
        });
        const title = svgEl('title');
        title.textContent = `Channel: ${item.channel}\nTop 5 advertiser share: ${formatPercent(item.share)}\nTop 5 duration: ${formatDurationValue(item.topTotal, true)}\nUnique advertisers: ${formatCount(item.advertiserCount)}`;
        bar.appendChild(title);
        svg.appendChild(bar);
        addWrappedText(svg, item.channel, margin.left - 10, y + (barH * 0.58), 14, '#1f2937', 10, 'end', 700);
        const label = svgEl('text', {
          x: Math.min(margin.left + barW + 8, margin.left + plotW - 4),
          y: y + (barH * 0.62),
          fill: '#1f2937',
          'font-size': 11,
          'font-weight': 800,
          'text-anchor': 'start'
        });
        label.textContent = `${item.share.toFixed(1)}% (${formatDurationValue(item.topTotal)})`;
        svg.appendChild(label);
      });
      addWrappedText(svg, 'Top 5 Advertiser Share of Channel Duration', margin.left + plotW / 2, height - 10, 28, '#1f2937', 13, 'middle', 800);
      const yAxisTitle = svgEl('text', {
        x: 22,
        y: margin.top + plotH / 2,
        fill: '#1f2937',
        'font-size': 13,
        'font-weight': 800,
        'text-anchor': 'middle',
        transform: `rotate(-90 22 ${margin.top + plotH / 2})`
      });
      yAxisTitle.textContent = 'Channel';
      svg.appendChild(yAxisTitle);
      renderLegend(dom.sections.g13.legend, [{
        label: 'Top 5 advertiser share',
        color: themeVar('--brand', '#2563eb')
      }]);
      dom.sections.g13.metric.textContent = 'Higher percentages indicate stronger advertiser concentration within a channel.';
    }
    function renderExcluded() {
      dom.excludedChips.textContent = `Excluded categories: ${PAYLOAD.excluded.map(sentenceCaseName).join(' • ')}`;
    }
    function formatPercent(value) {
      return `${(value || 0).toFixed(2)}%`;
    }
    function graph5UnitMeta() {
      const unit = state.global.time || state.sections.g5.time || 'minutes';
      if (unit === 'minutes') {
        return {
          unit,
          convert: value => value / 60,
          format: value => `${value.toFixed(1)} min`
        };
      }
      return {
        unit: 'seconds',
        convert: value => value,
        format: value => `${formatNumber(Math.round(value))} sec`
      };
    }
    function collectSelectedValues(keys, field) {
      const values = [];
      keys.forEach(sectionKey => {
        const value = state.sections[sectionKey] && state.sections[sectionKey][field];
        if (Array.isArray(value)) {
          value.forEach(item => {
            if (item) values.push(item);
          });
          return;
        }
        if (value) values.push(value);
      });
      return [...new Set(values)];
    }
    function getDashboardSummaryRows() {
      return getGlobalFilteredRows();
    }
    function renderSummary() {
      const rows = getDashboardSummaryRows();
      const unitWord = activeTimeUnit() === 'minutes' ? 'minutes' : 'seconds';
      if (!rows.length) {
        dom.summaryLines.innerHTML = [
          `Total advertisement duration: 0 ${unitWord} distributed across the filtered dataset.`,
          'Top 5 highest performing categories: No category data is available for the current selection.',
          'Top 5 advertisers: No advertiser data is available for the current selection.',
          'Key trend: No trend is available because the filtered dataset is empty.',
          'Additional insight: Aaj Tak comparison is unavailable because the filtered dataset is empty.'
        ].map(line => `<div class="summary-line">${line}</div>`).join('');
        renderHeaderStats();
        return;
      }
      const total = rows.reduce((sum, row) => sum + row.aaddur, 0);
      const channelDistribution = buildChannelDistribution(rows);
      const categories = buildCategoryDistribution(rows);
      const advertisers = aggregateAdvertisors(rows);
      const topChannel = channelDistribution[0] || { channel: 'N/A', total: 0 };
      const topCategory = categories[0] || { category: 'N/A', total: 0 };
      const topCategoryPct = total ? (topCategory.total / total) * 100 : 0;
      const topChannelPct = total ? (topChannel.total / total) * 100 : 0;
      const topFiveCategories = categories
        .slice(0, 5)
        .map(item => `${sentenceCaseName(item.category)} (${formatDurationValue(item.total, true)})`)
        .join(', ') || 'No category data is available for the current selection';
      const topFiveAdvertisers = advertisers
        .slice(0, 5)
        .map(item => `${titleCaseName(item.advertisor)} (${formatDurationValue(item.total, true)})`)
        .join(', ') || 'No advertiser data is available for the current selection';
      const channelDistributionInline = channelDistribution
        .map(item => `${titleCaseName(item.channel)} (${formatDurationValue(item.total, true)})`)
        .join(', ') || 'no channels are available for the current selection';
      const topFiveAdvertiserTotal = advertisers.slice(0, 5).reduce((sum, item) => sum + item.total, 0);
      const topFiveCategoryTotal = categories.slice(0, 5).reduce((sum, item) => sum + item.total, 0);
      const advertiserShare = total ? (topFiveAdvertiserTotal / total) * 100 : 0;
      const categoryShare = total ? (topFiveCategoryTotal / total) * 100 : 0;
      const aajTakChannel = channelDistribution.find(item => String(item.channel || '').trim().toUpperCase() === 'AAJ TAK') || null;
      const aajTakDeltaPct = aajTakChannel && aajTakChannel.total
        ? ((topChannel.total - aajTakChannel.total) / aajTakChannel.total) * 100
        : null;
      const aajTakComparison = !aajTakChannel || !aajTakChannel.total
        ? 'Aaj Tak comparison is unavailable for the current filtered dataset'
        : String(topChannel.channel || '').trim().toUpperCase() === 'AAJ TAK'
          ? 'Aaj Tak is the reference channel at 0.00% variance'
          : `${titleCaseName(topChannel.channel)} is ${formatPercent(Math.abs(aajTakDeltaPct))} ${aajTakDeltaPct >= 0 ? 'above' : 'below'} Aaj Tak`;
      const lines = [
        `Total advertisement duration: ${formatDurationValue(total, true)} distributed across ${channelDistributionInline}.`,
        `Top 5 highest performing categories: ${topFiveCategories}.`,
        `Top 5 advertisers: ${topFiveAdvertisers}.`,
        `Key trend: ${titleCaseName(topChannel.channel)} is the strongest performing channel with ${formatDurationValue(topChannel.total, true)} (${formatPercent(topChannelPct)}) of total advertisement duration, while ${sentenceCaseName(topCategory.category)} remains the leading category contributing ${formatPercent(topCategoryPct)} of the overall advertisement duration.`,
        `Additional insight: The top five advertisers contribute ${formatPercent(advertiserShare)} of total duration, the top five categories contribute ${formatPercent(categoryShare)}, and ${aajTakComparison}.`
      ];
      dom.summaryLines.innerHTML = lines.map(line => `<div class="summary-line">${line}</div>`).join('');
      renderHeaderStats();
    }
    function categoryFilterLabel(sectionState, emptyLabel) {
      return Array.isArray(sectionState.category)
        ? ((sectionState.category || []).length ? sectionState.category.join(', ') : emptyLabel)
        : (sectionState.category || emptyLabel);
    }
    function multiFilterLabel(values, emptyLabel) {
      return Array.isArray(values)
        ? (values.length ? values.join(', ') : emptyLabel)
        : (values || emptyLabel);
    }
    function filterSummaryLines(sectionKey, sectionState, forPage = false) {
      const categoryLabel = categoryFilterLabel(state.global, forPage ? 'All' : 'all');
      const channelLabel = multiFilterLabel(state.global.channel, forPage ? 'All' : 'all');
      const advertiserLabel = multiFilterLabel(state.global.advertisor, forPage ? 'All' : 'all');
      return forPage
        ? [
            `Top N: ${state.global.topN || 'All'}`,
            `Start Date: ${state.global.start ? formatDate(state.global.start) : 'All'}`,
            `End Date: ${state.global.end ? formatDate(state.global.end) : 'All'}`,
            `Channel: ${channelLabel}`,
            `Category: ${categoryLabel}`,
            `Advertiser: ${advertiserLabel}`,
            `Time: ${state.global.time || 'minutes'}`
          ]
        : [`<strong>Global</strong> | Top N: ${state.global.topN || 'all'}, Start: ${state.global.start || 'all'}, End: ${state.global.end || 'all'}, Channel: ${channelLabel}, Category: ${categoryLabel}, Advertiser: ${advertiserLabel}, Time: ${state.global.time || 'minutes'}`];
    }
    function getActiveFiltersMarkup() {
      return `<div class="summary-line">${filterSummaryLines('global', state.global)[0]}</div>`;
    }
    function getSelectedDateRangeText() {
      const start = state.global.start || '';
      const end = state.global.end || '';
      if (!start && !end) return 'All Dates';
      if (start && end) return `${formatDate(start)} to ${formatDate(end)}`;
      return formatDate(start || end);
    }
    function getActiveFiltersPageMarkup() {
      return `
          <div class="pdf-filter-card">
            <h3>Global Filters</h3>
            ${filterSummaryLines('global', state.global, true).map(line => `<div class="summary-line">${line}</div>`).join('')}
          </div>
        `;
    }
    function exportDashboardPdf() {
      const printWindow = window.open('', '_blank', 'width=1280,height=900');
      if (!printWindow) return;
      const title = 'CTV FCT Dashboard';
      const generatedAt = new Date().toLocaleString();
      const summaryHtml = document.getElementById('summaryLines').innerHTML;
      const graphSections = SECTION_KEYS.map(sectionKey => `${sectionKey}Chart`)
        .map(id => document.getElementById(id)?.closest('.section'))
        .filter(Boolean);
      const graphPages = graphSections.map((section, index) => {
        const heading = section.querySelector('.section-head h2')?.textContent || `Graph ${index + 1}`;
        const panelHtml = section.querySelector('.panel')?.outerHTML || '';
        return `
          <section class="pdf-page">
            <div class="pdf-page-head">
              <div class="pdf-kicker">Graph ${index + 1}</div>
              <h2>${heading}</h2>
            </div>
            ${panelHtml}
          </section>
        `;
      }).join('');
      const styles = document.querySelector('style').outerHTML;
      printWindow.document.write(`<!DOCTYPE html><html><head><title>${title}</title>${styles}<style>
        @page { size: A5 portrait; margin: 8mm; }
        body { background: #ffffff !important; }
        .pdf-scale { transform: scale(0.42); transform-origin: top left; width: 238.095%; }
        .page.pdf-export { max-width: none; padding: 0; }
        .pdf-page { min-height: 100vh; padding: 32px; page-break-after: always; break-after: page; display: flex; flex-direction: column; gap: 18px; }
        .pdf-page:last-child { page-break-after: auto; break-after: auto; }
        .pdf-cover { justify-content: center; }
        .pdf-cover .hero { margin: 0; }
        .pdf-page-head h2 { margin: 6px 0 0; font-size: 30px; font-weight: 900; }
        .pdf-kicker { color: #9fc2f2; font-size: 12px; font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }
        .pdf-filter-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
        .pdf-filter-card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; box-shadow: 0 2px 8px rgba(15,23,42,0.08); }
        .pdf-filter-card h3 { margin: 0 0 12px; font-size: 18px; }
        .pdf-page .panel { margin: 0; box-shadow: none; }
        .pdf-page .chart-box { height: calc(100vh - 260px); min-height: 620px; }
        @media print {
          .pdf-page { min-height: auto; }
          .pdf-page .chart-box { height: 620px !important; min-height: 620px !important; }
        }
      </style></head><body><div class="pdf-scale"><div class="page pdf-export">
      <section class="pdf-page pdf-cover">
        <section class="hero">
          <div class="hero-copy">
            <h1>${title}</h1>
            <p class="hero-subtitle">Advertising Analytics Dashboard</p>
            <div class="hero-meta">
              <div class="meta-pill">Date Range: ${getSelectedDateRangeText()}</div>
            </div>
          </div>
        </section>
        <div class="panel section-card">
          <div class="section-head"><h2>Executive Summary</h2></div>
          <div class="summary-lines">${summaryHtml}</div>
        </div>
        <div class="panel section-card">
          <div class="section-head"><h2>Key Insights</h2></div>
          <div class="summary-lines">${summaryHtml}</div>
        </div>
      </section>
      <section class="pdf-page">
        <div class="pdf-page-head">
          <div class="pdf-kicker">Page 2</div>
          <h2>Active Filters</h2>
        </div>
        <div class="pdf-filter-grid">${getActiveFiltersPageMarkup()}</div>
      </section>
      ${graphPages}
      </div></div></body></html>`);
      printWindow.document.close();
      printWindow.focus();
      setTimeout(() => printWindow.print(), 300);
    }
    function cloneSectionState(source) {
      if (!source) return null;
      return {
        ...source,
        channel: Array.isArray(source.channel) ? [...source.channel] : source.channel,
        category: Array.isArray(source.category) ? [...source.category] : source.category,
        advertisor: Array.isArray(source.advertisor) ? [...source.advertisor] : source.advertisor
      };
    }
    function getDatasetNameForExport() {
      const status = String(dom.statusText?.textContent || '').trim();
      const loaded = status.match(/Loaded(?:\\s+CSV|\\s+workbook|\\s+shared dashboard snapshot\\.|\\s+embedded dataset)?\\s*file:\\s*(.+)$/i)
        || status.match(/Loaded\\s+CSV\\s+file:\\s*(.+)$/i)
        || status.match(/Loaded\\s+workbook:\\s*(.+)$/i);
      if (loaded && loaded[1]) return loaded[1].replace(/\\.[^.]+$/, '');
      return 'Dashboard';
    }
    function sanitizeFilenamePart(value) {
      return String(value || 'Dashboard')
        .replace(/[\\/:*?"<>|]+/g, ' ')
        .replace(/\\s+/g, '_')
        .replace(/^_+|_+$/g, '')
        .slice(0, 60) || 'Dashboard';
    }
    function buildShareFilename() {
      const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\\.\\d+Z$/, '').replace('T', '_');
      return `CTV FCT_${sanitizeFilenamePart(getDatasetNameForExport())}_${stamp}.html`;
    }
    function serializeDashboardState() {
      return {
        reportClock: new Date().toISOString(),
        statusText: dom.statusText?.textContent || 'Loaded shared dashboard snapshot.',
        supplemental: {
          ...state.supplemental
        },
        global: {
          ...state.global,
          channel: [...(state.global.channel || [])],
          category: [...(state.global.category || [])],
          advertisor: [...(state.global.advertisor || [])]
        },
        sections: SECTION_KEYS.reduce((acc, sectionKey) => {
          acc[sectionKey] = cloneSectionState(state.sections[sectionKey]);
          return acc;
        }, {})
      };
    }
    function applyExportedState(snapshot) {
      if (!snapshot) return;
      if (snapshot.reportClock) state.reportClock = snapshot.reportClock;
      if (snapshot.supplemental) {
        state.supplemental = {
          ...state.supplemental,
          ...snapshot.supplemental
        };
      }
      if (snapshot.global) {
        state.global = {
          ...state.global,
          ...snapshot.global,
          channel: [...(snapshot.global.channel || [])],
          category: [...(snapshot.global.category || [])],
          advertisor: [...(snapshot.global.advertisor || [])]
        };
      }
      if (snapshot.sections) {
        SECTION_KEYS.forEach(sectionKey => {
          if (!snapshot.sections[sectionKey]) return;
          const next = snapshot.sections[sectionKey];
          state.sections[sectionKey] = {
            ...state.sections[sectionKey],
            ...next,
            channel: Array.isArray(next.channel) ? [...next.channel] : next.channel,
            category: Array.isArray(next.category) ? [...next.category] : next.category,
            advertisor: Array.isArray(next.advertisor) ? [...next.advertisor] : next.advertisor
          };
        });
      }
      dom.global.topN.value = state.global.topN || '10';
      dom.global.start.value = state.global.start || '';
      dom.global.end.value = state.global.end || '';
      dom.global.time.value = state.global.time || 'minutes';
      setMultiSelectValues(dom.global.channel, state.global.channel || []);
      setMultiSelectValues(dom.global.category, state.global.category || []);
      setMultiSelectValues(dom.global.advertisor, state.global.advertisor || []);
      updateMultiDropdownValue(dom.global, 'channel', state.global.channel || [], 'All Channels', 'Channels');
      updateCategoryDropdownValue(dom.global, state.global.category || []);
      updateMultiDropdownValue(dom.global, 'advertisor', state.global.advertisor || [], 'All Advertisers', 'Advertisers');
      populateGlobalChannelDropdown('');
      populateGlobalCategoryDropdown('');
      populateGlobalAdvertisorDropdown('');
      if (dom.statusText && snapshot.statusText) {
        dom.statusText.textContent = snapshot.statusText;
      }
      applyGlobalStateToSections();
      if (dom.sections.g2.barBtn && dom.sections.g2.pieBtn) {
        dom.sections.g2.barBtn.classList.toggle('active', state.sections.g2.view !== 'pie');
        dom.sections.g2.pieBtn.classList.toggle('active', state.sections.g2.view === 'pie');
      }
      if (dom.sections.g3.heatmapBtn && dom.sections.g3.barBtn) {
        dom.sections.g3.heatmapBtn.classList.toggle('active', state.sections.g3.view !== 'bar');
        dom.sections.g3.barBtn.classList.toggle('active', state.sections.g3.view === 'bar');
      }
      renderAll();
    }
    function exportDashboardShare() {
      const exportPayload = {
        rows: state.rawRows,
        excluded: [...EXCLUDED],
        generatedAt: new Date().toISOString()
      };
      const exportState = serializeDashboardState();
      const preloadScript = `\n<script>window.PRELOADED_DATASET = ${JSON.stringify(exportPayload.rows)};window.PRELOADED_DASHBOARD_STATE = ${JSON.stringify(exportState)};window.EXPORTED_DASHBOARD_MODE = true;<\\/script>\n`;
      const exportOnlyStyle = `\n<style>
      #fileUpload,
      #uploadBtn,
      #uploadCheck,
      #sheetBtn,
      #sheetCheck,
      #sheetMenu {
        display: none !important;
      }
      .header-icon-group {
        gap: 0 !important;
      }
      </style>\n`;
      let exportedHtml = '<!DOCTYPE html>\\n' + document.documentElement.outerHTML;
      exportedHtml = exportedHtml.replace(/<body([^>]*)style="[^"]*overflow:\\s*hidden;?[^"]*"([^>]*)>/i, '<body$1$2>');
      exportedHtml = exportedHtml.replace('<head>', `<head>${preloadScript}${exportOnlyStyle}`);
      const blob = new Blob([exportedHtml], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = buildShareFilename();
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    function openShareModal() {
      if (!dom.shareModal) return;
      dom.shareModal.hidden = false;
      document.body.style.overflow = 'hidden';
      if (dom.shareDownloadBtn) dom.shareDownloadBtn.focus();
    }
    function closeShareModal() {
      if (!dom.shareModal) return;
      dom.shareModal.hidden = true;
      document.body.style.overflow = '';
      if (dom.shareBtn) dom.shareBtn.focus();
    }
    function handleShareDownload() {
      closeShareModal();
      exportDashboardShare();
    }
    function renderSection(sectionKey) {
      const rows = getSectionRows(sectionKey);
      setSectionInsight(sectionKey, buildSectionInsight(sectionKey, rows));
      if (sectionKey === 'g1') drawGraph1(rows);
      if (sectionKey === 'g2') {
        if (state.sections.g2.view === 'pie') {
          drawGraph2Pie(rows);
        } else {
          drawGraph2Bar(rows);
        }
      }
      if (sectionKey === 'g3') {
        if (state.sections.g3.view === 'bar') {
          drawGraph3Bar(rows);
        } else {
          drawGraph3Heatmap(rows);
        }
      }
      if (sectionKey === 'g4') drawGraph4(rows);
      if (sectionKey === 'g5') drawGraph5(rows);
      if (sectionKey === 'g6') drawGraph6Bar(rows);
      if (sectionKey === 'g7') drawGraph7(rows);
      if (sectionKey === 'g8') drawGraph8(rows);
      if (sectionKey === 'g9') drawGraph9(rows);
      if (sectionKey === 'g10') drawGraph10(rows);
      if (sectionKey === 'g11') drawGraph11(rows);
      if (sectionKey === 'g12') drawGraph12(rows);
      if (sectionKey === 'g13') drawGraph13(rows);
    }
    function renderAll() {
      applyGlobalStateToSections();
      rerenderSections(SECTION_KEYS);
      renderSummary();
      renderDatasetSummary();
      renderHeaderStats();
      updateStickyFilterPosition();
    }
    function syncSectionState(sectionKey) {
      const controls = dom.sections[sectionKey];
      if (!controls) return;
      if (!state.sections[sectionKey]) {
        state.sections[sectionKey] = {
          topN: state.global.topN,
          start: state.global.start,
          end: state.global.end,
          channel: [...state.global.channel],
          category: [...state.global.category],
          advertisor: [...state.global.advertisor],
          time: state.global.time,
          view: ''
        };
      }
      const target = state.sections[sectionKey];
      if (!target) return;
      if (controls.topN) target.topN = controls.topN.value;
      if (controls.start) target.start = controls.start.value;
      if (controls.end) target.end = controls.end.value;
      if (controls.channel) target.channel = Array.from(controls.channel.selectedOptions).map(option => option.value);
      if (sharedCategorySections().includes(sectionKey)) {
        target.category = Array.from(controls.category.selectedOptions).map(option => option.value);
      } else if (controls.category) {
        target.category = controls.category.value;
      }
      if (sectionKey === 'g5') {
        target.advertisor = Array.from(controls.advertisor.selectedOptions).map(option => option.value);
        target.time = controls.time.value;
      }
    }
    function syncGlobalFromSection(sectionKey) {
      const controls = dom.sections[sectionKey];
      if (controls.topN && dom.global.topN) dom.global.topN.value = controls.topN.value;
      if (controls.start && dom.global.start) dom.global.start.value = controls.start.value;
      if (controls.end && dom.global.end) dom.global.end.value = controls.end.value;
      if (controls.channel && dom.global.channel) setMultiSelectValues(dom.global.channel, Array.from(controls.channel.selectedOptions).map(option => option.value));
      if (controls.advertisor && dom.global.advertisor) setMultiSelectValues(dom.global.advertisor, Array.from(controls.advertisor.selectedOptions).map(option => option.value));
      if (controls.time && dom.global.time) dom.global.time.value = controls.time.value;
      syncGlobalChannelSelection(Array.from(controls.channel.selectedOptions).map(option => option.value), { preserveSearchText: true });
      if (sharedCategorySections().includes(sectionKey) && controls.category) {
        syncGlobalCategorySelection(Array.from(controls.category.selectedOptions).map(option => option.value), { preserveSearchText: true });
      }
      if (controls.advertisor) {
        syncGlobalAdvertisorSelection(Array.from(controls.advertisor.selectedOptions).map(option => option.value), { preserveSearchText: true });
      }
      syncGlobalState();
    }
    function bindSection(sectionKey) {
      const controls = dom.sections[sectionKey];
      if (!controls.reset || !controls.start || !controls.end || !controls.channel) return;
      const controlKeys = sectionKey === 'g5'
        ? ['time']
        : ['topN'];
      controlKeys.forEach(key => {
        if (!controls[key]) return;
        controls[key].addEventListener('change', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) return;
          syncSectionState(sectionKey);
          syncGlobalFromSection(sectionKey);
          syncAndRenderSections(SECTION_KEYS);
        });
      });
      ['start', 'end'].forEach(key => {
        controls[key].addEventListener('change', () => {
          if (!handleDateRangeChange(controls, key)) return;
          syncSectionState(sectionKey);
          syncGlobalFromSection(sectionKey);
          syncAndRenderSections(SECTION_KEYS);
        });
      });
      controls.channelTrigger.addEventListener('click', event => {
        event.preventDefault();
        controls.channelDropdown.classList.toggle('open');
        if (controls.channelDropdown.classList.contains('open')) controls.channelSearch.focus();
      });
      controls.channelSearch.addEventListener('input', () => {
        populateChannelDropdown(sectionKey, controls.channelSearch.value);
      });
      controls.channelAll.addEventListener('click', () => {
        if (!validateDateRange(controls.start.value, controls.end.value)) return;
        controls.channelDropdown.classList.add('open');
        syncSharedChannelSelection(getChannelValues(), sectionKey, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      controls.channelClear.addEventListener('click', () => {
        if (!validateDateRange(controls.start.value, controls.end.value)) return;
        controls.channelDropdown.classList.add('open');
        syncSharedChannelSelection([], sectionKey, { preserveSearchText: true });
        syncAndRenderSections(SECTION_KEYS);
      });
      if (sharedCategorySections().includes(sectionKey)) {
        controls.categoryTrigger.addEventListener('click', event => {
          event.preventDefault();
          controls.categoryDropdown.classList.toggle('open');
          if (controls.categoryDropdown.classList.contains('open')) {
            controls.categorySearch.focus();
          }
        });
        controls.categorySearch.addEventListener('input', () => {
          populateCategoryDropdown(sectionKey, controls.categorySearch.value);
        });
        controls.categoryAll.addEventListener('click', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) return;
          controls.categoryDropdown.classList.add('open');
          syncSharedCategorySelection(getCategoryValues(), sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
          renderSummary();
        });
        controls.categoryClear.addEventListener('click', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) return;
          controls.categoryDropdown.classList.add('open');
          syncSharedCategorySelection([], sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
          renderSummary();
        });
      }
      if (controls.advertisorTrigger) {
        controls.advertisorTrigger.addEventListener('click', event => {
          event.preventDefault();
          controls.advertisorDropdown.classList.toggle('open');
          if (controls.advertisorDropdown.classList.contains('open')) controls.advertisorSearch.focus();
        });
        controls.advertisorSearch.addEventListener('input', () => {
          populateAdvertisorDropdown(sectionKey, controls.advertisorSearch.value);
        });
        controls.advertisorAll.addEventListener('click', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) return;
          controls.advertisorDropdown.classList.add('open');
          syncSharedAdvertisorSelection(getAdvertisorValues(state.global.channel), sectionKey, { preserveSearchText: true });
          syncAndRenderSections(SECTION_KEYS);
        });
        controls.advertisorClear.addEventListener('click', () => {
          if (!validateDateRange(controls.start.value, controls.end.value)) return;
          controls.advertisorDropdown.classList.add('open');
          syncSharedAdvertisorSelection([], sectionKey, { preserveSearchText: true });
          syncAndRenderSections(SECTION_KEYS);
        });
      }
      controls.reset.addEventListener('click', () => {
        if (controls.topN) controls.topN.value = '10';
        setMultiSelectValues(controls.channel, []);
        if (sharedCategorySections().includes(sectionKey)) {
          controls.categorySearch.value = '';
          syncSharedCategorySelection([], sectionKey);
        } else if (controls.category) {
          controls.category.value = '';
        }
        const dates = uniqueSorted(state.cleanedRows.map(row => row.date));
        controls.start.value = dates[0] || '';
        controls.end.value = dates[dates.length - 1] || '';
        if (sectionKey === 'g2') {
          state.sections.g2.view = 'bar';
          dom.sections.g2.barBtn.classList.add('active');
          dom.sections.g2.pieBtn.classList.remove('active');
        }
        if (sectionKey === 'g3') {
          state.sections.g3.view = 'heat';
          dom.sections.g3.heatmapBtn.classList.add('active');
          dom.sections.g3.barBtn.classList.remove('active');
        }
        if (sectionKey === 'g5') {
          setMultiSelectValues(controls.advertisor, []);
          controls.time.value = 'minutes';
        }
        syncSharedChannelSelection([], sectionKey, { preserveSearchText: true });
        if (controls.advertisor) syncSharedAdvertisorSelection([], sectionKey, { preserveSearchText: true });
        if (sharedCategorySections().includes(sectionKey)) {
          syncGlobalFromSection(sectionKey);
          syncAndRenderSections(SECTION_KEYS);
        } else {
          syncSectionState(sectionKey);
          syncGlobalFromSection(sectionKey);
          syncAndRenderSections(SECTION_KEYS);
        }
      });
    }
    function toggleFullScreen(sectionKey) {
      const panel = dom.sections[sectionKey].panel;
      if (!document.fullscreenElement) {
        if (panel.requestFullscreen) panel.requestFullscreen();
      } else if (document.fullscreenElement === panel) {
        if (document.exitFullscreen) document.exitFullscreen();
      }
    }
    function updateFullButtons() {
      SECTION_KEYS.forEach(sectionKey => {
        const panel = dom.sections[sectionKey].panel;
        const isActive = document.fullscreenElement === panel;
        dom.sections[sectionKey].fullBtn.textContent = isActive ? 'Exit Full Screen' : 'Full Screen';
      });
    }
    function moveGlobalFiltersToFullscreen(panel) {
      const wrap = dom.stickyFilterWrap;
      const shell = dom.stickyFilterShell;
      if (!wrap || !shell || !panel) return;
      if (panel.contains(shell)) return;
      wrap.classList.add('is-stuck');
      wrap.style.setProperty('--sticky-filter-height', `${shell.offsetHeight}px`);
      shell.classList.remove('is-stuck');
      shell.style.left = '';
      shell.style.width = '';
      panel.insertBefore(shell, panel.firstChild);
    }
    function restoreGlobalFiltersFromFullscreen() {
      const wrap = dom.stickyFilterWrap;
      const shell = dom.stickyFilterShell;
      if (!wrap || !shell) return;
      if (wrap.contains(shell)) return;
      wrap.appendChild(shell);
      wrap.classList.remove('is-stuck');
      wrap.style.removeProperty('--sticky-filter-height');
      shell.classList.remove('is-stuck');
      shell.style.left = '';
      shell.style.width = '';
    }
    function initializeSections() {
      initializeGlobalControls();
      SECTION_KEYS.forEach(sectionKey => {
        initializeSectionControls(sectionKey);
        if (!state.initialized && dom.sections[sectionKey].reset) bindSection(sectionKey);
        if (!state.initialized) {
          dom.sections[sectionKey].fullBtn.addEventListener('click', () => toggleFullScreen(sectionKey));
        }
      });
      if (!state.initialized) {
        bindGlobalControls();
        if (dom.pdfBtn) {
          dom.pdfBtn.addEventListener('click', exportDashboardPdf);
        }
        if (dom.shareBtn) {
          dom.shareBtn.addEventListener('click', openShareModal);
        }
        if (dom.shareCancelBtn) {
          dom.shareCancelBtn.addEventListener('click', closeShareModal);
        }
        if (dom.shareDownloadBtn) {
          dom.shareDownloadBtn.addEventListener('click', handleShareDownload);
        }
        if (dom.shareModal) {
          dom.shareModal.addEventListener('click', event => {
            if (event.target === dom.shareModal) {
              closeShareModal();
            }
          });
        }
        dom.sections.g2.barBtn.addEventListener('click', () => {
          state.sections.g2.view = 'bar';
          dom.sections.g2.barBtn.classList.add('active');
          dom.sections.g2.pieBtn.classList.remove('active');
          renderSection('g2');
        });
        dom.sections.g2.pieBtn.addEventListener('click', () => {
          state.sections.g2.view = 'pie';
          dom.sections.g2.pieBtn.classList.add('active');
          dom.sections.g2.barBtn.classList.remove('active');
          renderSection('g2');
        });
        dom.sections.g3.heatmapBtn.addEventListener('click', () => {
          state.sections.g3.view = 'heat';
          dom.sections.g3.heatmapBtn.classList.add('active');
          dom.sections.g3.barBtn.classList.remove('active');
          renderSection('g3');
        });
        dom.sections.g3.barBtn.addEventListener('click', () => {
          state.sections.g3.view = 'bar';
          dom.sections.g3.barBtn.classList.add('active');
          dom.sections.g3.heatmapBtn.classList.remove('active');
          renderSection('g3');
        });
        if (dom.sections.g11.compareCount) {
          dom.sections.g11.compareCount.addEventListener('change', () => {
            state.sections.g11.topN = dom.sections.g11.compareCount.value || '3';
            renderSection('g11');
          });
        }
        document.addEventListener('fullscreenchange', () => {
          const fullPanel = document.fullscreenElement && document.fullscreenElement.classList && document.fullscreenElement.classList.contains('panel')
            ? document.fullscreenElement
            : null;
          if (fullPanel) moveGlobalFiltersToFullscreen(fullPanel);
          else restoreGlobalFiltersFromFullscreen();
          updateFullButtons();
          renderAll();
        });
        window.addEventListener('scroll', updateStickyFilterPosition, { passive: true });
        window.addEventListener('resize', handleViewportChange);
        window.addEventListener('orientationchange', handleViewportChange);
        window.addEventListener('keydown', event => {
          if (event.key === 'Escape' && dom.shareModal && !dom.shareModal.hidden) {
            closeShareModal();
          }
        });
        document.addEventListener('click', event => {
          if (dom.global.channelDropdown && !dom.global.channelDropdown.contains(event.target)) {
            dom.global.channelDropdown.classList.remove('open');
          }
          if (dom.global.categoryDropdown && !dom.global.categoryDropdown.contains(event.target)) {
            dom.global.categoryDropdown.classList.remove('open');
          }
          if (dom.global.advertisorDropdown && !dom.global.advertisorDropdown.contains(event.target)) {
            dom.global.advertisorDropdown.classList.remove('open');
          }
          if (dom.sheetMenu && dom.sheetBtn && !dom.sheetMenu.contains(event.target) && !dom.sheetBtn.contains(event.target)) {
            hideSheetMenu();
          }
          SECTION_KEYS.forEach(sectionKey => {
            ['channelDropdown', 'categoryDropdown', 'advertisorDropdown'].forEach(field => {
              const dropdown = dom.sections[sectionKey][field];
              if (dropdown && !dropdown.contains(event.target)) {
                dropdown.classList.remove('open');
              }
            });
          });
        });
      }
      syncGlobalState();
      applyGlobalStateToSections();
      state.initialized = true;
      if (dom.sections.g3.heatmapBtn && dom.sections.g3.barBtn) {
        dom.sections.g3.heatmapBtn.classList.toggle('active', state.sections.g3.view === 'heat');
        dom.sections.g3.barBtn.classList.toggle('active', state.sections.g3.view === 'bar');
      }
      updateFullButtons();
      handleViewportChange();
    }
    function loadRows(rows, status, preprocessMetadata = null, options = {}) {
      state.rawRows = rows;
      state.standardizedRows = rows;
      state.preprocessMetadata = preprocessMetadata;
      state.cleanedRows = cleanRows(rows);
      if (!state.rawRows.length) {
        throw new Error('The selected CSV file is empty.');
      }
      if (!state.cleanedRows.length) {
        throw new Error('No valid dashboard rows remain after applying the exclusion rules.');
      }
      initializeSections();
      renderExcluded();
      clearWorkbookSelection({
        preserveSuccessState: !!options.preserveSheetSuccessState,
        preserveWorkbook: !!options.preserveWorkbookSelection
      });
      setStatus(status, false);
      renderAll();
    }
    if (dom.fileUpload) {
      if (dom.uploadBtn) {
        dom.uploadBtn.addEventListener('click', () => {
          resetDashboardState();
          dom.fileUpload.click();
        });
      }
      dom.fileUpload.addEventListener('change', async event => {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        try {
          setStatus(`Reading file: ${file.name}`, false);
          const fileName = String(file.name || '').toLowerCase();
          if (fileName.endsWith('.csv')) {
            const preprocessed = await parseUploadedCsvFile(file);
            setUploadSuccessState(true);
            clearWorkbookSelection();
            loadRows(preprocessed.dashboardRows, `Loaded CSV file: ${file.name}`, preprocessed.metadata);
          } else if (fileName.endsWith('.xlsx')) {
            await prepareWorkbookSelection(file);
          } else {
            throw new Error('Unsupported file format. Please select a .csv or .xlsx file.');
          }
        } catch (error) {
          setUploadSuccessState(false);
          clearWorkbookSelection();
          setStatus(error.message || 'Could not read the selected file', true);
        } finally {
          event.target.value = '';
        }
      });
    }
    if (dom.sheetBtn) {
      dom.sheetBtn.addEventListener('click', () => {
        toggleSheetMenu();
      });
    }
    if (Array.isArray(window.PRELOADED_DATASET)) {
      loadRows(window.PRELOADED_DATASET, 'Loaded shared dashboard snapshot.');
      if (window.PRELOADED_DASHBOARD_STATE) {
        applyExportedState(window.PRELOADED_DASHBOARD_STATE);
      }
    } else {
      renderExcluded();
      initializeSections();
      renderAll();
      setStatus('', false);
    }
  </script>
</body>
</html>
"""
html = html.replace("__GENERATED_AT__", payload["generatedAt"])
html = html.replace("__REPORT_DATE__", report_date)
html = html.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=True))
html = html.replace("__COLUMN_MAPPING_CONFIG_JSON__", json.dumps(column_mapping_config, ensure_ascii=True))
html = html.replace("__VALUE_MAPPING_CONFIG_JSON__", json.dumps(value_mapping_config, ensure_ascii=True))
html = html.replace("__XLSX_BUNDLE__", xlsx_bundle)
html = html.replace("__GLOBAL_FILTER_HTML__", build_global_filter_html())
html = html.replace("__SECTIONS_HTML__", build_sections_html())
html = html.replace("__TAIL_SUMMARY_HTML__", build_tail_summary_html())
html = html.replace("__DATASET_SUMMARY_HTML__", build_dataset_summary_html())
html = html.replace("__STATE_SECTIONS_JS__", build_state_sections_js())
html = html.replace("__DOM_SECTIONS_JS__", build_dom_sections_js())
OUTPUT_PATH.write_text(html, encoding="utf-8")
print(OUTPUT_PATH)
