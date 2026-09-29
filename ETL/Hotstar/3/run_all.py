"""
run_all.py — run all three OTT sports scrapers and produce one merged CSV.

Usage
-----
    # Run all three live
    python run_all.py

    # Run only specific platforms
    python run_all.py --platforms hotstar sonyliv

    # Re-parse saved raw files (no browser needed)
    python run_all.py --raw-hotstar hotstar_raw.jsonl \\
                      --raw-sonyliv sonyliv_raw.jsonl \\
                      --raw-zee5    zee5_raw.jsonl

    # Specific sport only
    python run_all.py --sport cricket

Output
------
    hotstar_sports.csv    — Hotstar sports only
    sonyliv_sports.csv    — SonyLIV sports only
    zee5_sports.csv       — ZEE5 sports only
    ott_sports_merged.csv — All three combined, same columns

Terminal summary shows:
    • per-platform counts by content type
    • top sports / tournaments across all platforms
    • which platform has what sport coverage
    • free vs subscription breakdown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ── entry-point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platforms",    nargs="*",
                    choices=["hotstar", "sonyliv", "zee5"],
                    default=["hotstar", "sonyliv", "zee5"])
    ap.add_argument("--raw-hotstar",  help="Hotstar JSONL to re-parse")
    ap.add_argument("--raw-sonyliv",  help="SonyLIV JSONL to re-parse")
    ap.add_argument("--raw-zee5",     help="ZEE5 JSONL to re-parse")
    ap.add_argument("--sport",        help="filter summary to one sport")
    ap.add_argument("--out",          default="ott_sports_merged.csv")
    ap.add_argument("--delay",        type=float, default=1.5)
    ap.add_argument("--overwrite",    action="store_true")
    a = ap.parse_args()

    dfs = []

    # ── Hotstar ──────────────────────────────────────────────────────────────
    if "hotstar" in a.platforms:
        print("\n" + "═"*50)
        print("  HOTSTAR")
        print("═"*50)
        # Hotstar uses the existing explorer/catalog combo
        # For run_all, we crawl the sports section directly
        try:
            import hotstar_catalog as hc
            from catalog_base import Browser, save, COMMON_COLUMNS

            rows:   list[dict] = []
            seen:   set        = set()

            def on_json(url, data):
                import re
                m    = re.search(r"pageName=([\w-]+)", url)
                page = m.group(1).title() if m else "Sports"
                for tray, items in hc.iter_trays(data):
                    for it in items:
                        row = hc.item_to_row(it, tray, page)
                        if not row:
                            continue
                        key = (row["content_id"], row["rail"])
                        if key in seen:
                            continue
                        seen.add(key)
                        # Map hotstar row → COMMON_COLUMNS
                        rows.append({
                            "platform":             "Hotstar",
                            "rail":                 row.get("rail"),
                            "page":                 row.get("page"),
                            "section":              row.get("series_tag"),
                            "content_id":           str(row.get("content_id", "")),
                            "series_id":            "",
                            "title":                row.get("title", ""),
                            "series_title":         "",
                            "episode_title":        "",
                            "content_type":         row.get("content_type", ""),
                            "content_subtype":      "",
                            "is_live":              False,
                            "description":          row.get("description", "") or "",
                            "year":                 row.get("year"),
                            "release_date":         None,
                            "rating":               row.get("rating"),
                            "duration_sec":         None,
                            "duration_label":       row.get("duration"),
                            "season_number":        None,
                            "episode_number":       None,
                            "episode_count":        None,
                            "sport":                row.get("series_tag"),
                            "tournament":           row.get("series_tag"),
                            "match_status":         None,
                            "match_start_utc":      None,
                            "teams":                None,
                            "primary_genre":        row.get("primary_genre"),
                            "genre_tags":           row.get("genre_tags", ""),
                            "languages":            row.get("languages", ""),
                            "original_language":    row.get("original_language"),
                            "available_languages":  row.get("available_languages", ""),
                            "language_count":       row.get("language_count"),
                            "is_free":              True,   # Hotstar AVOD
                            "subscription_required": False,
                            "pay_per_view":         False,
                            "found_in":             row.get("found_in", ""),
                            "detail_url":           row.get("detail_url"),
                            "poster_url":           row.get("poster_path"),
                        })

            if a.raw_hotstar:
                import json
                print(f"  re-parsing {a.raw_hotstar} …")
                for line in open(a.raw_hotstar, encoding="utf-8"):
                    d = json.loads(line)
                    on_json(d["url"], d["data"])
            else:
                b = Browser(on_json, raw_path="hotstar_raw.jsonl",
                            append=not a.overwrite, delay=a.delay)
                b.start()
                sports_seeds = [
                    "/in/sports",
                    "/in/sports/cricket",
                    "/in/sports/football",
                    "/in/sports/tennis",
                    "/in/sports/kabaddi",
                    "/in/sports/hockey",
                    "/in/sports/badminton",
                    "/in/sports/motorsports",
                ]
                try:
                    for slug in sports_seeds:
                        print(f"    {slug} …")
                        b.visit(hc.BASE + slug, deep=True)
                        print(f"    {len(rows)} rows")
                finally:
                    b.close()

            df_h = save(rows, "hotstar_sports.csv", COMMON_COLUMNS)
            dfs.append(df_h)
        except Exception as e:
            print(f"  ✗ Hotstar failed: {e}")

    # ── SonyLIV ──────────────────────────────────────────────────────────────
    if "sonyliv" in a.platforms:
        print("\n" + "═"*50)
        print("  SONYLIV")
        print("═"*50)
        try:
            import sonyliv_catalog as sl
            if a.raw_sonyliv:
                df_s = sl.parse_file(a.raw_sonyliv, "sonyliv_sports.csv")
            else:
                df_s = sl.crawl(out="sonyliv_sports.csv",
                                 append=not a.overwrite, delay=a.delay)
            dfs.append(df_s)
        except Exception as e:
            print(f"  ✗ SonyLIV failed: {e}")

    # ── ZEE5 ────────────────────────────────────────────────────────────────
    if "zee5" in a.platforms:
        print("\n" + "═"*50)
        print("  ZEE5")
        print("═"*50)
        try:
            import zee5_catalog as z5
            if a.raw_zee5:
                df_z = z5.parse_file(a.raw_zee5, "zee5_sports.csv")
            else:
                df_z = z5.crawl(out="zee5_sports.csv",
                                  append=not a.overwrite, delay=a.delay)
            dfs.append(df_z)
        except Exception as e:
            print(f"  ✗ ZEE5 failed: {e}")

    if not dfs:
        print("No data collected.")
        sys.exit(1)

    # ── Merge ────────────────────────────────────────────────────────────────
    merged = pd.concat(dfs, ignore_index=True)
    if a.sport:
        merged = merged[
            merged["sport"].str.lower().str.contains(a.sport.lower(), na=False)
            | merged["genre_tags"].str.lower().str.contains(a.sport.lower(), na=False)
            | merged["tournament"].str.lower().str.contains(a.sport.lower(), na=False)
        ]
    merged.to_csv(a.out, index=False)
    print(f"\n  ✓ merged → {a.out}  ({len(merged)} rows)")

    # ── Summary ──────────────────────────────────────────────────────────────
    print_summary(merged)


def print_summary(df: pd.DataFrame):
    print("\n" + "═"*60)
    print("  FULL SUMMARY — ALL PLATFORMS")
    print("═"*60)

    total   = len(df)
    unique  = df["content_id"].nunique()
    print(f"\n  Total rows  : {total}")
    print(f"  Unique IDs  : {unique}")

    print("\n  ── By Platform ──")
    for plat, grp in df.groupby("platform"):
        print(f"    {plat:<12} {len(grp):>5} rows  "
              f"({grp['content_id'].nunique()} unique)")

    print("\n  ── Content types ──")
    ct = df.groupby(["platform", "content_type"]).size().unstack(fill_value=0)
    print(ct.to_string())

    print("\n  ── Top sports ──")
    sports = df["sport"].dropna().value_counts().head(15)
    for sp, cnt in sports.items():
        platforms = ", ".join(sorted(
            df[df["sport"] == sp]["platform"].dropna().unique()
        ))
        print(f"    {sp:<20} {cnt:>5}  [{platforms}]")

    print("\n  ── Top tournaments ──")
    tourn = df["tournament"].dropna().value_counts().head(10)
    for t, cnt in tourn.items():
        print(f"    {str(t)[:45]:<45} {cnt:>5}")

    print("\n  ── Access model ──")
    free_cnt = df["is_free"].sum()
    sub_cnt  = df["subscription_required"].sum()
    ppv_cnt  = df["pay_per_view"].sum()
    print(f"    Free AVOD   : {int(free_cnt):>5}")
    print(f"    Sub required: {int(sub_cnt):>5}")
    print(f"    Pay-per-view: {int(ppv_cnt):>5}")

    print("\n  ── Live content ──")
    live = df["is_live"].sum()
    print(f"    Live titles : {int(live):>5}")

    print("\n  ── Missing data ──")
    for col in ["sport", "tournament", "description", "year", "rating"]:
        if col in df.columns:
            miss = df[col].isna().sum()
            pct  = miss / len(df) * 100
            print(f"    {col:<20} missing: {miss:>5} ({pct:.1f}%)")

    print("═"*60 + "\n")


if __name__ == "__main__":
    main()
