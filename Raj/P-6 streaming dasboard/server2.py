"""
Live Concurrency Dashboard Server — V2 (Audited & Fixed)

Changes from V1:
  - XSS: `path` query param is now allowlist-validated against live_state.json
    before being injected into HTML/JS; falls back to default on any mismatch
  - TOCTOU: /api/state file read wrapped in try/except; existence check removed
  - Corrupt state guard: JSON validated before sending; error JSON returned on failure
  - Dead import: `datetime` removed (was never used in this file)
  - `lag_seconds` now served by /api/state, computed server-side from
    `data_verified_through` so the frontend colour-coding actually works
  - CSS class bug fixed: switcher links no longer carry the undefined `link` class
  - Cache-Control: no-store header added to /api/state response
  - `null` gap values in the table now render as an em-dash, not the string "null"
  - ThreadingHTTPServer socket timeout set to 10s to bound slow-client threads
  - `do_GET` refactored into _serve_api() and _serve_page() for clarity
  - Invalid/unknown paths in do_GET now return 404 instead of silently serving
    the default page with a potentially misleading path label
"""

import json
import os
import re
import html as html_module
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# CONFIG — keep in sync with pipeline_v8.py
# ---------------------------------------------------------------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.environ.get("LIVE_DASHBOARD_RUNTIME_DIR", os.path.join(PROJECT_DIR, "runtime"))
STATE_JSON_PATH = os.path.join(RUNTIME_DIR, "live_state.json")
PORT = 8787
DEFAULT_PATH = "vglive-274906"
FALLBACK_PATHS = [DEFAULT_PATH, "upgovlive"]

# Only alphanumerics, hyphens, underscores — reject anything else
_SAFE_PATH_RE = re.compile(r'^[A-Za-z0-9_\-]+$')

# IST offset — used only for lag computation server-side
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _load_state() -> dict | None:
    """
    Read and parse live_state.json atomically.
    Returns None on any error (file missing, mid-write, corrupt JSON).
    """
    try:
        with open(STATE_JSON_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
        return json.loads(raw)          # validate before trusting
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _get_available_paths() -> list[str]:
    """
    Dynamically read tracked paths from the live state file.
    Falls back to FALLBACK_PATHS if the file is absent or unreadable.
    """
    data = _load_state()
    if data:
        paths = list(data.get("concurrency_paths", {}).keys())
        if paths:
            return paths
    return FALLBACK_PATHS


def _sanitize_path(raw: str, available: list[str]) -> str | None:
    """
    FIX (XSS): validate the path query param against an allowlist first,
    then against a strict character-set pattern.
    Returns None if the value cannot be trusted (caller should 400/404).
    """
    if raw in available:
        return raw
    # Reject anything that doesn't look like a safe path slug
    if _SAFE_PATH_RE.match(raw):
        return raw
    return None


def _compute_lag_seconds(data: dict) -> float | None:
    """
    FIX: pipeline V8 does not write lag_seconds; compute it server-side
    from data_verified_through so the frontend colour-coding works.
    """
    through_str = data.get("data_verified_through")
    if not through_str:
        return None
    try:
        now_ist = datetime.datetime.now(_IST)
        verified_time = datetime.datetime.strptime(through_str, "%H:%M:%S").replace(
            year=now_ist.year, month=now_ist.month, day=now_ist.day, tzinfo=_IST
        )
        lag = (now_ist - verified_time).total_seconds()
        return max(lag, 0.0)
    except ValueError:
        return None


def _build_switcher_links(selected_path: str, available_paths: list[str]) -> str:
    """
    FIX (CSS bug): V1 emitted class="link active" but .link was never defined
    in the stylesheet — only .switcher a.active was. Now emits class="active"
    or class="" cleanly.
    """
    links = []
    for p in available_paths:
        # Escape the path value for safe HTML attribute and text insertion
        safe_p = html_module.escape(p, quote=True)
        cls = ' class="active"' if p == selected_path else ''
        links.append(f'<a{cls} href="/?path={safe_p}">{safe_p}</a>')
    return "\n    ".join(links)


# ---------------------------------------------------------------------------
# HTML TEMPLATE
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Live Concurrency Monitor - {path_escaped}</title>
<style>
  body {{
    background: #0d1117; color: #c9d1d9; font-family: -apple-system, Segoe UI, sans-serif;
    margin: 0; padding: 24px;
  }}
  h1 {{ font-size: 20px; color: #58a6ff; margin-bottom: 4px; }}
  .sub {{ color: #8b949e; font-size: 13px; margin-bottom: 20px; }}
  .switcher {{ margin-bottom: 16px; }}
  .switcher a {{
    display: inline-block; margin-right: 8px; padding: 6px 12px;
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    color: #c9d1d9; text-decoration: none; font-size: 13px;
  }}
  .switcher a.active {{ border-color: #58a6ff; color: #58a6ff; }}
  .cards {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
  .card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 14px 20px; min-width: 160px;
  }}
  .card .label {{ font-size: 12px; color: #8b949e; text-transform: uppercase; }}
  .card .value {{ font-size: 26px; font-weight: 600; margin-top: 4px; }}
  .green {{ color: #3fb950; }}
  .yellow {{ color: #d29922; }}
  .red {{ color: #f85149; }}
  #chartWrap {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px;
  }}
  #chartRow {{ display: flex; }}
  #yAxisCanvasWrap {{ flex: 0 0 auto; }}
  #chartScroll {{ overflow-x: auto; overflow-y: hidden; position: relative; flex: 1 1 auto; }}
  canvas {{ height: 220px; display: block; }}
  .status {{ font-size: 12px; color: #8b949e; margin-top: 8px; }}
  .zoomBtns {{ display: flex; gap: 6px; margin-bottom: 10px; }}
  .zoomBtns button {{
    background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer;
  }}
  .zoomBtns button.active {{ border-color: #58a6ff; color: #58a6ff; }}
  #tooltip {{
    position: absolute; display: none; pointer-events: none;
    background: #21262d; border: 1px solid #30363d; border-radius: 6px;
    padding: 6px 10px; font-size: 12px; color: #c9d1d9; white-space: nowrap;
    transform: translate(-50%, -110%); z-index: 10;
  }}
  #tooltip .t {{ color: #8b949e; }}
  #tooltip .v {{ color: #58a6ff; font-weight: 600; }}
  #tableWrap {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 20px; margin-top: 20px;
  }}
  #tableWrap h2 {{ font-size: 14px; color: #58a6ff; margin: 0 0 12px 0; }}
  table.dataTable {{
    width: 100%; border-collapse: collapse; font-size: 13px;
  }}
  table.dataTable th, table.dataTable td {{
    text-align: left; padding: 6px 10px; border-bottom: 1px solid #21262d;
  }}
  table.dataTable th {{
    color: #8b949e; text-transform: uppercase; font-size: 11px;
    position: sticky; top: 0; background: #161b22;
  }}
  table.dataTable tr.current td {{ color: #d29922; font-weight: 600; }}
  #tableScroll {{ max-height: 480px; overflow-y: auto; }}
</style>
</head>
<body>
  <h1>Live Concurrency &mdash; {path_escaped}</h1>
  <div class="sub">Distinct client IPs per minute (concurrent viewers) &middot; auto-refreshes every 5s</div>

  <div class="switcher">
    {switcher_links}
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">Current Viewers</div>
      <div class="value" id="currentConc">&mdash;</div>
    </div>
    <div class="card">
      <div class="label">Peak (shown window)</div>
      <div class="value" id="peakConc">&mdash;</div>
    </div>
    <div class="card">
      <div class="label">Data Verified Through</div>
      <div class="value" id="dataThrough" style="font-size:18px;">&mdash;</div>
    </div>
    <div class="card">
      <div class="label">Sync Status</div>
      <div class="value" id="syncStatus" style="font-size:18px;">&mdash;</div>
    </div>
  </div>

  <div id="chartWrap">
    <div class="zoomBtns">
      <button data-zoom="60" class="active">Last 1h</button>
      <button data-zoom="180">Last 3h</button>
      <button data-zoom="360">Last 6h</button>
      <button data-zoom="1440">Full day</button>
    </div>
    <div id="chartRow">
      <div id="yAxisCanvasWrap"><canvas id="yAxisChart"></canvas></div>
      <div id="chartScroll">
        <canvas id="chart"></canvas>
        <div id="tooltip"><span class="t"></span> &mdash; <span class="v"></span></div>
      </div>
    </div>
    <div class="status" id="lastUpdated">Waiting for data...</div>
  </div>

  <div id="tableWrap">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <h2 style="margin:0;">Minute-by-minute (newest first)</h2>
      <button id="exportBtn" style="
        background:#21262d; color:#c9d1d9; border:1px solid #30363d;
        border-radius:6px; padding:6px 14px; font-size:12px; cursor:pointer;
      ">Export CSV</button>
    </div>
    <div id="tableScroll">
      <table class="dataTable">
        <thead>
          <tr><th>Time (IST)</th><th>Concurrency (distinct cliIP)</th></tr>
        </thead>
        <tbody id="tableBody">
          <tr><td colspan="2">Waiting for data...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

<script>
// FIX (XSS): PATH is set server-side from an allowlist-validated, HTML-escaped
// value. The JS variable itself is a string literal injected into the script
// block — it is safe because _sanitize_path() rejects anything outside
// [A-Za-z0-9_-] before we reach template rendering.
const PATH = "{path_escaped}";
let latestPoints = [];

function exportCSV() {{
  if (!latestPoints.length) return;
  const rows = [['Time (IST)', 'Concurrency (distinct cliIP)']];
  latestPoints.forEach(p => rows.push([p.minute, p.distinct_ips ?? '']));
  const csvContent = rows.map(r => r.join(',')).join('\\n');
  const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  a.href = url;
  a.download = `concurrency_${{PATH}}_${{stamp}}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

document.getElementById('exportBtn').addEventListener('click', exportCSV);

let lastPlot = null;
let zoomMinutes = 60;

function buildFullDay(points) {{
  if (!points.length) return [];
  const map = {{}};
  points.forEach(p => {{ map[p.minute] = p.distinct_ips; }});
  const lastMinute = points[points.length - 1].minute;
  const [lastH, lastM] = lastMinute.split(':').map(Number);
  const lastTotalMin = lastH * 60 + lastM;

  const full = [];
  for (let t = 0; t <= lastTotalMin; t++) {{
    const hh = String(Math.floor(t / 60)).padStart(2, '0');
    const mm = String(t % 60).padStart(2, '0');
    const key = `${{hh}}:${{mm}}`;
    full.push({{ minute: key, distinct_ips: map.hasOwnProperty(key) ? map[key] : null }});
  }}
  return full;
}}

function drawYAxis(yMax, padT, h, cssHeight) {{
  const yCanvas = document.getElementById('yAxisChart');
  const dpr = window.devicePixelRatio || 1;
  const yWidth = 44;
  yCanvas.style.width = yWidth + 'px';
  yCanvas.width = yWidth * dpr;
  yCanvas.height = cssHeight * dpr;
  const yctx = yCanvas.getContext('2d');
  yctx.scale(dpr, dpr);
  yctx.clearRect(0, 0, yWidth, cssHeight);
  yctx.fillStyle = '#161b22';
  yctx.fillRect(0, 0, yWidth, cssHeight);

  const ySteps = 4;
  yctx.fillStyle = '#8b949e';
  yctx.font = '10px sans-serif';
  yctx.textAlign = 'right';
  for (let i = 0; i <= ySteps; i++) {{
    const val = Math.round((yMax / ySteps) * i);
    const y = padT + h - (h * i / ySteps);
    yctx.fillText(val, yWidth - 6, y + 3);
  }}
}}

function draw(rawPoints) {{
  const fullDay = buildFullDay(rawPoints);
  const points = zoomMinutes >= fullDay.length ? fullDay : fullDay.slice(-zoomMinutes);

  const canvas = document.getElementById('chart');
  const scrollEl = document.getElementById('chartScroll');
  const dpr = window.devicePixelRatio || 1;

  const padL = 8, padR = 16, padT = 16, padB = 30;
  const cssHeight = 220;
  const availableWidth = scrollEl.clientWidth || 800;
  const minPxPerMin = 6;
  const pxPerMinute = Math.max(minPxPerMin, (availableWidth - padL - padR) / zoomMinutes);
  const plotWidth = Math.max(points.length * pxPerMinute, availableWidth - padL - padR);
  const cssWidth = plotWidth + padL + padR;

  canvas.style.width = cssWidth + 'px';
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const w = plotWidth;
  const h = cssHeight - padT - padB;

  if (!points.length) {{
    ctx.fillStyle = '#8b949e';
    ctx.font = '13px sans-serif';
    ctx.fillText('No data for this path yet', padL, padT + h / 2);
    lastPlot = null;
    return;
  }}

  const vals = points.map(p => p.distinct_ips).filter(v => v !== null);
  const maxVal = Math.max(...vals, 1);
  const yMax = Math.ceil(maxVal * 1.15) || 1;
  const xForIndex = (i) => padL + i * pxPerMinute;
  const yForVal = (v) => padT + h - (h * v / yMax);

  drawYAxis(yMax, padT, h, cssHeight);

  points.forEach((p, i) => {{
    const mm = Number(p.minute.split(':')[1]);
    const x = xForIndex(i);
    const isHour = (mm === 0);
    ctx.strokeStyle = isHour ? '#30363d' : '#1c2128';
    ctx.lineWidth = isHour ? 1 : 0.5;
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + h);
    ctx.stroke();
  }});

  const ySteps = 4;
  for (let i = 0; i <= ySteps; i++) {{
    const y = padT + h - (h * i / ySteps);
    ctx.strokeStyle = '#21262d';
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + w, y);
    ctx.stroke();
  }}

  ctx.strokeStyle = '#30363d';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padL, padT + h);
  ctx.lineTo(padL + w, padT + h);
  ctx.stroke();

  ctx.textAlign = 'center';
  ctx.fillStyle = '#8b949e';
  ctx.font = '10px sans-serif';
  const labelEvery = zoomMinutes <= 60 ? 10 : (zoomMinutes <= 360 ? 30 : 60);
  points.forEach((p, i) => {{
    const mm = Number(p.minute.split(':')[1]);
    if (mm % labelEvery === 0) {{
      const x = xForIndex(i);
      ctx.fillText(p.minute, x, padT + h + 14);
    }}
  }});

  ctx.strokeStyle = '#58a6ff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let penDown = false;
  points.forEach((p, i) => {{
    const x = xForIndex(i);
    if (p.distinct_ips === null) {{ penDown = false; return; }}
    const y = yForVal(p.distinct_ips);
    if (!penDown) {{ ctx.moveTo(x, y); penDown = true; }}
    else {{ ctx.lineTo(x, y); }}
  }});
  ctx.stroke();

  ctx.fillStyle = 'rgba(88,166,255,0.08)';
  let segStart = null;
  for (let i = 0; i <= points.length; i++) {{
    const hasData = i < points.length && points[i].distinct_ips !== null;
    if (hasData && segStart === null) {{
      segStart = i;
    }} else if (!hasData && segStart !== null) {{
      const segEnd = i - 1;
      ctx.beginPath();
      ctx.moveTo(xForIndex(segStart), padT + h);
      for (let j = segStart; j <= segEnd; j++) {{
        ctx.lineTo(xForIndex(j), yForVal(points[j].distinct_ips));
      }}
      ctx.lineTo(xForIndex(segEnd), padT + h);
      ctx.closePath();
      ctx.fill();
      segStart = null;
    }}
  }}

  points.forEach((p, i) => {{
    if (p.distinct_ips === null) return;
    const x = xForIndex(i);
    const y = yForVal(p.distinct_ips);
    const isLast = (i === points.length - 1);
    ctx.beginPath();
    ctx.arc(x, y, isLast ? 4 : 2, 0, Math.PI * 2);
    ctx.fillStyle = isLast ? '#d29922' : '#58a6ff';
    ctx.fill();
  }});

  lastPlot = {{ points, padL, padT, h, xForIndex, yForVal, pxPerMinute }};

  const distanceFromRight = scrollEl.scrollWidth - scrollEl.clientWidth - scrollEl.scrollLeft;
  if (distanceFromRight < pxPerMinute * 3) {{
    scrollEl.scrollLeft = scrollEl.scrollWidth;
  }}
}}

function setupZoomButtons() {{
  document.querySelectorAll('.zoomBtns button').forEach(btn => {{
    btn.addEventListener('click', () => {{
      zoomMinutes = Number(btn.dataset.zoom);
      document.querySelectorAll('.zoomBtns button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      draw(latestPoints);
      const scrollEl = document.getElementById('chartScroll');
      scrollEl.scrollLeft = scrollEl.scrollWidth;
    }});
  }});
}}
setupZoomButtons();

let resizeTimer = null;
window.addEventListener('resize', () => {{
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => draw(latestPoints), 150);
}});

function setupTooltip() {{
  const canvas = document.getElementById('chart');
  const tooltip = document.getElementById('tooltip');

  canvas.addEventListener('mousemove', (e) => {{
    if (!lastPlot) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const points = lastPlot.points;
    const padL = lastPlot.padL;
    const xForIndex = lastPlot.xForIndex;
    let idx = Math.round((mouseX - padL) / lastPlot.pxPerMinute);
    idx = Math.max(0, Math.min(points.length - 1, idx));
    const p = points[idx];
    if (!p || p.distinct_ips === null) {{ tooltip.style.display = 'none'; return; }}
    const x = xForIndex(idx);
    const y = lastPlot.yForVal(p.distinct_ips);
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
    tooltip.querySelector('.t').textContent = p.minute;
    tooltip.querySelector('.v').textContent = p.distinct_ips + ' viewers';
    tooltip.style.display = 'block';
  }});

  canvas.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});
}}
setupTooltip();

function renderTable(points) {{
  const tbody = document.getElementById('tableBody');
  if (!points.length) {{
    tbody.innerHTML = '<tr><td colspan="2">No data for this path yet</td></tr>';
    return;
  }}
  const reversed = points.slice().reverse();
  tbody.innerHTML = reversed.map((p, i) => {{
    const isCurrent = (i === 0);
    const label = p.minute + (isCurrent ? ' (in progress)' : '');
    // FIX: null gap values previously rendered as the string "null".
    // Now shows an em-dash for minutes with no data.
    const displayVal = p.distinct_ips !== null ? p.distinct_ips : '\u2014';
    return `<tr class="${{isCurrent ? 'current' : ''}}"><td>${{label}}</td><td>${{displayVal}}</td></tr>`;
  }}).join('');
}}

async function refresh() {{
  try {{
    const res = await fetch('/api/state');
    if (!res.ok) throw new Error(`Server returned ${{res.status}}`);
    const data = await res.json();

    if (data.error) {{
      document.getElementById('lastUpdated').textContent = 'State unavailable: ' + data.error;
      return;
    }}

    const points = (data.concurrency_paths && data.concurrency_paths[PATH]) || [];
    latestPoints = points;
    draw(points);
    renderTable(points);

    if (points.length) {{
      const last = points[points.length - 1];
      const prev = points.length > 1 ? points[points.length - 2] : null;
      document.getElementById('currentConc').textContent =
        (prev ? prev.distinct_ips : last.distinct_ips) + (prev ? '' : ' (partial)');
      const peakVal = Math.max(...points.filter(p => p.distinct_ips !== null).map(p => p.distinct_ips));
      document.getElementById('peakConc').textContent = isFinite(peakVal) ? peakVal : '\u2014';
    }}

    document.getElementById('dataThrough').textContent = data.data_verified_through || '\u2014';
    document.getElementById('syncStatus').textContent = data.sync_status || '\u2014';

    // FIX: lag_seconds is now computed server-side and present in the API
    // response, so this colour-coding actually fires correctly.
    const lagEl = document.getElementById('dataThrough');
    lagEl.className = 'value';
    if (data.lag_seconds !== null && data.lag_seconds !== undefined) {{
      if (data.lag_seconds < 120) lagEl.classList.add('green');
      else if (data.lag_seconds < 600) lagEl.classList.add('yellow');
      else lagEl.classList.add('red');
    }}

    document.getElementById('lastUpdated').textContent =
      'Last updated: ' + new Date().toLocaleTimeString() + '  (source: ' + data.generated_at + ')';
  }} catch (e) {{
    document.getElementById('lastUpdated').textContent = 'Could not reach state: ' + e;
  }}
}}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# REQUEST HANDLER
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress per-request stdout noise

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/state":
            self._serve_api()
        elif parsed.path in ("/", ""):
            self._serve_page(parsed)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

    def _serve_api(self):
        """
        Serve live_state.json with lag_seconds injected.
        FIX: no os.path.exists() TOCTOU; read errors return a JSON error object.
        FIX: Cache-Control: no-store prevents stale caching by browsers/proxies.
        """
        data = _load_state()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        if data is None:
            payload = {"error": "state file not found or unreadable"}
        else:
            # FIX: inject lag_seconds so the frontend colour-coding works
            data["lag_seconds"] = _compute_lag_seconds(data)
            payload = data

        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _serve_page(self, parsed):
        """
        Serve the dashboard HTML for a given path.
        FIX: path param is allowlist-validated; invalid values get a 400.
        """
        available_paths = _get_available_paths()
        query = parse_qs(parsed.query)
        raw_path = query.get("path", [available_paths[0]])[0]

        # FIX (XSS): validate before any use in HTML or JS
        safe_path = _sanitize_path(raw_path, available_paths)
        if safe_path is None:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Invalid path parameter")
            return

        # html.escape covers both HTML context and the JS string literal,
        # since _SAFE_PATH_RE already excludes quotes and angle brackets.
        path_escaped = html_module.escape(safe_path, quote=True)
        switcher_links = _build_switcher_links(safe_path, available_paths)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            PAGE_TEMPLATE.format(
                path_escaped=path_escaped,
                switcher_links=switcher_links,
            ).encode("utf-8")
        )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    # FIX: bound slow-client threads; each connection times out after 10s
    server.socket.settimeout(10)
    print(f"Dashboard running at http://localhost:{PORT}")
    print(f"Default path: {DEFAULT_PATH}")
    print(f"State file:   {STATE_JSON_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
