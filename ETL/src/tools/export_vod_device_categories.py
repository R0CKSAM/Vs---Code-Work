"""Export published VOD viewing by date/video and five exhaustive device categories.

Default range: last seven completed IST calendar days. Unknown includes blank,
NA and unrecognized form factors. Watch hours are the dashboard's request-based
estimate (including retries/errors), not measured player viewing time.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from build_vod_query_dashboard import read_dashboard_day

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = ("mobile", "ctv", "tablet", "desktop", "unknown")
UNIT = Decimal("0.000001")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--dashboard", type=Path, default=ROOT / "output/exports/vod_stream_query_analysis_dashboard.html")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    end = args.end or (datetime.now(timezone(timedelta(hours=5, minutes=30))).date() - timedelta(days=1))
    start = args.start or end - timedelta(days=6)
    if start > end:
        parser.error("Start must be on or before end")
    target = args.output or ROOT / "output/exports" / f"vod_device_categories_{start}_{end}.csv"
    data_dir = args.dashboard.with_name(args.dashboard.stem + "_data")
    html = args.dashboard.read_text(encoding="utf-8")
    match = re.search(r"^const dashboardIndex=(.+);\r?$", html, re.M)
    if not match:
        raise ValueError("Missing dashboard date index")
    index = json.loads(match.group(1))
    # Check publication in addition to file existence: stale payloads may remain.
    published = set(re.findall(r"\d{4}-\d{2}-\d{2}", json.dumps(index)))
    dates = [str(start + timedelta(days=i)) for i in range((end-start).days+1)]
    missing = [d for d in dates if d not in published or not (data_dir / f"{d}.js").exists()]
    if missing:
        raise ValueError(f"Requested dashboard days unavailable: {missing}")
    output_rows = []
    factors = Counter()
    daily = []
    for day in dates:
        groups = {}
        source_total = Decimal(0)
        rows = read_dashboard_day(data_dir / f"{day}.js")
        for row in rows:
            if row["log_date"] != day:
                raise ValueError(f"Unexpected row date in {day}")
            key = str(row.get("content_code") or "").strip().lower() or "Unknown / Unmarked"
            group = groups.setdefault(key, {"ips": set(), "devices": set(), "hours": [Decimal(0)] * 5})
            for field, dest in (("cli_ip", "ips"), ("device_id", "devices")):
                value = str(row.get(field) or "").strip()
                if value:
                    group[dest].add(value)
            factor = str(row.get("decoded_form_factor") or "").strip().lower()
            factors[factor] += 1
            category = factor if factor in CATEGORIES else "unknown"
            hours = Decimal(str(row.get("request_watch_hours") or 0))
            if not hours.is_finite() or hours < 0:
                raise ValueError("Invalid watch hours")
            group["hours"][CATEGORIES.index(category)] += hours
            source_total += hours
        grouped_total = sum(sum(g["hours"]) for g in groups.values())
        if abs(grouped_total - source_total) > Decimal("1e-15"):
            raise ValueError(f"Watch-time reconciliation failed: {day}")
        for key, group in sorted(groups.items()):
            hours = [v.quantize(UNIT, rounding=ROUND_HALF_UP) for v in group["hours"]]
            record = {"date_ist": day, "video_key": key, "distinct_cliip": len(group["ips"]), "distinct_device_id": len(group["devices"]), "total_watch_hours": f"{sum(hours):.6f}"}
            for category, value in zip(CATEGORIES, hours):
                record[f"{category}_watch_hours"] = f"{value:.6f}"
            output_rows.append(record)
        daily.append({"date": day, "payload_rows": len(rows), "video_keys": len(groups), "source_watch_hours": str(source_total)})
        print(f"{day}: {len(groups)} video keys", flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]) if output_rows else ["date_ist", "video_key"])
        writer.writeheader()
        writer.writerows(output_rows)
    temporary.replace(target)
    target.with_suffix(".validation.json").write_text(json.dumps({"source": str(args.dashboard), "days": daily, "rows": len(output_rows), "raw_form_factors": dict(factors), "notes": ["Watch hours estimate all requests, including retries/errors.", "Unknown includes blank/NA and unrecognized device categories.", "Hours rounded to six decimals; total equals sum of displayed categories.", "Distinct IP/device counts must not be summed across rows to infer unique viewers."]}, indent=2), encoding="utf-8")
    print(f"Wrote {len(output_rows)} rows: {target}")


if __name__ == "__main__":
    main()
