"""
patch_dashboard.py
------------------
Patches output/chrome_report_dashboard.html to inject:
  1. Landing tracker data from frequency_report.json (or landing_history.csv)
  2. landing_channel_tracker.js script
  3. Fixes the reportBundle fallback to include the landing key

Run with: python patch_dashboard.py
"""
from __future__ import annotations
import json, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "output" / "chrome_report_dashboard.html"
JSON_PATH = BASE_DIR / "output" / "frequency_report.json"
TRACKER_JS_PATH = BASE_DIR / "static" / "landing_channel_tracker.js"
LANDING_CSV = BASE_DIR / "history" / "landing_history.csv"


# ── 1. Read tracker JS ────────────────────────────────────────────────────────
if not TRACKER_JS_PATH.exists():
    print(f"ERROR: {TRACKER_JS_PATH} not found.")
    raise SystemExit(1)

tracker_js = TRACKER_JS_PATH.read_text(encoding="utf-8")
print(f"✓ Read landing_channel_tracker.js ({len(tracker_js):,} chars)")


# ── 2. Build landing payload ──────────────────────────────────────────────────
landing_payload = None

# First try to extract from frequency_report.json
if JSON_PATH.exists():
    print(f"  Reading {JSON_PATH.name} ({JSON_PATH.stat().st_size // 1024 // 1024} MB)…")
    try:
        raw = JSON_PATH.read_text(encoding="utf-8")
        # Strip the JS wrapper: window.__CHROME_REPORT_DATA__ = {...};
        match = re.match(r'^window\.__CHROME_REPORT_DATA__\s*=\s*(\{.*\});?\s*$', raw, re.DOTALL)
        if match:
            bundle = json.loads(match.group(1))
            if "landing" in bundle:
                landing_payload = bundle["landing"]
                weeks = landing_payload.get("weeks", [])
                records = landing_payload.get("records", [])
                print(f"✓ Extracted landing data from JSON: {len(weeks)} weeks, {len(records):,} records")
    except Exception as e:
        print(f"  Warning: Could not read JSON: {e}")

# Fallback: build from CSV
if landing_payload is None:
    print(f"  Building landing payload from {LANDING_CSV.name}…")
    try:
        import pandas as pd
        from datetime import datetime, timezone

        df = pd.read_csv(LANDING_CSV, dtype=str).fillna("")
        weeks = sorted(
            list(df["Week"].unique()),
            key=lambda w: (int(re.search(r"\d+", w).group()) if re.search(r"\d+", w) else 0, w),
        )
        grouped: dict = {}
        for _, row in df.iterrows():
            sf_crn = str(row.get("SF CRN", row.get("SFRN NUMBER", ""))).strip()
            put_up_lcn = str(row.get("PUT-UP LCN", row.get("Popup LCN", ""))).strip()
            put_up_channel = str(row.get("PUT-UP CHANNEL", row.get("Popup Channel", ""))).strip()
            key = (row.get("Band",""), row.get("Market",""), row.get("City",""),
                   row.get("Headend",""), row.get("State",""), row.get("District",""),
                   row.get("Feed",""), row.get("CRN NO",""), sf_crn, row.get("MSO",""))
            if key not in grouped:
                grouped[key] = {
                    "band": str(row.get("Band","")).strip(),
                    "market": str(row.get("Market","")).strip(),
                    "city": str(row.get("City","")).strip(),
                    "headend": str(row.get("Headend","")).strip(),
                    "state_name": str(row.get("State","")).strip(),
                    "district": str(row.get("District","")).strip(),
                    "feed": str(row.get("Feed","")).strip(),
                    "crn_no": str(row.get("CRN NO","")).strip(),
                    "sf_crn": sf_crn,
                    "mso": str(row.get("MSO","")).strip(),
                    "put_up_lcn": put_up_lcn,
                    "put_up_channel": put_up_channel,
                    "weeks": {},
                }
            wk = str(row.get("Week","")).strip()
            grouped[key]["weeks"][wk] = {
                "lcn_1":     str(row.get("Landing 1 LCN","")).strip(),
                "channel_1": str(row.get("Landing 1 Channel", row.get("Landing 1",""))).strip(),
                "genre_1":   str(row.get("Landing 1 Genre","")).strip(),
                "lcn_2":     str(row.get("Landing 2 LCN","")).strip(),
                "channel_2": str(row.get("Landing 2 Channel", row.get("Landing 2",""))).strip(),
                "genre_2":   str(row.get("Landing 2 Genre","")).strip(),
                "lcn_3":     str(row.get("Landing 3 LCN","")).strip(),
                "channel_3": str(row.get("Landing 3 Channel", row.get("Landing 3",""))).strip(),
                "genre_3":   str(row.get("Landing 3 Genre","")).strip(),
                "lcn_b1":    str(row.get("Barker 1 LCN","")).strip(),
                "barker_1":  str(row.get("Barker 1 Channel", row.get("Barker 1",""))).strip(),
                "lcn_b2":    str(row.get("Barker 2 LCN","")).strip(),
                "barker_2":  str(row.get("Barker 2 Channel", row.get("Barker 2",""))).strip(),
                "put_up_lcn": put_up_lcn,
                "put_up_channel": put_up_channel,
            }
        landing_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "records": list(grouped.values()),
            "message": "",
        }
        print(f"✓ Built landing payload from CSV: {len(weeks)} weeks, {len(grouped):,} records")
    except Exception as e:
        print(f"ERROR building landing payload: {e}")
        raise SystemExit(1)


# ── 3. Patch the HTML ─────────────────────────────────────────────────────────
if not HTML_PATH.exists():
    print(f"ERROR: {HTML_PATH} not found.")
    raise SystemExit(1)

print(f"\n  Reading {HTML_PATH.name}…")
html = HTML_PATH.read_text(encoding="utf-8")

# Build the data JSON (safe for embedding in <script>)
landing_json = json.dumps(landing_payload, ensure_ascii=False, separators=(",", ":"))
landing_json_safe = landing_json.replace("</", "<\\/")

# ─── 3a. Fix fallback reportBundle: add landing key if not present ─────────────
OLD_OTS_FALLBACK = '  ots: { generated_at: "", weeks: [], visible_weeks: [], filters: { markets: [], channels: [] }, table: { records: [], total_count: 0 }, message: "OTS data file could not be loaded.", source_directory: "" }\r\n};'
NEW_OTS_FALLBACK = '  ots: { generated_at: "", weeks: [], visible_weeks: [], filters: { markets: [], channels: [] }, table: { records: [], total_count: 0 }, message: "OTS data file could not be loaded.", source_directory: "" },\r\n  landing: { generated_at: "", weeks: [], records: [], message: "Landing data file could not be loaded." }\r\n};'

OLD_OTS_FALLBACK_LF = '  ots: { generated_at: "", weeks: [], visible_weeks: [], filters: { markets: [], channels: [] }, table: { records: [], total_count: 0 }, message: "OTS data file could not be loaded.", source_directory: "" }\n};'
NEW_OTS_FALLBACK_LF = '  ots: { generated_at: "", weeks: [], visible_weeks: [], filters: { markets: [], channels: [] }, table: { records: [], total_count: 0 }, message: "OTS data file could not be loaded.", source_directory: "" },\n  landing: { generated_at: "", weeks: [], records: [], message: "Landing data file could not be loaded." }\n};'

if OLD_OTS_FALLBACK in html:
    html = html.replace(OLD_OTS_FALLBACK, NEW_OTS_FALLBACK, 1)
    print("✓ Fixed reportBundle fallback to include landing key (CRLF)")
elif OLD_OTS_FALLBACK_LF in html:
    html = html.replace(OLD_OTS_FALLBACK_LF, NEW_OTS_FALLBACK_LF, 1)
    print("✓ Fixed reportBundle fallback to include landing key (LF)")
elif "landing: { generated_at" in html:
    print("  reportBundle fallback already has landing key — skipping")
else:
    print("  WARNING: Could not patch reportBundle fallback (pattern not found)")


# ─── 3b. Check if tracker script is already injected ─────────────────────────
TRACKER_MARKER = "initLandingTrackerDashboard"
if TRACKER_MARKER in html:
    print(f"  Tracker script already injected — skipping duplicate injection")
else:
    # Build injection block
    injection = (
        "\r\n  <script>\r\n"
        f"window.__LANDING_TRACKER_STANDALONE_DATA__ = (window.__CHROME_REPORT_DATA__ && window.__CHROME_REPORT_DATA__.landing)"
        f" || {landing_json_safe};\r\n"
        "  </script>\r\n"
        "  <script>\r\n"
        + tracker_js
        + "\r\n  </script>\r\n"
    )

    # Inject before </body>
    CLOSE_BODY_CRLF = "</body>\r\n</html>"
    CLOSE_BODY_LF   = "</body>\n</html>"

    if CLOSE_BODY_CRLF in html:
        html = html.replace(CLOSE_BODY_CRLF, injection + "</body>\r\n</html>", 1)
        print("✓ Injected landing_channel_tracker.js before </body> (CRLF)")
    elif CLOSE_BODY_LF in html:
        html = html.replace(CLOSE_BODY_LF, injection + "</body>\n</html>", 1)
        print("✓ Injected landing_channel_tracker.js before </body> (LF)")
    else:
        # Last resort: append before </body>
        body_idx = html.rfind("</body>")
        if body_idx >= 0:
            html = html[:body_idx] + injection + html[body_idx:]
            print("✓ Injected landing_channel_tracker.js (rfind fallback)")
        else:
            print("ERROR: Could not find </body> in HTML")
            raise SystemExit(1)


# ─── 3c. Write patched HTML ───────────────────────────────────────────────────
HTML_PATH.write_text(html, encoding="utf-8")
print(f"\n✅ Patched HTML saved: {HTML_PATH}")
print(f"   Total lines: {html.count(chr(10)):,}")
print(f"\nOpen the file in your browser:")
print(f"  {HTML_PATH}")
