"""Compare distinct audience IPs in an existing viewer index; never sum daily uniques."""
import argparse
import csv
from datetime import date, datetime, timedelta
import html
import ipaddress
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb


def normalize_ip(value):
    try:
        address = ipaddress.ip_address(value.strip())
        return str(getattr(address, "ipv4_mapped", None) or address)
    except (ValueError, AttributeError):
        return None


def dates(start, end):
    while start <= end:
        yield start
        start += timedelta(days=1)


def validate_periods(bstart, bend, tstart, tend):
    if not bstart <= bend < tstart <= tend:
        raise ValueError("Baseline must precede target; periods cannot overlap or be reversed.")
    if tend >= datetime.now(ZoneInfo("Asia/Kolkata")).date():
        raise ValueError("Only completed past dates are supported.")


def check_coverage(audit, source, requested):
    evidence = {row["date"]: row for row in audit.get("daily", [])}
    for day in requested:
        item = evidence.get(str(day), {})
        result = next((r for r in item.get("sources", []) if r.get("source") == source), {})
        if result.get("status") != "PASS" or not result.get("selected", {}).get("full_day"):
            raise ValueError(f"No full-day source evidence for {source} {day}; partial dates are excluded.")


def compare(index, audit, source, bstart, bend, tstart, tend, channels=(), all_http=False):
    validate_periods(bstart, bend, tstart, tend)
    requested = list(dates(bstart, bend)) + list(dates(tstart, tend))
    check_coverage(audit, source, requested)
    con = duckdb.connect()
    try:
        con.execute("SET threads=2")
        con.execute("SET memory_limit='2GB'")
        con.create_function("canonical_ip", normalize_ip, ["VARCHAR"], "VARCHAR", null_handling="special")
        con.from_parquet(str(index)).create_view("viewer_index")
        present = {r[0] for r in con.execute(
            "SELECT DISTINCT CAST(log_date AS DATE) FROM viewer_index WHERE source=?", [source]).fetchall()}
        missing = set(requested) - present
        if missing:
            raise ValueError(f"Viewer index is missing requested dates: {sorted(map(str, missing))}")
        filters = "" if all_http else " AND CAST(statusCode AS VARCHAR) IN ('200','206')"
        params = [tstart, source, bstart, bend, tstart, tend]
        if channels:
            filters += " AND channel_name IN (" + ",".join("?" for _ in channels) + ")"
            params.extend(channels)
        con.execute("""CREATE TEMP TABLE selected AS
            SELECT DISTINCT CASE WHEN CAST(log_date AS DATE)>=? THEN 'target' ELSE 'baseline' END period,
                canonical_ip(CAST(cliIP AS VARCHAR)) ip, channel_name
            FROM viewer_index WHERE source=? AND
                (CAST(log_date AS DATE) BETWEEN ? AND ? OR CAST(log_date AS DATE) BETWEEN ? AND ?)
                AND raw_ts_rows > 0""" + filters, params)
        excluded = con.execute("SELECT COUNT(*) FROM selected WHERE ip IS NULL").fetchone()[0]
        con.execute("DELETE FROM selected WHERE ip IS NULL")
        query = """WITH memberships AS (
            SELECT ip, BOOL_OR(period='target') t, BOOL_OR(period='baseline') b
            FROM selected {where} GROUP BY ip)
            SELECT COUNT(*) FILTER(WHERE b), COUNT(*) FILTER(WHERE t),
                   COUNT(*) FILTER(WHERE b AND t), COUNT(*) FILTER(WHERE t AND NOT b),
                   COUNT(*) FILTER(WHERE b AND NOT t) FROM memberships"""
        def row(channel):
            counts = con.execute(query.format(where="" if channel is None else "WHERE channel_name=?"),
                                 [] if channel is None else [channel]).fetchone()
            baseline, target, returning, new, absent = counts
            pct = lambda n, d: round(100 * n / d, 2) if d else None
            return dict(scope="overall" if channel is None else "channel", channel=channel or "All selected channels",
                        baseline_ips=baseline, target_ips=target, returning_ips=returning,
                        new_to_baseline_ips=new, not_seen_again_ips=absent,
                        returning_share_pct=pct(returning, target), new_share_pct=pct(new, target),
                        baseline_retention_pct=pct(returning, baseline), not_seen_again_pct=pct(absent, baseline))
        channel_names = [r[0] for r in con.execute("SELECT DISTINCT channel_name FROM selected WHERE channel_name IS NOT NULL ORDER BY 1").fetchall()]
        return dict(source=source, baseline=[str(bstart), str(bend)], target=[str(tstart), str(tend)],
                    identity="canonical audience IP, not a verified person", all_http=all_http,
                    excluded_invalid_ip_memberships=excluded, rows=[row(None), *[row(c) for c in channel_names]])
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--coverage-audit", required=True, type=Path)
    parser.add_argument("--source", required=True, choices=["fast", "stream"])
    for field in ("baseline-start", "baseline-end", "target-start", "target-end"):
        parser.add_argument("--" + field, required=True, type=date.fromisoformat)
    parser.add_argument("--channel", action="append", default=[])
    parser.add_argument("--all-http", action="store_true", help="Include failed requests as audience activity; default is 200/206 media segments.")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.index, json.loads(args.coverage_audit.read_text()), args.source,
                     args.baseline_start, args.baseline_end, args.target_start, args.target_end,
                     args.channel, args.all_http)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    keys = list(result["rows"][0])
    with (args.out_dir / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(result["rows"])
    heads = "".join(f"<th>{html.escape(k.replace('_', ' ').title())}</th>" for k in keys)
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[k]) if r[k] is not None else 'N/A')}</td>" for k in keys) + "</tr>" for r in result["rows"])
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Audience Comparison</title><style>body{{font:15px system-ui;margin:24px;color:#172332;background:#f7f9fc}}h1{{font-size:24px}}.table{{overflow:auto}}table{{border-collapse:collapse;background:white}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #d8dfe8;white-space:nowrap}}th{{background:#e3eef5}}p{{max-width:850px;line-height:1.6}}</style>
    <h1>{args.source.upper()} Audience Comparison</h1><p>Baseline: {args.baseline_start} to {args.baseline_end}. Target: {args.target_start} to {args.target_end}.</p>
    <p>Unique audience IPs are not verified people. New means absent from the selected baseline. Channel retention is same-channel overlap; overall retention spans all selected channels. Channel counts are not additive. N/A means a zero denominator. HTTP scope: {'all statuses, including failures' if args.all_http else '200/206 media segment activity'}.</p>
    <div class="table"><table><thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table></div></html>"""
    (args.out_dir / "comparison.html").write_text(document, encoding="utf-8")
    print(json.dumps(result["rows"][0], indent=2))


if __name__ == "__main__":
    main()
