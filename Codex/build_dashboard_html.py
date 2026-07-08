import csv
import json
from datetime import datetime
from pathlib import Path
CSV_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT.csv")
OUTPUT_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT Dashboard.html")
STANDALONE_OUTPUT_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT Dashboard Standalone.html")
MOBILE_OUTPUT_PATH = Path(r"D:\Vs - Code Work\Codex\CTV FCT Dashboard Mobile.html")
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
rows = []
with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh)
    for record in reader:
        rows.append(
            {
                "channel": (record.get("Channel Name") or "").strip(),
                "date": parse_date(record.get("Pdate") or ""),
                "adtime": (record.get("Adst") or "").strip(),
                "product": (record.get("Brand Name") or "").strip(),
                "company": (record.get("Company") or "").strip(),
                "aaddur": parse_int(record.get("Aaddur") or "0"),
                "category": (record.get("Category") or "").strip(),
            }
        )
generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
report_date = datetime.now().strftime("%d %b %Y")
payload = {
    "rows": [],
    "excluded": EXCLUDED,
    "generatedAt": generated_at,
}
embedded_payload = {
    "rows": rows,
    "excluded": EXCLUDED,
    "generatedAt": generated_at,
}
def select_control(control_id: str, label: str, options: str = "", extra: str = "") -> str:
    return f'<div><label class="label" for="{control_id}">{label}</label><select id="{control_id}"{extra}>{options}</select></div>'
def date_control(control_id: str, label: str) -> str:
    return f'<div><label class="label" for="{control_id}">{label}</label><input id="{control_id}" type="date"></div>'
def reset_control(control_id: str) -> str:
    return f'<div><label class="label">&nbsp;</label><button id="{control_id}" type="button">Reset</button></div>'
def category_dropdown(section_key: str) -> str:
    arrow = "â–¾" if section_key == "g1" else "&#9660;"
    return f"""          <div class="multi-dropdown" id="{section_key}CategoryDropdown">
            <label class="label" for="{section_key}CategoryTrigger">Category</label>
            <button class="multi-dropdown-trigger" id="{section_key}CategoryTrigger" type="button">
              <span class="multi-dropdown-value" id="{section_key}CategoryValue">All Categories</span>
              <span>{arrow}</span>
            </button>
            <div class="multi-dropdown-panel">
              <input class="multi-dropdown-search" id="{section_key}CategorySearch" type="text" placeholder="Search categories">
              <div class="multi-dropdown-actions">
                <button id="{section_key}CategoryAll" type="button">Select All</button>
                <button id="{section_key}CategoryClear" type="button">Clear All</button>
              </div>
              <div class="multi-dropdown-options" id="{section_key}CategoryOptions"></div>
            </div>
            <select id="{section_key}Category" multiple hidden></select>
          </div>"""
def section_block(section_class: str, title: str, controls: list[str], chart_id: str, extras: str = "", head_actions: str = "") -> str:
    return f"""    <section class="{section_class}">
      <div class="section-head">
        <h2>{title}</h2>
      </div>
      <div class="panel section-card">
        <div class="section-controls">
{chr(10).join(controls)}
        </div>
        <div class="chart-head">
          <div class="chart-actions">
{head_actions}
            <button class="full-btn" id="{chart_id[:2]}FullBtn" type="button">Full Screen</button>
          </div>
        </div>
{extras}
        <div class="chart-box" id="{chart_id}"></div>
      </div>
    </section>"""
def build_sections_html() -> str:
    top_n = '<option value="10">Top 10</option><option value="20">Top 20</option>'
    return "\n\n".join([
        section_block("section graph1-scope", "Top Advertiser (FCT in Seconds)", [select_control("g1TopN", "Top N", top_n), date_control("g1Start", "Start Date"), date_control("g1End", "End Date"), select_control("g1Channel", "Channel"), category_dropdown("g1"), reset_control("g1Reset")], "g1Chart", '        <div class="legend" id="g1Legend"></div>'),
        section_block("section", "Top Advertiser by Channels (FCT in Seconds)", [select_control("g2TopN", "Top N", top_n), date_control("g2Start", "Start Date"), date_control("g2End", "End Date"), select_control("g2Channel", "Channel"), category_dropdown("g2"), reset_control("g2Reset")], "g2Chart", '        <div class="legend" id="g2Legend"></div>', '            <div class="toggle-group">\n              <button class="toggle-btn active" id="g2BarBtn" type="button">Bar Chart</button>\n              <button class="toggle-btn" id="g2PieBtn" type="button">Pie Chart</button>\n            </div>\n'),
        section_block("section", "Top Advertiser by Date (FCT in Seconds)", [select_control("g3TopN", "Top N", top_n), date_control("g3Start", "Start Date"), date_control("g3End", "End Date"), select_control("g3Channel", "Channel"), category_dropdown("g3"), reset_control("g3Reset")], "g3Chart", '        <div class="legend" id="g3Legend"></div>'),
        section_block("section", "Channel Category Overview", [select_control("g4TopN", "Category View", top_n), date_control("g4Start", "Start Date"), date_control("g4End", "End Date"), select_control("g4Channel", "Channel"), reset_control("g4Reset")], "g4Chart"),
        section_block("section", "FCT Hourly Analysis", [date_control("g5Start", "Start Date"), date_control("g5End", "End Date"), select_control("g5Channel", "Channel"), category_dropdown("g5"), select_control("g5Advertisor", "Advertiser"), select_control("g5Time", "Time", '<option value="minutes">Minutes</option><option value="seconds">Seconds</option>'), reset_control("g5Reset")], "g5Chart", '        <div class="legend-scale" id="g5Legend">\n          <span>Low AD Duration</span>\n          <div class="legend-gradient"></div>\n          <span>High AD Duration</span>\n        </div>\n        <div class="total-panel">\n          <div class="total-title">Total</div>\n          <div class="total-grid" id="g5TotalGrid"></div>\n        </div>'),
    ])
def build_state_sections_js() -> str:
    return "\n".join([
        "        g1: { topN: '10', start: '', end: '', channel: '', category: [], view: 'bar' },",
        "        g2: { topN: '10', start: '', end: '', channel: '', category: [], view: 'bar' },",
        "        g3: { topN: '10', start: '', end: '', channel: '', category: [], view: 'bar' },",
        "        g4: { topN: '10', start: '', end: '', channel: '', category: '', view: 'heat' },",
        "        g5: { start: '', end: '', channel: '', category: [], advertisor: '', time: 'minutes', view: 'heat' }",
    ])
def build_dom_sections_js() -> str:
    section_fields = {
        "g1": ["topN", "start", "end", "channel", "category", "categoryDropdown", "categoryTrigger", "categoryValue", "categorySearch", "categoryOptions", "categoryAll", "categoryClear", "reset", "legend", "chart", "panel", "fullBtn"],
        "g2": ["topN", "start", "end", "channel", "category", "categoryDropdown", "categoryTrigger", "categoryValue", "categorySearch", "categoryOptions", "categoryAll", "categoryClear", "reset", "legend", "chart", "panel", "fullBtn", "barBtn", "pieBtn"],
        "g3": ["topN", "start", "end", "channel", "category", "categoryDropdown", "categoryTrigger", "categoryValue", "categorySearch", "categoryOptions", "categoryAll", "categoryClear", "reset", "legend", "chart", "panel", "fullBtn"],
        "g4": ["topN", "start", "end", "channel", "reset", "chart", "panel", "fullBtn"],
        "g5": ["start", "end", "channel", "category", "categoryDropdown", "categoryTrigger", "categoryValue", "categorySearch", "categoryOptions", "categoryAll", "categoryClear", "advertisor", "time", "reset", "legend", "chart", "totalGrid", "panel", "fullBtn"],
    }
    suffix = {"topN": "TopN", "start": "Start", "end": "End", "channel": "Channel", "category": "Category", "categoryDropdown": "CategoryDropdown", "categoryTrigger": "CategoryTrigger", "categoryValue": "CategoryValue", "categorySearch": "CategorySearch", "categoryOptions": "CategoryOptions", "categoryAll": "CategoryAll", "categoryClear": "CategoryClear", "reset": "Reset", "legend": "Legend", "chart": "Chart", "fullBtn": "FullBtn", "barBtn": "BarBtn", "pieBtn": "PieBtn", "advertisor": "Advertisor", "time": "Time", "totalGrid": "TotalGrid"}
    blocks = []
    for key, fields in section_fields.items():
        lines = [f"        {key}: {{"]
        for field in fields:
            lines.append(f"          panel: document.getElementById('{key}Chart').closest('.panel')," if field == "panel" else f"          {field}: document.getElementById('{key}{suffix[field]}'),")
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
      --bg: #050b14;
      --bg-2: #0b1524;
      --panel: #111d30;
      --panel-2: #16253c;
      --line: rgba(210, 225, 244, 0.16);
      --line-strong: rgba(210, 225, 244, 0.26);
      --text: #f4f8ff;
      --muted: #c0cde0;
      --shadow: 0 22px 56px rgba(0, 0, 0, 0.45);
      --font: "Roboto", "Segoe UI", Arial, sans-serif;
      --accent-1: #6bb5ff;
      --accent-2: #57e0cf;
      --accent-3: #ffcf70;
      --accent-4: #ff8ca8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: var(--font);
      background:
        radial-gradient(circle at top right, rgba(107, 181, 255, 0.14), transparent 18%),
        radial-gradient(circle at top left, rgba(87, 224, 207, 0.10), transparent 20%),
        linear-gradient(180deg, #030812, var(--bg) 44%, var(--bg-2));
    }
    .page {
      max-width: 1600px;
      margin: 0 auto;
      padding: 34px 32px 48px;
    }
    .hero, .panel {
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 18px;
      transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
    }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.8fr) minmax(320px, 0.95fr);
      gap: 28px;
      padding: 34px 36px;
      align-items: center;
      position: relative;
      overflow: hidden;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at top right, rgba(107, 181, 255, 0.18), transparent 24%),
        linear-gradient(135deg, rgba(255,255,255,0.03), transparent 55%);
      pointer-events: none;
    }
    .hero-copy,
    .hero-actions {
      position: relative;
      z-index: 1;
    }
    .hero h1 {
      margin: 0;
      font-size: 52px;
      font-weight: 900;
      letter-spacing: 1.4px;
      line-height: 1;
    }
    .hero-subtitle {
      margin: 10px 0 0;
      color: #d7e6fb;
      font-size: 16px;
      letter-spacing: 0.4px;
    }
    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }
    .meta-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid rgba(210, 225, 244, 0.14);
      background: rgba(255,255,255,0.04);
      color: #e8f1ff;
      font-size: 12px;
      font-weight: 700;
    }
    .hero-actions {
      display: flex;
      flex-direction: column;
      gap: 14px;
      align-items: stretch;
    }
    .upload-box {
      border: 1px solid rgba(210, 225, 244, 0.14);
      border-radius: 16px;
      padding: 18px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .label {
      display: block;
      margin-bottom: 8px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.9px;
      color: var(--muted);
    }
    input, select, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      background: #000000;
      color: var(--text);
      font: inherit;
      transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease, background 160ms ease;
    }
    input:hover, select:hover, button:hover,
    input:focus, select:focus, button:focus {
      border-color: rgba(107, 181, 255, 0.44);
      box-shadow: 0 0 0 3px rgba(107, 181, 255, 0.10);
      outline: none;
    }
    input[type="date"] {
      background: #000000;
      color: #ffffff;
      color-scheme: dark;
      caret-color: #ffffff;
    }
    input[type="date"]::-webkit-datetime-edit,
    input[type="date"]::-webkit-datetime-edit-fields-wrapper,
    input[type="date"]::-webkit-datetime-edit-text,
    input[type="date"]::-webkit-datetime-edit-month-field,
    input[type="date"]::-webkit-datetime-edit-day-field,
    input[type="date"]::-webkit-datetime-edit-year-field {
      color: #ffffff;
    }
    input[type="date"]::placeholder {
      color: #ffffff;
      opacity: 1;
    }
    input[type="date"]::-webkit-calendar-picker-indicator {
      filter: brightness(0) invert(1);
      opacity: 1;
      cursor: pointer;
    }
    input::file-selector-button {
      border: 0;
      border-radius: 10px;
      padding: 8px 10px;
      margin-right: 10px;
      background: rgba(107, 181, 255, 0.16);
      color: var(--text);
      cursor: pointer;
      font-weight: 700;
    }
    .status {
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .section {
      margin-top: 36px;
    }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }
    .section-head h2 {
      margin: 0;
      font-size: 26px;
      font-weight: 900;
      letter-spacing: 0.2px;
    }
    .section-card {
      padding: 24px;
    }
    .panel:hover {
      transform: translateY(-2px);
      box-shadow: 0 28px 62px rgba(0, 0, 0, 0.48);
      border-color: rgba(210, 225, 244, 0.22);
    }
    .section-controls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
      align-items: end;
    }
    .graph1-scope,
    .graph1-scope .label,
    .graph1-scope .legend,
    .graph1-scope .legend *,
    .graph1-scope button,
    .graph1-scope input,
    .graph1-scope select {
      font-family: "Montserrat", "Roboto", "Segoe UI", Arial, sans-serif;
    }
    .multi-dropdown {
      position: relative;
      display: grid;
      gap: 8px;
    }
    .multi-dropdown-trigger {
      min-height: 46px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      text-align: left;
    }
    .multi-dropdown-value {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .multi-dropdown-panel {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      right: 0;
      z-index: 30;
      padding: 12px;
      border-radius: 16px;
      border: 1px solid rgba(210, 225, 244, 0.18);
      background: #08111d;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.38);
      display: none;
    }
    .multi-dropdown.open .multi-dropdown-panel {
      display: block;
    }
    .multi-dropdown-search {
      margin-bottom: 10px;
    }
    .multi-dropdown-actions {
      display: flex;
      gap: 8px;
      margin-bottom: 10px;
    }
    .multi-dropdown-actions button {
      min-width: 0;
      padding: 8px 10px;
      font-size: 11px;
    }
    .multi-dropdown-options {
      max-height: 220px;
      overflow: auto;
      display: grid;
      gap: 6px;
      padding-right: 4px;
    }
    .multi-dropdown-option {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(255,255,255,0.03);
      font-size: 13px;
      cursor: pointer;
    }
    .multi-dropdown-option input {
      width: auto;
      margin: 0;
    }
    .chart-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
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
    .toggle-group {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(255,255,255,0.04);
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
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.3px;
      cursor: pointer;
    }
    .toggle-btn.active {
      background: linear-gradient(135deg, #4289f2, #2867cf);
      color: #ffffff;
      box-shadow: 0 8px 18px rgba(40, 103, 207, 0.28);
    }
    .full-btn {
      width: auto;
      min-width: 126px;
      padding: 10px 16px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.3px;
      cursor: pointer;
    }
    .pdf-btn {
      width: 100%;
      border-radius: 16px;
      padding: 13px 16px;
      background: linear-gradient(135deg, #2f74ff, #5aa8ff);
      color: #ffffff;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.3px;
      box-shadow: 0 10px 24px rgba(47, 116, 255, 0.28);
    }
    .chart-box {
      height: 500px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
      padding: 16px;
    }
    .legend {
      margin-bottom: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .legend-scale {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .total-panel {
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(210, 225, 244, 0.12);
      background: linear-gradient(180deg, rgba(17, 29, 48, 0.96), rgba(13, 24, 40, 0.96));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .total-title {
      color: #f4f8ff;
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0.3px;
      margin-bottom: 10px;
    }
    .total-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px 12px;
    }
    .total-chip {
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(8, 17, 29, 0.86);
      border: 1px solid rgba(216,227,241,0.12);
    }
    .total-chip-label {
      color: #bcd1ea;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .total-chip-value {
      color: #f8fbff;
      font-size: 15px;
      font-weight: 800;
    }
    .legend-gradient {
      flex: 1;
      height: 12px;
      border-radius: 999px;
      border: 1px solid rgba(210, 225, 244, 0.18);
      background: linear-gradient(90deg, #1a2434 0%, #23496f 25%, #2d73a9 50%, #3996d9 75%, #73c5ff 100%);
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 7px;
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
    .excluded-inline {
      color: #ffd98e;
      font-size: 14px;
      line-height: 1.7;
      letter-spacing: 0.2px;
    }
    .excluded-inline strong {
      color: #fff2cc;
    }
    .excluded-items {
      color: #ffb86b;
      font-weight: 700;
    }
    .empty {
      height: 100%;
      min-height: 180px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 14px;
    }
    .summary-lines {
      display: grid;
      gap: 12px;
      color: #e8f1ff;
      font-size: 15px;
      line-height: 1.7;
    }
    .summary-line {
      position: relative;
      padding: 14px 16px 14px 20px;
      border: 1px solid rgba(210, 225, 244, 0.10);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.03);
    }
    .summary-line::before {
      content: "";
      position: absolute;
      left: 0;
      top: 10px;
      bottom: 10px;
      width: 4px;
      border-radius: 999px;
      background: linear-gradient(180deg, var(--accent-1), var(--accent-2));
    }
    .info-note {
      margin-top: 14px;
      color: #bfd0e7;
      font-size: 13px;
      line-height: 1.6;
    }
    .panel:fullscreen, .panel:-webkit-full-screen {
      width: 100vw;
      height: 100vh;
      margin: 0;
      padding: 28px;
      border-radius: 0;
      overflow: auto;
      background: linear-gradient(180deg, #0f1a2d, #111d30);
    }
    .panel:fullscreen .chart-box, .panel:-webkit-full-screen .chart-box {
      height: calc(100vh - 190px);
      min-height: 560px;
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
        background: #08111d !important;
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
      .hero, .section-controls {
        grid-template-columns: 1fr;
      }
      .hero {
        padding: 28px 24px;
      }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-copy">
        <h1>CTV FCT Dashboard</h1>
        <p class="hero-subtitle">Advertising Analytics Dashboard</p>
        <div class="hero-meta">
          <div class="meta-pill">Report Date: __REPORT_DATE__</div>
          <div class="meta-pill">Last Updated: __GENERATED_AT__</div>
        </div>
      </div>
      <div class="hero-actions">
        <div class="upload-box">
          <label class="label" for="fileUpload">Upload CSV</label>
          <input id="fileUpload" type="file" accept=".csv">
          <div class="status" id="statusText">Choose a CSV file to generate the dashboard.</div>
        </div>
        <button class="pdf-btn" id="pdfBtn" type="button">Download Dashboard PDF</button>
      </div>
    </section>
    <section class="section">
      <div class="excluded-inline">
        <strong>Excluded Categories:</strong>
        <span class="excluded-items" id="excludedChips"></span>
      </div>
    </section>
    <section class="section">
      <div class="panel section-card">
        <div class="section-head">
          <h2>Dashboard Summary</h2>
        </div>
        <div class="summary-lines" id="summaryLines"></div>
      </div>
    </section>
__SECTIONS_HTML__
  <script>
    const PAYLOAD = __PAYLOAD_JSON__;
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
      heat: ['#1a2434', '#23496f', '#2d73a9', '#3996d9', '#73c5ff']
    };
    const state = {
      rawRows: [],
      cleanedRows: [],
      initialized: false,
      sections: {
__STATE_SECTIONS_JS__
      }
    };
    const dom = {
      fileUpload: document.getElementById('fileUpload'),
      pdfBtn: document.getElementById('pdfBtn'),
      statusText: document.getElementById('statusText'),
      excludedChips: document.getElementById('excludedChips'),
      summaryLines: document.getElementById('summaryLines'),
      sections: {
__DOM_SECTIONS_JS__
      }
    };
    const SECTION_KEYS = ['g1', 'g2', 'g3', 'g4', 'g5'];
    const CATEGORY_SECTION_KEYS = ['g1', 'g2', 'g3', 'g5'];
    function formatNumber(value) { return numberFormat.format(value || 0); }
    function metricLabel() { return 'AD Duration'; }
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
      if (/^\\d{4}-\\d{2}-\\d{2}$/.test(raw)) return raw;
      const parts = raw.split('-').map(p => p.trim());
      if (parts.length === 3) {
        let [day, month, year] = parts;
        if (year.length === 2) year = '20' + year.padStart(2, '0');
        return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
      }
      return raw;
    }
    function normalizeRow(record) {
      const aaddur = Number.parseInt(String(record['Aaddur'] || '0').replace(/,/g, ''), 10);
      return {
        channel: String(record['Channel Name'] || '').trim(),
        date: normalizeDate(record['Pdate'] || ''),
        adtime: normalizeTimeValue(record['Adst'] || ''),
        product: String(record['Brand Name'] || '').trim(),
        company: String(record['Company'] || '').trim(),
        aaddur: Number.isFinite(aaddur) ? aaddur : 0,
        category: String(record['Category'] || '').trim()
      };
    }
    function parseCsv(text) {
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
        } else if (ch === ',' && !inQuotes) {
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
      if (!lines.length) return rows;
      const headers = lines[0].map(v => (v || '').trim());
      const index = Object.fromEntries(headers.map((value, idx) => [value, idx]));
      const required = ['Channel Name', 'Pdate', 'Brand Name', 'Company', 'Aaddur', 'Category'];
      for (const key of required) {
        if (!(key in index)) throw new Error('Missing required column: ' + key);
      }
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        rows.push(normalizeRow({
          'Channel Name': line[index['Channel Name']] || '',
          'Pdate': line[index['Pdate']] || '',
          'Adst': 'Adst' in index ? (line[index['Adst']] || '') : '',
          'Brand Name': line[index['Brand Name']] || '',
          'Company': line[index['Company']] || '',
          'Aaddur': line[index['Aaddur']] || '',
          'Category': line[index['Category']] || ''
        }));
      }
      return rows;
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
    function colorForValue(value, maxValue) {
      const scale = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)));
      const palette = chartPalettes.heat;
      if (scale === 0) return palette[0];
      if (scale < 0.25) return palette[1];
      if (scale < 0.5) return palette[2];
      if (scale < 0.75) return palette[3];
      return palette[4];
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
      const scale = Math.max(0.18, Math.min(1, value / Math.max(maxValue, 1)));
      const rgb = hexToRgb(channelColor(channel, 'g2'));
      const alpha = 0.16 + scale * 0.78;
      return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha.toFixed(3)})`;
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
      box.innerHTML = '';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('class', 'chart');
      box.appendChild(svg);
      return { svg, width, height };
    }
    function svgEl(name, attrs = {}) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
      return el;
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
        x, y, fill,
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
    function rerenderSections(sectionKeys) {
      sectionKeys.forEach(renderSection);
    }
    function syncAndRenderSections(sectionKeys) {
      sectionKeys.forEach(syncSectionState);
      rerenderSections(sectionKeys);
    }
    function updateCategoryDropdownValue(sectionKey) {
      const controls = dom.sections[sectionKey];
      const selected = state.sections[sectionKey].category || [];
      if (!controls.categoryValue) return;
      if (!selected.length) {
        controls.categoryValue.textContent = 'All Categories';
        return;
      }
      controls.categoryValue.textContent = selected.length <= 2
        ? selected.join(', ')
        : `${selected.length} Categories Selected`;
    }
    function syncSharedCategorySelection(selectedValues, sourceSectionKey = 'g1', options = {}) {
      const nextValues = uniqueSorted(selectedValues || []);
      sharedCategorySections().forEach(sectionKey => {
        state.sections[sectionKey].category = [...nextValues];
        const controls = dom.sections[sectionKey];
        if (controls.categorySearch && sectionKey !== sourceSectionKey && !options.preserveSearchText) {
          controls.categorySearch.value = '';
        }
      });
      sharedCategorySections().forEach(sectionKey => {
        populateCategoryDropdown(sectionKey, dom.sections[sectionKey].categorySearch ? dom.sections[sectionKey].categorySearch.value : '');
      });
    }
    function populateCategoryDropdown(sectionKey, filterText = '') {
      const controls = dom.sections[sectionKey];
      const select = controls.category;
      const selected = new Set(state.sections[sectionKey].category || []);
      const values = uniqueSorted(state.cleanedRows.map(row => row.category));
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
      controls.categoryOptions.innerHTML = filtered.map(value => `
        <label class="multi-dropdown-option">
          <input type="checkbox" value="${value.replace(/"/g, '&quot;')}" ${selected.has(value) ? 'checked' : ''}>
          <span>${value}</span>
        </label>
      `).join('');
      controls.categoryOptions.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.addEventListener('change', () => {
          const next = new Set(state.sections[sectionKey].category || []);
          if (input.checked) next.add(input.value);
          else next.delete(input.value);
          syncSharedCategorySelection([...next], sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
          renderSummary();
        });
      });
      updateCategoryDropdownValue(sectionKey);
    }
    function initializeSectionControls(sectionKey) {
      const rows = state.cleanedRows;
      const dates = uniqueSorted(rows.map(row => row.date));
      const channels = uniqueSorted(rows.map(row => row.channel));
      const section = dom.sections[sectionKey];
      populateSelect(section.channel, channels, 'All Channels');
      if (sharedCategorySections().includes(sectionKey)) {
        populateCategoryDropdown(sectionKey);
      } else if (section.category) {
        populateSelect(section.category, uniqueSorted(rows.map(row => row.category)), 'All Categories');
      }
      if (sectionKey === 'g5') {
        const advertisors = uniqueSorted(rows.map(row => row.product));
        populateSelect(section.advertisor, advertisors, 'All Advertisers');
        section.time.value = 'minutes';
      }
      section.start.value = dates[0] || '';
      section.end.value = dates[dates.length - 1] || '';
      section.start.min = dates[0] || '';
      section.start.max = dates[dates.length - 1] || '';
      section.end.min = dates[0] || '';
      section.end.max = dates[dates.length - 1] || '';
    }
    function getSectionRows(sectionKey) {
      const sectionState = state.sections[sectionKey];
      let rows = state.cleanedRows.filter(row => {
        if (sectionState.channel && row.channel !== sectionState.channel) return false;
        if (Array.isArray(sectionState.category) && sectionState.category.length && !sectionState.category.includes(row.category)) return false;
        if (!Array.isArray(sectionState.category) && sectionState.category && row.category !== sectionState.category) return false;
        if (sectionState.start && row.date && row.date < sectionState.start) return false;
        if (sectionState.end && row.date && row.date > sectionState.end) return false;
        if (sectionKey === 'g5') {
          const hour = parseHourValue(row.adtime);
          if (hour === null || hour < 6) return false;
          if (sectionState.advertisor && row.product !== sectionState.advertisor) return false;
        }
        return true;
      });
      return rows;
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
      return {
        channels,
        rows: topAdvertisors.map(item => ({
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
    function drawAxes(svg, margin, plotW, plotH, xTitle, yTitle, width, height, maxValue) {
      for (let i = 0; i <= 4; i++) {
        const y = margin.top + plotH - (plotH * i / 4);
        svg.appendChild(svgEl('line', { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, stroke: 'rgba(216,227,241,0.18)', 'stroke-width': 1 }));
        const tick = svgEl('text', { x: margin.left - 8, y: y + 5, fill: '#d8e3f1', 'font-size': 12, 'text-anchor': 'end' });
        tick.textContent = formatNumber(Math.round(maxValue * i / 4));
        svg.appendChild(tick);
      }
      const xAxisLabel = svgEl('text', {
        x: margin.left + plotW / 2,
        y: height - 6,
        fill: '#f4f8ff',
        'font-size': 15,
        'font-weight': 700,
        'text-anchor': 'middle'
      });
      xAxisLabel.textContent = xTitle;
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 20,
        y: margin.top + plotH / 2,
        fill: '#f4f8ff',
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
        `<span class="legend-item"><i class="legend-swatch" style="background:${item.color}"></i>${item.label}</span>`
      ).join('');
    }
    function drawGraph1(rows) {
      const topAdvertisers = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g1.topN, 10));
      if (!topAdvertisers.length) {
        drawEmpty(dom.sections.g1.chart, 'No data available for selected filters');
        dom.sections.g1.legend.innerHTML = '';
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g1.chart);
      svg.style.fontFamily = '"Montserrat", "Roboto", "Segoe UI", Arial, sans-serif';
      const margin = { top: 18, right: 24, bottom: 118, left: 70 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxValue = Math.max(...topAdvertisers.map(item => item.total), 1);
      drawAxes(svg, margin, plotW, plotH, 'Top Advertisers', 'Total Advertisement Duration', width, height, maxValue);
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
          fill: '#e0f0ff',
          'font-size': 11,
          'font-weight': 800,
          'text-anchor': 'middle'
        });
        dataLabel.textContent = formatNumber(item.total);
        svg.appendChild(dataLabel);
        addWrappedText(svg, item.advertisor, x + barW / 2, margin.top + plotH + 18, 12, '#f4f8ff', 10, 'middle', 700);
      });
      renderLegend(dom.sections.g1.legend, [{ label: 'Total AD Duration', color: chartPalettes.g1[0] }]);
    }
    function drawGraph2Bar(rows) {
      const topAdvertisors = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g2.topN, 10));
      const matrix = buildAdvertisorChannelMatrix(rows, topAdvertisors);
      if (!matrix.rows.length || !matrix.channels.length) {
        drawEmpty(dom.sections.g2.chart, 'No data available for selected filters');
        dom.sections.g2.legend.innerHTML = '';
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g2.chart);
      const margin = { top: 18, right: 24, bottom: 118, left: 58 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxValue = Math.max(...matrix.rows.flatMap(row => matrix.channels.map(channel => row.values[channel] || 0)), 1);
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
            stroke: 'rgba(216,227,241,0.20)',
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
            fill: '#ffffff', 'font-size': 11.5, 'font-weight': 700, 'text-anchor': 'middle'
          });
          dataLabel.textContent = value ? formatNumber(value) : '';
          svg.appendChild(dataLabel);
        });
        addWrappedText(
          svg,
          row.advertisor,
          startX + ((matrix.channels.length * (barW + 2)) - 2) / 2,
          margin.top + plotH + 18,
          12,
          '#eef5ff',
          10.5,
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
      const distribution = buildChannelDistribution(rows);
      if (!distribution.length) {
        drawEmpty(dom.sections.g2.chart, 'No data available for selected filters');
        dom.sections.g2.legend.innerHTML = '';
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g2.chart);
      const cx = width * 0.44;
      const cy = height * 0.53;
      const radius = Math.min(width, height) * 0.31;
      const innerRadius = radius * 0.42;
      const total = distribution.reduce((sum, item) => sum + item.total, 0) || 1;
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
        svg.appendChild(svgEl('path', { d: path, fill, stroke: '#08111d', 'stroke-width': 1.2 }));
        const title = svgEl('title');
        title.textContent = `Channel: ${item.channel}\nAD Duration: ${formatNumber(item.total)} sec\nShare: ${(fraction * 100).toFixed(0)}%`;
        svg.lastChild.appendChild(title);
        const mid = startAngle + (endAngle - startAngle) / 2;
        const label = polar(radius + 38, mid);
        addWrappedText(svg, `${item.channel} ${formatNumber(item.total)} sec ${(fraction * 100).toFixed(0)}% AD`, label.x, label.y, 16, '#f4f8ff', 10, mid > Math.PI / 2 || mid < -Math.PI / 2 ? 'end' : 'start', 700);
        startAngle = endAngle;
      });
      const centerTop = svgEl('text', { x: cx, y: cy - 8, fill: '#f4f8ff', 'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle' });
      centerTop.textContent = 'AD Duration';
      svg.appendChild(centerTop);
      const centerValue = svgEl('text', { x: cx, y: cy + 16, fill: '#dcecff', 'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle' });
      centerValue.textContent = `${formatNumber(total)} sec`;
      svg.appendChild(centerValue);
      renderLegend(dom.sections.g2.legend, distribution.map(item => ({
        label: item.channel,
        color: channelColor(item.channel, 'g2')
      })));
    }
    function drawGraph3(rows) {
      const topAdvertisors = aggregateAdvertisors(rows).slice(0, Number.parseInt(state.sections.g3.topN, 10));
      const matrix = buildAdvertisorDateMatrix(rows, topAdvertisors);
      if (!matrix.rows.length || !topAdvertisors.length) {
        drawEmpty(dom.sections.g3.chart, 'No data available for selected filters');
        dom.sections.g3.legend.innerHTML = '';
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g3.chart);
      const margin = { top: 18, right: 24, bottom: 86, left: 58 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const maxValue = Math.max(...matrix.rows.flatMap(row => topAdvertisors.map(item => row.values[item.advertisor] || 0)), 1);
      drawAxes(svg, margin, plotW, plotH, 'Date', metricLabel(), width, height, maxValue);
      const groupW = plotW / Math.max(matrix.rows.length, 1);
      const barW = Math.max((groupW - 14) / Math.max(topAdvertisors.length, 1) - 2, 3);
      for (let gi = 0; gi <= matrix.rows.length; gi++) {
        const x = margin.left + gi * groupW;
        svg.appendChild(svgEl('line', {
          x1: x,
          y1: margin.top,
          x2: x,
          y2: margin.top + plotH,
          stroke: 'rgba(216,227,241,0.18)',
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
          const dataLabel = svgEl('text', {
            x: x + barW / 2, y: Math.max(y - 6, margin.top + 10),
            fill: '#ffffff', 'font-size': 11.5, 'font-weight': 700, 'text-anchor': 'middle'
          });
          dataLabel.textContent = value ? formatNumber(value) : '';
          svg.appendChild(dataLabel);
        });
        addWrappedText(svg, formatDate(row.date), startX + ((topAdvertisors.length * (barW + 2)) - 2) / 2, margin.top + plotH + 16, 10, '#eef5ff', 10.5, 'middle', 700);
      });
      renderLegend(dom.sections.g3.legend, topAdvertisors.map((item, idx) => ({
        label: item.advertisor,
        color: chartPalettes.g3[idx % chartPalettes.g3.length]
      })));
    }
    function drawGraph4(rows) {
      const matrix = buildHeatmapMatrix(rows, Number.parseInt(state.sections.g4.topN, 10));
      if (!matrix.channels.length || !matrix.categories.length) {
        drawEmpty(dom.sections.g4.chart, 'No data available for selected filters');
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g4.chart);
      const margin = { top: 24, right: 28, bottom: 92, left: 156 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const cellW = plotW / Math.max(matrix.channels.length, 1);
      const cellH = plotH / Math.max(matrix.categories.length, 1);
      const backgroundFill = '#08111d';
      svg.appendChild(svgEl('rect', {
        x: margin.left, y: margin.top, width: plotW, height: plotH, rx: 12,
        fill: 'rgba(255,255,255,0.02)', stroke: 'rgba(255,255,255,0.08)'
      }));
      const xAxisLabel = svgEl('text', {
        x: margin.left + plotW / 2, y: height - 10, fill: '#f4f8ff',
        'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle'
      });
      xAxisLabel.textContent = 'Channel';
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 28, y: margin.top + plotH / 2, fill: '#f4f8ff',
        'font-size': 17, 'font-weight': 800, 'text-anchor': 'middle',
        transform: `rotate(-90 28 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = 'Category';
      svg.appendChild(yAxisLabel);
      for (let ci = 0; ci <= matrix.channels.length; ci++) {
        const x = margin.left + ci * cellW;
        svg.appendChild(svgEl('line', {
          x1: x, y1: margin.top, x2: x, y2: margin.top + plotH,
          stroke: 'rgba(216,227,241,0.18)', 'stroke-width': 1
        }));
      }
      for (let ri = 0; ri <= matrix.categories.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', {
          x1: margin.left, y1: y, x2: margin.left + plotW, y2: y,
          stroke: 'rgba(216,227,241,0.18)', 'stroke-width': 1
        }));
      }
      matrix.channels.forEach((channel, ci) => {
        addWrappedText(svg, channel, margin.left + ci * cellW + cellW / 2, margin.top + plotH + 18, 10, '#eef5ff', 11.5, 'middle', 700);
      });
      matrix.categories.forEach((category, ri) => {
        addWrappedText(svg, category, margin.left - 10, margin.top + ri * cellH + cellH * 0.56, 18, '#eef5ff', 11.5, 'end', 700);
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
            fill: hasValue ? colorForValue(value, matrix.maxValue) : backgroundFill,
            stroke: hasValue ? 'rgba(216,227,241,0.16)' : 'rgba(8,17,29,0.96)',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = hasValue
            ? `Channel: ${channel}\nCategory: ${category}\nAD Duration: ${formatNumber(value)} sec`
            : `Channel: ${channel}\nCategory: ${category}\nNo data available`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (hasValue && cellW >= 52 && cellH >= 28) {
            const label = svgEl('text', {
              x: x + cellW / 2, y: y + cellH * 0.58,
              fill: '#f8fbff', 'font-size': 12, 'font-weight': 800, 'text-anchor': 'middle'
            });
            label.textContent = formatNumber(value);
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
        return;
      }
      const { svg, width, height } = makeSvg(dom.sections.g5.chart);
      const margin = { top: 28, right: 28, bottom: 78, left: 140 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const cellW = plotW / Math.max(matrix.hours.length, 1);
      const cellH = plotH / Math.max(matrix.channels.length, 1);
      const xAxisLabel = svgEl('text', { x: margin.left + plotW / 2, y: height - 8, fill: '#f4f8ff', 'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle' });
      xAxisLabel.textContent = 'Hour of Day';
      svg.appendChild(xAxisLabel);
      const yAxisLabel = svgEl('text', {
        x: 24, y: margin.top + plotH / 2, fill: '#f4f8ff',
        'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle',
        transform: `rotate(-90 24 ${margin.top + plotH / 2})`
      });
      yAxisLabel.textContent = 'Channel';
      svg.appendChild(yAxisLabel);
      matrix.hours.forEach((hour, ci) => {
        addWrappedText(svg, hourLabel(hour), margin.left + ci * cellW + cellW / 2, margin.top + plotH + 18, 5, '#d8e3f1', 10.5, 'middle', 700);
      });
      matrix.channels.forEach((channel, ri) => {
        addWrappedText(svg, channel, margin.left - 10, margin.top + ri * cellH + cellH * 0.56, 14, '#d8e3f1', 11, 'end', 700);
      });
      for (let ci = 0; ci <= matrix.hours.length; ci++) {
        const x = margin.left + ci * cellW;
        svg.appendChild(svgEl('line', {
          x1: x, y1: margin.top, x2: x, y2: margin.top + plotH,
          stroke: 'rgba(216,227,241,0.20)', 'stroke-width': 1
        }));
      }
      for (let ri = 0; ri <= matrix.channels.length; ri++) {
        const y = margin.top + ri * cellH;
        svg.appendChild(svgEl('line', {
          x1: margin.left, y1: y, x2: margin.left + plotW, y2: y,
          stroke: 'rgba(216,227,241,0.20)', 'stroke-width': 1
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
            stroke: 'rgba(216,227,241,0.18)',
            'stroke-width': 1
          });
          const title = svgEl('title');
          title.textContent = `Channel: ${channel}\nTime Slot: ${hourSlotLabel(hour)}\nAD Duration: ${unitMeta.format(displayValue)}`;
          rect.appendChild(title);
          svg.appendChild(rect);
          if (value && cellW >= 28 && cellH >= 22) {
            const label = svgEl('text', {
              x: x + cellW / 2, y: y + cellH * 0.58,
              fill: '#f4f8ff', 'font-size': 11.5, 'font-weight': 800, 'text-anchor': 'middle'
            });
            label.textContent = unitMeta.unit === 'minutes'
              ? displayValue.toFixed(2)
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
          <div class="total-chip-value">${unitMeta.unit === 'minutes' ? item.displayValue.toFixed(2) + ' min' : formatNumber(Math.round(item.displayValue)) + ' sec'}</div>
        </div>
      `).join('');
    }
    function renderExcluded() {
      dom.excludedChips.textContent = PAYLOAD.excluded.join(' • ');
    }
    function formatPercent(value) {
      return `${(value || 0).toFixed(2)}%`;
    }
    function graph5UnitMeta() {
      const unit = state.sections.g5.time || 'seconds';
      if (unit === 'minutes') {
        return {
          unit,
          convert: value => value / 60,
          format: value => `${value.toFixed(2)} min`
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
      const channelValues = collectSelectedValues(SECTION_KEYS, 'channel');
      const categoryValues = collectSelectedValues(CATEGORY_SECTION_KEYS, 'category');
      const advertisorValues = collectSelectedValues(['g5'], 'advertisor');
      const dateRanges = SECTION_KEYS
        .map(sectionKey => ({
          start: state.sections[sectionKey].start || '',
          end: state.sections[sectionKey].end || ''
        }))
        .filter(range => range.start || range.end);
      return state.cleanedRows.filter(row => {
        if (channelValues.length && !channelValues.includes(row.channel)) return false;
        if (categoryValues.length && !categoryValues.includes(row.category)) return false;
        if (advertisorValues.length && !advertisorValues.includes(row.product)) return false;
        if (dateRanges.length) {
          const inAnyRange = dateRanges.some(range => {
            if (range.start && row.date && row.date < range.start) return false;
            if (range.end && row.date && row.date > range.end) return false;
            return true;
          });
          if (!inAnyRange) return false;
        }
        return true;
      });
    }
    function renderSummary() {
      const rows = getDashboardSummaryRows();
      if (!rows.length) {
        dom.summaryLines.innerHTML = [
          'Total records analyzed: 0.',
          'Overall advertisement duration: 0 seconds.',
          'Top advertisers are not available for the current selection.',
          'Category performance cannot be determined for the current selection.',
          'No significant trend is available because the filtered dataset is empty.'
        ].map(line => `<div class="summary-line">${line}</div>`).join('');
        return;
      }
      const totalRecords = rows.length;
      const total = rows.reduce((sum, row) => sum + row.aaddur, 0);
      const advertisers = aggregateAdvertisors(rows);
      const topAdvertisor = advertisers[0];
      const topChannel = buildChannelDistribution(rows)[0];
      const categories = buildCategoryDistribution(rows);
      const topCategory = categories[0];
      const lowestCategory = categories[categories.length - 1];
      const topThreeAdvertisers = advertisers.slice(0, 3).map(item => item.advertisor).join(', ');
      const topAdvertisorPct = total ? (topAdvertisor.total / total) * 100 : 0;
      const topChannelPct = total ? (topChannel.total / total) * 100 : 0;
      const topCategoryPct = total ? (topCategory.total / total) * 100 : 0;
      const lines = [
        `Total records analyzed: ${formatNumber(totalRecords)}.`,
        `Overall advertisement duration across the filtered dataset is ${formatNumber(total)} seconds.`,
        `Top advertisers: ${topThreeAdvertisers || topAdvertisor.advertisor}. The leading advertiser is ${topAdvertisor.advertisor} with ${formatNumber(topAdvertisor.total)} seconds, contributing ${formatPercent(topAdvertisorPct)} of total AD Duration.`,
        `Highest performing category is ${topCategory.category} with ${formatNumber(topCategory.total)} seconds, while the lowest performing category is ${lowestCategory.category} with ${formatNumber(lowestCategory.total)} seconds.`,
        `Key trend: ${topChannel.channel} is the strongest channel at ${formatNumber(topChannel.total)} seconds (${formatPercent(topChannelPct)}), and ${topCategory.category} remains the most dominant category with ${formatPercent(topCategoryPct)} of AD Duration.`
      ];
      dom.summaryLines.innerHTML = lines.map(line => `<div class="summary-line">${line}</div>`).join('');
    }
    function categoryFilterLabel(sectionState, emptyLabel) {
      return Array.isArray(sectionState.category)
        ? ((sectionState.category || []).length ? sectionState.category.join(', ') : emptyLabel)
        : (sectionState.category || emptyLabel);
    }
    function filterSummaryLines(sectionKey, sectionState, forPage = false) {
      const categoryLabel = categoryFilterLabel(sectionState, forPage ? 'All' : 'all');
      if (sectionKey === 'g5') {
        return forPage
          ? [
              `Start Date: ${sectionState.start ? formatDate(sectionState.start) : 'All'}`,
              `End Date: ${sectionState.end ? formatDate(sectionState.end) : 'All'}`,
              `Channel: ${sectionState.channel || 'All'}`,
              `Category: ${categoryLabel}`,
              `Advertiser: ${sectionState.advertisor || 'All'}`,
              `Time: ${sectionState.time || 'minutes'}`
            ]
          : [`<strong>${sectionKey.toUpperCase()}</strong> | Start: ${sectionState.start || 'all'}, End: ${sectionState.end || 'all'}, Channel: ${sectionState.channel || 'all'}, Category: ${categoryLabel}, Advertiser: ${sectionState.advertisor || 'all'}, Time: ${sectionState.time || 'minutes'}`];
      }
      if (sectionKey === 'g4') {
        return forPage
          ? [
              `Top N: ${sectionState.topN || 'All'}`,
              `Start Date: ${sectionState.start ? formatDate(sectionState.start) : 'All'}`,
              `End Date: ${sectionState.end ? formatDate(sectionState.end) : 'All'}`,
              `Channel: ${sectionState.channel || 'All'}`
            ]
          : [`<strong>${sectionKey.toUpperCase()}</strong> | Top N: ${sectionState.topN || 'all'}, Start: ${sectionState.start || 'all'}, End: ${sectionState.end || 'all'}, Channel: ${sectionState.channel || 'all'}`];
      }
      return forPage
        ? [
            `Top N: ${sectionState.topN || 'All'}`,
            `Start Date: ${sectionState.start ? formatDate(sectionState.start) : 'All'}`,
            `End Date: ${sectionState.end ? formatDate(sectionState.end) : 'All'}`,
            `Channel: ${sectionState.channel || 'All'}`,
            `Category: ${categoryLabel}`
          ]
        : [`<strong>${sectionKey.toUpperCase()}</strong> | Top N: ${sectionState.topN || 'all'}, Start: ${sectionState.start || 'all'}, End: ${sectionState.end || 'all'}, Channel: ${sectionState.channel || 'all'}, Category: ${categoryLabel}`];
    }
    function getActiveFiltersMarkup() {
      return SECTION_KEYS
        .map(sectionKey => `<div class="summary-line">${filterSummaryLines(sectionKey, state.sections[sectionKey])[0]}</div>`)
        .join('');
    }
    function getSelectedDateRangeText() {
      const ranges = SECTION_KEYS
        .map(sectionKey => ({
          start: state.sections[sectionKey].start || '',
          end: state.sections[sectionKey].end || ''
        }))
        .filter(range => range.start || range.end);
      if (!ranges.length) return 'All Dates';
      const starts = ranges.map(range => range.start).filter(Boolean).sort((a, b) => a.localeCompare(b));
      const ends = ranges.map(range => range.end).filter(Boolean).sort((a, b) => a.localeCompare(b));
      const start = starts[0] || '';
      const end = ends[ends.length - 1] || '';
      if (!start && !end) return 'All Dates';
      if (start && end) return `${formatDate(start)} to ${formatDate(end)}`;
      return formatDate(start || end);
    }
    function getActiveFiltersPageMarkup() {
      return SECTION_KEYS.map(sectionKey => `
          <div class="pdf-filter-card">
            <h3>${sectionKey.toUpperCase()}</h3>
            ${filterSummaryLines(sectionKey, state.sections[sectionKey], true).map(line => `<div class="summary-line">${line}</div>`).join('')}
          </div>
        `).join('');
    }
    function exportDashboardPdf() {
      const printWindow = window.open('', '_blank', 'width=1280,height=900');
      if (!printWindow) return;
      const title = 'CTV FCT Dashboard';
      const generatedAt = new Date().toLocaleString();
      const summaryHtml = document.getElementById('summaryLines').innerHTML;
      const graphSections = ['g1Chart', 'g2Chart', 'g3Chart', 'g4Chart', 'g5Chart']
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
        body { background: #08111d !important; }
        .page.pdf-export { max-width: none; padding: 0; }
        .pdf-page { min-height: 100vh; padding: 32px; page-break-after: always; break-after: page; display: flex; flex-direction: column; gap: 18px; }
        .pdf-page:last-child { page-break-after: auto; break-after: auto; }
        .pdf-cover { justify-content: center; }
        .pdf-cover .hero { margin: 0; }
        .pdf-page-head h2 { margin: 6px 0 0; font-size: 30px; font-weight: 900; }
        .pdf-kicker { color: #9fc2f2; font-size: 12px; font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }
        .pdf-filter-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
        .pdf-filter-card { background: linear-gradient(180deg, #111d30, #16253c); border: 1px solid rgba(210, 225, 244, 0.14); border-radius: 18px; padding: 18px; }
        .pdf-filter-card h3 { margin: 0 0 12px; font-size: 18px; }
        .pdf-page .panel { margin: 0; box-shadow: none; }
        .pdf-page .chart-box { height: calc(100vh - 260px); min-height: 620px; }
        @media print {
          .pdf-page { min-height: auto; }
          .pdf-page .chart-box { height: 620px !important; min-height: 620px !important; }
        }
      </style></head><body><div class="page pdf-export">
      <section class="pdf-page pdf-cover">
        <section class="hero">
          <div class="hero-copy">
            <h1>${title}</h1>
            <p class="hero-subtitle">Advertising Analytics Dashboard</p>
            <div class="hero-meta">
              <div class="meta-pill">Date Range: ${getSelectedDateRangeText()}</div>
              <div class="meta-pill">Last Updated: ${generatedAt}</div>
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
      </div></body></html>`);
      printWindow.document.close();
      printWindow.focus();
      setTimeout(() => printWindow.print(), 300);
    }
    function renderSection(sectionKey) {
      const rows = getSectionRows(sectionKey);
      if (sectionKey === 'g1') drawGraph1(rows);
      if (sectionKey === 'g2') {
        if (state.sections.g2.view === 'pie') {
          drawGraph2Pie(rows);
        } else {
          drawGraph2Bar(rows);
        }
      }
      if (sectionKey === 'g3') drawGraph3(rows);
      if (sectionKey === 'g4') drawGraph4(rows);
      if (sectionKey === 'g5') drawGraph5(rows);
    }
    function renderAll() {
      rerenderSections(SECTION_KEYS);
      renderSummary();
    }
    function syncSectionState(sectionKey) {
      const controls = dom.sections[sectionKey];
      const target = state.sections[sectionKey];
      if (controls.topN) target.topN = controls.topN.value;
      target.start = controls.start.value;
      target.end = controls.end.value;
      target.channel = controls.channel.value;
      if (sharedCategorySections().includes(sectionKey)) {
        target.category = Array.from(controls.category.selectedOptions).map(option => option.value);
      } else if (controls.category) {
        target.category = controls.category.value;
      }
      if (sectionKey === 'g5') {
        target.advertisor = controls.advertisor.value;
        target.time = controls.time.value;
      }
    }
    function bindSection(sectionKey) {
      const controls = dom.sections[sectionKey];
      const controlKeys = sectionKey === 'g5'
        ? ['start', 'end', 'channel', 'advertisor', 'time', 'category']
        : ['topN', 'start', 'end', 'channel', 'category'];
      controlKeys.forEach(key => {
        if (!controls[key]) return;
        controls[key].addEventListener('change', () => {
          syncSectionState(sectionKey);
          renderSection(sectionKey);
          renderSummary();
        });
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
          controls.categoryDropdown.classList.add('open');
          syncSharedCategorySelection(uniqueSorted(state.cleanedRows.map(row => row.category)), sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
          renderSummary();
        });
        controls.categoryClear.addEventListener('click', () => {
          controls.categoryDropdown.classList.add('open');
          syncSharedCategorySelection([], sectionKey, { preserveSearchText: true });
          syncAndRenderSections(sharedCategorySections());
          renderSummary();
        });
      }
      controls.reset.addEventListener('click', () => {
        if (controls.topN) controls.topN.value = '10';
        controls.channel.value = '';
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
          state.sections.g3.view = 'bar';
        }
        if (sectionKey === 'g5') {
          controls.advertisor.value = '';
          controls.time.value = 'minutes';
        }
        if (sharedCategorySections().includes(sectionKey)) {
          syncAndRenderSections(sharedCategorySections());
        } else {
          syncSectionState(sectionKey);
          renderSection(sectionKey);
        }
        renderSummary();
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
    function initializeSections() {
      SECTION_KEYS.forEach(sectionKey => {
        initializeSectionControls(sectionKey);
        if (!state.initialized) bindSection(sectionKey);
        syncSectionState(sectionKey);
        if (!state.initialized) {
          dom.sections[sectionKey].fullBtn.addEventListener('click', () => toggleFullScreen(sectionKey));
        }
      });
      if (!state.initialized) {
        if (dom.pdfBtn) {
          dom.pdfBtn.addEventListener('click', exportDashboardPdf);
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
        document.addEventListener('fullscreenchange', () => {
          updateFullButtons();
          renderAll();
        });
        document.addEventListener('click', event => {
          sharedCategorySections().forEach(sectionKey => {
            const dropdown = dom.sections[sectionKey].categoryDropdown;
            if (dropdown && !dropdown.contains(event.target)) {
              dropdown.classList.remove('open');
            }
          });
        });
      }
      state.initialized = true;
      updateFullButtons();
    }
    function loadRows(rows, status) {
      state.rawRows = rows;
      state.cleanedRows = cleanRows(rows);
      initializeSections();
      renderExcluded();
      dom.statusText.textContent = status;
      renderAll();
    }
    if (dom.fileUpload) {
      dom.fileUpload.addEventListener('change', async event => {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        try {
          const text = await file.text();
          loadRows(parseCsv(text), `Loaded file: ${file.name}`);
        } catch (error) {
          dom.statusText.textContent = error.message || 'Could not read CSV file';
        }
      });
    }
    renderExcluded();
    initializeSections();
    renderAll();
  </script>
</body>
</html>
"""
html = html.replace("__GENERATED_AT__", payload["generatedAt"])
html = html.replace("__REPORT_DATE__", report_date)
html = html.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=True))
html = html.replace("__SECTIONS_HTML__", build_sections_html())
html = html.replace("__STATE_SECTIONS_JS__", build_state_sections_js())
html = html.replace("__DOM_SECTIONS_JS__", build_dom_sections_js())
def build_standalone_html(source_html: str) -> str:
    standalone_markup = """      <div class="upload-box">
        <label class="label">Embedded Dataset</label>
        <div class="status" id="statusText">Loaded embedded dataset and ready for interactive use.</div>
      </div>"""
    start_marker = '      <div class="upload-box">'
    end_marker = "      </div>"
    start = source_html.find(start_marker)
    if start != -1:
        end = source_html.find(end_marker, start)
        if end != -1:
            end += len(end_marker)
            standalone = source_html[:start] + standalone_markup + source_html[end:]
        else:
            standalone = source_html
    else:
        standalone = source_html
    standalone = standalone.replace(
        json.dumps(payload, ensure_ascii=True),
        json.dumps(embedded_payload, ensure_ascii=True),
        1,
    )
    standalone = standalone.replace(
        "    renderExcluded();\n    initializeSections();\n    renderAll();",
        "    loadRows(PAYLOAD.rows, 'Loaded embedded dataset');",
        1,
    )
    return standalone
def build_mobile_html(source_html: str) -> str:
    mobile_css = """
    @media (max-width: 768px) {
      .page {
        padding: 14px 12px 24px;
      }
      .hero {
        padding: 22px 18px;
        gap: 16px;
      }
      .hero h1 {
        font-size: 34px;
        letter-spacing: 0.6px;
      }
      .hero-subtitle {
        font-size: 14px;
      }
      .hero-meta {
        gap: 10px;
      }
      .meta-pill {
        width: 100%;
        justify-content: center;
      }
      .section {
        margin-top: 22px;
      }
      .section-head h2 {
        font-size: 21px;
      }
      .section-card {
        padding: 16px;
      }
      .section-controls {
        grid-template-columns: 1fr;
        gap: 10px;
      }
      .chart-head {
        flex-direction: column;
        align-items: flex-start;
      }
      .chart-actions {
        width: 100%;
        flex-wrap: wrap;
        margin-left: 0;
      }
      .toggle-group {
        width: 100%;
        justify-content: space-between;
      }
      .toggle-btn,
      .full-btn {
        min-width: 0;
        flex: 1 1 auto;
      }
      .chart-box {
        height: 360px;
        padding: 10px;
      }
      .legend,
      .legend-scale {
        gap: 8px;
        font-size: 11px;
      }
      .panel:fullscreen .chart-box,
      .panel:-webkit-full-screen .chart-box {
        height: calc(100vh - 220px);
        min-height: 420px;
      }
    }
"""
    return source_html.replace("  </style>", mobile_css + "\n  </style>", 1)
standalone_html = build_standalone_html(html)
mobile_html = build_mobile_html(standalone_html)
OUTPUT_PATH.write_text(html, encoding="utf-8")
STANDALONE_OUTPUT_PATH.write_text(standalone_html, encoding="utf-8")
MOBILE_OUTPUT_PATH.write_text(mobile_html, encoding="utf-8")
print(OUTPUT_PATH)
print(STANDALONE_OUTPUT_PATH)
print(MOBILE_OUTPUT_PATH)
